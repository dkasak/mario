#!/usr/bin/env python3
# Copyright (c) 2015 Damir Jelić, Denis Kasak
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import mimetypes
import os
import re
import subprocess
import sys
import tempfile

from enum import Enum
from functools import reduce
from urllib.parse import urlparse

import argparse
import configparser
import logging as log
import magic
import notify2
import requests
from xdg import BaseDirectory

from mario.parser import make_parser, parse_rules_file
from mario.util import ElasticDict


class Kind(Enum):
    raw  = 1
    text = 2
    url = 3


def lookup_content_type(url):
    headers = {'User-agent': 'Mozilla/5.0 (Windows NT 6.3; rv:36.0) '
                             'Gecko/20100101 Firefox/36.0'}

    try:
        request = requests.head(url, headers=headers)
        response = request.headers['content-type']
    except (requests.RequestException, KeyError):
        return None, None

    if ';' in response:
        content_type, encoding = response.split(';', maxsplit=1)
        return content_type, encoding.strip()

    return response, None


def escape_match_group_references(action):
    return re.sub(r"{(\d*)}", r"{\\\1}", action)


def get_var_references(s):
    start = 0
    while True:
        p1 = s.find("{", start)
        p2 = s.find("}", p1+1)
        if p1 != -1 and p2 != -1:
            start = p2+1
            yield s[p1:p2+1]
        else:
            return


def kind_is_func(msg, arguments, cache):
    try:
        return msg['kind'] == Kind[arguments[0]], msg, cache
    except KeyError:
        return False, msg, cache


def arg_is_func(msg, arguments, cache):
    arg, checks = arguments

    ret = arg.format(**msg) in checks
    return ret, msg, cache


def arg_matches_func(msg, arguments, cache):
    arg, patterns = arguments
    arg = arg.format(**msg)

    for pattern in patterns:
        m = re.search(pattern, arg)

        if m:
            matches = {"\\{}".format(i): e
                       for i, e in enumerate(m.groups())}
            msg.update(matches)
            return True, msg, cache
    else:
        return False, msg, cache


def arg_rewrite_func(msg, arguments, cache):
    arg, patterns = arguments

    # Escape regex match group references in the argument, if any
    arg = escape_match_group_references(arg)

    tmp = arg.format(**msg)
    arg = arg.strip('{}')

    def split(acc, pattern):
        return acc.replace(*pattern.split(',', 2))
    tmp = reduce(split, patterns, tmp)

    msg[arg] = tmp

    return True, msg, cache


def mime_from_buffer(buf):
    try:
        t = magic.from_buffer(buf, mime=True)
    except AttributeError:
        try:
            m = magic.open(magic.MIME)
            m.load()
            t, _ = m.buffer(buf.encode('utf-8')).split(';')
        except AttributeError:
            log.error('Your \'magic\' module is unsupported. '
                      'Install either https://github.com/ahupp/python-magic '
                      'or https://github.com/file/file/tree/master/python '
                      '(official \'file\' python bindings, available as the '
                      'python-magic package on many distros)')

            raise SystemExit

    return t


def detect_mimetype(kind, var):
    if kind == Kind.url:
        t, _ = mimetypes.guess_type(var)

        if not t:
            log.debug('Failed mimetype guessing... '
                      'Trying Content-Type header.')
            t, _ = lookup_content_type(var)

            if t:
                log.debug('Content-Type: %s', t)
            else:
                log.debug('Failed fetching Content-Type.')

    elif kind == Kind.raw:
        t = mime_from_buffer(var)
    elif kind == Kind.text:
        t = 'text/plain'
    else:
        t = None

    return t


def arg_istype_func(msg, arguments, cache):
    arg, patterns = arguments
    arg = arg.format(**msg)

    type_cache = cache['type']

    if arg in type_cache.keys():
        t = type_cache[arg]
    else:
        t = detect_mimetype(msg['kind'], arg)

    if t:
        type_cache[arg] = t

        for pattern in patterns:
            m = re.search(pattern, t)

            if m:
                break
    else:
        log.info("Couldn't determine mimetype.")
        return False, msg, cache

    if m:
        log.debug('\tType matches: {}'.format(m.group()))
        matches = {"\\{}".format(i): e
                   for i, e in enumerate(m.groups())}
        msg.update(matches)
        return bool(m), msg, cache
    else:
        log.debug('\tType doesn\'t match or cannot guess type.')
        return False, msg, cache


def log_var_references(msg, action):
    vs = get_var_references(action)
    for v in vs:
        var_name = v.strip('{}')

        log.info('\t\t{{{var}}} = {value}'.format(
            var=var_name.lstrip('\\'),
            value=msg[var_name]))


def plumb_run_func(msg, argument_string):
    try:
        log_var_references(msg, argument_string)
    except KeyError as e:
        log.info('\t\tNo such variable: {{{var}}}'.format(var=e.args[0]))
        return False, msg

    arguments = [arg.format(**msg) for arg in argument_string.split()]

    try:
        ret = subprocess.call(arguments)
        if ret == 0:
            return True, msg
        else:
            log.info('\t\tTarget program exited with non-zero exit code'
                     ' (%s)', format(ret))
            return False, msg
    except FileNotFoundError as e:
        log.info("\t\tRule failed because there is no program named '%s' on "
                 "the PATH.", format(e.strerror.split("'")[1]))
        return False, msg


def plumb_notify_func(msg, arguments):
    message = arguments.format(**msg)
    n = notify2.Notification(msg['rule_name'], message)
    n.show()

    return True, msg


def plumb_save_func(msg, arguments):
    with tempfile.NamedTemporaryFile("w", prefix="plumber-temp-", delete=False) as f:
        f.write(msg['data'])
        msg['data_file'] = f.name

    return True, msg


def plumb_download_func(msg, arguments):
    try:
        log_var_references(msg, arguments)
    except KeyError as e:
        log.info('\t\tNo such variable: {{{var}}}'.format(var=e.args[0]))
        return False, msg

    headers = {'User-agent': 'Mozilla/5.0 (Windows NT 6.3; rv:36.0) '
               'Gecko/20100101 Firefox/36.0'}

    tmp_dir = tempfile.gettempdir()

    url = arguments.format(**msg)

    request = requests.get(url, headers=headers, stream=True)

    try:
        with tempfile.NamedTemporaryFile(prefix='plumber-', dir=tmp_dir, delete=False) as f:
            for chunk in request.iter_content(chunk_size=1024):
                if chunk:  # filter out keep-alive new chunks
                    f.write(chunk)
                    f.flush()

            msg['filename'] = f.name
            return True, msg
    except OSError as e:
        log.info('Error downloading file: ' + str(e))
        return False, msg


match_clauses = {
    'kind is': kind_is_func,
    'arg is': arg_is_func,
    'arg istype': arg_istype_func,
    'arg matches': arg_matches_func,
    'arg rewrite': arg_rewrite_func,
}

action_clauses = {
    'plumb run': plumb_run_func,
    'plumb notify': plumb_notify_func,
    'plumb save': plumb_save_func,
    'plumb download': plumb_download_func,
}


def handle_rules(msg, rules):
    log.info('Matching message against rules.')

    cache = {
        'type': {},
    }

    for rule in rules:
        rule_name, rule_lines = rule

        match_lines, action_lines = rule_lines
        log.debug('Matching against rule [%s]', rule_name)

        for line in match_lines:
            obj, verb = line[0:2]
            arguments = line[2:]

            f = match_clauses[obj + ' ' + verb]
            res, msg, cache = f(msg, arguments, cache)

            if not res:
                rule_matched = False
                break
        else:
            rule_matched = True

        if rule_matched:
            log.info('Rule [%s] matched.', rule_name)
            msg['rule_name'] = rule_name

            for line in action_lines:
                obj, verb, action = line
                log.info('\tExecuting action "%s = %s" for rule [%s].',
                         obj + ' ' + verb, action, rule_name)

                # regex match group references (i.e. number variables, e.g.
                # {0}) get prepended with a backslash (e.g. {\0}) so they can
                # be referred by name in python's format() instead of being
                # interpreted as positional arguments
                action = escape_match_group_references(action)

                f = action_clauses[obj + ' ' + verb]
                res, msg = f(msg, action)
                if not res:
                    break
            break
        else:
            msg.reverse()   # reset all changes to the message made in this rule
    else:
        log.info('No rule matched.')


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--verbose', action='count',
                        help='increase log verbosity level (pass multiple times)')
    parser.add_argument('msg', help='message to handle')

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('kind', help='kind of message',
                       nargs='?',
                       choices=[k.name for k in Kind])
    group.add_argument('--guess', action='store_true',
                       help='guess the kind of the message')

    parser.add_argument('--config', type=argparse.FileType('r'),
                        help='config file to use')
    parser.add_argument('--rules',
                        help='rules file to use')

    parser.add_argument('--print-mimetype', action='store_true',
                        help='detect and print the mimetype of the message data, '
                        'then exit')

    args = parser.parse_args()

    if args.kind:
        args.kind = Kind[args.kind]

    return args


def setup_logger(verbosity):
    if verbosity:
        log_levels = {
            1: log.WARNING,
            2: log.INFO,
            3: log.DEBUG
        }
        try:
            verbosity = log_levels[verbosity]
        except KeyError:
            verbosity = log.DEBUG

        log.basicConfig(format='%(levelname)s:\t%(message)s', level=verbosity)

    else:
        log.basicConfig(format='%(levelname)s:\t%(message)s')


def parse_rules(args, config):
    parser = make_parser()

    if args.rules:
        rules_filename = args.rules
    else:
        rules_filename = config['rules file']

    try:
        with open(rules_filename) as rules_file:
            log.info('Using rules file {}'.format(rules_file.name))
            rules = parse_rules_file(parser, rules_file)
    except OSError as e:
        log.error('Rules file doesn\'t exist: {}'.format(e.filename))
        return None

    return rules


def parse_config(args):
    def_rules_dir = os.path.join(BaseDirectory.xdg_config_home, 'mario',
                                 'rules.d')
    def_rules_file = os.path.join(BaseDirectory.xdg_config_home, 'mario',
                                  'mario.plumb')
    defaults = {
        'strict content lookup': False, # TODO
        'notifications': False,         # TODO
        'rules file': def_rules_file,
        'rules dir': def_rules_dir,     # TODO
    }

    config = configparser.ConfigParser(defaults=defaults,
                                       default_section='mario')

    config_file = None

    if args.config:
        config_file = args.config
    else:
        default_config = os.path.join(BaseDirectory.xdg_config_home, 'mario',
                                      'config')
        try:
            config_file = open(default_config)
        except OSError as e:
            log.info('Config file doesn\'t exist: {}'.format(e.filename))
            return defaults

    log.info('Using config file {}'.format(config_file.name))

    config.read_file(config_file)
    config_file.close()

    log.debug('Config parsed.')

    return config.defaults()


def main():
    # suppress most log messages from requests
    log.getLogger("requests").setLevel(log.WARNING)

    args = parse_arguments()

    setup_logger(args.verbose)

    # initialize Desktop Notifications
    notify2.init('mario')

    # Use - to indicate the data part of the message will be read from
    # stdin.
    #
    # XXX: '-' is valid message data, though, so we may want to handle
    # this differently, but it suffices for now
    if args.msg == '-':
        args.msg = sys.stdin.buffer.read()

    if args.guess:
        log.info('Using heuristics to guess kind...')

        if type(args.msg) is bytes:
            try:
                args.msg = args.msg.decode('utf-8')
            except UnicodeDecodeError:
                args.kind = Kind.raw

        if type(args.msg) is str:
            url = urlparse(args.msg)

            if url.scheme:
                args.kind = Kind.url
            else:
                args.kind = Kind.text

        log.info('\tGuessed kind {}'.format(args.kind))

    if args.print_mimetype:
        print(detect_mimetype(args.kind, args.msg))
        sys.exit(0)

    config = parse_config(args)

    msg = {'data': args.msg,
           'kind': args.kind
          }

    if args.kind == Kind.url:
        url = urlparse(args.msg)
        msg['netloc'] = url.netloc
        msg['netpath'] = url.path

    rules = parse_rules(args, config)

    if not rules:
        log.info('Syntax error in rules file. Quitting...')
        sys.exit(1)
    else:
        log.info('Rules parsed.')

    handle_rules(ElasticDict(msg), rules)


if __name__ == '__main__':
    main()

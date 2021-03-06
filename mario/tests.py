# Copyright (c) 2015 Damir Jelić, Denis Kasak
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import unittest

from mario.core import (get_var_references,
                        arg_matches_func,
                        arg_rewrite_func,
                        Kind)
from mario.parser import (make_parser,
                          parse_rules_string_exc,
                          extract_parse_result_as_list)
from mario.util import ElasticDict

# PARSER TESTS

simple_rule = '''[test]
kind is raw
arg matches {data} regex_string
plumb run firefox'''

simple_res = [
    ['test', (
        ['kind', 'is', 'raw'],
        [
            ['arg', 'matches', '{data}', ['regex_string']]
        ],
        [
            ['plumb', 'run', 'firefox']
        ]
    )]
]


multiple_margs_rule1 = '''[test]
kind is url
arg matches {data} regex_string
                   regex_inbetween
plumb run firefox'''

multiple_margs_res1 = [
    ['test', (
        ['kind', 'is', 'url'],
        [
            ['arg', 'matches', '{data}', ['regex_string', 'regex_inbetween']]
        ],
        [
            ['plumb', 'run', 'firefox']
        ]
    )]
]


multiple_margs_rule2 = '''[test]
kind is raw
arg matches {data} foo
            bar
        baz
                    spam
plumb run firefox'''

multiple_margs_res2 = [
    ['test', (
        ['kind', 'is', 'raw'],
        [
            ['arg', 'matches', '{data}', ['foo', 'bar', 'baz', 'spam']]
        ],
        [
            ['plumb', 'run', 'firefox']
        ]
    )]
]


multiple_clauses_per_block = '''[test]
kind is raw
data matches foo
arg matches {spam} eggs
plumb run swallow
plumb download {spam}'''

multiple_clauses_per_block_res = [
    ['test', (
        ['kind', 'is', 'raw'],
        [
            ['arg', 'matches', '{data}', ['foo']],
            ['arg', 'matches', '{spam}', ['eggs']]
        ],
        [
            ['plumb', 'run', 'swallow'],
            ['plumb', 'download', '{spam}']
        ]
    )]
]


no_match_block = '''[test]
kind is raw
plumb run swallow
plumb download {spam}
'''

no_match_block_res = [
    ['test', (
        ['kind', 'is', 'raw'],
        [],
        [
            ['plumb', 'run', 'swallow'],
            ['plumb', 'download', '{spam}']
        ]
    )],
]


multiple_rules = '''[test]
kind is raw
arg matches {data} regex_string
                   regex_inbetween
plumb run firefox
[test2]
kind is raw
arg is {data} something
plumb run echo {data}'''

multiple_res = [
    ['test', (
        ['kind', 'is', 'raw'],
        [
            ['arg', 'matches', '{data}', ['regex_string', 'regex_inbetween']]
        ],
        [
            ['plumb', 'run', 'firefox']
        ]
    )],
    ['test2', (
        ['kind', 'is', 'raw'],
        [
            ['arg', 'is', '{data}', ['something']]
        ],
        [
            ['plumb', 'run', 'echo {data}']
        ]
    )]
]


rule_with_comment = '''# this is a comment
[test] # even here?
kind is raw
# another one
    
arg matches {data} regex_string # commenting is fun

   # maybe here with some whitespace?

plumb run firefox # inline commenting wherever I want

#even here ?'''


rule_complex_variable = '''[test]
kind is raw
arg matches /bla/{data}/bla.py regex_string
plumb run firefox'''

complex_var_res = [
    ['test', (
        ['kind', 'is', 'raw'],
        [
            ['arg', 'matches', '/bla/{data}/bla.py', ['regex_string']]
        ],
        [
            ['plumb', 'run', 'firefox']
        ]
    )]
]


rule_unicode_names = '''[čest]
kind is raw
arg matches /bla/{data}/ćla.py regex_stringić # comments ¹²³
plumb run firefȭx'''

res_unicode_names = [
    ['čest', (
        ['kind', 'is', 'raw'],
        [
            ['arg', 'matches', '/bla/{data}/ćla.py', ['regex_stringić']]
        ],
        [
            ['plumb', 'run', 'firefȭx']
        ]
    )]
]


multiple_variables_rule = '''[test]
kind is raw
arg matches /bla/{data}/{another} regex_string
plumb run firefox'''

multiple_variables_res = [
    ['test', (
        ['kind', 'is', 'raw'],
        [
            ['arg', 'matches', '/bla/{data}/{another}', ['regex_string']]
        ],
        [
            ['plumb', 'run', 'firefox']
        ]
    )]
]


liberal_whitespace = '''[test] # co
kind is raw
arg     matches         {data}         regex_string      #   white      space    
plumb     run        firefox'''


data_object_rule = '''[test]
kind is raw
data matches regex_string
plumb run firefox'''


data_multiple_margs_rule = '''[test]
kind is url
data matches regex_string
             regex_inbetween
plumb run firefox'''


verb_istype = '''[test]
kind is raw
data istype text/plain
plumb run editor
'''

verb_istype_res = [
    ['test', (
        ['kind', 'is', 'raw'],
        [
            ['arg', 'istype', '{data}', ['text/plain']]
        ],
        [
            ['plumb', 'run', 'editor']
        ]
    )]
]


class ParserTest(unittest.TestCase):
    def parser_test_helper(self, rule, result):
        parser = make_parser()
        res = parse_rules_string_exc(parser,
                                     rule,
                                     extract_parse_result_as_list)
        self.assertEqual(result, res)

    def test_validate_parser(self):
        parser = make_parser()
        parser.validate()

    def test_simple_rule(self):
        self.parser_test_helper(simple_rule, simple_res)

    def test_multiple_match_args(self):
        self.parser_test_helper(multiple_margs_rule1, multiple_margs_res1)

    def test_multiple_match_args_with_inconsistent_whitespace(self):
        self.parser_test_helper(multiple_margs_rule2, multiple_margs_res2)

    def test_multiple_clauses_per_block(self):
        self.parser_test_helper(multiple_clauses_per_block,
                                multiple_clauses_per_block_res)

    def test_no_match_block(self):
        self.parser_test_helper(no_match_block, no_match_block_res)

    def test_multiple_rules(self):
        self.parser_test_helper(multiple_rules, multiple_res)

    def test_rule_with_comment(self):
        self.parser_test_helper(rule_with_comment, simple_res)

    def test_complex_var(self):
        self.parser_test_helper(rule_complex_variable, complex_var_res)

    def test_unicode(self):
        self.parser_test_helper(rule_unicode_names, res_unicode_names)

    def test_multiple_variables(self):
        self.parser_test_helper(multiple_variables_rule,
                                multiple_variables_res)

    def test_whitespace(self):
        self.parser_test_helper(liberal_whitespace, simple_res)

    def test_data_object(self):
        self.parser_test_helper(data_object_rule, simple_res)

    def test_data_multiple_marg(self):
        self.parser_test_helper(data_multiple_margs_rule, multiple_margs_res1)

    def test_verb_istype(self):
        self.parser_test_helper(verb_istype, verb_istype_res)


# UTIL TESTS

class TestElasticDict(unittest.TestCase):
    def test_empty_is_zero_length(self):
        d = ElasticDict()
        self.assertEqual(len(d), 0)

    def test_empty_is_empty_after_reverse(self):
        d = ElasticDict()
        d['spam'] = 'eggs'
        d.reverse()
        self.assertDictEqual(dict(d), {})

    def test_reverse_deletes_added_items(self):
        d = ElasticDict()
        d['spam'] = 'bacon'
        d.reverse()
        self.assertNotIn('spam', d)

    def test_reverse_resets_changes(self):
        d = ElasticDict({'spam': 'eggs'})
        d['spam'] = 'bacon'
        d.reverse()
        self.assertEqual(d['spam'], 'eggs')

    def test_nonexistent_raises_keyerror(self):
        d = ElasticDict()
        with self.assertRaises(KeyError):
            d['bar']

    def test_strain(self):
        d = ElasticDict({'tea': 'oolong'})
        d['tea'] = 'green'
        d['grenade']  = 'antioch'
        self.assertDictEqual(d.strain, {'grenade': 'antioch',
                                        'tea': 'green'})

    def test_iter(self):
        d = ElasticDict({'a': 1, 'b': 2})
        d['b'] = 42
        d['c'] = 3
        self.assertListEqual(list(d), ['a', 'b', 'c'])


# CORE TESTS

class CoreTest(unittest.TestCase):
    def test_arg_matches_func_match_groups(self):
        self.assertEqual(
            arg_matches_func(
                {'data': 'foo1bar2'},
                ("{data}", ["foo(.)bar(.)"]),
                {}
            ),
            (True, {'data': 'foo1bar2', '\\0': '1', '\\1': '2'}, {})
        )

    def test_arg_rewrite_simple(self):
        self.assertEqual(
            arg_rewrite_func({'data': 'oolong',
                              'kind': Kind['raw']},
                             ['{data}', ['oo,', 'g,g jing']],
                             {}),
            (True, {'data': 'long jing', 'kind': Kind['raw']}, {})
        )

    def test_get_var_references_basic(self):
        self.assertListEqual(
            list(get_var_references('{0}')),
            ['{0}']
        )

    def test_get_var_references_basic_spaces(self):
        self.assertListEqual(
            list(get_var_references('   {0} \t  ')),
            ['{0}']
        )

    def test_get_var_references_multiple_vars(self):
        self.assertListEqual(
            list(get_var_references("{0}www{1}foo {abc}")),
            ['{0}', '{1}', '{abc}']
        )


if __name__ == '__main__':
        unittest.main()

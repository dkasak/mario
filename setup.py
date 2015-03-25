#!/usr/bin/env python3
import os, shutil
from setuptools import setup
from pkg_resources import require, DistributionNotFound

try:
    require('Magic_file_extensions')
    magic_module = 'Magic_file_extensions'
except DistributionNotFound:
    magic_module = 'python-magic'

setup(name = 'mario',
      version = '0.1',
      author = 'Damir Jelić, Denis Kasak',
      author_email = 'poljar[at]termina.org.uk, dkasak[at]termina.org.uk',
      description = ('A simple plumber'),
      install_requires = [magic_module, 'pyxdg'],
      license = 'ISC',
      entry_points = {
          "console_scripts" : ['mario = mario:main']
          }
     )

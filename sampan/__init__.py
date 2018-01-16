#!/usr/bin/env python
# coding: utf-8

import platform

__author__ = ['Yifan Wang <yifan_wang@silanis.com>']
__copyright__ = "Copyright (C) 2017, The Sampan Authors"
__license__ = "MIT"
__version__ = '2017.11.03'
__description__ = 'python web toolkit'
__status__ = "Internal"


if platform.python_version_tuple() < ('3', '6') or platform.python_implementation() != 'CPython':
    raise RuntimeError('Sampan requires CPython 3.6 or greater.')


class SampanError(Exception):
    pass

#!/usr/bin/env python
# coding: utf-8


__author__ = ['Yifan Wang <yifan_wang@silanis.com>']
__copyright__ = "Copyright (C) 2016, The Sampan Authors"
__license__ = "MIT"
__version__ = '0.2.1'
__description__ = 'The Python utility library'


# Check Environment ###########################################################
###############################################################################
def check_environment():
    import platform
    if platform.python_version_tuple() < ('3', '6') or platform.python_implementation() != 'CPython':
        raise RuntimeError('Sampan requires CPython 3.6 or greater.')


check_environment()




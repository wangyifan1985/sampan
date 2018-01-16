#!/usr/bin/env python
# coding: utf-8


import platform

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

if platform.python_version_tuple() < ('3', '6') or platform.python_implementation() != 'CPython':
    raise RuntimeError('CPython version 3.6+ is required.')

import sampan

setup(name='sampan',
      version=sampan.__version__,
      description=sampan.__description__,
      long_description=sampan.__doc__,
      author=sampan.__author__,
      author_email='yifan_wang@silanis.com',
      url='https://github.com/wangyifan1985/sampan',
      packages=['sampan'],
      license='MIT',
      platforms='any',
      classifiers=['Development Status :: 4 - Beta',
                   'Environment :: Web Environment',
                   'Intended Audience :: Developers',
                   'License :: OSI Approved :: MIT License',
                   'Operating System :: OS Independent',
                   'Topic :: Software Development :: Libraries :: Application Frameworks',
                   'Programming Language :: Python :: 3.6'
                   'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
                   'Topic :: Software Development :: Libraries :: Python Modules']
)
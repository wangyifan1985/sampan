#!/usr/bin/env python
# coding: utf-8

import re
import io
import os
import time
import sys
import typing
import time
from collections import OrderedDict, abc

""" A Python implementation for java.util.Properties """


__author__ = ['Yifan Wang <yifan_wang@silanis.com>']
__copyright__ = "Copyright (C) 2018, Yifan WANG"
__license__ = "MIT"
__version__ = '0.1.0'
__description__ = 'Java Properties file tools'
__status__ = "Internal"


# Constants ###################################################################
###############################################################################
DMT = '%a %b %d %H:%M:%S %Z %Y'
ENCODING = 'latin-1'


# Errors ######################################################################
###############################################################################
class PropertiesError(Exception):
    pass


# Properties ##################################################################
###############################################################################


class Properties:
    re_property = re.compile(r'(.+?)(?<!\\)(?:\s*[=|:]\s*)(.*)')
    re_property_space = re.compile(r'(.+?)(?<!\\)(?:[ ]+)(.+)')
    re_tail = re.compile(r'([\\]+)$')

    def __init__(self, defaults=None):
        self._props = OrderedDict()
        if defaults is not None:
            if isinstance(defaults, abc.Mapping):
                self._props.update(defaults)
            elif isinstance(defaults, Properties):
                self._props.update(defaults._props)
            else:
                raise PropertiesError(f'Unknown default properties type: {type(defaults)}')

    def __setitem__(self, key, value):
        self.setProperty(key, value)

    def __getitem__(self, key):
        return self.getProperty(key)

    def __getattr__(self, name):
        try:
            return self.__dict__[name]
        except KeyError:
            if hasattr(self._props, name):
                return getattr(self._props, name)

    def __len__(self):
        return len(self._props)

    def __eq__(self, other):
        return isinstance(other, Properties) and self._props == other._props

    def __contains__(self, key):
        return key in self._props

    def __delitem__(self, key):
        del self._props[key]

    def __str__(self):
        s = '{'
        for key, value in self._props.items():
            s = ''.join((s, key, '=', value, ', '))

        s = ''.join((s[:-2], '}'))
        return s

    def __iter__(self):
        return iter(self._props)

    def setProperty(self, key: str, value: str):
        self._props[key] = value

    def getProperty(self, key: str, defaultValue: str=None):
        if defaultValue:
            return self._props.get(key, defaultValue)
        return self._props.get(key)

    def list(self, out=sys.stdout):
        for key, value in self._props.items():
            print(''.join((key, '=', value)), out)

    def propertyNames(self):
        return self._props.keys()

    def stringPropertyNames(self):
        return set(self._props.keys())

    def escape(self, value: str):
        return value.replace(':', '\:').replace('=', '\=')

    def unescape(self, value: str):
        return value.replace('\:', ':').replace('\=', '=')

    def load(self, ins: typing.IO):
        lineno = 0
        lines = iter(ins.readlines())
        for line in lines:
            lineno += 1
            line = line.strip()
            if not line or line.startswith('#') or line.startswith('!'):
                continue
            while line.endswith(r'\\'):
                if len(self.re_tail.fullmatch(line).group(1)) % 2 == 1:
                    line = line[:-1] + next(lines).strip()
                    lineno += 1
            m = self.re_property.match(line)
            if m:
                key = m.group(1)
                value = m.group(2)
            else:
                m = self.re_property_space.match(line)
                if m:
                    key = m.group(1)
                    value = m.group(2)
                else:
                    raise PropertiesError(f'Illegal property at line: {lineno}')
            self.setProperty(key, value)

    def store(self, out, comments: str=None):
        lines = []
        if comments:
            lines.append(''.join(('#', comments)))
        lines.append(''.join(('#', time.strftime(DMT, time.gmtime()))))
        for k, v in self._props.items():
            lines.append(f'{k}={v}')
        if 'b' in out.mode:
            out.write('\n'.encode(ENCODING).join([s.encode(ENCODING) for s in lines]))
        else:
            out.write('\n'.join(lines))



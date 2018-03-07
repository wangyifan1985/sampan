#!/usr/bin/env python
# coding: utf-8

import re
import time
import sys
import typing
import time
from collections import OrderedDict

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
CRLF = '\r\n'
COMMENT = '#'
ENCODING = 'latin-1'
STR_NAME = '<string>'
RE_FLAGS = re.MULTILINE | re.DOTALL
WS = r'[ \t\n\r]*'


# Errors ######################################################################
###############################################################################
class PropertiesError(Exception):
    def __init__(self, line: int, msg: str='Exception parsing Properties: '):
        self.line = line
        self.msg = msg

    def __str__(self):
        s= ''.join((self.msg, 'line ', self.line))
        return s


# Properties ##################################################################
###############################################################################


class Properties:

    def __init__(self, defaults=None):
        self._props = OrderedDict()

    def getProperty(self, key: str, defaultValue: str=None):
        if defaultValue:
            return self._props.get(key, defaultValue)
        return self._props.get(key)

    def list(self, out):
        pass

    def load(self, ins):
        pass

    def loadFromXML(self, ins):
        pass

    def propertyNames(self):
        return self._props.keys()

    def setProperty(self, key: str, value: str):
        self._props[key] = value

    def store(self, writer, comments: str):
        if comments:
            writer.write(''.join((COMMENT, comments, CRLF)))
        writer.write(''.join((COMMENT, time.strftime(DMT, time.gmtime()), CRLF)))
        writer.write(str(self) + '\n')

    def storeToXML(self, out, comments: str, encoding: str=ENCODING):
        pass

    def stringPropertyNames(self):
        return set(self._props.keys())



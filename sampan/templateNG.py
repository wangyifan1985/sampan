#!/usr/bin/env python
# coding: utf-8

"""
A tiny template system
"""

import re
import datetime
import typing
from enum import Enum
from html import escape
from urllib.parse import quote
from json import dumps
from . import SampanError


# Errors ######################################################################
###############################################################################
class TemplateError(SampanError):
    def __init__(self, msg: str):
        self.msg = msg

    def __str__(self):
        return self.msg


class TemplateParseError(TemplateError):
    def __init__(self, s: str, pos: int, msg: str='Can not parse template: '):
        super(TemplateParseError, self).__init__(msg)
        self.s = s
        self.pos = pos

    def __str__(self):
        line, col = self.linecol(self.s, self.pos)
        return ''.join((self.msg, line, ' : ', col))


# Template ####################################################################
###############################################################################
class _Reader:
    def __init__(self, s):
        self.s = s
        self.pos = 0

    def find(self, ss: str, start: int=0, end: int=None):
        start += self.pos
        if end is None:
            index = self.s.find(ss, start)
        else:
            end += self.pos
            assert end >= start
            index = self.s.find(ss, start, end)
        if index != -1:
            index -= self.pos
        return index

    def consume(self, count: int=None):
        if count is None:
            count = len(self.s) - self.pos
        new_pos = self.pos + count
        s = self.s[self.pos:new_pos]
        self.pos = new_pos
        return s

    def remain(self):
        return len(self.s) - self.pos

    def __len__(self):
        return self.remain()

    def __str__(self):
        return self.s[self.pos:]

    def __getitem__(self, key: typing.Union[slice, int]):
        if isinstance(key, slice):
            start, stop, step = key.indices(self.remain())
            start = self.pos if start is None else start + self.pos
            if stop is not None:
                stop += self.pos
            return self.s[slice(start, stop, step)]
        elif key < 0:
            return self.s[key]
        else:
            return self.s[self.pos + key]


class Tag(Enum):
    COMMENT = ('{#', '#}')
    EXPRESSION = ('{{', '}}')
    STATEMENT = ('{%', '%}')


class _Parser:
    def __init__(self):
        self.parsers = {}

    def register(self, tag: Tag, key: str, func: typing.Callable):
        self.parsers[(tag, key)] = func


class Template:
    _parser = _Parser()

    @classmethod
    def parser(cls, tag: Tag, key: str=None):
        def wrapper(func):
            cls._parser.register(tag, key, func)
            return func
        return wrapper

    @staticmethod
    def comment_retain():
        print('retain comment')

    def __new__(cls, template):
        cls._parser.register(Tag.COMMENT, 'retain', cls.comment_retain)
        return super(Template, cls).__new__(cls)

    def __init__(self, template: str):
        self.template = template
        self.chunks = dict()
        self.namespace = {
            'escape': escape,
            'html_escape': escape,
            'url_escape': quote,
            'json_encode': dumps,
            'squeeze': lambda s: re.sub(r'[\x00-\x20]+', ' ', s).strip(),
            'datetime': datetime
        }


@Template.parser(Tag.COMMENT, 'ignore')
def comment_ignore():
    print('ignore comment')
#!/usr/bin/env python
# coding: utf-8

"""
A tiny template system
"""

import re
import typing
import datetime
import linecache
import threading
from io import StringIO
from enum import Enum
from html import escape
from urllib.parse import quote
from json import dumps
from . import SampanError, ENCODING
from .util import to_str

__all__ = ['Template', 'TemplateError', 'Tag', 'Node']

# Constants ###################################################################
###############################################################################
INDENT = 4
STRING_NAME = '<string>'


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


class _Writer(object):
    def __init__(self, file, named_blocks, loader, current_template):
        self.file = file
        self.named_blocks = named_blocks
        self.loader = loader
        self.current_template = current_template
        self.apply_counter = 0
        self.include_stack = []
        self._indent = 0

    def indent_size(self):
        return self._indent

    def indent(self):
        class Indenter(object):
            def __enter__(_):
                self._indent += 1
                return self

            def __exit__(_, *args):
                assert self._indent > 0
                self._indent -= 1

        return Indenter()

    def include(self, template, line):
        self.include_stack.append((self.current_template, line))
        self.current_template = template

        class IncludeTemplate(object):
            def __enter__(_):
                return self

            def __exit__(_, *args):
                self.current_template = self.include_stack.pop()[0]

        return IncludeTemplate()

    def write_line(self, line, line_number, indent=None):
        if indent is None:
            indent = self._indent
        line_comment = '  # %s:%d' % (self.current_template.name, line_number)
        if self.include_stack:
            ancestors = ['%s:%d' % (tmpl.name, lineno)
                         for (tmpl, lineno) in self.include_stack]
            line_comment += ' (via %s)' % ', '.join(reversed(ancestors))
        print('    ' * indent + line + line_comment, file=self.file)


class Tag(Enum):
    COMMENT = ('{#', '#}')
    EXPRESSION = ('{{', '}}')
    STATEMENT = ('{%', '%}')


class Node:
    def generate(self, writer):
        raise NotImplementedError()


class Template:
    _parsers = {}

    @classmethod
    def parser(cls, tag: Tag, key: str):
        def wrapper(node: typing.Type[Node]):
            cls._parsers[(tag, key)] = node

            def wrapped(*args, **kwargs):
                return node(*args, **kwargs)
            return wrapped
        return wrapper

    def __new__(cls, template):
        return super(Template, cls).__new__(cls)

    def __init__(self, template: str):
        self.chunks = {}
        self.template = template
        self.lock = threading.RLock()
        self.namespace = {
            '_tt_str': lambda s: s.decode(ENCODING) if isinstance(s, bytes) else str(s, ENCODING),
            'escape': escape,
            'html_escape': escape,
            'url_escape': quote,
            'json_encode': dumps,
            'squeeze': lambda s: re.sub(r'[\x00-\x20]+', ' ', s).strip(),
            'datetime': datetime
        }

    def parse(self, reader: _Reader, writer: _Writer):
        pass

    def generate(self, **kwargs):
        buffer = StringIO()
        reader = _Reader(self.template)
        writer = _Writer(buffer)
        self.parse(reader, writer)
        self.namespace.update(**kwargs)
        exec(buffer.getvalue(), self.namespace, None)
        execute = self.namespace['_tt_execute']
        linecache.clearcache()
        return execute()


class _Root(Node):
    def __init__(self, template, body):
        self.template = template
        self.body = body
        self.line = 0

    def generate(self, writer):
        writer.write_line('def _tt_execute():', self.line)
        with writer.indent():
            writer.write_line('_tt_buffer = []', self.line)
            writer.write_line('_tt_append = _tt_buffer.append', self.line)
            self.body.generate(writer)
            writer.write_line("return _tt_utf8('').join(_tt_buffer)", self.line)

    def each_child(self):
        return self.body,
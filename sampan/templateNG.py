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
BOUNDARY = ('{', '}')
RE_FLAGS = re.MULTILINE | re.DOTALL
WS = re.compile(r'[ \t\n\r]*', RE_FLAGS)


# Errors ######################################################################
###############################################################################
class TemplateError(SampanError):
    @staticmethod
    def linecol(s: str, pos: int):
        line = s.count('\n', 0, pos) + 1
        col = pos + 1 if line == 1 else pos - s.rindex('\n', 0, pos)
        return str(line), str(col)

    def __init__(self, msg: str):
        self.msg = msg

    def __str__(self):
        return self.msg


class TemplateParseError(TemplateError):
    def __init__(self, reader, msg: str='Can not parse template: '):
        super(TemplateParseError, self).__init__(msg)
        self.reader = reader

    def __str__(self):
        line, col = self.linecol(self.reader.s, self.reader.pos)
        return ''.join((self.msg, line, ' : ', col))


# Template ####################################################################
###############################################################################
class _Reader:
    def __init__(self, s):
        self.s = s
        self.pos = 0

    def find(self, sub: str, start: int=0, end: int=None) -> int:
        index = self.s.find(sub, start + self.pos, end if end is None else end + self.pos)
        return index if index == -1 else index - self.pos

    def re_find(self, regex, start: int=0, end: int=None) -> tuple:
        return regex.match(self.s, start + self.pos, len(self.s) if end is None else end + self.pos)


    def consume(self, count: int=None) -> str:
        if count is None:
            count = len(self.s) - self.pos
        new_pos = self.pos + count
        sub = self.s[self.pos:new_pos]
        self.pos = new_pos
        return sub

    def re_consume(self, regex):
        m = regex.match(self.s, self.pos)
        if m is not None:
            self.pos = m.end()
        return m

    def eof(self) -> bool:
        return self.pos == len(self.s) - 1

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
    def __init__(self, file: typing.IO, named_blocks, current_template):
        self.file = file
        self.named_blocks = named_blocks
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

    def write_line(self, line, indent=None):
        if indent is None:
            indent = self._indent
        print('    ' * indent + line, file=self.file)


class Node:
    reader = None
    writer = None
    def __init__(self, reader: _Reader=None, writer: _Writer=None):
        self.reader = reader
        self.writer = writer

    def generate(self):
        raise NotImplementedError


class _Root(Node):
    def __init__(self, writer: _Writer):
        super(_Root, self).__init__(writer=writer)
        self.chunks = []

    def generate(self):
        self.writer.write_line('def tt_execute():')
        with self.writer.indent():
            self.writer.write_line('tt_buffer = []')
            self.writer.write_line('tt_append = tt_buffer.append')
            for chunk in self.chunks:
                chunk.generate()
            self.writer.write_line("return tt_str('').join(tt_buffer)")

    def add_chunk(self, chunk: Node):
        self.chunks.append(chunk)


class _Text(Node):
    pattern = re.compile(rf'[^{BOUNDARY[0]}]+', RE_FLAGS)

    def __init__(self, reader, writer):
        super(_Text, self).__init__(reader, writer)
        self.text = self.reader.re_consume(self.pattern).group()

    def generate(self):
        self.writer.write_line(f'tt_append({repr(to_str(self.text))})')


class _Comment(Node):
    tag = (f'{BOUNDARY[0]}#', f'#{BOUNDARY[1]}')
    pattern = re.compile(rf'{_Comment.tag[0]}'
                         rf'.+?'
                         rf'{_Comment.tag[1]}', RE_FLAGS)

    def __init__(self, reader, writer):
        super(_Comment, self).__init__(reader, writer)
        _ = self.reader.re_consume(self.pattern)

    def generate(self):
        pass


class _Expression(Node):
    tag = (f'{BOUNDARY[0]}{{', f'}}{BOUNDARY[1]}')
    pattern = re.compile(rf'{_Expression.tag[0]}{WS.pattern}'
                         rf'(.+?)'
                         rf'{WS.pattern}{_Expression.tag[1]}')

    def __init__(self, reader, writer, auto_escape=None):
        super(_Expression, self).__init__(reader, writer)
        self.exp = self.reader.re_consume(self.pattern).group(1)
        self.auto_escape = auto_escape
    
    def generate(self):
        self.writer.write_line(f'tt_tmp = {self.exp}')
        self.writer.write_line('if isinstance(tt_tmp, str): tt_tmp = tt_str(tt_tmp)')
        if self.auto_escape is not None:
            self.writer.write_line(f'tt_tmp = tt_str({self.auto_escape}(tt_tmp))')
        self.writer.write_line('tt_append(tt_tmp)')


class _Statement(Node):
    tag = (f'{BOUNDARY[0]}%', f'%{BOUNDARY[1]}')
    pattern = re.compile(rf'{tag[0]}{WS.pattern}([a-zA-Z0-9_]+?{WS.pattern}.+?){WS.pattern}{tag[1]}')

    def __init__(self, reader, writer):
        super(_Statement, self).__init__(reader, writer)
        self.stat = self.reader.re_consume(self.pattern).group(1)

    def generate(self):
        self.writer.write_line(self.stat)

class _StatementComment(_Statement):
    def __init__(self, reader, writer):
        super(_StatementComment, self).__init__(reader, writer)

    def generate(self):
        pass

class _StatementRaw(_Statement):
    def __init__(self, reader, writer):
        super(_StatementRaw, self).__init__(reader, writer)
        _, _, self.stat = super(_StatementRaw, self).stat.partition(' ')

    def generate(self):
        self.writer.write_line(f'tt_tmp = {self.stat}')
        self.writer.write_line('if isinstance(tt_tmp, str): tt_tmp = tt_str(tt_tmp)')
        self.writer.write_line('tt_append(tt_tmp)')



    
    

    


class Template:
    def __init__(self, raw: str):
        self.cache = {}
        self.raw = raw
        self.buffer = StringIO()
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

    def generate(self, **kwargs):
        _root = self.parse(_Reader(self.raw), _Writer(self.buffer))
        self.namespace.update(**kwargs)
        exec(self.buffer.getvalue(), self.namespace, None)
        execute = self.namespace['tt_execute']
        linecache.clearcache()
        return execute()

    def parse(self, reader: _Reader, writer: _Writer) -> _Root:
        root = _Root(writer)
        while not reader.eof():
            if reader[0] == BOUNDARY[0]:
                if reader[1] == '#':
                    root.add_chunk(_Comment(reader, writer))
                elif reader[1] == '{':
                    root.add_chunk(_Expression(reader, writer))
                elif reader[1] == '%':
                    operator = reader.re_find(rf'{BOUNDARY[0]}%{WS_RE.pattern}([a-zA-Z0-9_]+?){WS_RE.pattern}').group(1)
                    if operator in ('import', 'from', 'set'):
                        root.add_chunk(_Statement(reader, writer))
                    elif operator == 'comment':
                        root.add_chunk(_StatementComment(reader, writer))
                    elif operator == 'raw':
                        root.add_chunk(_StatementRaw(reader, writer))
                    


            else:
                root.add_chunk(_Text(reader, writer))

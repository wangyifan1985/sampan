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
RE_FLAGS = re.MULTILINE | re.DOTALL
WS = r'[ \t\n\r]*'


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

    def find(self, regex, start: int=0, end: int=None) -> tuple:
        return regex.match(self.s, start + self.pos, len(self.s) if end is None else end + self.pos)

    def consume(self, regex):
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
    tag = ('{', '}')

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
    regex = re.compile(rf'[^{Node.tag[0]}]+', RE_FLAGS)

    def __init__(self, reader, writer):
        super(_Text, self).__init__(reader, writer)
        self.text = self.reader.consume(self.regex).group()

    def generate(self):
        self.writer.write_line(f'tt_append({repr(to_str(self.text))})')


class _Comment(Node):
    tag = (f'{Node.tag[0]}#', f'#{Node.tag[1]}')
    regex = re.compile(rf'{tag[0]}.+?{tag[1]}', RE_FLAGS)

    def __init__(self, reader, writer):
        super(_Comment, self).__init__(reader, writer)
        _ = self.reader.consume(self.regex)

    def generate(self):
        pass


class _Expression(Node):
    tag = (f'{Node.tag[0]}{{', f'}}{Node.tag[1]}')
    regex = re.compile(rf'{tag[0]}{WS}(.+?){WS}{tag[1]}')

    def __init__(self, reader, writer, auto_escape=None):
        super(_Expression, self).__init__(reader, writer)
        self.exp = self.reader.consume(self.regex).group(1)
        self.auto_escape = auto_escape
    
    def generate(self):
        self.writer.write_line(f'tt_tmp = {self.exp}')
        self.writer.write_line('if isinstance(tt_tmp, str): tt_tmp = tt_str(tt_tmp)')
        if self.auto_escape is not None:
            self.writer.write_line(f'tt_tmp = tt_str({self.auto_escape}(tt_tmp))')
        self.writer.write_line('tt_append(tt_tmp)')


class _Statement(Node):
    tag = (f'{Node.tag[0]}%', f'%{Node.tag[1]}')
    regex = re.compile(rf'{tag[0]}{WS}([a-zA-Z0-9_]+?{WS}.+?){WS}{tag[1]}')
    regex_end = re.compile(rf'{tag[0]}{WS}end{WS}{tag[1]}')

    def __init__(self, reader, writer):
        super(_Statement, self).__init__(reader, writer)
        self.stat = self.reader.consume(self.regex).group(1)

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
        _, _, self.stat = self.stat.partition(' ')

    def generate(self):
        self.writer.write_line(f'tt_tmp = {self.stat}')
        self.writer.write_line('if isinstance(tt_tmp, str): tt_tmp = tt_str(tt_tmp)')
        self.writer.write_line('tt_append(tt_tmp)')


class _StatementAutoescape(_Statement):
    def __init__(self, reader, writer, template):
        super(_StatementAutoescape, self).__init__(reader, writer)
        self.template = template
        _, _, self.autoescape = self.stat.partition(' ')

    def generate(self):
        self.template.autoescape = None if self.autoescape == 'None' else self.template.namespace[self.autoescape]


class _StatementModule(_Statement):
    def __init__(self, reader, writer):
        super(_StatementModule, self).__init__(reader, writer)
        _, _, self.module = self.stat.partition(' ')

    def generate(self):
        self.writer.write_line(f'tt_modules.{self.module}')


class _StatementIf(_Statement):
    regex = re.compile(rf'{_Statement.tag[0]}{WS}((?:if|else|elif){WS}.+?){WS}{_Statement.tag[1]}'
                       rf'((?:(?!{_Statement.tag[0]}{WS}(?:else|elif|end)).)*)', RE_FLAGS)

    def __init__(self, reader, writer, template):
        super(_StatementIf, self).__init__(reader, writer)
        self.template = template
        self.stats = []
        _m = self.reader.consume(self.regex)
        while _m is not None:
            self.stats = (_m.group(1), self.template.parse(_Reader(_m.group(2)), self.writer))
            _m = self.reader.consume(self.regex)
        else:
            self.reader.consume(self.regex_end)

    def generate(self):
        for stat in self.stats:
            self.writer.write_line(f'{stat[0]}:')
            with self.writer.indent():
                if stat[1] is not None:
                    stat[1].generate()
                else:
                    self.writer.write_line('pass')


class _StatementLoop(_Statement):
    regex = re.compile(rf'{_Statement.tag[0]}{WS}((?:for|while){WS}.+?){WS}{_Statement.tag[1]}'
                       rf'(.+?){_Statement.regex_end.pattern}', RE_FLAGS)

    def __init__(self, reader, writer, template):
        super(_StatementLoop, self).__init__(reader, writer)
        self.template = template
        _m = self.reader.consume(self.regex)
        self.cond = _m.group(1)
        self.stat = _m.group(2)

    def generate(self):
        self.writer.write_line(f'{self.cond}:')
        with self.writer.indent():
            self.writer.write_line(f'{self.stat}')


class _StatementTry(_Statement):
    regex = re.compile(rf'{_Statement.tag[0]}{WS}((?:try|except|else|finally){WS}.+?){WS}{_Statement.tag[1]}'
                       rf'((?:(?!{_Statement.tag[0]}{WS}(?:except|else|finally|end)).)*)', RE_FLAGS)

    def __init__(self, reader, writer, template):
        super(_StatementTry, self).__init__(reader, writer)
        self.template = template
        self.stats = []
        _m = self.reader.consume(self.regex)
        while _m is not None:
            self.stats = (_m.group(1), self.template.parse(_Reader(_m.group(2)), self.writer))
            _m = self.reader.consume(self.regex)
        else:
            self.reader.consume(self.regex_end)

    def generate(self):
        for stat in self.stats:
            self.writer.write_line(f'{stat[0]}:')
            with self.writer.indent():
                if stat[1] is not None:
                    stat[1].generate()
                else:
                    self.writer.write_line('pass')


class _StatementBlock(_Statement):
    regex = re.compile(rf'{_Statement.tag[0]}{WS}(block{WS}.+?){WS}{_Statement.tag[1]}'
                       rf'(.+?){_Statement.regex_end.pattern}', RE_FLAGS)

    def __init__(self, reader, writer, template):
        super(_StatementBlock, self).__init__(reader, writer)
        self.template = template
        _m = self.reader.consume(self.regex)
        self.name = _m.group(1)
        self.body = _m.group(2)

    def generate(self):
        pass


class _StatementInclude(_Statement):
    def __init__(self, reader, writer, template):
        super(_StatementInclude, self).__init__(reader, writer)
        self.template = template
        _, _, self.name = super(_StatementInclude, self).stat.partition(' ')
        self.name = self.name.strip("'").strip('"')

    def generate(self):
        pass


class _StatementExtends(_StatementInclude):
    def __init__(self, reader, writer, template):
        super(_StatementExtends, self).__init__(reader, writer, template)

    def generate(self):
        pass





class Template:
    def __init__(self, raw: str, autoescape: typing.Callable=None):
        self.cache = {}
        self.raw = raw
        self.buffer = StringIO()
        self.lock = threading.RLock()
        self.autoescape = autoescape
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
            if reader[0] == Node.tag[0]:
                if reader[1] == '#':
                    root.add_chunk(_Comment(reader, writer))
                elif reader[1] == '{':
                    root.add_chunk(_Expression(reader, writer))
                elif reader[1] == '%':
                    operator = reader.find(rf'{Node.tag[0]}%{WS}([a-zA-Z0-9_]+?){WS}').group(1)
                    if operator in ('import', 'from', 'set', 'break', 'continue', 'pass'):
                        root.add_chunk(_Statement(reader, writer))
                    elif operator == 'comment':
                        root.add_chunk(_StatementComment(reader, writer))
                    elif operator == 'raw':
                        root.add_chunk(_StatementRaw(reader, writer))
                    elif operator == 'if':
                        root.add_chunk(_StatementIf(reader, writer, self))
                    elif operator in ('for', 'while'):
                        root.add_chunk(_StatementLoop(reader, writer, self))
                    elif operator == 'block':
                        root.add_chunk(_StatementBlock(reader, writer, self))
                    elif operator == 'extends':
                        root.add_chunk(_StatementExtends(reader, writer, self))
                    else:
                        raise TemplateParseError(reader)
            else:
                root.add_chunk(_Text(reader, writer))
        return root

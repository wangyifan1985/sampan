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


class Tag(Enum):
    COMMENT = ('{#', '#}')
    EXPRESSION = ('{{', '}}')
    STATEMENT = ('{%', '%}')


class Node:
    writer = None

    def __init__(self, writer: _Writer):
        self.writer = writer

    def generate(self):
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

    def __new__(cls, s):
        return super(Template, cls).__new__(cls)

    def __init__(self, s: str):
        self.raw = s
        self.cache = {}
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

    def parse(self, reader: _Reader, writer: _Writer) -> _Root:
        root = _Root(writer)
        while True:
            # Find next template directive
            curly = 0
            while True:
                curly = reader.find('{', curly)
                if curly == -1 or curly + 1 == reader.remaining():
                    # EOF
                    if in_block:
                        msg = 'Missing end block for {}'.format(in_block)
                        raise TemplateError(msg, template.name, reader.line)
                    body.chunks.append(_Text(reader.consume(), reader.line))
                    return body
                # If the first curly brace is not the start of a special token,
                # start searching from the character after it
                if reader[curly + 1] not in ('{', '%', '#'):
                    curly += 1
                    continue
                # When there are more than 2 curlies in a row, use the
                # innermost ones.  This is useful when generating languages
                # like latex where curlies are also meaningful
                if curly + 2 < reader.remaining() and reader[curly + 1] == '{' and reader[curly + 2] == '{':
                    curly += 1
                    continue
                break

            # Append any text before the special token
            if curly > 0:
                cons = reader.consume(curly)
                body.chunks.append(_Text(cons, reader.line))

            start_brace = reader.consume(2)
            line = reader.line

            # Template directives may be escaped as '{{!' or '{%!'.
            # In this case output the braces and consume the '!'.
            # This is especially useful in conjunction with jquery templates,
            # which also use double braces.
            if reader.remaining() and reader[0] == '!':
                reader.consume(1)
                body.chunks.append(_Text(start_brace, line))
                continue

            # Comment
            if start_brace == '{#':
                end = reader.find('#}')
                if end == -1:
                    raise TemplateError('Missing end comment #}', template.name, reader.line)
                _ = reader.consume(end).strip()
                reader.consume(2)
                continue

            # Expression
            if start_brace == '{{':
                end = reader.find('}}')
                if end == -1:
                    raise TemplateError('Missing end expression }}', template.name, reader.line)
                contents = reader.consume(end).strip()
                reader.consume(2)
                if not contents:
                    raise TemplateError('Empty expression', template.name, reader.line)
                body.chunks.append(_Expression(contents, line))
                continue

            # Block
            assert start_brace == '{%', start_brace
            end = reader.find('%}')
            if end == -1:
                raise TemplateError('Missing end block %}', template.name, reader.line)
            contents = reader.consume(end).strip()
            reader.consume(2)
            if not contents:
                raise TemplateError('Empty block tag ({% %})', template.name, reader.line)
            operator, space, suffix = contents.partition(' ')
            suffix = suffix.strip()

            # Intermediate ('else', 'elif', etc) blocks
            intermediate_blocks = {
                'else': {'if', 'for', 'while', 'try'},
                'elif': {'if'},
                'except': {'try'},
                'finally': {'try'},
            }
            allowed_parents = intermediate_blocks.get(operator)
            if allowed_parents is not None:
                if not in_block:
                    msg = '{} outside {} block'.format(operator, allowed_parents)
                    raise TemplateError(msg, template.name, reader.line)
                if in_block not in allowed_parents:
                    msg = '{} block cannot be attached to {} block'.format(operator, in_block)
                    raise TemplateError(msg, template.name, reader.line)
                body.chunks.append(_IntermediateControlBlock(contents, line))
                continue

            # End tag
            elif operator == 'end':
                if not in_block:
                    raise TemplateError('Extra {% end %} block', template.name, reader.line)
                return body

            elif operator in ('extends', 'include', 'set', 'import', 'from',
                              'comment', 'auto_escape', 'raw', 'module'):
                block = None
                if operator == 'comment':
                    continue
                if operator == 'extends':
                    suffix = suffix.strip('"').strip("'")
                    if not suffix:
                        raise TemplateError('extends missing file path', template.name, reader.line)
                    block = _ExtendsBlock(suffix)
                elif operator in ('import', 'from'):
                    if not suffix:
                        raise TemplateError('import missing statement', template.name, reader.line)
                    block = _Statement(contents, line)
                elif operator == 'include':
                    suffix = suffix.strip('"').strip("'")
                    if not suffix:
                        raise TemplateError('include missing file path', template.name, reader.line)
                    block = _IncludeBlock(suffix, template.name, line)
                elif operator == 'set':
                    if not suffix:
                        raise TemplateError('set missing statement', template.name, reader.line)
                    block = _Statement(suffix, line)
                elif operator == 'auto_escape':
                    fn = suffix.strip()
                    if fn == 'None':
                        fn = None
                    template.auto_escape = fn
                    continue
                elif operator == 'raw':
                    block = _Expression(suffix, line, raw=True)
                elif operator == 'module':
                    block = _Module(suffix, line)
                body.chunks.append(block)
                continue

            elif operator in ('apply', 'block', 'try', 'if', 'for', 'while'):
                # parse inner body recursively
                if operator in ('for', 'while'):
                    block_body = _parse(template, reader, operator, operator)
                elif operator == 'apply':
                    # apply creates a nested function so syntactically it's not
                    # in the loop.
                    block_body = _parse(template, reader, operator, None)
                else:
                    block_body = _parse(template, reader, operator, in_loop)

                if operator == 'apply':
                    if not suffix:
                        raise TemplateError('apply missing method name', template.name, reader.line)
                    block = _ApplyBlock(suffix, line, block_body)
                elif operator == 'block':
                    if not suffix:
                        raise TemplateError('block missing name', template.name, reader.line)
                    block = _NamedBlock(suffix, block_body, template, line)
                else:
                    block = _ControlBlock(contents, line, block_body)
                body.chunks.append(block)
                continue

            elif operator in ('break', 'continue'):
                if not in_loop:
                    raise TemplateError('{} outside {} block'.format(operator, 'for, while'), template.name, reader.line)
                body.chunks.append(_Statement(contents, line))
                continue

            else:
                raise TemplateError('unknown operator: {}'.format(operator), template.name, reader.line)

        def generate(self, **kwargs):
            reader = _Reader(self.template)
            writer = _Writer(self.buffer)
            root = self.parse(reader, writer)
            self.namespace.update(**kwargs)
            exec(buffer.getvalue(), self.namespace, None)
            execute = self.namespace['_tt_execute']
            linecache.clearcache()
            return execute()


class _Root(Node):
    def __init__(self, writer):
        super(_Root, self).__init__(writer)
        self.chunks = []

    def generate(self):
        self.writer.write_line('def tt_execute():')
        with self.writer.indent():
            self.writer.write_line('tt_buffer = []')
            for chunk in self.chunks:
                chunk.generate()
            self.writer.write_line("return tt_str('').join(tt_buffer)")

    def add_chunk(self, chunk: Node):
        self.chunks.append(chunk)

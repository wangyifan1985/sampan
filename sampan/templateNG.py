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
WS_RE = re.compile(r'[ \t\n\r]*', RE_FLAGS)


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
        m = regex.match(self.s, self.pos)

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
    text_re = re.compile(rf'[^{BOUNDARY[0]}]+', RE_FLAGS)

    def __init__(self, reader, writer):
        super(_Text, self).__init__(reader, writer)
        self.text = self.reader.re_consume(self.text_re).group()

    def generate(self):
        self.writer.write_line(f'tt_append({repr(to_str(self.text))})')


class _Comment(Node):
    comment_re = re.compile(rf'{BOUNDARY[0]}#.+?#{BOUNDARY[1]}', RE_FLAGS)

    def __init__(self, reader, writer):
        super(_Comment, self).__init__(reader, writer)
        _ = self.reader.re_consume(self.comment_re)

    def generate(self):
        pass


class _Expression(Node):
    exp_re = re.compile(rf'{BOUNDARY[0]}{{{WS_RE.pattern}(.+?){WS_RE.pattern}}}{BOUNDARY[1]}', RE_FLAGS)

    def __init__(self, reader, writer, raw=False, auto_escape=None):
        super(_Expression, self).__init__(reader, writer)
        self.exp = self.reader.re_consume(self.exp_re).group(1)
        self.raw = raw
        self.auto_escape = auto_escape
    
    def generate(self):
        self.writer.write_line(f'tt_tmp = {self.exp}')
        self.writer.write_line('if isinstance(tt_tmp, str): tt_tmp = tt_str(tt_tmp)')
        if not self.raw and self.auto_escape is not None:
            self.writer.write_line(f'tt_tmp = tt_str({self.auto_escape}(tt_tmp))')
        self.writer.write_line('tt_append(tt_tmp)')



class Template:
    parsers = {
        ('#', None): _Comment,
        ('{', None): _Expression,
        ('%', ''): _
    }

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
        _root = self.scan(_Reader(self.raw), _Writer(self.buffer))
        self.namespace.update(**kwargs)
        exec(self.buffer.getvalue(), self.namespace, None)
        execute = self.namespace['tt_execute']
        linecache.clearcache()
        return execute()

    def scan(self, reader: _Reader, writer: _Writer) -> _Root:
        root = _Root(writer)
        while not reader.eof():
            if reader[0] == BOUNDARY[0]:
                if reader[1] == '#':
                    root.add_chunk(_Comment(reader, writer))
                elif reader[1] == '{':
                    root.add_chunk(_Expression(reader, writer))
                elif reader[1] == '%':

            else:
                root.add_chunk(_Text(reader, writer))


                
                

            start = reader.consume(2)
            line = reader.line

            # Template directives may be escaped as '{{!' or '{%!'.
            # In this case output the braces and consume the '!'.
            # This is especially useful in conjunction with jquery templates,
            # which also use double braces.
            if reader.remaining() and reader[0] == '!':
                reader.consume(1)
                root.add_chunk(_Text(writer, start))
                continue

            # Comment
            if start == self.brace_start(Tag.COMMENT)
                end = reader.find(self.brace_end(Tag.COMMENT))
                if end == -1:
                    raise TemplateParseError(reader.s, pos, f'Missing end comment: "{self.brace_end(Tag.COMMENT)}":')
                reader.consume(end + 2)
                continue

            # Expression
            if start == self.brace_start(Tag.EXPRESSION)
                end = reader.find(self.brace_end(Tag.EXPRESSION))
                if end == -1:
                    raise TemplateParseError(reader.s, pos, f'Missing end expression "{self.brace_end(Tag.EXPRESSION)}":')
                contents = reader.consume(end).strip()
                reader.consume(2)
                if not contents:
                    raise TemplateParseError(reader.s, pos, 'Empty expression: ')
                root.add_chunk(self.parser[(Tag.EXPRESSION, '')](writer, contents))
                continue
            
            # Block
            if start == self.brace_start(Tag.STATEMENT)
                end = reader.find(self.brace_end(Tag.STATEMENT))
                if end == -1:
                    raise TemplateParseError(reader.s, pos, f'Missing end block "{self.brace_end(Tag.STATEMENT)}"')
                contents = reader.consume(end).strip()
                reader.consume(2)
                if not contents:
                    raise TemplateParseError(reader.s, pos, 'Empty block tag: ')
                operator, space, suffix = contents.partition(' ')
                suffix =suffix.strip()

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








if __name__ == '__main__':
    a = "{{abc"
    r = _Reader(a)
    print(r.find('{{'))
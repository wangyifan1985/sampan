#!/usr/bin/env python
# coding: utf-8

"""
    A extensible template system inspired by tornado.template.

    +--------+------------+-----------------+---------------------------------------------+----------------------+
    | Tag    | Operator   | Keywords        | Examples                                    | Handler              |
    +========+============+=================+=============================================+======================+
    | {# #}  |            |                 | {# this is comment #}                       | _Comment             |
    +--------+------------+-----------------+---------------------------------------------+----------------------+
    | {{ }}  |            |                 | {{ toto }},   {{ 'toto'.upper() }}          | _Expression          |
    +--------+------------+-----------------+---------------------------------------------+----------------------+
    | {% %}  | import     |                 | {% import html %}                           | _StatementInline     |
    +--------+------------+-----------------+---------------------------------------------+----------------------+
    | {% %}  | from       | import          | {% from html import escape %}               | _StatementInline     |
    +--------+------------+-----------------+---------------------------------------------+----------------------+
    | {% %}  | set        |                 | {% set toto=1 %}                            | _StatementInline     |
    +--------+------------+-----------------+---------------------------------------------+----------------------+
    | {% %}  | break      |                 | {% break %}                                 | _StatementInline     |
    +--------+------------+-----------------+---------------------------------------------+----------------------+
    | {% %}  | continue   |                 | {% continue %}                              | _StatementInline     |
    +--------+------------+-----------------+---------------------------------------------+----------------------+
    | {% %}  | autoescape |                 | {% autoescape toto %}                       | _StatementAutoescape |
    +--------+------------+-----------------+---------------------------------------------+----------------------+
    | {% %}  | comment    |                 | {% comment this is comment %}               | _StatementComment    |
    +--------+------------+-----------------+---------------------------------------------+----------------------+
    | {% %}  | raw        |                 | {% raw toto %}                              | _StatementRaw        |
    +--------+------------+-----------------+---------------------------------------------+----------------------+
    | {% %}  | if         | else, elif, end | {% if toto > 10 %}...{% else %}...{% end %} | _StatementIf         |
    +--------+------------+-----------------+---------------------------------------------+----------------------+
    | {% %}  | for        | in, end         | {% for toto in toto_list %}...{% end %}     | _StatementLoop       |
    +--------+------------+-----------------+---------------------------------------------+----------------------+
    | {% %}  | while      | end             | {% while toto > 10 %}...{% end %}           | _StatementLoop       |
    +--------+------------+-----------------+---------------------------------------------+----------------------+
    | {% %}  | include    |                 | {% include path/to/file %}                  | _StatementInclude    |
    +--------+------------+-----------------+---------------------------------------------+----------------------+
    | {% %}  | block      | end             | {% block toto %}...{% end %}                | _StatementBlock      |
    +--------+------------+-----------------+---------------------------------------------+----------------------+
    | {% %}  | extends    |                 | {% extends path/to/file %}                  | _StatementExtends    |
    +--------+------------+-----------------+---------------------------------------------+----------------------+
"""

import re
import os
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
STR_NAME = '<string>'
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
    def __init__(self, reader, msg: str='Exception parsing template: '):
        super(TemplateParseError, self).__init__(msg)
        self.reader = reader

    def __str__(self):
        line, col = self.linecol(self.reader.s, self.reader.pos)
        return ''.join((self.msg, 'line ', line, ' - ', 'column ', col))


# Template ####################################################################
###############################################################################
class _Reader:
    def __init__(self, s):
        self.s = s
        self.pos = 0

    def match(self, regex, start: int=0, end: int=None):
        return regex.match(self.s, start + self.pos, len(self.s) if end is None else end + self.pos)

    def consume(self, regex):
        m = regex.match(self.s, self.pos)
        if m is not None:
            self.pos = m.end()
        return m

    def remain(self):
        return len(self.s) - self.pos


class _Writer(object):
    def __init__(self, file: StringIO, named_blocks, current_template):
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

    def include(self, template):
        self.include_stack.append(self.current_template)
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


class _Node:
    tag = ('{', '}')

    def __init__(self, reader: _Reader=None):
        self.reader = reader

    def each_child(self):
        return ()

    def find_named_blocks(self, loader, named_blocks):
        for child in self.each_child():
            child.find_named_blocks(loader, named_blocks)

    def generate(self, writer: _Writer):
        raise NotImplementedError


class _Body(_Node):
    def __init__(self):
        super(_Body, self).__init__()
        self.chunks = []

    def add_chunk(self, node: _Node):
        self.chunks.append(node)

    def each_child(self):
        return self.chunks

    def generate(self, writer: _Writer):
        for chunk in self.chunks:
            chunk.generate(writer)


class _File(_Node):
    def __init__(self, template, body: _Body):
        super(_File, self).__init__()
        self.template = template
        self.body = body

    def each_child(self):
        return self.body,

    def generate(self, writer: _Writer):
        writer.write_line('def tt_execute():')
        with writer.indent():
            writer.write_line('tt_buffer = []')
            writer.write_line('tt_append = tt_buffer.append')
            self.body.generate(writer)
            writer.write_line("return tt_str('').join(tt_buffer)")


class _Text(_Node):
    regex = re.compile(rf'[^{_Node.tag[0]}]+', RE_FLAGS)

    def __init__(self, **kwargs):
        super(_Text, self).__init__(**kwargs)
        self.text = self.reader.consume(self.regex).group()

    def generate(self, writer: _Writer):
        writer.write_line(f'tt_append({repr(to_str(self.text))})')


class _Comment(_Node):
    tag = (f'{_Node.tag[0]}#', f'#{_Node.tag[1]}')
    regex = re.compile(rf'{tag[0]}.+?{tag[1]}', RE_FLAGS)

    def __init__(self, **kwargs):
        super(_Comment, self).__init__(**kwargs)
        _ = self.reader.consume(self.regex)

    def generate(self, writer: _Writer):
        pass


class _Expression(_Node):
    tag = (f'{_Node.tag[0]}{{', f'}}{_Node.tag[1]}')
    regex = re.compile(rf'{tag[0]}{WS}(.+?){WS}{tag[1]}')

    def __init__(self, template, **kwargs):
        super(_Expression, self).__init__(**kwargs)
        self.template = template
        self.exp = self.reader.consume(self.regex).group(1)
    
    def generate(self, writer: _Writer):
        writer.write_line(f'tt_tmp = {self.exp}')
        writer.write_line('if isinstance(tt_tmp, str): tt_tmp = tt_str(tt_tmp)')
        if self.template.autoescape is not None:
            writer.write_line(f'tt_tmp = tt_str(autoescape_{id(self.template.autoescape)}(tt_tmp))')
        writer.write_line('tt_append(tt_tmp)')


class _Statement(_Node):
    tag = (f'{_Node.tag[0]}%', f'%{_Node.tag[1]}')
    
    def __init__(self, **kwargs):
        super(_Statement, self).__init__(**kwargs)

    def generate(self, writer: _Writer):
        raise NotImplementedError


class _StatementInline(_Statement):
    regex = re.compile(rf'{_Statement.tag[0]}{WS}([a-zA-Z0-9_]+?{WS}.+?){WS}{_Statement.tag[1]}')

    def __init__(self, **kwargs):
        super(_StatementInline, self).__init__(**kwargs)
        self.stat = self.reader.consume(self.regex).group(1)

    def generate(self, writer: _Writer):
        writer.write_line(self.stat)


class _StatementComment(_StatementInline):
    def __init__(self, **kwargs):
        super(_StatementComment, self).__init__(**kwargs)

    def generate(self, writer: _Writer):
        pass


class _StatementSet(_StatementInline):
    def __init__(self, **kwargs):
        super(_StatementSet, self).__init__(**kwargs)
        _, _, self.exp = self.stat.partition(' ')

    def generate(self, writer: _Writer):
        writer.write_line(self.exp)


class _StatementRaw(_StatementInline):
    def __init__(self, **kwargs):
        super(_StatementRaw, self).__init__(**kwargs)
        _, _, self.exp = self.stat.partition(' ')

    def generate(self, writer: _Writer):
        writer.write_line(f'tt_tmp = {self.exp}')
        writer.write_line('if isinstance(tt_tmp, str): tt_tmp = tt_str(tt_tmp)')
        writer.write_line('tt_append(tt_tmp)')


class _StatementAutoescape(_StatementInline):
    def __init__(self, template, **kwargs):
        super(_StatementAutoescape, self).__init__(**kwargs)
        self.template = template
        _, _, self.name = self.stat.partition(' ')

    def generate(self, writer: _Writer):
        if self.name == 'None':
            self.template.autoescape = None
        else:
            _ns = self.template.namespace
            if self.name not in _ns:
                raise TemplateError(f'Unknown autoescape function "{self.name}".')
            self.template.autoescape = _ns.setdefault(f'autoescape_{id(_ns[self.name])}', _ns[self.name])



class _StatementIf(_Statement):
    regex = re.compile(rf'{_Statement.tag[0]}{WS}((?:if|else|elif).*?){WS}{_Statement.tag[1]}'
                       rf'((?:(?!{_Statement.tag[0]}{WS}(?:else|elif|end)).)*)', RE_FLAGS)
    regex_end = re.compile(rf'{_Statement.tag[0]}{WS}end{WS}{_Statement.tag[1]}')

    def __init__(self, template, **kwargs):
        super(_StatementIf, self).__init__(**kwargs)
        self.template = template
        self.stats = {}
        _m = self.reader.consume(self.regex)
        while _m:
            self.stats[_m.group(1)] = self.template.parser.parse(_m.group(2))
            _m = self.reader.consume(self.regex)
        else:
            self.reader.consume(self.regex_end)

    def generate(self, writer: _Writer):
        print(self.stats)
        for cond, stat in self.stats.items():
            writer.write_line(f'{cond}:')
            with writer.indent():
                stat.generate(writer)


class _StatementLoop(_Statement):
    regex = re.compile(rf'{_Statement.tag[0]}{WS}((?:for|while){WS}.+?){WS}{_Statement.tag[1]}'
                       rf'(.+?){_Statement.tag[0]}{WS}end{WS}{_Statement.tag[1]}', RE_FLAGS)

    def __init__(self, template, **kwargs):
        super(_StatementLoop, self).__init__(**kwargs)
        self.template = template
        _m = self.reader.consume(self.regex)
        self.cond = _m.group(1)
        with self.template.parser.in_loop():
            self.stat = self.template.parser.parse(_m.group(2))

    def generate(self, writer: _Writer):
        writer.write_line(f'{self.cond}:')
        with writer.indent():
            self.stat.generate(writer)


class _StatementTry(_Statement):
    regex = re.compile(rf'{_Statement.tag[0]}{WS}((?:try|except|else|finally){WS}.+?){WS}{_Statement.tag[1]}'
                       rf'((?:(?!{_Statement.tag[0]}{WS}(?:except|else|finally|end)).)*)', RE_FLAGS)

    def __init__(self, template, **kwargs):
        super(_StatementTry, self).__init__(**kwargs)
        self.template = template
        self.stats = []
        _m = self.reader.consume(self.regex)
        while _m is not None:
            self.stats = (_m.group(1), self.template.parse(_Reader(_m.group(2))))
            _m = self.reader.consume(self.regex)
        else:
            self.reader.consume(self.regex_end)

    def generate(self, writer: _Writer):
        for stat in self.stats:
            writer.write_line(f'{stat[0]}:')
            with writer.indent():
                if stat[1] is not None:
                    stat[1].generate()
                else:
                    writer.write_line('pass')


class _StatementInclude(_Statement):
    def __init__(self, template, **kwargs):
        super(_StatementInclude, self).__init__(**kwargs)
        self.template = template
        _, _, self.name = super(_StatementInclude, self).stat.partition(' ')
        self.name = self.name.strip("'").strip('"')

    def find_blocks(self, loader, named_blocks):
        included = loader.load(self.name)
        included.file.find_blocks(loader, named_blocks)

    def generate(self, writer: _Writer):
        included = writer.loader.load(self.name)
        with writer.include(included):
            included.file


class _StatementBlock(_Statement):
    regex = re.compile(rf'{_Statement.tag[0]}{WS}(block{WS}.+?){WS}{_Statement.tag[1]}'
                       rf'(.+?){_Statement.tag[0]}{WS}end{WS}{_Statement.tag[1]}', RE_FLAGS)

    def __init__(self, template, **kwargs):
        super(_StatementBlock, self).__init__(**kwargs)
        self.template = template
        _m = self.reader.consume(self.regex)
        self.name = _m.group(1)
        self.block = _m.group(2)

    def each_child(self):
        return self.block

    def find_blocks(self, loader, named_blocks):
        named_blocks[self.name] = self
        _Node.find_blocks(self, loader, named_blocks)

    def generate(self, writer: _Writer):
        if self.name not in self.template.cache:
            _buffer = StringIO()
            _body = self.template.parse(_Reader(self.block), _Writer(_buffer))
            _body.generate()
            self.template.cache[self.name] = _buffer.getvalue()


class _StatementExtends(_Statement):
    def __init__(self, template, **kwargs):
        super(_StatementExtends, self).__init__(**kwargs)
        self.template = template
        _, _, self.name = super(_StatementExtends, self).stat.partition(' ')
        self.name = self.name.strip("'").strip('"')
        
    def each_child(self):
        return super(_StatementExtends, self).each_child()
    
    def find_blocks(self, loader, named_blocks):
        super(_StatementExtends, self).find_blocks(loader, named_blocks)

    def generate(self, writer: _Writer):
        if self.name not in self.template.cache:
            _buffer = StringIO()
            with open(self.name, mode='r', encoding=ENCODING) as f:
                _body = self.template.parse(_Reader(f.read()), _Writer(_buffer))
                _body.generate()
            self.template.cache[self.name] = _buffer.getvalue()


class _Parser:
    def __init__(self, template, in_loop=False, in_block=False):
        self.template = template
        self._in_loop = in_loop
        self._in_block = in_block

    def in_loop(self):
        class InLoop:
            def __enter__(_):
                self._in_loop = True
                return self

            def __exit__(_, *args):
                assert self._in_loop
                self._in_loop = False
        return InLoop()

    def in_block(self):
        class InBlock:
            def __enter__(_):
                self._in_block = True
                return self

            def __exit__(_, *args):
                assert self._in_block
                self._in_block = False
        return InBlock()

    def parse(self) -> _Body:
        body = _Body()
        while self.template.reader.remain() > 0:
            m = self.template.reader.match(self.template.regex_tag)
            if m:
                tag = m.group(1)
                if tag == '#':
                    body.add_chunk(_Comment(reader=reader))
                elif tag == '{':
                    body.add_chunk(_Expression(template=self.template, reader=reader))
                elif tag == '%':
                    operator = self.template.reader.match(self.template.regex_operator).group(1)
                    if operator in ('import', 'from'):
                        body.add_chunk(_StatementInline(reader=reader))
                    elif operator in ('break', 'continue'):
                        if not self._in_loop:
                            raise TemplateParseError(reader, f'Incorrect operator "{operator}" position found '
                                                             f'in {self.template.name}: ')
                        body.add_chunk(_StatementInline(reader=reader))
                    elif operator == 'set':
                        body.add_chunk(_StatementSet(reader=reader))
                    elif operator == 'comment':
                        body.add_chunk(_StatementComment(reader=reader))
                    elif operator == 'raw':
                        body.add_chunk(_StatementRaw(reader=reader))
                    elif operator == 'autoescape':
                        body.add_chunk(_StatementAutoescape(template=self.template, reader=reader))
                    elif operator == 'if':
                        body.add_chunk(_StatementIf(template=self.template, reader=reader))
                    elif operator in ('for', 'while'):
                        body.add_chunk(_StatementLoop(template=self.template, reader=reader))
                    elif operator == 'include':
                        body.add_chunk(_StatementInclude(template=self.template, reader=reader))
                    elif operator == 'block':
                        body.add_chunk(_StatementBlock(template=self.template, reader=reader))
                    elif operator == 'extends':
                        body.add_chunk(_StatementExtends(template=self.template, reader=reader))
                    else:
                        raise TemplateParseError(reader, f'Unknown operator "{operator}" found in {self.template.name}: ')
                else:
                    raise TemplateParseError(reader, f'Unknown tag "{tag}" found in {self.template.name}: ')
            else:
                body.add_chunk(_Text(reader=reader))
        return body


class _Loader:
    def __init__(self, namespace=None, autoescape=None):
        self.namespace = namespace or {}
        self.autoescape = autoescape
        self.templates = dict()
        self.lock = threading.RLock()

    def reset(self):
        with self.lock:
            self.templates = {}

    def load(self, obj: str) -> Template:
        raise NotImplementedError


class Template:
    regex_tag = re.compile(rf'{_Node.tag[0]}([#,{{,%])')
    regex_operator = re.compile(rf'{_Node.tag[0]}%{WS}([a-zA-Z0-9_]+)')

    def __init__(self, raw: str, name: str=STR_NAME, autoescape: typing.Callable=None, loader: _Loader=None):
        self.namespace = {
            'tt_str': lambda s: s.decode(ENCODING) if isinstance(s, bytes) else str(s),
            'html_escape': escape,
            'url_quote': quote,
            'json_encode': dumps,
            'squeeze': lambda s: re.sub(r'[\x00-\x20]+', ' ', s).strip(),
            'datetime': datetime
        }
        self.reader = _Reader(raw)
        self.name = name
        if loader and loader.namespace:
            self.namespace.update(loader.namespace)
        self.autoescape = loader.autoescape if loader and loader.autoescape else autoescape
        if self.autoescape:
            self.namespace.setdefault(f'autoescape_{id(self.autoescape)}', self.autoescape)
        self.parser = _Parser(self)
        self.file = _File(self, self.parser.parse())
        print('+++++++++++++++')
        print(self.file.body.chunks)
        print('+++++++++++++++')
        self.compiled = self.compile(loader)

    def get_ancestors(self, loader):
        ancestors = [self.file]
        for chunk in self.file.body.chunks:
            if isinstance(chunk, _StatementExtends):
                if not loader:
                    raise TemplateError('{% extends %} block found, but no template loader')
                template = loader.load(chunk.name)
                ancestors.extend(template.get_ancestors(loader))
        return ancestors

    def compile(self, loader):
        buffer = StringIO()
        try:
            named_blocks = {}
            ancestors = self.get_ancestors(loader)
            ancestors.reverse()
            for ancestor in ancestors:
                ancestor.find_named_blocks(loader, named_blocks)
            writer = _Writer(buffer, named_blocks, ancestors[0].template)
            ancestors[0].generate(writer)
            print('*******************')
            print(buffer.getvalue())
            print('*******************')
            return compile(buffer.getvalue(), f"{self.name.replace('.', '_')}.gen.py", 'exec', dont_inherit=True)
        finally:
            buffer.close()

    def generate(self, **kwargs):
        ns = {}
        ns.update(self.namespace)
        ns.update(**kwargs)
        exec(self.compiled, ns, None)
        execute = ns['tt_execute']
        linecache.clearcache()
        return execute()


# Loader ######################################################################
###############################################################################
class StringLoader(_Loader):
    def __init__(self, name: str=STR_NAME, **kwargs):
        super(StringLoader, self).__init__(**kwargs)
        self.name = name

    def load(self, s: str):
        if self.name not in self.templates:
            with self.lock:
                self.templates[self.name] = Template(s, self.name, self.autoescape, self)
        return self.templates[self.name]


class FileLoader(_Loader):
    def __init__(self, path: str=os.path.dirname(__file__), **kwargs):
        super(FileLoader, self).__init__(**kwargs)
        self.path = os.path.abspath(path)

    def load(self, name: str):
        if name not in self.templates:
            with self.lock:
                file_path = os.path.abspath(os.path.join(self.path, name))
                with open(file_path, mode='r', encoding=ENCODING) as f:
                    self.templates[name] = Template(f.read(), name, self.autoescape, self)
        return self.templates[name]

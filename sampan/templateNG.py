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

__all__ = ['Template', 'TemplateError', 'StringLoader', 'FileLoader']

# Constants ###################################################################
###############################################################################
INDENT = 4
ENCODING = 'utf-8'
STR_NAME = '<string>'
RE_FLAGS = re.MULTILINE | re.DOTALL
WS = r'[ \t\n\r]*'


# Errors ######################################################################
###############################################################################
class TemplateError(Exception):
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


# Utilities ###################################################################
###############################################################################
def to_str(_bytes, encoding='utf8'):
    if not isinstance(_bytes, bytes):
        if isinstance(_bytes, str):
            return _bytes
        raise TypeError
    return _bytes.decode(encoding)


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
    def __init__(self, template, named_blocks):
        self.buffer = StringIO()
        self.template = template
        self.named_blocks = named_blocks
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
        self.include_stack.append(self.template)
        self.template = template

        class IncludeTemplate(object):
            def __enter__(_):
                return self

            def __exit__(_, *args):
                self.current_template = self.include_stack.pop()[0]

        return IncludeTemplate()

    def write_line(self, line, indent=None):
        if indent is None:
            indent = self._indent
        print('    ' * indent + line, file=self.buffer)

    def output(self, filename):
        print('--------------------')
        print(self.buffer.getvalue())
        print('--------------------')
        return compile(self.buffer.getvalue(), filename, 'exec', dont_inherit=True)

    def close(self):
        self.buffer.close()


class _Node:
    tag = ('{', '}')

    def __init__(self, template):
        self.template = template

    def each_child(self):
        return ()

    def find_named_blocks(self, loader, named_blocks):
        for child in self.each_child():
            child.find_named_blocks(loader, named_blocks)

    def generate(self):
        raise NotImplementedError


class _Body(_Node):
    def __init__(self, chunks, **kwargs):
        super(_Body, self).__init__(**kwargs)
        if chunks:
            self.chunks = chunks
        else:
            self.chunks = []

    def each_child(self):
        return self.chunks

    def generate(self):
        for chunk in self.chunks:
            chunk.generate()


class _File(_Node):
    def __init__(self, body: _Body, **kwargs):
        super(_File, self).__init__(**kwargs)
        self.body = body

    def each_child(self):
        return self.body,

    def generate(self):
        self.template.writer.write_line('def tt_execute():')
        with self.template.writer.indent():
            self.template.writer.write_line('tt_buffer = []')
            self.body.generate()
            self.template.writer.write_line("return tt_str('').join(tt_buffer)")


class _Text(_Node):
    regex = re.compile(rf'[^{_Node.tag[0]}]+', RE_FLAGS)

    def __init__(self, **kwargs):
        super(_Text, self).__init__(**kwargs)
        self.text = self.template.reader.consume(self.regex).group()

    def generate(self):
        self.template.writer.write_line(f'tt_buffer.append({repr(to_str(self.text))})')


class _Comment(_Node):
    tag = (f'{_Node.tag[0]}#', f'#{_Node.tag[1]}')
    regex = re.compile(rf'{tag[0]}.+?{tag[1]}', RE_FLAGS)

    def __init__(self, **kwargs):
        super(_Comment, self).__init__(**kwargs)
        _ = self.template.reader.consume(self.regex)

    def generate(self):
        pass


class _Expression(_Node):
    tag = (f'{_Node.tag[0]}{{', f'}}{_Node.tag[1]}')
    regex = re.compile(rf'{tag[0]}{WS}(.+?){WS}{tag[1]}')

    def __init__(self, **kwargs):
        super(_Expression, self).__init__(**kwargs)
        self.exp = self.template.reader.consume(self.regex).group(1)
    
    def generate(self):
        self.template.writer.write_line(f'tt_tmp = {self.exp}')
        self.template.writer.write_line('if isinstance(tt_tmp, str): tt_tmp = tt_str(tt_tmp)')
        if self.template.autoescape is not None:
            self.template.writer.write_line(f'tt_tmp = tt_str({self.template.autoescape}(tt_tmp))')
        self.template.writer.write_line('tt_buffer.append(tt_tmp)')


class _Statement(_Node):
    tag = (f'{_Node.tag[0]}%', f'%{_Node.tag[1]}')
    
    def __init__(self, **kwargs):
        super(_Statement, self).__init__(**kwargs)

    def generate(self):
        raise NotImplementedError


class _StatementInline(_Statement):
    regex = re.compile(rf'{_Statement.tag[0]}{WS}([a-zA-Z0-9_]+?{WS}.+?){WS}{_Statement.tag[1]}')

    def __init__(self, **kwargs):
        super(_StatementInline, self).__init__(**kwargs)
        self.stat = self.template.reader.consume(self.regex).group(1)

    def generate(self):
        self.template.writer.write_line(self.stat)


class _StatementComment(_StatementInline):
    def __init__(self, **kwargs):
        super(_StatementComment, self).__init__(**kwargs)

    def generate(self):
        pass


class _StatementSet(_StatementInline):
    def __init__(self, **kwargs):
        super(_StatementSet, self).__init__(**kwargs)
        _, _, self.exp = self.stat.partition(' ')

    def generate(self):
        self.template.writer.write_line(self.exp)


class _StatementRaw(_StatementInline):
    def __init__(self, **kwargs):
        super(_StatementRaw, self).__init__(**kwargs)
        _, _, self.exp = self.stat.partition(' ')

    def generate(self):
        self.template.writer.write_line(f'tt_tmp = {self.exp}')
        self.template.writer.write_line('if isinstance(tt_tmp, str): tt_tmp = tt_str(tt_tmp)')
        self.template.writer.write_line('tt_buffer.append(tt_tmp)')


class _StatementAutoescape(_StatementInline):
    def __init__(self, **kwargs):
        super(_StatementAutoescape, self).__init__(**kwargs)
        _, _, self.name = self.stat.partition(' ')

    def generate(self):
        if self.name == 'None':
            self.template.autoescape = None
        else:
            _ns = self.template.namespace
            if self.name not in _ns:
                raise TemplateError(f'Unknown autoescape function "{self.name}".')
            self.template.autoescape = _ns[self.name]


class _StatementIf(_Statement):
    regex = re.compile(rf'{_Statement.tag[0]}{WS}((?:if|else|elif).*?){WS}{_Statement.tag[1]}', RE_FLAGS)
    regex_end = re.compile(rf'{_Statement.tag[0]}{WS}end{WS}{_Statement.tag[1]}')

    def __init__(self, **kwargs):
        super(_StatementIf, self).__init__(**kwargs)
        self.stats = {}
        _m = self.template.reader.consume(self.regex)
        while _m:
            self.stats[_m.group(1)] = _Body(chunks=self.template.parser.parse(), template=self.template)
            _m = self.template.reader.consume(self.regex)
        else:
            self.template.reader.consume(self.regex_end)

    def generate(self):
        print(self.stats)
        for cond, stat in self.stats.items():
            self.template.writer.write_line(f'{cond}:')
            with self.template.writer.indent():
                stat.generate()


class _StatementLoop(_Statement):
    regex = re.compile(rf'{_Statement.tag[0]}{WS}((?:for|while){WS}.+?){WS}{_Statement.tag[1]}'
                       rf'(.+?){_Statement.tag[0]}{WS}end{WS}{_Statement.tag[1]}', RE_FLAGS)

    def __init__(self, **kwargs):
        super(_StatementLoop, self).__init__(**kwargs)
        _m = self.template.reader.consume(self.regex)
        self.cond = _m.group(1)
        with self.template.parser.in_loop():
            self.stat = self.template.parser.parse(_m.group(2))

    def generate(self):
        self.template.writer.write_line(f'{self.cond}:')
        with self.template.writer.indent():
            self.stat.generate()


class _StatementTry(_Statement):
    regex = re.compile(rf'{_Statement.tag[0]}{WS}((?:try|except|else|finally){WS}.+?){WS}{_Statement.tag[1]}'
                       rf'((?:(?!{_Statement.tag[0]}{WS}(?:except|else|finally|end)).)*)', RE_FLAGS)

    def __init__(self, **kwargs):
        super(_StatementTry, self).__init__(**kwargs)
        self.stats = []
        _m = self.template.reader.consume(self.regex)
        while _m is not None:
            self.stats = (_m.group(1), self.template.parse(_Reader(_m.group(2))))
            _m = self.template.reader.consume(self.regex)
        else:
            self.template.reader.consume(self.regex_end)

    def generate(self):
        for stat in self.stats:
            self.template.writer.write_line(f'{stat[0]}:')
            with self.template.writer.indent():
                if stat[1] is not None:
                    stat[1].generate()
                else:
                    self.template.writer.write_line('pass')


class _StatementInclude(_StatementInline):
    def __init__(self, **kwargs):
        super(_StatementInclude, self).__init__(**kwargs)
        _, _, self.name = self.stat.partition(' ')
        self.name = self.name.strip("'").strip('"')

    def find_blocks(self, loader, named_blocks):
        included = loader.load(self.name)
        included.file.find_blocks(loader, named_blocks)

    def generate(self):
        included = self.template.writer.loader.load(self.name)
        with self.template.writer.include(included):
            included.file


class _StatementBlock(_Statement):
    regex = re.compile(rf'{_Statement.tag[0]}{WS}(block{WS}.+?){WS}{_Statement.tag[1]}'
                       rf'(.+?){_Statement.tag[0]}{WS}end{WS}{_Statement.tag[1]}', RE_FLAGS)

    def __init__(self, **kwargs):
        super(_StatementBlock, self).__init__(**kwargs)
        _m = self.template.reader.consume(self.regex)
        self.name = _m.group(1)
        self.block = _m.group(2)

    def each_child(self):
        return self.block

    def find_blocks(self, loader, named_blocks):
        named_blocks[self.name] = self
        _Node.find_named_blocks(self, loader, named_blocks)

    def generate(self):
        if self.name not in self.template.cache:
            _buffer = StringIO()
            _body = self.template.parse(_Reader(self.block), _Writer(_buffer))
            _body.generate()
            self.template.cache[self.name] = _buffer.getvalue()


class _StatementExtends(_StatementInline):
    def __init__(self, **kwargs):
        super(_StatementExtends, self).__init__(**kwargs)
        _, _, self.name = super(_StatementExtends, self).stat.partition(' ')
        self.name = self.name.strip("'").strip('"')
        
    def each_child(self):
        return super(_StatementExtends, self).each_child()
    
    def find_blocks(self, loader, named_blocks):
        super(_StatementExtends, self).find_named_blocks(loader, named_blocks)

    def generate(self):
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
        self._in_nested = 0

    def in_nested(self):
        class InNested:
            def __enter__(_):
                self._in_nested += 1
                return self

            def __exit__(_, *args):
                assert self._in_nested > 0
                self._in_nested -= 1

        return InNested()

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

    def parse(self) -> typing.List[_Node]:
        chunks = []
        while self.template.reader.remain() > 0:
            m = self.template.reader.match(self.template.regex_tag)
            if m:
                tag = m.group(1)
                if tag == '#':
                    chunks.append(_Comment(template=self.template))
                elif tag == '{':
                    chunks.append(_Expression(template=self.template))
                elif tag == '%':
                    operator = self.template.reader.match(self.template.regex_operator).group(1)
                    if operator == 'end':
                        if self._in_nested == 0:
                            return chunks
                    if operator in ('import', 'from'):
                        chunks.append(_StatementInline(template=self.template))
                    elif operator in ('break', 'continue'):
                        if not self._in_loop:
                            raise TemplateParseError(self.template.reader, f'Incorrect operator "{operator}" position found '
                                                             f'in {self.template.name}: ')
                        chunks.append(_StatementInline(template=self.template))
                    elif operator == 'set':
                        chunks.append(_StatementSet(template=self.template))
                    elif operator == 'comment':
                        chunks.append(_StatementComment(template=self.template))
                    elif operator == 'raw':
                        chunks.append(_StatementRaw(template=self.template))
                    elif operator == 'autoescape':
                        chunks.append(_StatementAutoescape(template=self.template))
                    elif operator == 'if':
                        chunks.append(_StatementIf(template=self.template))
                    elif operator in ('for', 'while'):
                        chunks.append(_StatementLoop(template=self.template))
                    elif operator == 'include':
                        chunks.append(_StatementInclude(template=self.template))
                    elif operator == 'block':
                        chunks.append(_StatementBlock(template=self.template))
                    elif operator == 'extends':
                        chunks.append(_StatementExtends(template=self.template))
                    else:
                        raise TemplateParseError(self.template.reader, f'Unknown operator "{operator}" found in {self.template.name}: ')
                else:
                    raise TemplateParseError(self.template.reader, f'Unknown tag "{tag}" found in {self.template.name}: ')
            else:
                chunks.append(_Text(template=self.template))
        return chunks


class Template:
    regex_tag = re.compile(rf'{_Node.tag[0]}([#,{{,%])')
    regex_operator = re.compile(rf'{_Node.tag[0]}%{WS}([a-zA-Z0-9_]+)')

    def __init__(self, raw: str, name: str=STR_NAME, autoescape: typing.Callable=None, loader=None):
        self._auto_escape = None
        self.namespace = {
            'tt_str': lambda s: s.decode(ENCODING) if isinstance(s, bytes) else str(s),
            'html_escape': escape,
            'url_quote': quote,
            'json_encode': dumps,
            'squeeze': lambda s: re.sub(r'[\x00-\x20]+', ' ', s).strip(),
            'datetime': datetime
        }
        self.name = name
        if loader and loader.namespace:
            self.namespace.update(loader.namespace)
        self.autoescape = loader.autoescape if loader and loader.autoescape else autoescape
        self.reader = _Reader(raw)
        self.file = _File(body=_Body(_Parser(self).parse(), template=self), template=self)
        print('+++++++++++++++')
        print(self.file.body.chunks)
        print('+++++++++++++++')
        named_blocks = {}
        ancestors = self.get_ancestors(loader)
        ancestors.reverse()
        for ancestor in ancestors:
            ancestor.find_named_blocks(loader, named_blocks)
        self.writer = _Writer(ancestors[0].template, named_blocks)
        try:
            ancestors[0].generate()
            self.compiled = self.writer.output(f"{self.name.replace('.', '_')}.gen.py")
        finally:
            self.writer.close()

    @property
    def autoescape(self):
        if self._auto_escape:
            return f'tt_auto_escape_{id(self._auto_escape)}'
        return None

    @autoescape.setter
    def autoescape(self, func):
        self._auto_escape = func
        if func:
            self.namespace.setdefault(f'tt_auto_escape_{id(func)}', func)

    def get_ancestors(self, loader):
        ancestors = [self.file]
        for chunk in self.file.body.chunks:
            if isinstance(chunk, _StatementExtends):
                if not loader:
                    raise TemplateError('{% extends %} block found, but no template loader')
                template = loader.load(chunk.name)
                ancestors.extend(template.get_ancestors(loader))
        return ancestors

    def render(self, **kwargs):
        ns = {}
        ns.update(self.namespace)
        ns.update(**kwargs)
        exec(self.compiled, ns, None)
        execute = ns['tt_execute']
        linecache.clearcache()
        return execute()


# Loader ######################################################################
###############################################################################
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

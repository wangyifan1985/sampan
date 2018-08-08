#!/usr/bin/env python
# coding: utf-8

"""
A extensible template system, inspired by tornado.

Basic usage looks like::

    t = template.Template('<html>{{ myvalue }}</html>')
    print t.generate(myvalue='XXX')

`Loader` is a class that loads templates from a root directory and caches
the compiled templates::

    loader = template.Loader('/home/btaylor')
    print loader.load('test.html').generate(myvalue='XXX')

We compile all templates to raw Python. Error-reporting is currently... uh,
interesting. Syntax for the templates::

    ### base.html
    <html>
      <head>
        <title>{% block title %}Default title{% end %}</title>
      </head>
      <body>
        <ul>
          {% for student in students %}
            {% block student %}
              <li>{{ escape(student.name) }}</li>
            {% end %}
          {% end %}
        </ul>
      </body>
    </html>

    ### bold.html
    {% extends 'base.html' %}

    {% block title %}A bolder title{% end %}

    {% block student %}
      <li><span style='bold'>{{ escape(student.name) }}</span></li>
    {% end %}

Unlike most other template systems, we do not put any restrictions on the
expressions you can include in your statements. ``if`` and ``for`` blocks get
translated exactly into Python, so you can do complex expressions like::

   {% for student in [p for p in people if p.student and p.age > 23] %}
     <li>{{ escape(student.name) }}</li>
   {% end %}

Translating directly to Python means you can apply functions to expressions
easily, like the ``escape()`` function in the examples above. You can pass
functions in to your template just like any other variable
(In a `.RequestHandler`, override `.RequestHandler.get_template_namespace`)::

   ### Python code
   def add(x, y):
      return x + y
   template.execute(add=add)

   ### The template
   {{ add(1, 2) }}

We provide the functions `escape() <.html_escape>`, `.url_escape()`,
`.json_encode()`, and `.squeeze()` to all templates by default.


Variable names beginning with ``_tt_`` are reserved by the template
system and should not be used by application code.

Syntax Reference
----------------

Template expressions are surrounded by double curly braces: ``{{ ... }}``.
The contents may be any python expression, which will be escaped according
to the current autoescape setting and inserted into the output.  Other
template directives use ``{% %}``.

To comment out a section so that it is omitted from the output, surround it
with ``{# ... #}``.

These tags may be escaped as ``{{!``, ``{%!``, and ``{#!``
if you need to include a literal ``{{``, ``{%``, or ``{#`` in the output.


``{% apply *function* %}...{% end %}``
    Applies a function to the output of all template code between ``apply``
    and ``end``::

        {% apply linkify %}{{name}} said: {{message}}{% end %}

    Note that as an implementation detail apply blocks are implemented
    as nested functions and thus may interact strangely with variables
    set via ``{% set %}``, or the use of ``{% break %}`` or ``{% continue %}``
    within loops.

``{% autoescape *function* %}``
    Sets the autoescape mode for the current file.  This does not affect
    other files, even those referenced by ``{% include %}``.  Note that
    autoescaping can also be configured globally, at the `.Application`
    or `Loader`.::

        {% autoescape html_escape %}
        {% autoescape None %}

``{% block *name* %}...{% end %}``
    Indicates a named, replaceable block for use with ``{% extends %}``.
    Blocks in the parent template will be replaced with the contents of
    the same-named block in a child template.::

        <!-- base.html -->
        <title>{% block title %}Default title{% end %}</title>

        <!-- mypage.html -->
        {% extends 'base.html' %}
        {% block title %}My page title{% end %}

``{% comment ... %}``
    A comment which will be removed from the template output.  Note that
    there is no ``{% end %}`` tag; the comment goes from the word ``comment``
    to the closing ``%}`` tag.

``{% extends *filename* %}``
    Inherit from another template.  Templates that use ``extends`` should
    contain one or more ``block`` tags to replace content from the parent
    template.  Anything in the child template not contained in a ``block``
    tag will be ignored.  For an example, see the ``{% block %}`` tag.

``{% for *var* in *expr* %}...{% end %}``
    Same as the python ``for`` statement.  ``{% break %}`` and
    ``{% continue %}`` may be used inside the loop.

``{% from *x* import *y* %}``
    Same as the python ``import`` statement.

``{% if *condition* %}...{% elif *condition* %}...{% else %}...{% end %}``
    Conditional statement - outputs the first section whose condition is
    true.  (The ``elif`` and ``else`` sections are optional)

``{% import *module* %}``
    Same as the python ``import`` statement.

``{% include *filename* %}``
    Includes another template file.  The included file can see all the local
    variables as if it were copied directly to the point of the ``include``
    directive (the ``{% autoescape %}`` directive is an exception).
    Alternately, ``{% module Template(filename, **kwargs) %}`` may be used
    to include another template with an isolated namespace.

``{% raw *expr* %}``
    Outputs the result of the given expression without autoescaping.

``{% set *x* = *y* %}``
    Sets a local variable.

``{% try %}...{% except %}...{% else %}...{% finally %}...{% end %}``
    Same as the python ``try`` statement.

``{% while *condition* %}... {% end %}``
    Same as the python ``while`` statement.  ``{% break %}`` and
    ``{% continue %}`` may be used inside the loop.
"""
import datetime
import linecache
import os
import re
import json
import threading
from io import StringIO
from html import escape
from urllib.parse import quote
from .log import get_logger


__all__ = ['Template', 'TemplateError', 'StringLoader', 'FileLoader']


log = get_logger(__name__)
DEFAULT_AUTO_ESCAPE = 'html_escape'
DEFAULT_STRING_NAME = '<string>'


# Errors ######################################################################
###############################################################################
class TemplateError(Exception):
    """Raised for template syntax errors.
        ``TemplateError`` instances have ``filename`` and ``lineno`` attributes
        indicating the position of the error.
        .. versionchanged:: 4.3
           Added ``filename`` and ``lineno`` attributes.
        """

    def __init__(self, message, filename=None, lineno=0):
        self.message = message
        # The names "filename" and "lineno" are chosen for consistency
        # with python SyntaxError.
        self.filename = filename
        self.lineno = lineno

    def __str__(self):
        return '%s at %s:%d' % (self.message, self.filename, self.lineno)


# Utilities ###################################################################
###############################################################################
class ObjectDict(dict):
    """Makes a dictionary behave like an object, with attribute-style access.
        """

    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)

    def __setattr__(self, k, v):
        self[k] = v


def squeeze(s):
    """Replace all sequences of whitespace chars with a single space."""
    return re.sub(r"[\x00-\x20]+", " ", s).strip()


def to_str(_bytes, encoding='utf8'):
    if not isinstance(_bytes, bytes):
        if isinstance(_bytes, str):
            return _bytes
        raise TypeError
    return _bytes.decode(encoding)


def json_dumps(obj):
    return json.dumps(obj)


# Template ####################################################################
###############################################################################
class Template:
    def __init__(self, template_string, name=DEFAULT_STRING_NAME, loader=None, auto_escape=DEFAULT_AUTO_ESCAPE):
        self.name = name
        if loader and loader.auto_escape:
            self.auto_escape = loader.auto_escape
        else:
            self.auto_escape = auto_escape
        self.namespace = loader.namespace if loader else {}
        self.file = _File(self, _parse(self, _TemplateReader(to_str(template_string))))
        self.code = self._generate_python(loader)
        self.loader = loader
        self.compiled = compile(self.code, '{}.gen.py'.format(self.name.replace('.', '_')), 'exec', dont_inherit=True)

    @staticmethod
    def exec_in(code, glob, loc=None):
        if isinstance(code, str):
            code = compile(code, '<string>', 'exec', dont_inherit=True)
        exec(code, glob, loc)

    def generate(self, **kwargs):
        namespace = {
            'escape': escape,
            'html_escape': escape,
            'url_escape': quote,
            'json_encode': json_dumps,
            'squeeze': squeeze,
            'datetime': datetime,
            '_tt_utf8': to_str,  # for internal use
            '_tt_string_types': (str, bytes),
            # __name__ and __loader__ allow the traceback mechanism to find
            # the generated source code.
            '__name__': self.name.replace('.', '_'),
            '__loader__': ObjectDict(get_source=lambda name: self.code),
        }
        namespace.update(self.namespace)
        namespace.update(kwargs)
        self.exec_in(self.compiled, namespace)
        execute = namespace['_tt_execute']
        # Clear the traceback module's cache of source data now that
        # we've generated a new template (mainly for this module's
        # unittests, where different tests reuse the same name).
        linecache.clearcache()
        return execute()

    def _generate_python(self, loader):
        buffer = StringIO()
        try:
            # named_blocks maps from names to _NamedBlock objects
            named_blocks = {}
            ancestors = self._get_ancestors(loader)
            ancestors.reverse()
            for ancestor in ancestors:
                ancestor.find_named_blocks(loader, named_blocks)
            writer = _CodeWriter(buffer, named_blocks, loader,
                                 ancestors[0].template)
            ancestors[0].generate(writer)
            return buffer.getvalue()
        finally:
            buffer.close()

    def _get_ancestors(self, loader):
        ancestors = [self.file]
        for chunk in self.file.body.chunks:
            if isinstance(chunk, _ExtendsBlock):
                if not loader:
                    raise TemplateError('{% extends %} block found, but no template loader')
                template = loader.load(chunk.name, self.name)
                ancestors.extend(template._get_ancestors(loader))
        return ancestors


###############################################################################
# Loaders #####################################################################
###############################################################################
class BaseLoader:
    """Base class for template loaders.
      You must use a template loader to use template constructs like
      {% extends %} and {% include %}. The loader caches all
      templates after they are loaded the first time.
    """

    def __init__(self, namespace=None, auto_escape=DEFAULT_AUTO_ESCAPE):
        self.namespace = namespace or {}
        self.auto_escape = auto_escape
        self.templates = dict()
        self.lock = threading.RLock()

    def reset(self):
        """Resets the cache of compiled templates."""
        with self.lock:
            self.templates.clear()

    def load(self, obj):
        raise NotImplementedError()


class StringLoader(BaseLoader):
    def __init__(self, name=DEFAULT_STRING_NAME, **kwargs):
        super(StringLoader, self).__init__(**kwargs)
        self.name = name

    def load(self, template_string):
        if not template_string:
            msg = 'template_string is missing.'
            raise Exception(msg)
        if self.name not in self.templates:
            with self.lock:
                self.templates[self.name] = Template(template_string, self.name, loader=self)
        return self.templates[self.name]


class FileLoader(BaseLoader):
    def __init__(self, base_dir=None, **kwargs):
        super(FileLoader, self).__init__(**kwargs)
        if base_dir:
            self.base_dir = os.path.abspath(base_dir)
        else:
            self.base_dir = os.path.abspath(os.path.dirname(__file__))

    def load(self, name):
        if not name:
            msg = 'name is missing.'
            raise Exception(msg)
        if name not in self.templates:
            with self.lock:
                file_path = os.path.abspath(os.path.join(self.base_dir, name))
                with open(file_path, 'rb') as f:
                    self.templates[name] = Template(f.read(), name, loader=self)
        return self.templates[name]


###############################################################################
# Elements ####################################################################
###############################################################################
class _Node:
    def each_child(self):
        return ()

    def generate(self, writer):
        raise NotImplementedError()

    def find_named_blocks(self, loader, named_blocks):
        for child in self.each_child():
            child.find_named_blocks(loader, named_blocks)


class _File(_Node):
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


class _ChunkList(_Node):
    def __init__(self, chunks):
        self.chunks = chunks

    def generate(self, writer):
        for chunk in self.chunks:
            chunk.generate(writer)

    def each_child(self):
        return self.chunks


class _NamedBlock(_Node):
    def __init__(self, name, body, template, line):
        self.name = name
        self.body = body
        self.template = template
        self.line = line

    def each_child(self):
        return self.body,

    def generate(self, writer):
        block = writer.named_blocks[self.name]
        with writer.include(block.template, self.line):
            block.body.generate(writer)

    def find_named_blocks(self, loader, named_blocks):
        named_blocks[self.name] = self
        _Node.find_named_blocks(self, loader, named_blocks)


class _ExtendsBlock(_Node):
    def __init__(self, name):
        self.name = name

    def each_child(self):
        return super().each_child()

    def generate(self, writer):
        super().generate(writer)

    def find_named_blocks(self, loader, named_blocks):
        super().find_named_blocks(loader, named_blocks)


class _IncludeBlock(_Node):
    def __init__(self, name, template_name, line):
        self.name = name
        self.template_name = template_name
        self.line = line

    def find_named_blocks(self, loader, named_blocks):
        included = loader.load(self.name, self.template_name)
        included.file.find_named_blocks(loader, named_blocks)

    def generate(self, writer):
        included = writer.loader.load(self.name, self.template_name)
        with writer.include(included, self.line):
            included.file.body.generate(writer)


class _ApplyBlock(_Node):
    def __init__(self, method, line, body=None):
        self.method = method
        self.line = line
        self.body = body

    def each_child(self):
        return self.body,

    def generate(self, writer):
        method_name = '_tt_apply%d' % writer.apply_counter
        writer.apply_counter += 1
        writer.write_line('def %s():' % method_name, self.line)
        with writer.indent():
            writer.write_line('_tt_buffer = []', self.line)
            writer.write_line('_tt_append = _tt_buffer.append', self.line)
            self.body.generate(writer)
            writer.write_line("return _tt_utf8('').join(_tt_buffer)", self.line)
        writer.write_line('_tt_append(_tt_utf8(%s(%s())))' % (
            self.method, method_name), self.line)


class _ControlBlock(_Node):
    def __init__(self, statement, line, body=None):
        self.statement = statement
        self.line = line
        self.body = body

    def each_child(self):
        return self.body,

    def generate(self, writer):
        writer.write_line('%s:' % self.statement, self.line)
        with writer.indent():
            self.body.generate(writer)
            # Just in case the body was empty
            writer.write_line('pass', self.line)


class _IntermediateControlBlock(_Node):
    def __init__(self, statement, line):
        self.statement = statement
        self.line = line

    def generate(self, writer):
        # In case the previous block was empty
        writer.write_line('pass', self.line)
        writer.write_line('%s:' % self.statement, self.line, writer.indent_size() - 1)


class _Statement(_Node):
    def __init__(self, statement, line):
        self.statement = statement
        self.line = line

    def generate(self, writer):
        writer.write_line(self.statement, self.line)


class _Expression(_Node):
    def __init__(self, expression, line, raw=False):
        self.expression = expression
        self.line = line
        self.raw = raw

    def generate(self, writer):
        writer.write_line('_tt_tmp = %s' % self.expression, self.line)
        writer.write_line('if isinstance(_tt_tmp, _tt_string_types):'
                          ' _tt_tmp = _tt_utf8(_tt_tmp)', self.line)
        writer.write_line('else: _tt_tmp = _tt_utf8(str(_tt_tmp))', self.line)
        if not self.raw and writer.current_template.auto_escape is not None:
            # In python3 functions like html_escape return unicode,
            # so we have to convert to utf8 again.
            writer.write_line('_tt_tmp = _tt_utf8(%s(_tt_tmp))' %
                              writer.current_template.auto_escape, self.line)
        writer.write_line('_tt_append(_tt_tmp)', self.line)


class _Module(_Expression):
    def __init__(self, expression, line):
        super(_Module, self).__init__('_tt_modules.' + expression, line,
                                      raw=True)


class _Text(_Node):
    def __init__(self, value, line):
        self.value = value
        self.line = line

    def generate(self, writer):
        value = self.value
        if value:
            writer.write_line('_tt_append(%r)' % to_str(value), self.line)


class _CodeWriter(object):
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


class _TemplateReader:
    def __init__(self, text):
        self.text = text
        self.line = 1
        self.pos = 0

    def find(self, needle, start=0, end=None):
        start += self.pos
        if end is None:
            index = self.text.find(needle, start)
        else:
            end += self.pos
            assert end >= start
            index = self.text.find(needle, start, end)
        if index != -1:
            index -= self.pos
        return index

    def consume(self, count=None):
        if count is None:
            count = len(self.text) - self.pos
        new_pos = self.pos + count
        self.line += self.text.count('\n', self.pos, new_pos)
        s = self.text[self.pos:new_pos]
        self.pos = new_pos
        return s

    def remaining(self):
        return len(self.text) - self.pos

    def __len__(self):
        return self.remaining()

    def __str__(self):
        return self.text[self.pos:]

    def __getitem__(self, key):
        if type(key) is slice:
            size = len(self)
            start, stop, step = key.indices(size)
            if start is None:
                start = self.pos
            else:
                start += self.pos
            if stop is not None:
                stop += self.pos
            return self.text[slice(start, stop, step)]
        elif key < 0:
            return self.text[key]
        else:
            return self.text[self.pos + key]


###############################################################################
# Parser ######################################################################
###############################################################################
def _parse(template, reader, in_block=None, in_loop=None):
    body = _ChunkList([])
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

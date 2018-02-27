#!/usr/bin/env python
# coding: utf-8

from unittest import TestCase
from ..templateNG import Template
from html import escape
from pprint import pprint







tmpl1 = """
    <html>
      <head>
        <title>{{ title }}</title>
        {# this is comment #}
      </head>
      <body>
        <ul>
          {% for student in students %}
              <li>{{ escape(student.name) }}</li>
          {% end %}
        </ul>
        <p>{% if name %}
            {{ name }}
            {% else %}
            anonym
            {% end %}
        </p>
      </body>
    </html>
"""

tmpl2 = """{% if name %}
            {{ name }}
            {% else %}
            anonym
            {% end %}
        </p>
"""

tmpl3 = """{% for student in students %}
              <li>{{ escape(student.name) }}</li>
          {% end %}

"""

tmpl4 = """{% break %}

"""


class TestTemplate(TestCase):

    def test_text(self):
        txt = """<html>\n<body>\n\n<h1>My First Heading</h1>\n<p>My first paragraph.</p>\n\n</body></html>"""
        t = Template(txt)
        self.assertEqual(t.generate(), txt)

    def test_comment(self):
        cmt = """<html>\n<body>\n\n<h1>{# this is comment #}My First Heading</h1>\n<p>My first paragraph.</p>\n\n</body></html>"""
        expected = """<html>\n<body>\n\n<h1>My First Heading</h1>\n<p>My first paragraph.</p>\n\n</body></html>"""
        t = Template(cmt)
        self.assertEqual(t.generate(), expected)

    def test_exp_var_escaped(self):
        exp_var = """<html>\n<body>\n<h1>{{ title }}</h1>\n<p>My first paragraph.</p>\n</body>\n</html>"""
        expected = """<html>\n<body>\n<h1>My &quot;First&quot; Heading</h1>\n<p>My first paragraph.</p>\n</body>\n</html>"""
        t = Template(exp_var, autoescape=escape)
        self.assertEqual(t.generate(title='My "First" Heading'), expected)

    def test_exp_var(self):
        exp_var = """<html>\n<body>\n<h1>{{ title }}</h1>\n<p>My first paragraph.</p>\n</body>\n</html>"""
        expected = """<html>\n<body>\n<h1>hahah</h1>\n<p>My first paragraph.</p>\n</body>\n</html>"""
        t = Template(exp_var)
        self.assertEqual(t.generate(title="hahah"), expected)

    def test_exp_func(self):
        exp_func = """<html>\n<body>\n<h1>{{ hello(title) }}</h1>\n<p>My first paragraph.</p>\n</body>\n</html>"""
        expected = """<html>\n<body>\n<h1>hello toto</h1>\n<p>My first paragraph.</p>\n</body>\n</html>"""
        t = Template(exp_func)
        self.assertEqual(t.generate(hello=lambda s: 'hello '+s, title='toto'), expected)

    def test_exp_mth(self):
        exp_mth = """<html>\n<body>\n<h1>{{ 'toto'.upper() }}</h1>\n<p>My first paragraph.</p>\n</body>\n</html>"""
        expected = """<html>\n<body>\n<h1>TOTO</h1>\n<p>My first paragraph.</p>\n</body>\n</html>"""
        t = Template(exp_mth)
        self.assertEqual(t.generate(), expected)

    def test_sts_comment(self):
        sts_cmt = """<html>\n<body>\n\n<h1>{% comment this is comment %}My First Heading</h1>\n<p>My first paragraph.</p>\n\n</body></html>"""
        expected = """<html>\n<body>\n\n<h1>My First Heading</h1>\n<p>My first paragraph.</p>\n\n</body></html>"""
        t = Template(sts_cmt)
        self.assertEqual(t.generate(), expected)

    def test_sts_raw(self):
        sts_raw = """<html>\n<body>\n\n<h1>{% raw h1 %}</h1>\n<p>My first paragraph.</p>\n\n</body></html>"""
        expected = """<html>\n<body>\n\n<h1>My "First" Heading</h1>\n<p>My first paragraph.</p>\n\n</body></html>"""
        t = Template(sts_raw, autoescape=escape)
        self.assertEqual(t.generate(h1='My "First" Heading'), expected)

    def test_sts_autoescape(self):
        sts_esc = """<html>\n<body>\n\n<h1>{{ h1 }}</h1>\n{% autoescape html_escape%}<p>{{ p }}</p>\n\n{% autoescape None %}<footer>{{ footer }}</footer></body></html>"""
        expected = """<html>\n<body>\n\n<h1>'My First Heading'</h1>\n<p>My &quot;first&quot; paragraph.</p>\n\n<footer>My "footer" here</footer></body></html>"""
        t = Template(sts_esc, autoescape=repr)
        self.assertEqual(t.generate(h1='My First Heading', p='My "first" paragraph.', footer='My "footer" here'),
                         expected)

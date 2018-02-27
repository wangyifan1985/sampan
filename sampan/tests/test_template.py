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
        tmpl_txt = """<html>\n<body>\n\n<h1>My First Heading</h1>\n<p>My first paragraph.</p>\n\n</body></html>"""
        t = Template(tmpl_txt)
        self.assertEqual(t.generate(), tmpl_txt)

    def test_comment(self):
        tmpl_cmt = """<html>\n<body>\n\n<h1>{# this is comment #}My First Heading</h1>\n<p>My first paragraph.</p>\n\n</body></html>"""
        tmpl_expected = """<html>\n<body>\n\n<h1>My First Heading</h1>\n<p>My first paragraph.</p>\n\n</body></html>"""
        t = Template(tmpl_cmt)
        self.assertEqual(t.generate(), tmpl_expected)

    def test_exp_var_escaped(self):
        tmpl_exp_var = """<html>\n<body>\n<h1>{{ title }}</h1>\n<p>My first paragraph.</p>\n</body>\n</html>"""
        tmpl_expected = """<html>\n<body>\n<h1>My &quot;First&quot; Heading</h1>\n<p>My first paragraph.</p>\n</body>\n</html>"""
        t = Template(tmpl_exp_var, autoescape=escape)
        self.assertEqual(t.generate(title='My "First" Heading'), tmpl_expected)

    def test_exp_var(self):
        tmpl_exp_var = """<html>\n<body>\n<h1>{{ title }}</h1>\n<p>My first paragraph.</p>\n</body>\n</html>"""
        tmpl_expected = """<html>\n<body>\n<h1>hahah</h1>\n<p>My first paragraph.</p>\n</body>\n</html>"""
        t = Template(tmpl_exp_var)
        self.assertEqual(t.generate(title="hahah"), tmpl_expected)

    def test_exp_func(self):
        tmpl_exp_func = """<html>\n<body>\n<h1>{{ hello(title) }}</h1>\n<p>My first paragraph.</p>\n</body>\n</html>"""
        tmpl_expected = """<html>\n<body>\n<h1>hello toto</h1>\n<p>My first paragraph.</p>\n</body>\n</html>"""
        t = Template(tmpl_exp_func)
        self.assertEqual(t.generate(hello=lambda s: 'hello '+s, title='toto'), tmpl_expected)

    def test_exp_mth(self):
        tmpl_exp_mth = """<html>\n<body>\n<h1>{{ 'toto'.upper() }}</h1>\n<p>My first paragraph.</p>\n</body>\n</html>"""
        tmpl_expected = """<html>\n<body>\n<h1>TOTO</h1>\n<p>My first paragraph.</p>\n</body>\n</html>"""
        t = Template(tmpl_exp_mth)
        self.assertEqual(t.generate(), tmpl_expected)

    def test_sts_comment(self):
        tmpl_sts_cmt = """<html>\n<body>\n\n<h1>{% comment this is comment %}My First Heading</h1>\n<p>My first paragraph.</p>\n\n</body></html>"""
        tmpl_expected = """<html>\n<body>\n\n<h1>My First Heading</h1>\n<p>My first paragraph.</p>\n\n</body></html>"""
        t = Template(tmpl_sts_cmt)
        self.assertEqual(t.generate(), tmpl_expected)

    def test_sts_raw(self):
        tmpl_sts_raw = """<html>\n<body>\n\n<h1>{% raw title %}</h1>\n<p>My first paragraph.</p>\n\n</body></html>"""
        tmpl_expected = """<html>\n<body>\n\n<h1>My "First" Heading</h1>\n<p>My first paragraph.</p>\n\n</body></html>"""
        t = Template(tmpl_sts_raw, autoescape=escape)
        pprint(t.namespace)
        self.assertEqual(t.generate(title='My "First" Heading'), tmpl_expected)



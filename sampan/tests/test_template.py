#!/usr/bin/env python
# coding: utf-8

from unittest import TestCase
from ..templateNG import Template, _StatementIf
from ..template import Template as T2
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

    def test_sts_if_end(self):
        sts_if = """<html>\n<body>\n\n{% if h1 == True %} <h1>My First Heading</h1> {% end %}\n<p>My first paragraph.</p>\n\n</body></html>"""
        expected_h1_true = """<html>\n<body>\n\n <h1>My First Heading</h1> \n<p>My first paragraph.</p>\n\n</body></html>"""
        expected_h1_false = """<html>\n<body>\n\n\n<p>My first paragraph.</p>\n\n</body></html>"""
        t = Template(sts_if)
        self.assertEqual(t.generate(h1=True), expected_h1_true)
        self.assertEqual(t.generate(h1=False), expected_h1_false)

    def test_sts_if_else_end(self):
        sts_if = """<html>\n<body>\n\n{% if h1 == True %} <h1>First Heading</h1> {% else %} <h2>Second Heading</h2> {% end %}\n<p>My first paragraph.</p>\n\n</body></html>"""
        expected_h1_true = """<html>\n<body>\n\n <h1>First Heading</h1> \n<p>My first paragraph.</p>\n\n</body></html>"""
        expected_h1_false = """<html>\n<body>\n\n <h2>Second Heading</h2> \n<p>My first paragraph.</p>\n\n</body></html>"""
        print(_StatementIf.regex.pattern)
        t = Template(sts_if)
        self.assertEqual(t.generate(h1=True), expected_h1_true)
        self.assertEqual(t.generate(h1=False), expected_h1_false)

    def test_sts_if_elif_else_end(self):
        sts_if = """<html>\n<body>\n\n{% if h == 1 %} <h1>First Heading</h1> {% elif h == 2 %} <h2>Second Heading</h2> {% else %} <h3>Third Heading</h3> {% end %}\n<p>My first paragraph.</p>\n\n</body></html>"""
        expected_h_1 = """<html>\n<body>\n\n <h1>First Heading</h1> \n<p>My first paragraph.</p>\n\n</body></html>"""
        expected_h_2 = """<html>\n<body>\n\n <h2>Second Heading</h2> \n<p>My first paragraph.</p>\n\n</body></html>"""
        expected_h_3 = """<html>\n<body>\n\n <h3>Third Heading</h3> \n<p>My first paragraph.</p>\n\n</body></html>"""
        t = Template(sts_if)
        self.assertEqual(t.generate(h=1), expected_h_1)
        self.assertEqual(t.generate(h=2), expected_h_2)
        self.assertEqual(t.generate(h=3), expected_h_3)

    def test_sts_for(self):
        sts_for = """<html>\n<body>\n<ul>{% for student in students %}\n<li>{{ student }}</li>{% end %}\n</ul>\n</body>\n</html>"""
        expected = """<html>\n<body>\n<ul>\n<li>toto</li>\n<li>haha</li>\n</ul>\n</body>\n</html>"""
        t = Template(sts_for)
        self.assertEqual(t.generate(students=('toto', 'haha')), expected)

    def test_sts_while(self):
        sts_while = """<html>\n<body>\n{% set a = 1 %}<ul>{% while a < 3 %} \n<li>{{ student + str(a) }}{% set a += 1 %}</li>{% end %}\n</ul>\n</body>\n</html>"""
        expected = """<html>\n<body>\n<ul> \n<li>toto1</li> \n<li>toto2</li>\n</ul>\n</body>\n</html>"""
        t = Template(sts_while)
        self.assertEqual(t.generate(student='toto'), expected)

    def test_sts_for_break(self):
        sts_for = """<html>\n<body>\n<ul>{% for student in students %}\n<li>{{ student }}</li>{% break %}{% end %}\n</ul>\n</body>\n</html>"""
        t = Template(sts_for)
        print(t.generate(students=('toto', 'haha')))


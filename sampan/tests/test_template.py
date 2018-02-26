#!/usr/bin/env python
# coding: utf-8

from unittest import TestCase
from .. import templateNG


tmpl_text = """<!DOCTYPE html>
<html>
<body>

<h1>My First Heading</h1>

<p>My first paragraph.</p>

</body>
</html>"""

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
        t = templateNG.Template(tmpl_text)
        print(t.generate())


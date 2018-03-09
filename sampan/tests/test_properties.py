#!/usr/bin/env python
# coding: utf-8

import os
import pathlib
from pprint import pprint
import re
import sys
from io import StringIO
from unittest import TestCase
from tempfile import NamedTemporaryFile
from sampan.properties import Properties


class TestProperties(TestCase):

    def test_property_node_update(self):
        s = "key = value"
        props = Properties()
        props.load(StringIO(s))
        props["key"] = "another_value"
        print(str(props))
        self.assertTrue(str(props) == "{key=another_value}")

    def test_iterable_properties(self):
        d = dict([("a", "b"), ("c", "d"), ("e", "f")])
        props = Properties(d)
        self.assertEqual([key for key in props], list(d.keys()))

    def test_len(self):
        items = [("a", "b"), ("c", "d"), ("e", "f")]
        d = dict(items)
        props = Properties(d)
        self.assertEqual(len(props), 3)

    def test_empty_len(self):
        props = Properties()
        self.assertEqual(len(props), 0)
        d = dict()
        props = Properties(d)
        self.assertEqual(len(props), 0)

    def test_equals(self):
        items = [("a", "b"), ("c", "d"), ("e", "f")]
        props = Properties(dict(items))
        props2 = Properties(dict(items))
        self.assertTrue(props == props2)

    def test_not_equals(self):
        self.assertTrue(Properties(dict([("a", "b"), ("c", "d"), ("e", "f")]))
                        != Properties(dict([("c", "d"), ("e", "f")])))

    def test_update(self):
        d = dict([("a", "b"), ("c", "d"), ("e", "f")])
        props = Properties(d)
        props.update({"g": "h", "c": "i"})
        self.assertTrue(props == Properties(dict([("a", "b"), ("c", "i"), ("e", "f"), ("g", "h")])))

    def test_delete(self):
        d = dict([("a", "b"), ("c", "d"), ("e", "f")])
        props = Properties(d)
        del props["a"]
        self.assertTrue("a" not in props)
        self.assertTrue(props == Properties(dict([("c", "d"), ("e", "f")])))

    def test_str(self):
        d = dict([("a", "b"), ("c", "d"), ("e", "f")])
        props = Properties(d)
        props2 = Properties()
        props2.load(StringIO('\n'.join([f'{k}={v}' for k, v in props._props.items()])))
        self.assertEqual(props, props2)

    def test_store(self):
        properties = """foo : bar\nbar : baz\n"""
        p = Properties()
        p2 = Properties()
        p.load(StringIO(properties))
        with NamedTemporaryFile(delete=False, mode='w') as f:
            p.store(f)
        with open(f.name) as f:
            p2.load(f)
        self.assertEqual(p, p2)

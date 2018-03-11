#!/usr/bin/env python
# coding: utf-8

import os
import pathlib
from io import StringIO
from unittest import TestCase
from sampan.toto import get_samples


class TestToto(TestCase):
    TEST_CSV_FILE = os.path.join(str(pathlib.Path(__file__).parent), 'resources', 'test.csv')

    def test_get_samples(self):
        get_samples(self.TEST_CSV_FILE)

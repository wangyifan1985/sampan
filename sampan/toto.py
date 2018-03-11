#!/usr/bin/env python3

import fileinput
import subprocess
import time
import os
import pathlib
import csv
from .properties import Properties

def check_java_home(filename, java_home):
    with fileinput.FileInput(filename, inplace=True, backup='.bak') as file:
        for line in file:
            if line.startswith('JAVA_HOME=') and line.strip() != f'JAVA_HOME={java_home}':
                print(line.replace('JAVA_HOME=', f'JAVA_HOME={java_home}'), end='')
                break


def exec_command(*args):
    p = subprocess.Popen(' '.join(args),
                         stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE,
                         shell=True)
    # Read stdout from subprocess until the buffer is empty !
    for line in iter(p.stdout.readline, b''):
        if line: # Don't print blank lines
            yield line
    # This ensures the process has completed, AND sets the 'returncode' attr
    while p.poll() is None:
        time.sleep(.1) #Don't waste CPU-cycles
    # Empty STDERR buffer
    err = p.stderr.read()
    if p.returncode != 0:
        # The run_command() function is responsible for logging STDERR
        print("Error: " + str(err))

#for line in exec_command(cmd):
#    print(line)

def create_properties_file(filename, props, **kwargs):
    props = Properties(props)
    for k, v in kwargs:
        props.setProperty(k, v)
    with open(filename, mode='w') as f:
        props.store(f)


def get_samples(filename):
    with open(filename, newline='') as f:
        return csv.reader(f)


    


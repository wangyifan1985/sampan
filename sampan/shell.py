#!/usr/bin/env python
# coding: utf-8

import paramiko
import subprocess


__description__ = 'A universal shell client'

class BaseShell:
    def run(self, cmd: str) -> str:
        raise NotImplementedError


class SSHShell:
    def __init__(self, host, user, pwd):
        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self._client.connect(hostname=host, username=user, password=pwd)

    def close(self):
        self._client.close()

    def run(self, cmd):
        stdin, stdout, stderr = self._client.exec_command(cmd)
        return ''.join(stdout.readlines())


class LocalShell:
    def __init__(self):
        self._call = subprocess.call

    def run(self, cmd):
        return self._call(cmd, shell=True)


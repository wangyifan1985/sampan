#!/usr/bin/env python
# coding: utf-8


import base64
import ssl
import os
import mimetypes
from urllib import parse
from http import client


__all__ = ['BasicAuthentication', 'RestClient']


class BasicAuthentication:
    BASIC_AUTH_KEY = 'Authorization'
    BASIC_AUTH_VALUE_PREFIX = 'Basic '

    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.value = None
        self.reset(username, password)

    def reset(self, username, password):
        _auth_value = base64.encodebytes('{}:{}'.format(username, password).strip())
        self.value = '{}{}'.format(BasicAuthentication.BASIC_AUTH_VALUE_PREFIX, _auth_value)

    def get_key(self):
        return BasicAuthentication.BASIC_AUTH_KEY

    def get_value(self):
        return self.value

    def __repr__(self):
        return self.value


class RestClient:
    REQUEST_TIMEOUT = 30

    def __init__(self, base_url):
        mimetypes.add_type('application/json', '.json')
        self.base_url = base_url
        self.pr = parse.urlparse(self.base_url)
        self.headers = {'User-Agent': 'Basic Agent'}

        if self.pr.scheme == 'http':
            self.con = client.HTTPConnection(self.pr.netloc, timeout=self.REQUEST_TIMEOUT)
        else:
            self.con = client.HTTPSConnection(self.pr.netloc, timeout=self.REQUEST_TIMEOUT, context=ssl._create_unverified_context())

    def set_basic_authentication(self, basic_auth):
        self.headers[basic_auth.get_key()] = basic_auth.get_value()

    def disconnect(self):
        if self.con:
            self.con.close()

    def reset_headers(self):
        self.headers.clear()
        self.headers = {'User-Agent': 'Basic Agent'}

    def add_header(self, key, value):
        self.headers[key] = value

    def remove_header(self, key):
        if key in self.headers:
            del self.headers[key]

    def update_headers(self, _headers):
            self.headers.update(_headers)

    def add_accepts(self, accept=None):
        if accept is None:
            accept = []
        if accept:
            self.headers['Accept'] = ','.join(accept)
        else:
            self.headers['Accept'] = '*/*'

    def _get_content_type(self, filename):
        return mimetypes.guess_type(filename)[0] or 'application/octet-stream'

    def _get_full_url(self, path, args):
        if args:
            path += '?' + parse.urlencode(args)
        return parse.urljoin(self.pr.path if self.pr.path.endswith('/') else '{}/'.format(self.pr.path),
                             path[1:] if path.startswith('/') else path)

    '''def _get_files_list(self, files):
        _files = []
        _name = 'file' if len(files) == 1 else 'files[]'
        for _file in files:
            _filename = os.path.basename(_file)
            with open(_file, 'rb') as f:
                _file_value = f.read()
            _files.append((_name, _filename, _file_value))
        return _files'''

    def _get_files_list(self, body, files):
        _files = []
        if body:
            _name = 'file'
        else:
            _name = 'files[]'
        for _file in files:
            _filename = os.path.basename(_file)
            with open(_file, 'rb') as f:
                _file_value = f.read()
            _files.append((_name, _filename, _file_value))
        return _files

    def encode_multipart_formdata(self, fields, files):
        BOUNDARY = 'Boundary_1_240630125_1477681764147'
        CRLF = '\r\n'
        chunks = []
        for (key, value) in fields:
            chunks.append('--' + BOUNDARY)
            chunks.append('Content-Disposition: form-data; name="{}"'.format(key))
            chunks.append('Content-Type: application/json')
            chunks.append('')
            chunks.append(str(value))
        for (key, filename, value) in files:
            chunks.append('--' + BOUNDARY)
            chunks.append('Content-Disposition: form-data; name="{}"; filename="{}"'.format(key, filename))
            chunks.append('Content-Type: {}'.format(self._get_content_type(filename)))
            chunks.append('')
            if filename.endswith('.pdf'):
                chunks.append(str(value.decode('ISO8859-1')))
            else:
                chunks.append(str(value.decode('utf8')))
        chunks.append('--' + BOUNDARY + '--')
        chunks.append('')
        chunks = [str(chunk) for chunk in chunks]
        body = CRLF.join(chunks)
        content_type = 'multipart/form-data; boundary={}'.format(BOUNDARY)
        return content_type, body

    def invoke_non_multipart(self, method, path, args=None, headers=None):
        _headers = headers if headers is not None else {}
        _path = self._get_full_url(path, args)
        _headers['Content-Length'] = '0'
        _headers['Content-Type'] = 'text/xml'
        _headers.update(self.headers)
        self.con.request(method=method.upper(), url=_path, body=None, headers=_headers)
        resp = self.con.getresponse()
        resp_map = {'status': resp.status, 'reason': resp.reason, 'headers': resp.getheaders(), 'body': resp.read()}
        return resp_map

    def invoke_multipart(self, method, path, args=None, headers=None, body=None, files=None):
        _headers = headers if headers is not None else {}
        _path = self._get_full_url(path, args)

        if body and files:
            _fields = [('payload', body)]
            _files = self._get_files_list(body, files)
            content_type, _body = self.encode_multipart_formdata(_fields, _files)
            _headers['Content-Length'] = str(len(_body))
            _headers['Content-Type'] = content_type
        elif files:
            _fields = []
            _files = self._get_files_list(body, files)
            content_type, _body = self.encode_multipart_formdata(_fields, _files)
            _headers['Content-Length'] = str(len(_body))
            _headers['Content-Type'] = content_type
        elif body:
            _body = body
            if not _headers.get('Content-Type', None):
                _headers['Content-Type'] = mimetypes.types_map['.json']
            _headers['Content-Length'] = str(len(body))
        else:
            _body = None
            _headers['Content-Type'] = 'text/xml'
            _headers['Content-Length'] = '0'
        _headers.update(self.headers)
        self.con.request(method=method.upper(), url=_path, body=_body, headers=_headers)
        resp = self.con.getresponse()
        resp_map = {'status': resp.status, 'reason': resp.reason, 'headers': resp.getheaders(), 'body': resp.read()}
        return resp_map

    def request_get(self, path, args=None, headers=None):
        return self.invoke_non_multipart(method='get', path=path, args=args, headers=headers)

    def request_delete(self, path, args=None, headers=None):
        return self.invoke_non_multipart(method='delete', path=path, args=args, headers=headers)

    def request_head(self, path, args=None, headers=None):
        return self.invoke_non_multipart(method='head', path=path, args=args, headers=headers)

    def request_post(self, path, args=None, headers=None,  body=None, files=None):
        return self.invoke_multipart(method='post', path=path, args=args,  headers=headers, body=body, files=files)

    def request_put(self, path, args=None, headers=None,  body=None, files=None):
        return self.invoke_multipart(method='put', path=path, args=args, headers=headers, body=body, files=files)

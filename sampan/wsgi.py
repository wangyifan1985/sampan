#!/usr/bin/env python
# coding: utf-8

import os
import re
import socket
from io import BytesIO
from tempfile import TemporaryFile
from shutil import copyfileobj
from urllib.parse import urlparse, unquote_to_bytes


__all__ = [
    'RFC_822_DATETIME', 'WSGI_ENCODING', 'BUFFER_SIZE'
    'LF', 'CRLF', 'TAB', 'SPACE', 'COLON', 'SEMICOLON', 'EMPTY', 'NUMBER_SING', 'QUESTION_MARK', 'ASTERISK', 'FORWARD_SLASH', 'BACKSLASH',
    'ENC_LF', 'ENC_CRLF', 'ENC_TAB', 'ENC_SPACE', 'ENC_COLON', 'ENC_SEMICOLON', 'ENC_EMPTY', 'ENC_NUMBER_SING', 'ENC_QUESTION_MARK', 'ENC_ASTERISK', 'ENC_FORWARD_SLASH', 'ENC_BACKSLASH',
    'HTTP_STATUS',
    'WSGIError', 'BadRequest', 'RequestEntityTooLarge', 'RequestHeaderFieldsTooLarge', 'InternalServerError',


]

WSGI_ENCODING = 'ISO-8859-1'
BUFFER_SIZE = 8192
RFC_822_DATETIME = '%a, %d %b %Y %H:%M:%S GMT'

HTTP_STATUS = {
    # 1xx Informational
    100: '100 Continue',
    101: '101 Switching Protocols',
    102: '102 Processing',

    # 2xx Success
    200: '200 OK',
    201: '201 Created',
    202: '202 Accepted',
    203: '203 Non-Authoritative Information',
    204: '204 No Content',
    205: '205 Reset Content',
    206: '206 Partial Content',
    207: '207 Multi-Status',
    208: '208 Already Reported',
    226: '226 IM Used',

    # 3xx Redirection
    300: '300 Multiple Choices',
    301: '301 Moved Permanently',
    302: '302 Found',
    303: '303 See Other',
    304: '304 Not Modified',
    305: '305 Use Proxy',
    307: '307 Temporary Redirect',
    308: '308 Permanent Redirect',

    # 4xx Client Error
    400: '400 Bad Request',
    401: '401 Unauthorized',
    402: '402 Payment Required',
    403: '403 Forbidden',
    404: '404 Not Found',
    405: '405 Method Not Allowed',
    406: '406 Not Acceptable',
    407: '407 Proxy Authentication Required',
    408: '408 Request Time-out',
    409: '409 Conflict',
    410: '410 Gone',
    411: '411 Length Required',
    412: '412 Precondition Failed',
    413: '413 Request Entity Too Large',
    414: '414 URI Too Long',
    415: '415 Unsupported Media Type',
    416: '416 Range Not Satisfiable',
    417: '417 Expectation Failed',
    418: "418 I'm a teapot",
    421: '421 Misdirected Request',
    422: '422 Unprocessable Entity',
    423: '423 Locked',
    424: '424 Failed Dependency',
    426: '426 Upgrade Required',
    428: '428 Precondition Required',
    429: '429 Too Many Requests',
    431: '431 Request Header Fields Too Large',
    451: '451 Unavailable For Legal Reasons',

    # 5xx Server Error
    500: '500 Internal Server Error',
    501: '501 Not Implemented',
    502: '502 Bad Gateway',
    503: '503 Service Unavailable',
    504: '504 Gateway Time-out',
    505: '505 HTTP Version not supported',
    506: '506 Variant Also Negotiates',
    507: '507 Insufficient Storage',
    508: '508 Loop Detected',
    510: '510 Not Extended',
    511: '511 Network Authentication Required'
}

LF = '\n'
CRLF = '\r\n'
TAB = '\t'
SPACE = ' '
COLON = ':'
SEMICOLON = ';'
EMPTY = ''
SHARP = '#'
QUESTION = '?'
ASTERISK = '*'
SLASH = '/'
BACKSLASH = '\\'
UNDERSCORE = '_'
HYPHEN = '-'

ENC_LF = LF.encode(WSGI_ENCODING)
ENC_CRLF = CRLF.encode(WSGI_ENCODING)
ENC_TAB = TAB.encode(WSGI_ENCODING)
ENC_SPACE = SPACE.encode(WSGI_ENCODING)
ENC_COLON = COLON.encode(WSGI_ENCODING)
ENC_SEMICOLON = SEMICOLON.encode(WSGI_ENCODING)
ENC_EMPTY = EMPTY.encode(WSGI_ENCODING)
ENC_SHARP = SHARP.encode(WSGI_ENCODING)
ENC_QUESTION = QUESTION.encode(WSGI_ENCODING)
ENC_ASTERISK = ASTERISK.encode(WSGI_ENCODING)
ENC_SLASH = SLASH.encode(WSGI_ENCODING)
ENC_BACKSLASH = BACKSLASH.encode(WSGI_ENCODING)
ENC_UNDERSCORE = UNDERSCORE.encode(WSGI_ENCODING)
ENC_HYPHEN = HYPHEN.encode(WSGI_ENCODING)



# Fix for issue reported in https://bugs.python.org/issue6926,
# Python on Windows may not define IPPROTO_IPV6 in socket.
if socket.has_ipv6:
    if not hasattr(socket, 'IPPROTO_IPV6'):
        setattr(socket, 'IPPROTO_IPV6', 41)
    if not hasattr(socket, 'IPV6_V6ONLY'):
        setattr(socket, 'IPV6_V6ONLY', 27)


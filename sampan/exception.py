#!/usr/bin/env python
# coding: utf-8


from .wsgi import HTTP_STATUS


class SampanError(Exception):
    pass

class JSONError(SampanError):
    pass


class TemplateError(SampanError):
    """Raised for template syntax errors.
        ``TemplateError`` instances have ``filename`` and ``lineno`` attributes
        indicating the position of the error.
        .. versionchanged:: 4.3
           Added ``filename`` and ``lineno`` attributes.
        """

    def __init__(self, message, filename=None, lineno=0):
        self.message = message
        # The names "filename" and "lineno" are chosen for consistency
        # with python SyntaxError.
        self.filename = filename
        self.lineno = lineno

    def __str__(self):
        return '%s at %s:%d' % (self.message, self.filename, self.lineno)


class WSGIError(SampanError):
    pass


class BadRequest(WSGIError):
    status = HTTP_STATUS[400]


class RequestEntityTooLarge(WSGIError):
    status = HTTP_STATUS[413]


class RequestHeaderFieldsTooLarge(WSGIError):
    status = HTTP_STATUS[431]


class InternalServerError(WSGIError):
    status = HTTP_STATUS[500]


class ParsingError(WSGIError):
    pass
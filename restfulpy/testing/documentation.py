from os import makedirs
from os.path import join, exists, dirname, basename
from urllib.parse import quote
import warnings

from webtest import TestApp

from restfulpy.testing.constants import DOC_HEADER


class RequestSignature(object):
    def __init__(self, role, method, url, query_string=None):
        self.role = role
        self.method = method
        self.url = url
        self.query_string = query_string

    def __eq__(self, other):
        return self.__hash__() == other.__hash__()

    def __hash__(self):
        return hash((self.role, self.method, self.url, self.query_string))


class FormParameter(object):
    def __init__(self, name, value=None, type_=str, optional=False, default=None):
        self.name = name
        self.type_ = type_
        self.optional = optional
        self.value = value
        self.default = default

    @property
    def type_string(self):
        if self.type_ is None:
            return ''
        return self.type_ if isinstance(self.type_, str) else self.type_.__name__

    @property
    def value_string(self):
        if self.value is None:
            return ''

        if self.type_ == 'file':
            return basename(self.value)

        if self.type_ is bool:
            return str(self.value).lower()

        return self.value

    def __eq__(self, other):
        return self.__hash__() == other.__hash__()

    def __hash__(self):
        return hash(self.name)


class DocumentaryTestApp(TestApp):
    _files = []
    _signatures = set()
    _jwt_token = None
    __jwt_header_key__ = 'HTTP_X_JWT_TOKEN'

    def __init__(self, destination_dir, application, *args, **kwargs):
        self.application = application
        self.destination_dir = destination_dir
        super(DocumentaryTestApp, self).__init__(application.wsgi(), *args, **kwargs)

    @property
    def jwt_token(self):
        return self._jwt_token

    @jwt_token.setter
    def jwt_token(self, value):
        self._jwt_token = value

        if value is not None:
            self.extra_environ.update({
                self.__jwt_header_key__: value,
            })
        else:
            if self.__jwt_header_key__ in self.extra_environ:
                del self.extra_environ[self.__jwt_header_key__]

    def _ensure_file(self, filename, entity):
        if filename in self._files:
            return open(filename, 'a')
        else:
            d = dirname(filename)
            if not exists(d):
                makedirs(d)
            f = open(filename, 'w')
            f.write(DOC_HEADER % dict(version=self.application.version))
            f.write('\n%s' % entity)
            f.write('\n%s\n' % ('-' * len(entity)))
            self._files.append(filename)
            return f

    def document(self, role, method, url, resp, request_headers, model=None, params=None, query_string=None):
        signature = RequestSignature(role, method, url, tuple(query_string.keys()) if query_string else None)
        if signature in self._signatures:
            return
        path_parts = url.split('?')[0].split('/')[1:]
        if len(path_parts) == 1:
            p = path_parts[0].strip()
            entity = filename = p if p else 'index'
        else:
            version, entity = path_parts[0:2]
            filename = '_'.join(path_parts[:2] + [method.lower()])

        filename = join(self.destination_dir, '%s.md' % filename)
        f = self._ensure_file(filename, entity)

        # Extracting more params & info from model if available
        if params and model:
            for c in model.iter_json_columns(relationships=False, include_readonly_columns=False):
                json_name = c.info['json']
                column = model.get_column(c)

                if hasattr(column, 'default') and column.default:
                    default_ = column.default.arg if column.default.is_scalar else 'function(...)'
                else:
                    default_ = ''

                if 'attachment' in column.info:
                    type_ = 'attachment'
                else:
                    type_ = str if 'unreadable' in column.info and column.info['unreadable'] else \
                        column.type.python_type

                if json_name in params:
                    param = params[params.index(json_name)]
                    param.default = default_
                    if param.type_ is None:
                        param.type_ = type_
                    if param.optional is None:
                        param.optional = column.nullable
                else:
                    param = FormParameter(
                        json_name,
                        type_=type_,
                        optional=column.nullable,
                        default=default_)
                    params.append(param)

        try:
            f.write('\n- (%s) **%s** `%s`\n' % (role, method.upper(), url))
            if params:
                f.write('\n    - Form Parameters:\n\n')
                f.write('        | Parameter | Optional | Type | Default | Example |\n')
                f.write('        | --------- | -------- | ---- | ------- | ------- |\n')
                for param in params:
                    f.write('        | %s | %s | %s | %s | %s |\n' % (
                        param.name,
                        True if method.lower() == 'put' else param.optional,
                        param.type_string,
                        param.default if param.default is not None else '',
                        param.value_string))
            if query_string:
                f.write('\n    - Query String:\n\n')
                f.write('        | Parameter | Example |\n')
                f.write('        | --------- | ------- |\n')
                for name, value in query_string.items():
                    f.write('        | %s | %s |\n' % (
                        name,
                        str(value)))

            if request_headers:
                f.write('\n    - Request Headers:\n\n')
                for k, v in request_headers.items():
                    f.write('%s%s: %s\n' % (12 * ' ', k, v))

            f.write('\n    - Response Headers:\n\n')
            for k, v in resp.headers.items():
                f.write('%s%s: %s\n' % (12 * ' ', k, v))

            f.write('\n    - Response Body:\n\n')
            for l in resp.body.decode().splitlines():
                f.write('%s%s\n' % (12 * ' ', l))
            f.write('\n\n')
            self._signatures.add(signature)
        finally:
            f.write('\n')
            # f.write(DOC_LEGEND)
            # f.write('\n')
            f.close()

    def send_request(self, role, method, url, query_string=None, url_params=None,
                     params=None, model=None, doc=True, **kwargs):
        files = []
        parameters = {}
        if params:
            if isinstance(params, dict):
                parameters = params
                if doc:
                    warnings.warn('Skipping documentation generation, because the passed parameters are plain dict.')
                    doc = False
            else:
                for param in params:
                    if param.type_ == 'file':
                        files.append((param.name, param.value))
                    else:
                        parameters[param.name] = param.value

        if query_string:
            parameters.update(query_string)

        if files:
            kwargs['upload_files'] = files
        if parameters:
            kwargs['params'] = parameters

        real_url = (url % url_params) if url_params else url
        real_url = quote(real_url)
        kwargs['expect_errors'] = True
        resp = getattr(self, method.lower())(real_url, **kwargs)

        if doc:
            self.document(role, method, url, resp, kwargs.get('headers'), model=model, params=params, query_string=query_string)
        return resp

    def metadata(self, url, params='', headers=None, extra_environ=None,
                 status=None, upload_files=None, expect_errors=False,
                 content_type=None, xhr=False):
        if xhr:
            headers = self._add_xhr_header(headers)
        return self._gen_request('METADATA', url, params=params, headers=headers,
                                 extra_environ=extra_environ, status=status,
                                 upload_files=upload_files,
                                 expect_errors=expect_errors,
                                 content_type=content_type,
                                 )

    def undelete(self, url, params='', headers=None, extra_environ=None,
                 status=None, upload_files=None, expect_errors=False,
                 content_type=None, xhr=False):
        if xhr:
            headers = self._add_xhr_header(headers)
        return self._gen_request('UNDELETE', url, params=params, headers=headers,
                                 extra_environ=extra_environ, status=status,
                                 upload_files=upload_files,
                                 expect_errors=expect_errors,
                                 content_type=content_type,
                                 )

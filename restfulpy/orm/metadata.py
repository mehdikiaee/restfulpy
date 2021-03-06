

class MetadataField(object):
    def __init__(self, json_name, key, type_=str, default_=None, optional=None,
                 pattern=None, max_length=None, min_length=None, message='Invalid value',
                 watermark=None):
        self.json_name = json_name
        self.key = key[1:] if key.startswith('_') else key
        self.type_ = type_
        self.default_ = default_
        self.optional = optional
        self.pattern = pattern
        self.max_length = max_length
        self.min_length = min_length
        self.message = message
        self.watermark = watermark

    @property
    def type_name(self):
        return self.type_ if isinstance(self.type_, str) else self.type_.__name__

    def to_json(self):
        return dict(
            name=self.json_name,
            key=self.key,
            type_=self.type_name,
            default=self.default_,
            optional=self.optional,
            pattern=self.pattern,
            maxLength=self.max_length,
            minLength=self.min_length,
            message=self.message,
            watermark=self.watermark,
        )

    @classmethod
    def from_column(cls, c, info=None):
        if not info:
            info = c.info
        json_name = info['json']
        result = []

        if 'attachment' in info:
            result.append(cls(
                '%sUrl' % json_name,
                '%s_url' % c.key,
                type_='url',
                message=info.get('message') if 'message' in info else 'Invalid File'
            ))

            result.append(cls(
                '%sThumbnails' % json_name,
                '%s_thumbnails' % c.key,
                type_='dict',
                message=info.get('message') if 'message' in info else 'Invalid File'
            ))

        else:
            key = c.key

            if hasattr(c, 'default') and c.default:
                default_ = c.default.arg if c.default.is_scalar else 'function(...)'
            else:
                default_ = ''

            if 'unreadable' in info and info['unreadable']:
                type_ = 'str'
            elif hasattr(c, 'type'):
                type_ = c.type.python_type
            elif hasattr(c, 'target'):
                type_ = c.target.name
            else:
                raise AttributeError('Unable to recognize type of the column: %s' % c.name)

            result.append(cls(
                json_name,
                key,
                type_=type_,
                default_=default_,
                optional=c.nullable if hasattr(c, 'nullable') else None,
                pattern=info.get('pattern'),
                max_length=info.get('max_length') if 'max_length' in info else
                (c.type.length if hasattr(c, 'type') and hasattr(c.type, 'length') else None),
                min_length=info.get('min_length'),
                message=info.get('message') if 'message' in info else 'Invalid Value',
                watermark=info.get('watermark') if 'watermark' in info else None,
            ))

        return result
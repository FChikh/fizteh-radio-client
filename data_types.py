class LoginForm:
    def __init__(self, login: str = None, password: str = None):
        self._login = login
        self._password = password

    @property
    def login(self):
        return self._login

    @login.setter
    def login(self, value):
        self._login = value

    @property
    def password(self):
        return self._password

    @password.setter
    def password(self, value):
        self._password = value

    def to_dict(self):
        return {"login": self._login, "password": self._password}

    @classmethod
    def from_dict(cls, data):
        return cls(**data)

    def __repr__(self):
        return str(self.to_dict())


class TagType:
    def __init__(self, id: int = None, name: str = None):
        self._id = id
        self._name = name

    @property
    def id(self):
        return self._id

    @id.setter
    def id(self, value):
        self._id = value

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        self._name = value

    def to_dict(self):
        return {"id": self._id, "name": self._name}

    @classmethod
    def from_dict(cls, data):
        return cls(**data)

    def __repr__(self):
        return str(self.to_dict())


class TagTypes:
    def __init__(self, tag_types: list = None):
        self._tag_types = [TagType.from_dict(
            tag_type) for tag_type in tag_types] if tag_types else []

    @property
    def tag_types(self):
        return self._tag_types

    @tag_types.setter
    def tag_types(self, value):
        self._tag_types = [TagType.from_dict(tag_type) for tag_type in value]

    def to_dict(self):
        return {"tag_types": [tag_type.to_dict() for tag_type in self._tag_types]}

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, list):
            raise ValueError("data must be a list of tag type dictionaries")
        tag_types = []
        for item in data:
            if not isinstance(item, dict):
                raise ValueError(
                    "data must be a list of tag type dictionaries")
            tag_types.append(TagType.from_dict(item))
        return cls(**data)

    def __repr__(self):
        return str(self.to_dict())


class Tag:
    def __init__(self, id: int = None, name: str = None, type: TagType = None, meta: dict = None):
        self._id = id
        self._name = name
        self._type = type if isinstance(
            type, TagType) else TagType.from_dict(type) if type else None
        self._meta = meta

    @property
    def id(self):
        return self._id

    @id.setter
    def id(self, value):
        self._id = value

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        self._name = value

    @property
    def type(self):
        return self._type

    @type.setter
    def type(self, value):
        self._type = value if isinstance(
            value, TagType) else TagType.from_dict(value)

    @property
    def meta(self):
        return self._meta

    @meta.setter
    def meta(self, value):
        self._meta = value

    def to_dict(self):
        return {"id": self._id, "name": self._name, "type": self._type.to_dict(), "meta": self._meta}

    @classmethod
    def from_dict(cls, data):
        return cls(**data)

    def __repr__(self):
        return str(self.to_dict())


class TagList:
    def __init__(self, tags: list = None):
        self._tags = [Tag.from_dict(tag) for tag in tags] if tags else []

    @property
    def tags(self):
        return self._tags

    @tags.setter
    def tags(self, value):
        self._tags = [Tag.from_dict(tag) for tag in value]

    def to_dict(self):
        return [tag.to_dict() for tag in self._tags]

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, list):
            raise ValueError("data must be a list of tag dictionaries")
        return cls(tags=data)

    def __repr__(self):
        return str(self.to_dict())


class MediaRegister:
    def __init__(self, id: int = None, name: str = None, author: str = None, tags: TagList = None):
        self._id = id
        self._name = name
        self._author = author
        self._tags = tags if isinstance(
            tags, TagList) else TagList.from_dict(tags) if tags else None

    @property
    def id(self):
        return self._id

    @id.setter
    def id(self, value):
        self._id = value

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        self._name = value

    @property
    def author(self):
        return self._author

    @author.setter
    def author(self, value):
        self._author = value

    @property
    def tags(self):
        return self._tags

    @tags.setter
    def tags(self, value):
        self._tags = value if isinstance(
            value, TagList) else TagList.from_dict(value)

    def to_dict(self):
        return {
            "id": self._id,
            "name": self._name,
            "author": self._author,
            "tags": self._tags.to_dict() if self._tags else None
        }

    @classmethod
    def from_dict(cls, data):
        return cls(**data)

    def __repr__(self):
        return str(self.to_dict())


class Media:
    def __init__(self, id: int = None, name: str = None, author: str = None, duration: int = None, tags: TagList = None):
        self._id = id
        self._name = name
        self._author = author
        self._duration = duration
        self._tags = tags

    @property
    def id(self):
        return self._id

    @id.setter
    def id(self, value):
        self._id = value

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        self._name = value

    @property
    def author(self):
        return self._author

    @author.setter
    def author(self, value):
        self._author = value

    @property
    def duration(self):
        return self._duration

    @duration.setter
    def duration(self, value):
        self._duration = value

    @property
    def tags(self):
        return self._tags

    @tags.setter
    def tags(self, value):
        self._tags = value

    def to_dict(self):
        if self._id is None:
            return {
                "name": self._name,
                "author": self._author,
                "tags": self._tags
            }
        return {
            "id": self._id,
            "name": self._name,
            "author": self._author,
            "duration": self._duration,
            "tags": self._tags
        }

    @classmethod
    def from_dict(cls, data):
        return cls(**data)

    def __repr__(self):
        return str(self.to_dict())


class MediaArray:
    def __init__(self, media_array: list = None):
        self._media_array = [Media.from_dict(
            media) for media in media_array] if media_array else []

    @property
    def media_array(self):
        return self._media_array

    @media_array.setter
    def media_array(self, value):
        self._media_array = [Media.from_dict(media) for media in value]

    def to_dict(self):
        return {"media_array": [media.to_dict() for media in self._media_array]}

    @classmethod
    def from_dict(cls, data):
        return cls(**data)

    def __repr__(self):
        return str(self.to_dict())


class Segment:
    def __init__(self, id: int = None, mediaID: int = None, start: int = None, beginCut: int = None, stopCut: int = None):
        self._id = id
        self._media_id = mediaID
        self._start = start
        self._beginCut = beginCut
        self._stopCut = stopCut

    @property
    def id(self):
        return self._id

    @id.setter
    def id(self, value):
        self._id = value

    @property
    def media_id(self):
        return self._media_id

    @media_id.setter
    def media_id(self, value):
        self._media_id = value

    @property
    def start(self):
        return self._start

    @start.setter
    def start(self, value):
        self._start = value

    @property
    def begin_cut(self):
        return self._beginCut

    @begin_cut.setter
    def beginCut(self, value):
        self._beginCut = value

    @property
    def stop_cut(self):
        return self._stopCut

    @stop_cut.setter
    def stopCut(self, value):
        self._stopCut = value

    def to_dict(self):
        if self._id is None:
            return {
                "mediaID": self._media_id,
                "start": self._start,
                "beginCut": self._beginCut,
                "stopCut": self._stopCut
            }
        return {
            "id": self._id,
            "mediaID": self._media_id,
            "start": self._start,
            "beginCut": self._beginCut,
            "stopCut": self._stopCut
        }

    @classmethod
    def from_dict(cls, data):
        return cls(**data)

    def __repr__(self):
        return str(self.to_dict())


class Segments:
    def __init__(self, segments: list = None):
        self._segments = [Segment.from_dict(
            segment) for segment in segments] if segments else []

    @property
    def segments(self):
        return self._segments

    @segments.setter
    def segments(self, value):
        self._segments = [Segment.from_dict(segment) for segment in value]

    def to_dict(self):
        return {"segments": [segment.to_dict() for segment in self._segments]}

    @classmethod
    def from_dict(cls, data):
        return cls(**data)

    def __repr__(self):
        return str(self.to_dict())
    
class Live:
    def __init__(self, id: int = None, name: str = None, start: int = None, stop: int = None, delay: int = None, offset: int = None):
        self._id = id
        self._name = name
        self._start = start
        self._stop = stop
        self._delay = delay
        self._offset = offset

    @property
    def id(self):
        return self._id

    @id.setter
    def id(self, value):
        self._id = value

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        self._name = value

    @property
    def start(self):
        return self._start

    @start.setter
    def start(self, value):
        self._start = value

    @property
    def stop(self):
        return self._stop

    @stop.setter
    def stop(self, value):
        self._stop = value

    @property
    def delay(self):
        return self._delay

    @delay.setter
    def delay(self, value):
        self._delay = value

    @property
    def offset(self):
        return self._offset

    @offset.setter
    def offset(self, value):
        self._offset = value

    def to_dict(self):
        if self._id is None:
            return {
                "name": self._name,
                "start": self._start,
                "stop": self._stop,
            }
        return {
            "id": self._id,
            "name": self._name,
            "start": self._start,
            "stop": self._stop,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(**data)

    def __repr__(self):
        return str(self.to_dict())
    


class AutoDJConfig:
    def __init__(self, Tags: TagList = None, Stub: dict = None):
        self._Tags = Tags if isinstance(
            Tags, TagList) else TagList.from_dict(Tags) if Tags else None
        self._Stub = Stub

    @property
    def Tags(self):
        return self._Tags

    @Tags.setter
    def Tags(self, value):
        self._Tags = value if isinstance(
            value, TagList) else TagList.from_dict(value)

    @property
    def Stub(self):
        return self._Stub

    @Stub.setter
    def Stub(self, value):
        self._Stub = value

    def to_dict(self):
        return {
            "Tags": self._Tags.to_dict() if self._Tags else None,
            "Stub": self._Stub
        }

    @classmethod
    def from_dict(cls, data):
        return cls(**data)

    def __repr__(self):
        return str(self.to_dict())

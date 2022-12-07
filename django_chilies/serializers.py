from django.db.models import QuerySet
from rest_framework import serializers, fields
from rest_framework.fields import TimeField as SerializerTimeField

from .utils import time_to_current_timezone, time_from_current_timezone


class BlankableDatetimeField(serializers.DateTimeField):

    def __init__(self, allow_blank=True, *args, **kwargs):
        self._allow_blank = allow_blank
        super().__init__(*args, **kwargs)

    def to_internal_value(self, data):
        if self._allow_blank:
            if data == '':
                return self.default if self.default is not fields.empty else None
        return super().to_internal_value(data)


class BlankableIntegerField(serializers.IntegerField):

    def __init__(self, allow_blank=True, *args, **kwargs):
        self._allow_blank = allow_blank
        super().__init__(*args, **kwargs)

    def to_internal_value(self, data):
        if self._allow_blank:
            if data == '':
                return self.default if self.default is not fields.empty else None
        return super().to_internal_value(data)


class BlankableFloatField(serializers.FloatField):

    def __init__(self, allow_blank=True, *args, **kwargs):
        self._allow_blank = allow_blank
        super().__init__(*args, **kwargs)

    def to_internal_value(self, data):
        if self._allow_blank:
            if data == '':
                return self.default if self.default is not fields.empty else None
        return super().to_internal_value(data)


class CharacterSeparatedField(serializers.Field):
    def __init__(self, *args, **kwargs):
        self.separator = kwargs.pop('separator', ',')
        super(CharacterSeparatedField, self).__init__(*args, **kwargs)

    def to_representation(self, value):
        if not value:
            return []
        return value.split(self.separator)

    def to_internal_value(self, data):
        return self.separator.join(data)


class EnumDisplayField(serializers.SerializerMethodField):
    """
    For django model field with enum-choices
    """

    def __init__(self, name=None, f=None, **kwargs):
        self.f_name = name or f.field_name
        super().__init__(**kwargs)

    def to_representation(self, value):
        return getattr(value, 'get_%s_display' % self.f_name)()

    def to_internal_value(self, data):
        return None


class CustomValidators(object):

    @staticmethod
    def unique_list(value, target=None):
        if target:
            value = [target(x) for x in value]

        if len(set(value)) != len(value):
            raise serializers.ValidationError(
                'This field must be a list contains unique elements.')


class PaginationListSerializer(serializers.ListSerializer):
    def __init__(self, total, data, *args, **kwargs):
        self.__total = total
        if isinstance(data, QuerySet):
            self.__data = None
            super(self.__class__, self).__init__(data, *args, **kwargs)
        else:
            self.__data = data
            kwargs['child'] = kwargs.get('child', serializers.Field())
            super(self.__class__, self).__init__(*args, **kwargs)

    @property
    def data(self):
        return {'total': self.__total, 'rows': self.__data or super().data}


class ModelPaginationSerializer(serializers.ModelSerializer):
    def __init__(self, queryset=None, offset=None, limit=None, *args, **kwargs):
        self.Meta.list_serializer_class = PaginationListSerializer
        super().__init__(queryset, *args, **kwargs)

    def __new__(cls, queryset, *args, **kwargs):
        offset = kwargs.pop('offset', None)
        limit = kwargs.pop('limit', None)
        if limit is not None:
            if limit:
                total = queryset.count()
                queryset = queryset[offset: offset + limit]
            else:
                total = None
            return cls.many_init(total, queryset, *args, **kwargs)
        return super().__new__(cls, queryset, *args, **kwargs)


class ModelPaginationSerializerWithoutCount(serializers.ModelSerializer):
    def __init__(self, queryset=None, offset=None, limit=None, *args, **kwargs):
        self.Meta.list_serializer_class = PaginationListSerializer
        super().__init__(queryset, *args, **kwargs)

    def __new__(cls, queryset, *args, **kwargs):
        offset = kwargs.pop('offset', None)
        limit = kwargs.pop('limit', None)
        if limit is not None:
            if limit:
                queryset = queryset[offset: offset + limit]
            total = None
            return cls.many_init(total, queryset, *args, **kwargs)
        return super().__new__(cls, queryset, *args, **kwargs)


class ModelLessPaginationSerializer(serializers.Serializer):
    total = serializers.IntegerField(required=False)
    rows = serializers.ListField(required=False, default=[])


class SerializerTimeFieldWithZone(SerializerTimeField):
    """
    开启了USE_TZ，且TIME_ZONE = 'Asia/Shanghai'之后
    datetime.datetime的行为
    数据库.                  Django.                 drf.serializer返回
    2022-11-29 17:00:00 <-> 2022-11-29 17:00:00 <-> 2022-11-30 01:00:00
    原本datetime.time的行为
    17:00       <->         17:00       <->         17:00
    封装之后，现在datetime.time的行为
    17:00       <->         17:00       <->         01:00
    """
    def to_representation(self, value):
        if value is None:
            return None
        value = time_to_current_timezone(value)
        return super().to_representation(value)

    def to_internal_value(self, value):
        value = super().to_internal_value(value)
        if value is None:
            return value
        return time_from_current_timezone(value)

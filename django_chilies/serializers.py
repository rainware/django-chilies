from rest_framework import serializers, fields
from rest_framework.fields import TimeField as SerializerTimeField
from rest_framework.relations import RelatedField

from django.contrib.contenttypes.fields import GenericRelation, GenericForeignKey
from django.db import models
from django.db.models import QuerySet, ManyToManyField, DateTimeField, TimeField

# django版本兼容

if hasattr(models, 'ForeignObjectRel'):
    from django.db.models import ForeignObjectRel
else:
    ForeignObjectRel = type('ForeignObjectRel', (object,), {})
from django.db.models.fields.related import RelatedField

from .utils import time_to_current_timezone, time_from_current_timezone
from .settings import DATETIME_FORMAT, TIME_FORMAT


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


class Validators(object):

    @staticmethod
    def unique_list(value, target=None):
        if target:
            value = [target(x) for x in value]

        if len(set(value)) != len(value):
            raise serializers.ValidationError(
                'This field must be a list contains unique elements.')


class PaginationListSerializer(serializers.ListSerializer):
    def __init__(self, total, rows, *args, **kwargs):
        self.__total = total
        if isinstance(rows, QuerySet):
            self.__data = None
            super(self.__class__, self).__init__(rows, *args, **kwargs)
        else:
            self.__data = rows
            kwargs['child'] = kwargs.get('child', serializers.Field())
            super(self.__class__, self).__init__(*args, **kwargs)

    @property
    def data(self):
        return {'total': self.__total, 'rows': self.__data or super().data}


class ModelPaginationSerializer(serializers.ModelSerializer):
    def __init__(self, queryset=None, offset=None, limit=None, *args, **kwargs):
        self.Meta.list_serializer_class = PaginationListSerializer
        super().__init__(queryset, *args, **kwargs)
        if isinstance(offset, QuerySet):
            # 此时queryset是total，offset才是queryset
            total, queryset = queryset, offset
            for k, v in kwargs.get('context', {}).items():
                if callable(v):
                    kwargs['context'][k] = v(queryset, total)

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


class GenericModelSerializer(serializers.BaseSerializer):

    def to_representation(self, instance):
        slr_class = model_serializer_class(instance._meta.model)
        return slr_class(instance).data


def model_serializer_class(model_cls, include=None, related=None, extra=None, exclude=None,
                           include_sensitive=None,
                           include_display_fields=True, include_delete_fields=False, paging=False, count=True):
    """
    :param model_cls:
    :param include: list, 包含的字段
    :param related: dict, {field_name: serializer.Serializer()}, for ForeignKey/OneToOne/ManyToMany fields
    :param extra: dict, {field_name: serializer.SerializerMethodField()}, 非model字段
    :param exclude: list, 例外的字段
    :param include_sensitive: list, 包含的敏感字段，如果不设置，默认不返回敏感字段
    :param include_display_fields: bool, 是否display choice fields
    :param include_delete_fields: bool, 是否包含假删除字段
    :param paging: bool, 是否分页
    :param count: bool, paging为true时，是否计算总数。如果不计算，则返回的total值为None
    :return:
    """
    from .models.compositefk.fields import CompositeForeignKey

    parent_slr = serializers.ModelSerializer
    if paging:
        if not count:
            parent_slr = ModelPaginationSerializerWithoutCount
        else:
            parent_slr = ModelPaginationSerializer

    class SLR(parent_slr):

        def __init__(self, *args, **kwargs):
            _fields = kwargs.pop('fields', None)
            super().__init__(*args, **kwargs)

            if _fields is not None:
                # Drop any fields that are not specified in the `fields` argument.
                allowed = set(_fields)
                existing = set(self.fields)
                for field_name in existing - allowed:
                    self.fields.pop(field_name)

        class Meta:
            model = model_cls

    fs = []
    for f in model_cls._meta.get_fields():
        if exclude and f.name in exclude:
            continue
        if include and f.name not in include:
            continue
        sensitive_fields = getattr(model_cls, 'sensitive_fields', None)
        if sensitive_fields:
            if (f.name in sensitive_fields) and (f.name not in (include_sensitive or [])):
                continue

        # fields for fake delete
        if not include_delete_fields and f.name in ('deleted', 'deleter', 'delete_time'):
            continue

        # if isinstance(f, (GenericForeignKey, )):
        #     setattr(SLR, f.name, GenericForeignKeySerializer())
        #     SLR._declared_fields[f.name] = getattr(SLR, f.name)
        #     fs.append(f.name)
        #     continue

        # relations
        if isinstance(f, (RelatedField, ForeignObjectRel, CompositeForeignKey, GenericForeignKey)):
            if related and f.name in related:
                setattr(SLR, f.name, related[f.name])
                SLR._declared_fields[f.name] = related[f.name]
            else:
                if isinstance(f, (
                        ForeignObjectRel, ManyToManyField, CompositeForeignKey, GenericRelation, GenericForeignKey)):
                    # many to many relations & reverse relations ignored by default
                    continue
                else:
                    setattr(SLR, f.name, serializers.PrimaryKeyRelatedField(read_only=True))
                    SLR._declared_fields[f.name] = getattr(SLR, f.name)
        fs.append(f.name)

        # 日期field
        if isinstance(f, DateTimeField):
            setattr(SLR, f.name, serializers.DateTimeField(format=DATETIME_FORMAT))
            SLR._declared_fields[f.name] = getattr(SLR, f.name)

        if isinstance(f, TimeField):
            setattr(SLR, f.name, SerializerTimeFieldWithZone(format=TIME_FORMAT))
            SLR._declared_fields[f.name] = getattr(SLR, f.name)

        # choice field
        f_display = None
        if getattr(f, 'choices', None) and include_display_fields:
            f_display = '%s_display' % f.name
        if f_display and not ((exclude and f_display in exclude) or (include and f_display not in include)):
            setattr(SLR, f_display, serializers.CharField(source='get_%s' % f_display))
            SLR._declared_fields[f_display] = getattr(SLR, f_display)
            fs.append(f_display)

    if extra:
        for fname, get_func in extra.items():
            setattr(SLR, fname, serializers.SerializerMethodField())
            setattr(SLR, 'get_%s' % fname, get_func)
            SLR._declared_fields[fname] = getattr(SLR, fname)
            fs.append(fname)

    SLR.Meta.fields = fs

    return SLR

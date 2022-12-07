from collections import Counter
from operator import attrgetter

from compositefk.fields import CompositeForeignKey
from django.contrib.contenttypes.fields import GenericRelation
from django.db import models, transaction, router
from django.db.models import QuerySet, sql, signals, ForeignObjectRel, ManyToManyField, DateTimeField, TimeField, \
    ProtectedError, Func
from django.db.models.deletion import Collector
from django.db.models.fields.related import RelatedField
from django.utils import timezone
from rest_framework import serializers

from . import errors
from .serializers import ModelPaginationSerializer, ModelPaginationSerializerWithoutCount, \
    SerializerTimeFieldWithZone
from .consts import DATETIME_FORMAT, TIME_FORMAT
from .utils import time_to_current_timezone, time_from_current_timezone


def get_or_none(model_cls, kwargs, raise_error=False):
    try:
        return model_cls.objects.get(**kwargs)
    except (model_cls.DoesNotExist, errors.ResourceNotExist):
        if raise_error:
            raise errors.ResourceNotExist(model_cls._meta.object_name)
        else:
            return None


class CustomQuerySet(QuerySet):

    def get(self, *args, **kwargs):
        try:
            if 'pk' in kwargs and kwargs['pk'] is None:
                return None
            return super(CustomQuerySet, self).get(*args, **kwargs)
        except self.model.DoesNotExist:
            raise errors.ResourceNotExist('%s: %s,%s' % (self.model._meta.object_name,
                                                         args, kwargs))

    def get_or_none(self, *args, **kwargs):
        try:
            return super(CustomQuerySet, self).get(*args, **kwargs)
        except self.model.DoesNotExist:
            return None

    def delete(self, deleter=''):
        """Delete the records in the current QuerySet."""
        assert self.query.can_filter(), \
            "Cannot use 'limit' or 'offset' with delete."

        if self._fields is not None:
            raise TypeError("Cannot call delete() after .values() or .values_list()")

        del_query = self._chain()

        # The delete is actually 2 queries - one to find related objects,
        # and one to delete. Make sure that the discovery of related
        # objects is performed on the same database as the deletion.
        del_query._for_write = True

        # Disable non-supported fields.
        del_query.query.select_for_update = False
        del_query.query.select_related = False
        del_query.query.clear_ordering(force_empty=True)

        collector = FakeDeleteCollector(using=del_query.db)
        collector.collect(del_query)
        deleted, _rows_count = collector.delete(deleter=deleter)

        # Clear the result cache, in case this QuerySet gets reused.
        self._result_cache = None
        return deleted, _rows_count

    delete.alters_data = True
    delete.queryset_only = True

    # def delete(self, deleter=''):
    #     self.update(deleted=True, deleter=deleter,
    #                 delete_time=timezone.now())


class FakeDeleteModelManager(models.Manager):
    # 假删除
    def get_queryset(self):
        return CustomQuerySet(self.model).filter(deleted=False)


class FakeDeleteCollector(Collector):

    def delete(self, deleter=''):
        # sort instance collections
        for model, instances in self.data.items():
            self.data[model] = sorted(instances, key=attrgetter("pk"))

        # if possible, bring the models in an order suitable for databases that
        # don't support transactions or cannot defer constraint checks until the
        # end of a transaction.
        self.sort()
        # number of objects deleted for each model label
        deleted_counter = Counter()

        # Optimize for the case with a single obj and no dependencies
        if len(self.data) == 1 and len(instances) == 1:
            instance = list(instances)[0]
            if self.can_fast_delete(instance):
                with transaction.mark_for_rollback_on_error():
                    if issubclass(model, FakeDeleteModel):
                        if not instance.deleted:
                            count = 1
                            sql.UpdateQuery(model).update_batch([instance.pk],
                                                                {'deleted': True, 'deleter': deleter,
                                                                 'delete_time': timezone.now()}, self.using)
                        else:
                            count = 0
                    else:
                        count = sql.DeleteQuery(model).delete_batch(
                            [instance.pk], self.using)
                setattr(instance, model._meta.pk.attname, None)
                return count, {model._meta.label: count}

        with transaction.atomic(using=self.using, savepoint=False):
            # send pre_delete signals
            for model, obj in self.instances_with_model():
                if not model._meta.auto_created:
                    signals.pre_delete.send(
                        sender=model, instance=obj, using=self.using
                    )

            # fast deletes
            for qs in self.fast_deletes:
                # For FakeDelete
                if not qs:
                    continue
                if issubclass(qs.model, FakeDeleteModel):
                    query = sql.UpdateQuery(qs.model)
                    pk_list = [obj.pk for obj in qs if not obj.deleted]
                    if pk_list:
                        query.update_batch(pk_list,
                                           {'deleted': True, 'deleter': deleter,
                                            'delete_time': timezone.now()}, self.using)
                else:
                    count = qs._raw_delete(using=self.using)
                    deleted_counter[qs.model._meta.label] += count

            # update fields
            for model, instances_for_fieldvalues in self.field_updates.items():
                for (field, value), instances in instances_for_fieldvalues.items():
                    query = sql.UpdateQuery(model)
                    query.update_batch([obj.pk for obj in instances],
                                       {field.name: value}, self.using)

            # reverse instance collections
            for instances in self.data.values():
                instances.reverse()

            # delete instances
            for model, instances in self.data.items():
                # For FakeDelete
                if issubclass(model, FakeDeleteModel):
                    query = sql.UpdateQuery(model)
                    pk_list = [obj.pk for obj in instances if not obj.deleted]
                    if pk_list:
                        query.update_batch(pk_list,
                                           {'deleted': True, 'deleter': deleter,
                                            'delete_time': timezone.now()}, self.using)
                else:
                    query = sql.DeleteQuery(model)
                    pk_list = [obj.pk for obj in instances]
                    count = query.delete_batch(pk_list, self.using)
                    deleted_counter[model._meta.label] += count

                if not model._meta.auto_created:
                    for obj in instances:
                        signals.post_delete.send(
                            sender=model, instance=obj, using=self.using
                        )

        # update collected instances
        for instances_for_fieldvalues in self.field_updates.values():
            for (field, value), instances in instances_for_fieldvalues.items():
                for obj in instances:
                    setattr(obj, field.attname, value)
        for model, instances in self.data.items():
            for instance in instances:
                setattr(instance, model._meta.pk.attname, None)
        return sum(deleted_counter.values()), dict(deleted_counter)


class ModelWrapper(models.Model):
    @classmethod
    def serializer_class(cls, include=None, related=None, extra=None, exclude=None,
                         include_sensitive=None,
                         include_display_fields=True, include_delete_fields=False, paging=False, count=True):
        """
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

        parent_slr = serializers.ModelSerializer
        if paging:
            if not count:
                parent_slr = ModelPaginationSerializerWithoutCount
            else:
                parent_slr = ModelPaginationSerializer

        class SLR(parent_slr):

            class Meta:
                model = cls

        fs = []
        for f in cls._meta.get_fields():
            if exclude and f.name in exclude:
                continue
            if include and f.name not in include:
                continue
            if sensitive_fields := getattr(cls, 'sensitive_fields', None):
                if (f.name in sensitive_fields) and (f.name not in (include_sensitive or [])):
                    continue

            # fields for fake delete
            if not include_delete_fields and f.name in ('deleted', 'deleter', 'delete_time'):
                continue

            # relations
            if isinstance(f, (RelatedField, ForeignObjectRel, CompositeForeignKey)):
                if related and f.name in related:
                    setattr(SLR, f.name, related[f.name])
                    SLR._declared_fields[f.name] = related[f.name]
                else:
                    if isinstance(f, (ForeignObjectRel, ManyToManyField, CompositeForeignKey, GenericRelation)):
                        # many to many relations & reverse relations ignored by default
                        continue
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

    @classmethod
    def serializer(cls, instance=None, include=None, related=None, extra=None, exclude=None, include_sensitive=None,
                   include_display_fields=True, include_delete_fields=False, paging=False, **kwargs):

        serializer_cls = cls.serializer_class(include, related, extra, exclude, include_sensitive,
                                              include_display_fields, include_delete_fields, paging)
        return serializer_cls(instance, **kwargs)

    @classmethod
    def get(cls, *args, **kwargs):
        if 'pk' in kwargs and kwargs['pk'] is None:
            return None
        try:
            return cls.objects.get(*args, **kwargs)
        except cls.DoesNotExist:
            raise errors.ResourceNotExist('%s: %s,%s' % (cls._meta.object_name,

                                                         args, kwargs))

    @classmethod
    def get_or_none(cls, *args, **kwargs):
        if 'pk' in kwargs and kwargs['pk'] is None:
            return None
        try:
            return cls.objects.get(*args, **kwargs)
        except cls.DoesNotExist:
            return None

    @classmethod
    def raw_get(cls, *args, **kwargs):
        try:
            return cls.raw_objects.get(*args, **kwargs)
        except cls.DoesNotExist:
            raise errors.ResourceNotExist('%s: %s,%s' % (cls._meta.object_name,
                                                         args, kwargs))

    @classmethod
    def prefetch_related(cls, *args, **kwargs):
        return cls.objects.prefetch_related(*args, **kwargs)

    @classmethod
    def raw_prefetch_related(cls, *args, **kwargs):
        return cls.raw_objects.prefetch_related(*args, **kwargs)

    @classmethod
    def select_related(cls, *args, **kwargs):
        return cls.objects.select_related(*args, **kwargs)

    @classmethod
    def raw_select_related(cls, *args, **kwargs):
        return cls.raw_objects.select_related(*args, **kwargs)

    @classmethod
    def filter(cls, *args, **kwargs):
        return cls.objects.filter(*args, **kwargs)

    @classmethod
    def raw_filter(cls, *args, **kwargs):
        return cls.raw_objects.filter(*args, **kwargs)

    @classmethod
    def all(cls, *args, **kwargs):
        return cls.objects.all(*args, **kwargs)

    @classmethod
    def raw_all(cls, *args, **kwargs):
        return cls.raw_objects.all(*args, **kwargs)

    @classmethod
    def create(cls, *args, **kwargs):
        model_obj = cls.objects.create(*args, **kwargs)
        return model_obj

    @classmethod
    def bulk_create(cls, *args, **kwargs):
        return cls.objects.bulk_create(*args, **kwargs)

    def update(self, _refresh=True, **kwargs):
        kwargs['update_time'] = timezone.now()
        self.__class__.objects.filter(pk=self.pk).update(**kwargs)
        if _refresh:
            self.refresh_from_db()

    class Meta:
        abstract = True


class FakeDeleteModel(ModelWrapper):
    objects = FakeDeleteModelManager()
    raw_objects = models.Manager()

    deleted = models.BooleanField(default=False, db_index=True)
    deleter = models.CharField(max_length=32, default='', blank=True)
    delete_time = models.DateTimeField(null=True, default=None, blank=True)

    def delete(self, using=None, keep_parents=False, deleter=''):
        using = using or router.db_for_write(self.__class__, instance=self)
        assert self.pk is not None, (
                "%s object can't be deleted because its %s attribute is set to None." %
                (self._meta.object_name, self._meta.pk.attname)
        )
        collector = FakeDeleteCollector(using=using)
        try:
            collector.collect([self], keep_parents=keep_parents)
        except ProtectedError as e:
            items = [i for i in e.protected_objects]
            length = len(items)
            raise errors.OperationNotAllowed(
                '请先删除%s等%s条关联数据' % (
                    ', '.join(['%s(%s)' % (str(o), o._meta.verbose_name) for o in items[:3]]),
                    length
                ))
        return collector.delete(deleter)

    def recover(self):
        self.__class__.raw_objects.filter(pk=self.pk).update(deleted=False, deleter='', delete_time=None)

    delete.alters_data = True

    class Meta:
        base_manager_name = 'objects'
        abstract = True


class JSONUnquote(Func):
    function = 'JSON_UNQUOTE'
    arity = 1


class TimeFieldWithZone(TimeField):
    """
    为了确保在接口处理中一直是utc时间，请使用SerializerTimeFieldWithZone的功能
    """
    description = 'time zone aware time field'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def from_db_value(self, value, *args, **kwargs):
        if value is None:
            return None
        return time_to_current_timezone(value)

    def get_prep_value(self, value):
        if value is None:
            return value
        return time_from_current_timezone(value)

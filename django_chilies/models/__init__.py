from collections import Counter
from functools import reduce
from operator import attrgetter, or_

from django.db import models, transaction, router
from django.db.models import QuerySet, sql, signals, TimeField, \
    ProtectedError, Func, CharField
from django.db.models.deletion import Collector
from django.db.models.signals import post_save
from django.db.models.sql import AND
from django.db.models.sql.where import WhereNode
from django.forms import JSONField as _JSONField
from django.utils import timezone

from .. import errors
from ..common import DefaultJSONEncoder
from ..serializers import model_serializer_class
from ..utils import time_to_current_timezone, time_from_current_timezone


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
        self._not_support_combined_queries("delete")
        if self.query.is_sliced:
            raise TypeError("Cannot use 'limit' or 'offset' with delete().")
        if self.query.distinct or self.query.distinct_fields:
            raise TypeError("Cannot call delete() after .distinct().")
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
        del_query.query.clear_ordering(force=True)

        collector = FakeDeleteCollector(using=del_query.db, origin=self)
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
                with transaction.mark_for_rollback_on_error(self.using):
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
                        sender=model,
                        instance=obj,
                        using=self.using,
                        origin=self.origin,
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
                        deleted_counter[qs.model._meta.label] += len(pk_list)
                else:
                    count = qs._raw_delete(using=self.using)
                    if count:
                        deleted_counter[qs.model._meta.label] += count

            # update fields
            for (field, value), instances_list in self.field_updates.items():
                updates = []
                objs = []
                for instances in instances_list:
                    if (
                            isinstance(instances, models.QuerySet)
                            and instances._result_cache is None
                    ):
                        updates.append(instances)
                    else:
                        objs.extend(instances)
                if updates:
                    combined_updates = reduce(or_, updates)
                    combined_updates.update(**{field.name: value})
                if objs:
                    model = objs[0].__class__
                    query = sql.UpdateQuery(model)
                    query.update_batch(
                        list({obj.pk for obj in objs}), {field.name: value}, self.using
                    )

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
                        deleted_counter[model._meta.label] += len(pk_list)
                else:
                    query = sql.DeleteQuery(model)
                    pk_list = [obj.pk for obj in instances]
                    count = query.delete_batch(pk_list, self.using)
                    deleted_counter[model._meta.label] += count

                if not model._meta.auto_created:
                    for obj in instances:
                        signals.post_delete.send(
                            sender=model,
                            instance=obj,
                            using=self.using,
                            origin=self.origin,
                        )

        for model, instances in self.data.items():
            for instance in instances:
                setattr(instance, model._meta.pk.attname, None)
        return sum(deleted_counter.values()), dict(deleted_counter)


class ModelWrapper(models.Model):
    sensitive_fields = []

    @classmethod
    def serializer_class(cls, include=None, related=None, extra=None, exclude=None,
                         include_sensitive=None,
                         include_display_fields=True, include_delete_fields=False, paging=False, count=True):
        return model_serializer_class(cls, include, related, extra, exclude, include_sensitive,
                                      include_display_fields, include_delete_fields, paging, count)

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
        if 'id' in kwargs and kwargs['id'] is None:
            return None
        try:
            return cls.objects.get(*args, **kwargs)
        except cls.DoesNotExist:
            return None
        except errors.ResourceNotExist:
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
    def update_or_create(cls, *args, **kwargs):
        model_obj = cls.objects.update_or_create(*args, **kwargs)
        return model_obj

    @classmethod
    def bulk_create(cls, *args, **kwargs):
        objs = args[0]
        res = cls.objects.bulk_create(*args, **kwargs)
        for obj in objs:
            post_save.send(obj.__class__, instance=obj, created=True)

        return res

    def serialized_data(self, fields=None):
        return self.serializer(self, fields=fields).data

    def update(self, _refresh=True, **kwargs):
        if hasattr(self, 'update_time'):
            kwargs['update_time'] = timezone.now()
        update_fields = []
        for k, v in kwargs.items():
            update_fields.append(k)
            setattr(self, k, v)
        self.save(update_fields=update_fields)

    @classmethod
    def bulk_update(cls, *args, **kwargs):
        objs, fields = args[0], args[1]
        res = cls.objects.bulk_update(*args, **kwargs)
        for obj in objs:
            post_save.send(obj.__class__, instance=obj, created=False, update_fields=fields)

        return res

    class Meta:
        abstract = True


class StatusModel(models.Model):
    status = models.BooleanField(default=True)

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


class JSONField(_JSONField):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.encoder:
            self.encoder = DefaultJSONEncoder


class NullAgg(Func):
    """Annotation that causes GROUP BY without aggregating.

    A fake aggregate Func class that can be used in an annotation to cause
    a query to perform a GROUP BY without also performing an aggregate
    operation that would require the server to enumerate all rows in every
    group.

    Takes no constructor arguments and produces a value of NULL.

    Example:
        ContentType.objects.values('app_label').annotate(na=NullAgg())
    """
    template = 'NULL'
    contains_aggregate = True
    window_compatible = False
    arity = 0
    output_field = CharField()

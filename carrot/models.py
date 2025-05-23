from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from carrot.exceptions import CarrotConfigException

from datetime import datetime, timedelta
import json
import os
import sys

from typing import Optional, Iterable

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR + '/carrot')


class MessageLog(models.Model):
    """
    MessageLogs store information about a carrot task

    Lifecycle:
        #. A :class:`carrot.objects.Message` object is created and published.
        #. The act of publishing the message creates a MessageLog object with the status 'PUBLISHED'. The task now sits
           in the RabbitMQ queue until it has been consumed
        #. When a consumer digests the message, the status is updated to 'COMPLETED' if the task completes successfully
           or 'FAILED' if it encounters an exception. The output, traceback, exception message and logs are written
           back to the MessageLog object
        #. If a task has failed, it can be requeued. Requeueing a task will create a new :class:`carrot.objects.Message`
           object with the same parameters. In this case, the originally MessageLog object will be deleted
        #. If the task has been completed successfully, it will be deleted three days after completion, provided that
           the :function:`carrot.helper_tasks.cleanup` has not been disabled

    """
    STATUS_CHOICES = (
        ('PUBLISHED', 'Published'),
        ('IN_PROGRESS', 'In progress'),
        ('FAILED', 'Failed'),
        ('COMPLETED', 'Completed'),
    ) #:
    id = models.BigAutoField(primary_key=True)  # Use BigAutoField for the primary key
    status = models.CharField(max_length=11, choices=STATUS_CHOICES, default='PUBLISHED')
    exchange = models.CharField(max_length=200, blank=True, null=True)  #: the exchange
    queue = models.CharField(max_length=200, blank=True, null=True)
    routing_key = models.CharField(max_length=200, blank=True, null=True)
    uuid = models.CharField(max_length=200, db_index=True)
    priority = models.PositiveIntegerField(default=0)
    validate = models.BooleanField(default=True)
    worker = models.CharField(
        max_length=100, default=None, null=True, verbose_name=_("Worker"),
        help_text=_("Worker that executes the task")
    )

    task = models.CharField(max_length=200)  #: the import path for the task to be executed
    task_args = models.TextField(null=True, blank=True, verbose_name='Task positional arguments')
    content = models.TextField(null=True, blank=True, verbose_name='Task keyword arguments')

    exception = models.TextField(null=True, blank=True)
    traceback = models.TextField(null=True, blank=True)
    output = models.TextField(null=True, blank=True)

    publish_time = models.DateTimeField(null=True, blank=True)
    failure_time = models.DateTimeField(null=True, blank=True)
    completion_time = models.DateTimeField(null=True, blank=True)

    log = models.TextField(blank=True, null=True)

    @property
    def virtual_host(self) -> Optional[str]:
        from carrot.utilities import get_host_from_name
        try:
            return str(get_host_from_name(self.queue))
        except CarrotConfigException:
            """
            This exception may get raised here when a MessageLog is created with a queue that is later removed from the
            Django config. This method now returns `None` in these cases, so as not to break the monitor   

            Refer to https://github.com/chris104957/django-carrot/issues/81
            """
            return None

    @property
    def keywords(self) -> dict:
        """
        Used in :class:`carrot.views.MessageView` to display the keyword arguments as a table
        """
        return json.loads(self.content or '{}')

    def __str__(self) -> models.CharField:
        return self.task

    @property
    def positionals(self) -> Iterable:
        import ast
        if self.task_args == '()':
            return ()
        else:
            return [ast.literal_eval(arg.strip()) for arg in self.task_args[1:-1].split(',') if arg != '']

    def requeue(self) -> 'MessageLog':
        """
        Sends a failed MessageLog back to the queue. The original MessageLog is deleted
        """
        from carrot.utilities import publish_message
        msg = publish_message(self.task, *self.positionals, priority=self.priority, queue=self.queue,
                              exchange=self.exchange, routing_key=self.routing_key, validate=self.validate, 
                              **self.keywords)

        if self.pk:
            self.delete()

        return msg

    class Meta:
        app_label = "carrot"
        ordering = (
            '-failure_time', '-completion_time', 'status', '-priority', 
            'publish_time',
        )


class ScheduledTask(models.Model):
    """
    A model for scheduling tasks to run at a certain interval
    """
    INTERVAL_CHOICES = (
        ('seconds', 'seconds'),
        ('minutes', 'minutes'),
        ('hours', 'hours'),
        ('days', 'days'),
    )

    interval_type = models.CharField(max_length=200, choices=INTERVAL_CHOICES, default='seconds')
    interval_count = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])

    last_run_time = models.DateTimeField(blank=True, null=True)

    exchange = models.CharField(max_length=200, blank=True, null=True)
    routing_key = models.CharField(max_length=200, blank=True, null=True)
    queue = models.CharField(max_length=200, blank=True, null=True)
    task = models.CharField(max_length=200)
    task_args = models.TextField(null=True, blank=True, verbose_name='Positional arguments')
    content = models.TextField(null=True, blank=True, verbose_name='Keyword arguments')
    validate = models.BooleanField(default=True)
    priority = models.IntegerField(
        null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(255)],
        help_text="1 to 5 suggested, up to 255"
    )

    active = models.BooleanField(default=True)

    task_name = models.CharField(max_length=200, unique=True)

    class Meta:
        app_label = "carrot"
        
    def get_absolute_url(self) -> str:
        return reverse('edit-scheduled-task', args=[self.pk])

    @property
    def interval_display(self) -> str:
        return 'Every %i %s' % (self.interval_count, self.interval_type if self.interval_count > 1 else
            self.interval_type[:-1])

    @property
    def multiplier(self) -> int:
        if self.interval_type == 'minutes':
            return 60

        if self.interval_type == 'hours':
            return 60 * 60

        if self.interval_type == 'days':
            return 86400

        return 1

    @property
    def positional_arguments(self) -> tuple:
        if self.task_args:
            return tuple([a.strip() for a in self.task_args.split(',') if a])
        else:
            return ()

    @property
    def scheduled_time(self) -> bool:
        return self.last_run_time is not None

    @property
    def next_run_time(self) -> datetime:
        if not self.scheduled_time:
            return None
        return self.last_run_time + timedelta(seconds=self.interval_count * self.multiplier)

    def publish(self, priority: int = 0) -> MessageLog:
        from carrot.utilities import publish_message
        kwargs = json.loads(self.content or '{}')
        if isinstance(kwargs, str):
            kwargs = {}

        return publish_message(
            self.task, *self.positional_arguments, priority=self.priority or priority,
            queue=self.queue, exchange=self.exchange or '',
            routing_key=self.routing_key or self.queue, validate=self.validate,
            **kwargs
        )

    class Meta:
        ordering = ('-task', '-pk',)

    def __str__(self) -> models.CharField:
        return self.task

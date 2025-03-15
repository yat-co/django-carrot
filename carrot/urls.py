from django.urls import re_path
from carrot.views import MessageList
from carrot.utilities import decorate_class_view, decorate_function_view, create_class_view
from django.conf import settings
from carrot.api import (
    published_message_log_viewset, failed_message_log_viewset, completed_message_log_viewset, scheduled_task_viewset,
    detail_message_log_viewset, scheduled_task_detail, run_scheduled_task, task_list, validate_args, purge_messages,
    MessageLogViewset, requeue_pending
)
from typing import Any

try:
    decorators = settings.CARROT.get('monitor_authentication', [])
except AttributeError:
    decorators = []


def _(v: Any, **kwargs) -> Any:
    """
    Decorates a class based view with a custom auth decorator specified in the settings module
    """
    return decorate_class_view(v, decorators).as_view(**kwargs)


def _f(v: MessageLogViewset) -> Any:
    """
    The same as the above _ method, but for function-based views
    """
    return decorate_function_view(v, decorators)


urlpatterns = [
    re_path(r'^$', _(MessageList), name='carrot-monitor'),
    re_path(r'^api/message-logs/published/$', _f(published_message_log_viewset), name='published-messagelog'),
    re_path(r'^api/message-logs/failed/$', _f(failed_message_log_viewset)),
    re_path(r'^api/message-logs/purge/$', _f(purge_messages)),
    re_path(r'^api/message-logs/requeue/$', _f(requeue_pending)),
    re_path(r'^api/message-logs/completed/$', _f(completed_message_log_viewset)),
    re_path(r'^api/message-logs/(?P<pk>[0-9]+)/$', _f(detail_message_log_viewset)),
    re_path(r'^api/scheduled-tasks/$', _f(scheduled_task_viewset)),
    re_path(r'^api/scheduled-tasks/task-choices/$', _f(task_list)),
    re_path(r'^api/scheduled-tasks/validate-args/$', _f(validate_args)),
    re_path(r'^api/scheduled-tasks/(?P<pk>[0-9]+)/$', _f(scheduled_task_detail)),
    re_path(r'^api/scheduled-tasks/(?P<pk>[0-9]+)/run/$', _f(run_scheduled_task)),
]

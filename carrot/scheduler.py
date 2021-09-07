from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist

from datetime import datetime
import threading
import time
from typing import List

from carrot.models import ScheduledTask

SLEEP = settings.CARROT.get('sleep', 1)


class ScheduledTaskThread(threading.Thread):
    """
    A thread that handles a single :class:`carrot.models.ScheduledTask` object. When started, it waits for the interval
    to pass before publishing the task to the required queue

    While waiting for the task to be due for publication, the process continuously monitors the object in the Django
    project's database for changes to the interval, task, or arguments, or in case it gets deleted/marked as inactive
    and response accordingly
    """

    def __init__(self,
                 scheduled_task: ScheduledTask,
                 run_now: bool = False,
                 **filters) -> None:
        threading.Thread.__init__(self)
        self.id = scheduled_task.pk
        self.queue = scheduled_task.routing_key
        self.scheduled_task = scheduled_task
        self.run_now = run_now
        self.active = True
        self.filters = filters
        self.inactive_reason = ''

    def run(self) -> None:
        """
        Either continues to check for the next scheduled time to be past the current time stamp or initiates a timer, 
        then once the timer is equal to the ScheduledTask's interval.  Then scheduler checks to make sure that the 
        task has not been deactivated/deleted in the mean time, and that the manager has not been stopped, then publishes 
        it to  the queue
        """
        if self.run_now:
            self.scheduled_task.publish()

        if self.scheduled_task.scheduled_time:
            while True:
                while datetime.now() < self.scheduled_task.next_run_time:
                    if not self.active:
                        if self.inactive_reason:
                            print('Thread stop has been requested because of the following reason: %s.\n Stopping the '
                                'thread' % self.inactive_reason)

                        return

                    try:
                        self.scheduled_task = ScheduledTask.objects.get(pk=self.scheduled_task.pk, **self.filters)

                    except ObjectDoesNotExist:
                        print('Current task has been removed from the queryset. Stopping the thread')
                        return

                    ## TODO: Configurable Sleep Period
                    time.sleep(SLEEP)
                    print('Publishing message %s' % self.scheduled_task.task)
                    self.scheduled_task.publish()
                    
                    # Update Model to Next Time Period
                    self.scheduled_task.last_run_time = self.scheduled_task.next_run_time
                    self.scheduled_task.save()
        else:
            interval = self.scheduled_task.multiplier * self.scheduled_task.interval_count
            count = 0

            while True:
                while count < interval:
                    if not self.active:
                        if self.inactive_reason:
                            print('Thread stop has been requested because of the following reason: %s.\n Stopping the '
                                'thread' % self.inactive_reason)

                        return

                    try:
                        self.scheduled_task = ScheduledTask.objects.get(pk=self.scheduled_task.pk, **self.filters)
                        interval = self.scheduled_task.multiplier * self.scheduled_task.interval_count

                    except ObjectDoesNotExist:
                        print('Current task has been removed from the queryset. Stopping the thread')
                        return

                    time.sleep(SLEEP)
                    count += SLEEP

                print('Publishing message %s' % self.scheduled_task.task)
                self.scheduled_task.publish()
                count = 0


class ScheduledTaskManager(object):
    """
    The main scheduled task manager project. For every active :class:`carrot.models.ScheduledTask`, a
    :class:`ScheduledTaskThread` is created and started

    This object exists for the purposes of starting these threads on startup, or when a new ScheduledTask object
    gets created, and implements a .stop() method to stop all threads

    """

    def __init__(self, **options) -> None:
        self.threads: List[ScheduledTaskThread] = []
        self.filters = options.pop('filters', {'active': True})
        self.run_now = options.pop('run_now', False)
        self.tasks = ScheduledTask.objects.filter(**self.filters)

    def start(self) -> None:
        """
        Initiates and starts a scheduler for each given ScheduledTask
        """
        print('found %i scheduled tasks to run' % self.tasks.count())
        for t in self.tasks:
            print('starting thread for task %s' % t.task)
            thread = ScheduledTaskThread(t, self.run_now, **self.filters)
            thread.start()
            self.threads.append(thread)

    def add_task(self, task: ScheduledTask) -> None:
        """
        After the manager has been started, this function can be used to add an additional ScheduledTask starts a
        scheduler for it
        """
        thread = ScheduledTaskThread(task, self.run_now, **self.filters)
        thread.start()
        self.threads.append(thread)

    def stop(self) -> None:
        """
        Safely stop the manager
        """
        print('Attempting to stop %i running threads' % len(self.threads))

        for t in self.threads:
            print('Stopping thread %s' % t)
            t.active = False
            t.inactive_reason = 'A termination of service was requested'
            t.join()
            print('thread %s stopped' % t)

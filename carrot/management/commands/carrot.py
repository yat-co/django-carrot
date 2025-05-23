from carrot.consumer import ConsumerSet, LOGGING_FORMAT
from carrot.models import ScheduledTask
from carrot.objects import VirtualHost
from carrot.scheduler import ScheduledTaskManager
from django.core.management.base import BaseCommand, CommandParser
from django.conf import settings

from carrot import DEFAULT_BROKER

import sys
import os
import logging
import signal
import psutil
import time
import types
from typing import List, Optional


class Command(BaseCommand):
    """
    The main process for creating and running :class:`carrot.consumer.ConsumerSet` objects and starting thes scheduler
    """
    pks: list = []
    run = True
    help = 'Starts the carrot service.'
    scheduler: Optional[ScheduledTaskManager] = None
    active_consumer_sets: list = []

    def __init__(self,
                 stdout: str = None,
                 stderr: str = None,
                 nocolor: bool = False) -> None:
        """
        Initiates the Carrot process. All params are passed straight to the base class. SIGINT and SIGTERM signals
        bound; the process will exit gracefully on these events
        """
        signal.signal(signal.SIGINT, self.exit_gracefully)
        signal.signal(signal.SIGTERM, self.exit_gracefully)
        super(Command, self).__init__(stdout, stderr, nocolor)

    def exit_gracefully(self, signum: int, frame: types.FrameType) -> None:
        self.stdout.write(self.style.WARNING('Shutdown requested'))
        self.run = False

    def terminate(self, *args) -> None:
        """
        Tells the scheduler (if running) and consumer sets to stop running, and waits for the response
        """
        if self.scheduler:
            self.scheduler.stop()
            self.stdout.write(self.style.SUCCESS('Successfully closed scheduler'))

        self.stdout.write('Terminating running consumer sets (%i)...' % len(self.active_consumer_sets))
        count = 0
        for consumer_set in self.active_consumer_sets:
            count += 1
            consumer_set.stop_consuming()

        self.stdout.write(self.style.SUCCESS('Successfully closed %i consumer sets' % count))
        sys.exit()

    def add_arguments(self, parser: CommandParser) -> None:
        """
        Adds the relevant command line arguments
        """
        parser.add_argument("-l", "--logfile", type=str, help='The path to the log file',
                            default='/var/log/carrot.log')
        parser.add_argument('--no-scheduler', dest='run_scheduler', action='store_false', default=False,
                            help='Do not start scheduled tasks (only runs consumer sets)')
        parser.set_defaults(run_scheduler=True)
        parser.set_defaults(testmode=False)
        parser.add_argument('--loglevel', type=str, default='DEBUG', help='The logging level. Must be one of DEBUG, '
                                                                          'INFO, WARNING, ERROR, CRITICAL')

        parser.add_argument(
            '--incl_queues', type=str, required=False, help='Comma seperated Queues to Include for Consumers'
        )
        parser.add_argument(
            '--excl_queues', type=str, required=False, help='Comma seperated Queues to Exclude for Consumers'
        )
        parser.add_argument(
            '--worker', type=str, required=False, help='Node Worker Name (Optional)'
        )
        parser.add_argument('--testmode', dest='testmode', action='store_true', default=False,
                            help='Run in test mode. Prevents the command from running as a service. Should only be '
                                 'used when running Carrot\'s tests')

    def handle(self, **options) -> None:
        """
        The actual handler process. Performs the following actions:

        - Initiates and starts a new :class:`carrot.objects.ScheduledTaskManager`, which schedules all *active*
        :class:`carrot.objects.ScheduledTask` instances to run at the given intervals. This only happens if the
        **--no-scheduler** argument has not been provided - otherwise, the service only creates consumer objects

        - Loops through the queues registered in your Django project's settings module, and starts a
        new :class:`carrot.objects.ConsumerSet` for them. Each ConsumerSet will contain **n**
        :class:`carrot.objects.Consumer` objects, where **n** is the concurrency setting for the given queue (as
        defined in the Django settings)

        - Enters into an infinite loop which monitors your database for changes to your database - if any changes
        to the :class:`carrot.objects.ScheduledTask` queryset are detected, carrot updates the scheduler
        accordingly

        On receiving a **KeyboardInterrupt**, **SystemExit** or SIGTERM, the service first turns off each of the
        schedulers in turn (so no new tasks can be published to RabbitMQ), before turning off the Consumers in turn.
        The more Consumers/ScheduledTask objects you have, the longer this will take.

        :param options: provided by **argparse** (see above for the full list of available options)

        """
        signal.signal(signal.SIGTERM, self.terminate)

        # check if carrot service is already running, and warn the user if so
        running_pids = []
        for q in psutil.process_iter():
            if 'python' in q.name():
                if len(q.cmdline()) > 1 and 'manage.py' in q.cmdline()[1] and 'carrot' in q.cmdline()[2]:
                    if os.name == 'nt':
                        if not q._pid == os.getpid():
                            running_pids.append(q._pid)
                    else:
                        if not q._pid == os.getpgid(0):
                            running_pids.append(q._pid)

        if running_pids:
            self.stdout.write(
                self.style.WARNING('WARNING: Carrot service is already running with the following PID. Running more '
                                   'than one instance of carrot may lead to a memory leak:\n%s'
                                   % '\n'.join([str(pid) for pid in running_pids])))

        run_scheduler = options['run_scheduler']

        # Get Include or Exclude Queues Parameters
        incl_queues_str: Optional[str] = options.get("incl_queues")
        excl_queues_str: Optional[str] = options.get("excl_queues")
        assert (
            incl_queues_str is None or excl_queues_str is None
        ), "Can not provide `incl_queues` and `excl_queues`, provide either or neither"

        # Get Worker and Ensure Worker Provided in the Event of Splitting up Consumers
        worker: Optional[str] = options.get("worker")
        if incl_queues_str is not None or excl_queues_str is not None:
            if worker is None:
                raise ValueError(
                    f"Must Provide Worker Name if Queues Included/Excluded Provided"
                )

        try:
            queues = [
                q for q in settings.CARROT['queues'] if q.get('consumable', True)
            ]
            if incl_queues_str is not None:
                incl_queues = incl_queues_str.split(",")
                queues = [q for q in queues if q.get("name") in incl_queues]

            elif excl_queues_str is not None:
                excl_queues = excl_queues_str.split(",")
                queues = [
                    q for q in queues if q.get("name") not in excl_queues
                ]

        except (AttributeError, KeyError):
            queues = [{'name': 'default', 'host': DEFAULT_BROKER}]

        logfile: str = options['logfile']
        try:

            # logger
            loglevel = getattr(logging, options.get('loglevel', 'DEBUG'))

            logger = logging.getLogger('carrot')
            logger.setLevel(loglevel)

            file_handler = logging.FileHandler(logfile)
            file_handler.setLevel(loglevel)

            stream_handler = logging.StreamHandler()
            stream_handler.setLevel(loglevel)

            formatter = logging.Formatter(LOGGING_FORMAT)
            file_handler.setFormatter(formatter)
            stream_handler.setFormatter(formatter)

            logger.addHandler(file_handler)
            logger.addHandler(stream_handler)

            if run_scheduler:
                self.scheduler = ScheduledTaskManager(logger=logger)
                
            # scheduler
            if self.scheduler:
                self.scheduler.start()
                self.stdout.write(self.style.SUCCESS('Successfully started scheduler'))

            # consumers
            for queue in queues:
                kwargs = {
                    "queue": queue["name"],
                    "worker": worker,
                    "logger": logger,
                    "concurrency": queue.get("concurrency", 1),
                }

                if queue.get("consumer_class", None):
                    kwargs["consumer_class"] = queue.get("consumer_class")

                try:
                    vhost = VirtualHost(**queue["host"])
                except TypeError:
                    vhost = VirtualHost(url=queue["host"])

                c = ConsumerSet(host=vhost, **kwargs)
                c.start_consuming()
                self.active_consumer_sets.append(c)
                self.stdout.write(self.style.SUCCESS('Successfully started %i consumers for queue %s'
                                                     % (c.concurrency, queue['name'])))

            msg: str = f'All queues consumer sets started successfully. Full logs are at {logfile}.'
            if incl_queues_str is not None:
                msg: str = f'[Worker={worker}] {incl_queues_str} queues consumer sets started successfully. Full logs are at {logfile}.'
            elif excl_queues_str is not None:
                msg: str = f'[Worker={worker}] All queues excl=`{excl_queues_str}` consumer sets started successfully. Full logs are at {logfile}.'

            self.stdout.write(self.style.SUCCESS(msg))

            qs = ScheduledTask.objects.filter(active=True)
            self.pks = [t.pk for t in qs]

            while True:
                time.sleep(1)
                # Check status of threads
                cs: ConsumerSet
                for cs in self.active_consumer_sets:
                    for thread in cs.threads:
                        if thread.is_alive() or thread.alert_dead_thread:
                            continue

                        logger.error(
                            f"Consumer=`{thread.name}` on worker=`{thread.worker or ''}` died"
                        )
                        thread.alert_dead_thread = True  # Alert thread is dead
                        # TODO: Look at adding consumer set back
                        # TODO: Add checks/alerts for scheduler threads

                if not self.run:
                    self.terminate()

                if self.scheduler or options['testmode']:
                    new_qs = ScheduledTask.objects.filter(active=True)
                    active_pks = {st.pk for st in new_qs}
                    newly_added = set(self.pks) - active_pks

                    if new_qs.count() > len(self.pks) or newly_added:
                        self.stdout.write(self.style.SUCCESS('New active scheduled tasks have been added to the queryset'))
                        new_tasks = new_qs.exclude(pk__in=self.pks) or [ScheduledTask()]
                        for new_task in new_tasks:
                            self.stdout.write(self.style.SUCCESS('adding new task %s' % new_task))
                            if self.scheduler:
                                self.scheduler.add_task(new_task)

                        self.pks = [t.pk for t in new_qs]

                    elif new_qs.count() < len(self.pks):
                        self.pks = [t.pk for t in new_qs]

                if options['testmode']:
                    self.stdout.write(self.style.SUCCESS('TESTMODE:', options['testmode']))
                    raise SystemExit()

        except Exception as err:
            try:
                self.stderr.write(self.style.ERROR(err))
            except AttributeError:
                """
                This attribute error will happen when a pika exceptions.ChannelClosed error happens, as django can't 
                deal with the error styling for this type of exception. Instead, we write the stderr without the 
                colorisation
                """
                self.stderr.write(str(err))

        except (KeyboardInterrupt, SystemExit):
            # self.terminate()
            pass


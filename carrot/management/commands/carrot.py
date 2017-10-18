import time

from carrot.consumer import ConsumerSet
from carrot.models import ScheduledTask
from carrot.objects import VirtualHost
from carrot.scheduler import ScheduledTaskManager
from django.core.management.base import BaseCommand
from django.conf import settings
from carrot import DEFAULT_BROKER
import signal
import os
import sys


class Command(BaseCommand):
    """

    """
    help = 'Starts the carrot service.'
    scheduler = None

    def terminate(self, *args):
        self.stdout.write(self.style.WARNING('Shutdown requested'))

        if self.scheduler:
            self.scheduler.stop()

            self.stdout.write(self.style.SUCCESS('Successfully closed scheduler'))

        self.stdout.write('Terminating running consumer sets (%i)...' % len(self.active_consumer_sets))
        count = 0
        for consumer_set in self.active_consumer_sets:
            print('Terminating consumer set %s' % consumer_set)
            count += 1
            consumer_set.stop_consuming()
            print('Consumer set %s terminated' % consumer_set)

        self.stdout.write(self.style.SUCCESS('Successfully closed %i consumer sets' % count))
        sys.exit()

    def add_arguments(self, parser):
        parser.add_argument("-l", "--logfile", type=str, help='The path to the log file',
                            default='/var/log/carrot.log')
        parser.add_argument('--no-scheduler', dest='run_scheduler', action='store_false', default=False,
                            help='Do not start scheduled tasks (only runs consumer sets)')
        parser.set_defaults(run_scheduler=True)
        parser.set_defaults(testmode=False)
        parser.add_argument('--consumer-class', type=str, help='The consumer class to use',
                            default='carrot.objects.Consumer')
        parser.add_argument('--loglevel', type=str, default='DEBUG', help='The logging level. Must be one of DEBUG, '
                                                                          'INFO, WARNING, ERROR, CRITICAL')
        parser.add_argument('--testmode', dest='testmode', action='store_true', default=False,
                            help='Run in test mode. Prevents the command from running as a service. Should only be '
                                 'used when running Carrot\'s tests')

    def handle(self, **options):
        """
        The actual handler process. Performs the following actions:

            1. Initiates and starts a new :class:`carrot.objects.ScheduledTaskManager`, which schedules all *active*
               :class:`carrot.objects.ScheduledTask` instances to run at the given intervals. This only happens if the
               **--no-scheduler** argument has not been provided - otherwise, the service only creates consumer objects

            2. Loops through the queues registered in your Django project's settings module, and starts a
               new :class:`carrot.objects.ConsumerSet` for them. Each ConsumerSet will contain **n**
               :class:`carrot.objects.Consumer` objects, where **n** is the concurrency setting for the given queue (as
               defined in the Django settings)

            3. Enters into an infinite loop which monitors your database for changes to your database - if any changes
               to the :class:`carrot.objects.ScheduledTask` queryset are detected, carrot updates the scheduler
               accordingly

        On receiving a **KeyboardInterrupt** or **SystemExit**, the service first turns off each of the schedulers in
        turn (so no new tasks can be published to RabbitMQ), before turning off the Consumers in turn. The more
        Consumers/ScheduledTask objects you have, the longer this will take.

        :param options: provided by **argparse** (see above for the full list of available options)

        """
        signal.signal(signal.SIGINT, self.terminate)

        self.active_consumer_sets = []
        run_scheduler = options['run_scheduler']

        try:
            queues = [q for q in settings.CARROT['queues'] if q.get('consumable', True)]
        except KeyError:
            from carrot.utilities import get_host_from_name
            host = get_host_from_name(None)
            channel = host.blocking_connection.channel()
            channel.queue_declare(queue='default', durable=True, arguments={'x-max-priority': 255})

            queues = [{
                'name': 'default',
                'host': settings.CARROT.get('default_broker', DEFAULT_BROKER),
            }]

        if run_scheduler:
            self.scheduler = ScheduledTaskManager()

        try:
            # scheduler
            if self.scheduler:
                self.scheduler.start()
                self.stdout.write(self.style.SUCCESS('Successfully started scheduler'))

            # consumers

            for queue in queues:
                kwargs = {
                    'queue': queue['name'],
                    'logfile': options['logfile'],
                    'concurrency': queue.get('concurrency', 1),
                }

                if queue.get('consumer_class', None):
                    kwargs['consumer_class'] = queue.get('consumer_class')

                if options.get('loglevel', None):
                    kwargs['loglevel'] = options['loglevel']

                try:
                    vhost = VirtualHost(**queue['host'])
                except TypeError:
                    vhost = VirtualHost(url=queue['host'])

                c = ConsumerSet(host=vhost, **kwargs)
                c.start_consuming()
                self.active_consumer_sets.append(c)
                self.stdout.write(self.style.SUCCESS('Successfully started %i consumers for queue %s'
                                                     % (c.concurrency, queue['name'])))

            self.stdout.write(self.style.SUCCESS('All queues consumer sets started successfully. Full logs are at %s.'
                                                 'PIDFILE: %i'
                                                 % (options['logfile'], os.getpid())))

            qs = ScheduledTask.objects.filter(active=True)
            self.pks = [t.pk for t in qs]

            while True:
                time.sleep(1)

                if self.scheduler or options['testmode']:
                    new_qs = ScheduledTask.objects.filter(active=True)

                    if new_qs.count() > len(self.pks):
                        print('New active scheduled tasks have been added to the queryset')
                        new_tasks = new_qs.exclude(pk__in=self.pks) or [ScheduledTask()]
                        for new_task in new_tasks:
                            print('adding new task %s' % new_task)
                            self.scheduler.add_task(new_task)

                        self.pks = [t.pk for t in new_qs]

                    elif new_qs.count() < len(self.pks):
                        self.pks = [t.pk for t in new_qs]

                if options['testmode']:
                    print('TESTMODE:', options['testmode'])
                    raise SystemExit()

        except Exception as err:
            self.stderr.write(self.style.ERROR(err))

        except (SystemExit, KeyboardInterrupt):
            self.terminate()

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = '启动 ROI RQ Worker（可指定消费的队列）'

    def add_arguments(self, parser):
        parser.add_argument(
            '--burst',
            action='store_true',
            help='处理完当前队列中的任务后退出',
        )
        parser.add_argument(
            '--name',
            default='roi-worker',
            help='Worker 名称（日志标识）',
        )
        parser.add_argument(
            '--queues',
            default='',
            help='逗号分隔的队列名，如 roi_single 或 roi_bulk,roi_scheduled',
        )

    def handle(self, *args, **options):
        from django.conf import settings

        import django_rq

        raw_queues = (options.get('queues') or '').strip()
        if raw_queues:
            queues = [q.strip() for q in raw_queues.split(',') if q.strip()]
        else:
            queues = [
                getattr(settings, 'RQ_QUEUE_ROI_SINGLE', settings.RQ_QUEUE_ROI_HIGH),
                settings.RQ_QUEUE_ROI_DEFAULT,
                settings.RQ_QUEUE_ROI_SCHEDULED,
            ]
        worker = django_rq.get_worker(*queues, name=options['name'])
        profile = __import__('os').environ.get('SELLER_CREDENTIAL_PROFILE', 'single')
        self.stdout.write(
            self.style.SUCCESS(
                f'Worker {options["name"]} 监听队列 {queues}，凭证档位={profile}'
            )
        )
        if options['burst']:
            worker.work(burst=True)
        else:
            worker.work(with_scheduler=False)

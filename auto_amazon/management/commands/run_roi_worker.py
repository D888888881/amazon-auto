from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = '启动 ROI RQ Worker（消费 roi_high / roi_default / roi_scheduled 队列）'

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

    def handle(self, *args, **options):
        from django.conf import settings

        import django_rq

        queues = [
            settings.RQ_QUEUE_ROI_HIGH,
            settings.RQ_QUEUE_ROI_DEFAULT,
            settings.RQ_QUEUE_ROI_SCHEDULED,
        ]
        worker = django_rq.get_worker(*queues, name=options['name'])
        if options['burst']:
            worker.work(burst=True)
        else:
            worker.work(with_scheduler=False)

from django.core.management.base import BaseCommand

from auto_amazon.scheduled_jobs import run_scheduled_asin_jobs


class Command(BaseCommand):
    help = '运行重点关注 ASIN 的定时 ROI / 广告难度任务（默认仅处理到期项）'

    def add_arguments(self, parser):
        parser.add_argument(
            '--all',
            action='store_true',
            help='忽略到期时间，处理全部重点关注 ASIN',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='只扫描并记录，不实际计算',
        )

    def handle(self, *args, **options):
        due_only = not options['all']
        dry_run = options['dry_run']
        stats = run_scheduled_asin_jobs(due_only=due_only, dry_run=dry_run)
        self.stdout.write(self.style.SUCCESS(str(stats)))

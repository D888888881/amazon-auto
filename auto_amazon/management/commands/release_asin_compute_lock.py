from django.core.management.base import BaseCommand

from auto_amazon.asin_access import normalize_asin
from auto_amazon.asin_job_lock import force_release_asin, get_lock_owner


class Command(BaseCommand):
    help = '强制释放 ASIN 计算锁（任务异常中断后若提示「正在被其他任务计算」可使用）'

    def add_arguments(self, parser):
        parser.add_argument(
            'asins',
            nargs='+',
            help='要释放锁的 ASIN，例如 B0GMRQ1SSP',
        )

    def handle(self, *args, **options):
        for raw in options['asins']:
            asin = normalize_asin(raw)
            if not asin:
                self.stderr.write(self.style.WARNING(f'跳过无效 ASIN：{raw}'))
                continue
            owner = get_lock_owner(asin)
            if not owner:
                self.stdout.write(self.style.WARNING(f'{asin}：当前无计算锁'))
                continue
            if force_release_asin(asin):
                self.stdout.write(self.style.SUCCESS(f'{asin}：已释放（原占用：{owner}）'))
            else:
                self.stdout.write(self.style.ERROR(f'{asin}：释放失败'))

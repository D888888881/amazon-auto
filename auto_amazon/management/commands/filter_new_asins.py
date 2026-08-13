"""从 asins.txt 中剔除系统中已存在的 ASIN（与数据审核页 media/file 目录一致）。"""
from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from auto_amazon.asin_dedupe import filter_new_asins, parse_asin_text


class Command(BaseCommand):
    help = (
        '读取 asins.txt，剔除系统中已存在的 ASIN，写回剩余项。'
        '默认以 media/file/{ASIN}/ 目录是否存在为准（与数据审核页搜索一致）。'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            'input_file',
            help='ASIN 列表文件路径（每行一个 ASIN，或逗号/空格分隔）',
        )
        parser.add_argument(
            '--output',
            '-o',
            help='输出文件；默认原地覆盖 input_file',
        )
        parser.add_argument(
            '--removed',
            '-r',
            help='将被剔除的已存在 ASIN 写入此文件（每行一个）',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='只统计，不写文件',
        )
        parser.add_argument(
            '--include-dashboard',
            action='store_true',
            help='除 media/file 目录外，看板 AsinDashboardRow 有记录也算已存在',
        )

    def handle(self, *args, **options):
        input_path = Path(options['input_file']).expanduser().resolve()
        if not input_path.is_file():
            raise CommandError(f'文件不存在：{input_path}')

        asins = parse_asin_text(input_path.read_text(encoding='utf-8'))
        if not asins:
            self.stdout.write(self.style.WARNING('输入文件中没有有效 ASIN'))
            return

        result = filter_new_asins(
            asins,
            include_dashboard=bool(options['include_dashboard']),
        )

        self.stdout.write(f'输入文件：{input_path}')
        self.stdout.write(f'读取有效 ASIN：{result.total_raw} 个（去重后 {result.total_unique} 个）')
        if result.duplicate_lines:
            self.stdout.write(
                self.style.WARNING(f'重复 ASIN 行：{result.duplicate_lines} 个（已忽略）')
            )
        self.stdout.write(
            f'已存在来源：media/file 目录（{result.existing_source_count} 个）'
        )
        self.stdout.write(self.style.WARNING(f'系统中已存在：{result.existing_count} 个'))
        self.stdout.write(self.style.SUCCESS(f'保留（新 ASIN）：{result.keep_count} 个'))

        if options['dry_run']:
            self.stdout.write(self.style.NOTICE('dry-run：未写入任何文件'))
            if result.removed:
                preview = ', '.join(result.removed[:10])
                suffix = '…' if len(result.removed) > 10 else ''
                self.stdout.write(f'将剔除示例：{preview}{suffix}')
            return

        output_path = (
            Path(options['output']).expanduser().resolve()
            if options.get('output')
            else input_path
        )
        output_path.write_text(result.keep_text, encoding='utf-8')
        self.stdout.write(f'已写入：{output_path}')

        removed_path = options.get('removed')
        if removed_path:
            rp = Path(removed_path).expanduser().resolve()
            rp.write_text(result.removed_text, encoding='utf-8')
            self.stdout.write(f'已存在列表：{rp}')

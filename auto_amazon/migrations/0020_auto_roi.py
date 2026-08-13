from django.db import migrations, models
import django.db.models.deletion


def seed_roi_site_configs(apps, schema_editor):
    RoiSiteConfig = apps.get_model('auto_amazon', 'RoiSiteConfig')
    RoiSiteConfig.objects.update_or_create(
        marketplace='US',
        defaults={
            'platform_commission': 15.0,
            'default_refund_rate': 10.0,
            'default_fba_fee': 5.0,
            'default_unit_purchase': 10.0,
            'batch_size': 20,
            'asin_delay_min_sec': 1.0,
            'asin_delay_max_sec': 3.0,
            'batch_delay_min_sec': 4.0,
            'batch_delay_max_sec': 8.0,
            'max_ban_rotations_per_run': 30,
            'consecutive_fail_pause': 10,
            'max_ban_retries_per_asin': 3,
        },
    )
    RoiSiteConfig.objects.update_or_create(
        marketplace='UK',
        defaults={
            'platform_commission': 25.0,
            'default_refund_rate': 10.0,
            'default_fba_fee': 5.0,
            'default_unit_purchase': 10.0,
            'batch_size': 20,
            'asin_delay_min_sec': 1.0,
            'asin_delay_max_sec': 3.0,
            'batch_delay_min_sec': 4.0,
            'batch_delay_max_sec': 8.0,
            'max_ban_rotations_per_run': 30,
            'consecutive_fail_pause': 10,
            'max_ban_retries_per_asin': 3,
        },
    )


def unseed_roi_site_configs(apps, schema_editor):
    RoiSiteConfig = apps.get_model('auto_amazon', 'RoiSiteConfig')
    RoiSiteConfig.objects.filter(marketplace__in=['US', 'UK']).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('auto_amazon', '0019_marketplace_asin_root'),
    ]

    operations = [
        migrations.CreateModel(
            name='RoiSiteConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('marketplace', models.CharField(choices=[('US', '美国站'), ('UK', '英国站')], db_index=True, max_length=8, unique=True, verbose_name='站点')),
                ('platform_commission', models.FloatField(default=15.0, verbose_name='平台佣金(%)')),
                ('default_refund_rate', models.FloatField(default=10.0, verbose_name='默认退款率(%)')),
                ('default_fba_fee', models.FloatField(default=5.0, verbose_name='默认FBA($)')),
                ('default_unit_purchase', models.FloatField(default=10.0, verbose_name='默认采购价(￥)')),
                ('batch_size', models.PositiveIntegerField(default=20, verbose_name='批大小')),
                ('asin_delay_min_sec', models.FloatField(default=1.0, verbose_name='ASIN间隔最小秒')),
                ('asin_delay_max_sec', models.FloatField(default=3.0, verbose_name='ASIN间隔最大秒')),
                ('batch_delay_min_sec', models.FloatField(default=4.0, verbose_name='批间隔最小秒')),
                ('batch_delay_max_sec', models.FloatField(default=8.0, verbose_name='批间隔最大秒')),
                ('max_ban_rotations_per_run', models.PositiveIntegerField(default=30, verbose_name='单次跑最大换号次数')),
                ('consecutive_fail_pause', models.PositiveIntegerField(default=10, verbose_name='连续失败暂停阈值')),
                ('max_ban_retries_per_asin', models.PositiveIntegerField(default=3, verbose_name='单ASIN禁号重试')),
                ('exchange_rate_override', models.FloatField(blank=True, null=True, verbose_name='汇率覆盖')),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'ROI 站点定值',
                'verbose_name_plural': 'ROI 站点定值',
            },
        ),
        migrations.CreateModel(
            name='RoiAutoRun',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('marketplace', models.CharField(choices=[('US', '美国站'), ('UK', '英国站')], db_index=True, max_length=8, verbose_name='站点')),
                ('status', models.CharField(choices=[('running', '运行中'), ('paused', '已暂停'), ('stopped', '已停止'), ('done', '已完成'), ('error', '出错')], db_index=True, default='running', max_length=16)),
                ('total', models.PositiveIntegerField(default=0)),
                ('succeeded', models.PositiveIntegerField(default=0)),
                ('failed', models.PositiveIntegerField(default=0)),
                ('skipped', models.PositiveIntegerField(default=0)),
                ('current_asin', models.CharField(blank=True, max_length=32)),
                ('last_account', models.CharField(blank=True, max_length=128)),
                ('parity', models.FloatField(default=7.2, verbose_name='汇率')),
                ('done_asins', models.JSONField(blank=True, default=list)),
                ('ban_rotations', models.PositiveIntegerField(default=0)),
                ('consecutive_fails', models.PositiveIntegerField(default=0)),
                ('error_message', models.TextField(blank=True)),
                ('rq_job_id', models.CharField(blank=True, max_length=64)),
                ('started_at', models.DateTimeField(auto_now_add=True)),
                ('finished_at', models.DateTimeField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='roi_auto_runs', to='auth.user')),
            ],
            options={
                'verbose_name': '自动 ROI 任务',
                'verbose_name_plural': '自动 ROI 任务',
                'ordering': ['-started_at', '-id'],
            },
        ),
        migrations.CreateModel(
            name='RoiAutoRunLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('asin', models.CharField(db_index=True, max_length=32)),
                ('seq', models.PositiveIntegerField(default=0)),
                ('status', models.CharField(choices=[('success', '成功'), ('failed', '失败'), ('retry', '重试'), ('banned_rotated', '禁号换号')], max_length=16)),
                ('attempt', models.PositiveIntegerField(default=1)),
                ('account_username', models.CharField(blank=True, max_length=128)),
                ('duration_ms', models.PositiveIntegerField(blank=True, null=True)),
                ('error_summary', models.CharField(blank=True, max_length=500)),
                ('error_detail', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('run', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='logs', to='auto_amazon.roiautorun')),
            ],
            options={
                'verbose_name': '自动 ROI 日志',
                'verbose_name_plural': '自动 ROI 日志',
                'ordering': ['-created_at', '-id'],
            },
        ),
        migrations.AddIndex(
            model_name='roiautorun',
            index=models.Index(fields=['user', 'marketplace', 'status'], name='idx_roi_auto_user_mp_st'),
        ),
        migrations.RunPython(seed_roi_site_configs, unseed_roi_site_configs),
    ]

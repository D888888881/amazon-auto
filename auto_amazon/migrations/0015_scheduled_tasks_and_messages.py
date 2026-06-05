from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('auto_amazon', '0014_asindashboardrow_follow_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='asindashboardrow',
            name='last_scheduled_ad_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True, verbose_name='上次定时广告难度'),
        ),
        migrations.AddField(
            model_name='asindashboardrow',
            name='last_scheduled_roi_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True, verbose_name='上次定时ROI'),
        ),
        migrations.CreateModel(
            name='ScheduledJobLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('job_type', models.CharField(choices=[('roi', 'ROI'), ('ad_difficulty', '广告难度'), ('combined', '组合')], max_length=32)),
                ('status', models.CharField(choices=[('success', '成功'), ('partial', '部分成功'), ('failed', '失败'), ('skipped', '跳过')], max_length=16)),
                ('asin_list', models.JSONField(blank=True, default=list)),
                ('detail', models.TextField(blank=True)),
                ('started_at', models.DateTimeField(auto_now_add=True)),
                ('finished_at', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'verbose_name': '定时任务日志',
                'verbose_name_plural': '定时任务日志',
                'ordering': ['-started_at', '-id'],
            },
        ),
        migrations.CreateModel(
            name='ScheduledTaskMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('asin', models.CharField(db_index=True, max_length=32)),
                ('curr_ad_roi', models.FloatField(blank=True, null=True, verbose_name='当前去广告投产比')),
                ('curr_ad_difficulty', models.FloatField(blank=True, null=True, verbose_name='当前广告难度')),
                ('curr_ops_difficulty', models.FloatField(blank=True, null=True, verbose_name='当前运营难度')),
                ('latest_ad_roi', models.FloatField(blank=True, null=True, verbose_name='最新去广告投产比')),
                ('latest_ad_difficulty', models.FloatField(blank=True, null=True, verbose_name='最新广告难度')),
                ('latest_ops_difficulty', models.FloatField(blank=True, null=True, verbose_name='最新运营难度')),
                ('delta_ad_roi', models.FloatField(blank=True, null=True, verbose_name='对比去广告投产比')),
                ('delta_ad_difficulty', models.FloatField(blank=True, null=True, verbose_name='对比广告难度')),
                ('delta_ops_difficulty', models.FloatField(blank=True, null=True, verbose_name='对比运营难度')),
                ('delta_ad_roi_text', models.CharField(blank=True, max_length=32)),
                ('delta_ad_difficulty_text', models.CharField(blank=True, max_length=32)),
                ('delta_ops_difficulty_text', models.CharField(blank=True, max_length=32)),
                (
                    'alert_status',
                    models.CharField(
                        choices=[('normal', '未预警'), ('alert', '开始预警')],
                        default='normal',
                        max_length=16,
                    ),
                ),
                ('sent_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    'dashboard_row',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='schedule_messages',
                        to='auto_amazon.asindashboardrow',
                    ),
                ),
                (
                    'job_log',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='messages',
                        to='auto_amazon.scheduledjoblog',
                    ),
                ),
                (
                    'recipient',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='scheduled_task_messages',
                        to=settings.AUTH_USER_MODEL,
                        verbose_name='接收用户',
                    ),
                ),
            ],
            options={
                'verbose_name': '定时任务消息',
                'verbose_name_plural': '定时任务消息',
                'ordering': ['-sent_at', '-id'],
            },
        ),
    ]

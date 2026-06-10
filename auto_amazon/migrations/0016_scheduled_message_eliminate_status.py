from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('auto_amazon', '0015_scheduled_tasks_and_messages'),
    ]

    operations = [
        migrations.AlterField(
            model_name='scheduledtaskmessage',
            name='alert_status',
            field=models.CharField(
                choices=[
                    ('normal', '未预警'),
                    ('alert', '开始预警'),
                    ('eliminate', '立即淘汰'),
                ],
                default='normal',
                max_length=16,
            ),
        ),
    ]

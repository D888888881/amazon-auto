from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('auto_amazon', '0007_remove_review_interval_chart_json'),
    ]

    operations = [
        migrations.CreateModel(
            name='AsinFolderAssignment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('asin', models.CharField(db_index=True, max_length=32, unique=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                (
                    'assigned_by',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.SET_NULL,
                        related_name='asin_folder_assignments_created',
                        to=settings.AUTH_USER_MODEL,
                        verbose_name='分配人',
                    ),
                ),
                (
                    'assignees',
                    models.ManyToManyField(
                        blank=True,
                        related_name='asin_folder_assignments',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                'verbose_name': 'ASIN 文件夹分配',
                'verbose_name_plural': 'ASIN 文件夹分配',
            },
        ),
    ]

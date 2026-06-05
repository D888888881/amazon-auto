from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('auto_amazon', '0012_alter_importedmediapath_rel_path'),
    ]

    operations = [
        migrations.CreateModel(
            name='AsinUploadBatch',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('source_filename', models.CharField(blank=True, max_length=255, verbose_name='源文件名')),
                ('total_in_file', models.PositiveIntegerField(default=0, verbose_name='文件内 ASIN 数')),
                ('new_count', models.PositiveIntegerField(default=0, verbose_name='新增 ASIN 数')),
                ('skipped_count', models.PositiveIntegerField(default=0, verbose_name='跳过重复数')),
                ('is_downloaded', models.BooleanField(default=False, verbose_name='是否已下载')),
                ('downloaded_at', models.DateTimeField(blank=True, null=True, verbose_name='下载时间')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='上传时间')),
                (
                    'downloaded_by',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='asin_batch_downloads',
                        to=settings.AUTH_USER_MODEL,
                        verbose_name='下载人',
                    ),
                ),
                (
                    'user',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='asin_upload_batches',
                        to=settings.AUTH_USER_MODEL,
                        verbose_name='上传用户',
                    ),
                ),
            ],
            options={
                'verbose_name': 'ASIN 上传批次',
                'verbose_name_plural': 'ASIN 上传批次',
                'ordering': ['-created_at', '-id'],
            },
        ),
        migrations.CreateModel(
            name='AsinCatalogItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('asin', models.CharField(db_index=True, max_length=32, unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                (
                    'batch',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='items',
                        to='auto_amazon.asinuploadbatch',
                        verbose_name='所属批次',
                    ),
                ),
                (
                    'uploaded_by',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='asin_catalog_items',
                        to=settings.AUTH_USER_MODEL,
                        verbose_name='上传用户',
                    ),
                ),
            ],
            options={
                'verbose_name': 'ASIN 库条目',
                'verbose_name_plural': 'ASIN 库条目',
                'ordering': ['-created_at', 'asin'],
            },
        ),
    ]

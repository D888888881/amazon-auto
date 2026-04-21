# Generated manually for ImportedMediaPath

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('auto_amazon', '0010_asindataupdatestamp'),
    ]

    operations = [
        migrations.CreateModel(
            name='ImportedMediaPath',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('rel_path', models.CharField(db_index=True, max_length=512, unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                (
                    'user',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='imported_media_paths',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                'verbose_name': '导入文件路径',
                'verbose_name_plural': '导入文件路径',
            },
        ),
    ]

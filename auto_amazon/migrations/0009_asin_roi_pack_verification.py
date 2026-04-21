# Generated manually for AsinRoiPackVerification

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('auto_amazon', '0008_asin_folder_assignment'),
    ]

    operations = [
        migrations.CreateModel(
            name='AsinRoiPackVerification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('asin', models.CharField(db_index=True, max_length=32, unique=True)),
                ('verified_at', models.DateTimeField(auto_now=True)),
                (
                    'verified_by',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='roi_pack_verifications',
                        to=settings.AUTH_USER_MODEL,
                        verbose_name='确认人',
                    ),
                ),
            ],
            options={
                'verbose_name': 'ROI 表校验确认',
                'verbose_name_plural': 'ROI 表校验确认',
            },
        ),
    ]

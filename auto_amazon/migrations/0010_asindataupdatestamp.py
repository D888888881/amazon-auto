# Generated manually for AsinDataUpdateStamp

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('auto_amazon', '0009_asin_roi_pack_verification'),
    ]

    operations = [
        migrations.CreateModel(
            name='AsinDataUpdateStamp',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('asin', models.CharField(db_index=True, max_length=32, unique=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'ASIN 数据更新时间',
                'verbose_name_plural': 'ASIN 数据更新时间',
            },
        ),
    ]


# MySQL：unique CharField 建议 max_length<=255（Django 文档 mysql.W003）

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('auto_amazon', '0011_importedmediapath'),
    ]

    operations = [
        migrations.AlterField(
            model_name='importedmediapath',
            name='rel_path',
            field=models.CharField(db_index=True, max_length=255, unique=True),
        ),
    ]

# Generated manually for marketplace separation on imports / catalog

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('auto_amazon', '0017_asindashboardrow_marketplace'),
    ]

    operations = [
        migrations.AddField(
            model_name='importedmediapath',
            name='marketplace',
            field=models.CharField(
                choices=[('US', '美国站'), ('UK', '英国站')],
                db_index=True,
                default='US',
                max_length=8,
                verbose_name='站点',
            ),
        ),
        migrations.AddField(
            model_name='asinuploadbatch',
            name='marketplace',
            field=models.CharField(
                choices=[('US', '美国站'), ('UK', '英国站')],
                db_index=True,
                default='US',
                max_length=8,
                verbose_name='站点',
            ),
        ),
        migrations.AddField(
            model_name='asincatalogitem',
            name='marketplace',
            field=models.CharField(
                choices=[('US', '美国站'), ('UK', '英国站')],
                db_index=True,
                default='US',
                max_length=8,
                verbose_name='站点',
            ),
        ),
        # Drop old single-column unique indexes before composite unique constraints.
        migrations.AlterField(
            model_name='importedmediapath',
            name='rel_path',
            field=models.CharField(db_index=True, max_length=255),
        ),
        migrations.AlterField(
            model_name='asincatalogitem',
            name='asin',
            field=models.CharField(db_index=True, max_length=32),
        ),
        migrations.AddConstraint(
            model_name='importedmediapath',
            constraint=models.UniqueConstraint(
                fields=('rel_path', 'marketplace'),
                name='uniq_imported_media_path_marketplace',
            ),
        ),
        migrations.AddConstraint(
            model_name='asincatalogitem',
            constraint=models.UniqueConstraint(
                fields=('asin', 'marketplace'),
                name='uniq_asin_catalog_asin_marketplace',
            ),
        ),
    ]

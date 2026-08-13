# Generated manually for MarketplaceAsinRoot materialization

from django.db import migrations, models
import re


_ASIN_RE = re.compile(r'^B0[A-Z0-9]{8}$', re.IGNORECASE)


def _backfill_roots(apps, schema_editor):
    ImportedMediaPath = apps.get_model('auto_amazon', 'ImportedMediaPath')
    MarketplaceAsinRoot = apps.get_model('auto_amazon', 'MarketplaceAsinRoot')
    seen: set[tuple[str, str]] = set()
    rows = []
    for rel_path, marketplace in ImportedMediaPath.objects.values_list('rel_path', 'marketplace').iterator(
        chunk_size=2000
    ):
        seg = str(rel_path).replace('\\', '/').strip('/').split('/')[0].strip().upper()
        if not _ASIN_RE.match(seg):
            continue
        mp = (marketplace or 'US').strip().upper() or 'US'
        key = (mp, seg)
        if key in seen:
            continue
        seen.add(key)
        rows.append(MarketplaceAsinRoot(marketplace=mp, asin=seg))
        if len(rows) >= 500:
            MarketplaceAsinRoot.objects.bulk_create(rows, ignore_conflicts=True)
            rows = []
    if rows:
        MarketplaceAsinRoot.objects.bulk_create(rows, ignore_conflicts=True)


def _noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('auto_amazon', '0018_import_catalog_marketplace'),
    ]

    operations = [
        migrations.CreateModel(
            name='MarketplaceAsinRoot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('marketplace', models.CharField(choices=[('US', '美国站'), ('UK', '英国站')], db_index=True, max_length=8, verbose_name='站点')),
                ('asin', models.CharField(db_index=True, max_length=32)),
                ('first_imported_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': '站点 ASIN 根',
                'verbose_name_plural': '站点 ASIN 根',
            },
        ),
        migrations.AddConstraint(
            model_name='marketplaceasinroot',
            constraint=models.UniqueConstraint(fields=('marketplace', 'asin'), name='uniq_marketplace_asin_root'),
        ),
        migrations.AddIndex(
            model_name='marketplaceasinroot',
            index=models.Index(fields=['marketplace', 'asin'], name='idx_mp_asin_root_mp_asin'),
        ),
        migrations.RunPython(_backfill_roots, _noop_reverse),
    ]

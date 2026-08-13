# Generated manually for multi-user ROI verify + global passed flag

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def forwards_migrate_verifications(apps, schema_editor):
    Row = apps.get_model('auto_amazon', 'AsinRoiPackVerification')
    User = apps.get_model(settings.AUTH_USER_MODEL)
    fallback = User.objects.filter(is_superuser=True).order_by('id').first()
    if fallback is None:
        fallback = User.objects.order_by('id').first()
    if fallback is None:
        return
    for row in Row.objects.all().iterator():
        uid = getattr(row, 'user_id', None) or getattr(row, 'verified_by_id', None) or fallback.id
        mp = getattr(row, 'marketplace', None) or 'US'
        if mp not in ('US', 'UK'):
            mp = 'US'
        Row.objects.filter(pk=row.pk).update(user_id=uid, marketplace=mp)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('auto_amazon', '0020_auto_roi'),
    ]

    operations = [
        migrations.CreateModel(
            name='AsinPassedFlag',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('asin', models.CharField(db_index=True, max_length=32)),
                (
                    'marketplace',
                    models.CharField(
                        choices=[('US', '美国站'), ('UK', '英国站')],
                        db_index=True,
                        default='US',
                        max_length=8,
                        verbose_name='站点',
                    ),
                ),
                ('passed_at', models.DateTimeField(auto_now=True)),
                (
                    'passed_by',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='asin_passed_flags',
                        to=settings.AUTH_USER_MODEL,
                        verbose_name='标记人',
                    ),
                ),
            ],
            options={
                'verbose_name': 'ASIN 已通过',
                'verbose_name_plural': 'ASIN 已通过',
            },
        ),
        migrations.AddConstraint(
            model_name='asinpassedflag',
            constraint=models.UniqueConstraint(
                fields=('asin', 'marketplace'),
                name='uniq_asin_passed_asin_mp',
            ),
        ),
        migrations.AddField(
            model_name='asinroipackverification',
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
            model_name='asinroipackverification',
            name='user',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='roi_pack_verifications_v2',
                to=settings.AUTH_USER_MODEL,
                verbose_name='校验人',
            ),
        ),
        migrations.RunPython(forwards_migrate_verifications, noop_reverse),
        migrations.RemoveField(
            model_name='asinroipackverification',
            name='verified_by',
        ),
        migrations.AlterField(
            model_name='asinroipackverification',
            name='user',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='roi_pack_verifications',
                to=settings.AUTH_USER_MODEL,
                verbose_name='校验人',
            ),
        ),
        migrations.AlterField(
            model_name='asinroipackverification',
            name='asin',
            field=models.CharField(db_index=True, max_length=32),
        ),
        migrations.AddConstraint(
            model_name='asinroipackverification',
            constraint=models.UniqueConstraint(
                fields=('user', 'asin', 'marketplace'),
                name='uniq_roi_verify_user_asin_mp',
            ),
        ),
        migrations.AddIndex(
            model_name='asinroipackverification',
            index=models.Index(fields=['asin', 'marketplace'], name='idx_roi_verify_asin_mp'),
        ),
        migrations.AddIndex(
            model_name='asinroipackverification',
            index=models.Index(fields=['user', 'marketplace'], name='idx_roi_verify_user_mp'),
        ),
    ]

# Generated manually for marketplace support

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('auto_amazon', '0016_scheduled_message_eliminate_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='asindashboardrow',
            name='marketplace',
            field=models.CharField(
                choices=[('US', '美国站'), ('UK', '英国站')],
                db_index=True,
                default='US',
                max_length=8,
                verbose_name='站点',
            ),
        ),
        migrations.RemoveConstraint(
            model_name='asindashboardrow',
            name='uniq_asin_dashboard_user_asin',
        ),
        migrations.AddConstraint(
            model_name='asindashboardrow',
            constraint=models.UniqueConstraint(
                fields=('user', 'asin', 'marketplace'),
                name='uniq_asin_dashboard_user_asin_marketplace',
            ),
        ),
    ]

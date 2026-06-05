from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('auto_amazon', '0013_asin_upload_batch'),
    ]

    operations = [
        migrations.AddField(
            model_name='asindashboardrow',
            name='follow_status',
            field=models.CharField(
                choices=[('normal', '未关注'), ('priority', '重点关注')],
                db_index=True,
                default='normal',
                max_length=16,
                verbose_name='关注',
            ),
        ),
    ]

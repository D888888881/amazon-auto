from django.apps import AppConfig


class AutoAmazonConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'auto_amazon'

    def ready(self):
        import auto_amazon.signals  # noqa: F401

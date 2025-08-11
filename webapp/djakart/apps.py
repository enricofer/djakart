from django.apps import AppConfig


class VersioniConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'djakart'
    def ready(self):
        import djakart.signals

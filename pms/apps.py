from django.apps import AppConfig


class PmsConfig(AppConfig):
    name = 'pms'
from django.apps import AppConfig

class PmsConfig(AppConfig):
    name = "pms"

    def ready(self):
        import pms.signals

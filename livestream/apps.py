from django.apps import AppConfig


class LivestreamConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "livestream"

    def ready(self):
        import livestream.signals.livestream_signals
        import livestream.signals.message_signals
        import livestream.signals.moderation_signals
        import livestream.signals.participant_signals
        import livestream.signals.reaction_signals

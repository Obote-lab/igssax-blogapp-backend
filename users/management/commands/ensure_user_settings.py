from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from users.models import UserSettings

User = get_user_model()


class Command(BaseCommand):
    help = "Ensure all users have UserSettings objects"

    def handle(self, *args, **options):
        created_count = 0
        for user in User.objects.all():
            settings, created = UserSettings.objects.get_or_create(user=user)
            if created:
                created_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Ensured settings for all users. Created {created_count} new settings objects."
            )
        )

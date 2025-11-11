from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from livestream.models import LiveStream


class Command(BaseCommand):
    help = "Clean up old ended streams"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Delete streams ended more than X days ago (default: 30)",
        )

    def handle(self, *args, **options):
        days = options["days"]
        cutoff_date = timezone.now() - timedelta(days=days)

        old_streams = LiveStream.objects.filter(
            status=LiveStream.StreamStatus.ENDED, ended_at__lt=cutoff_date
        )

        count = old_streams.count()
        old_streams.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully deleted {count} streams older than {days} days"
            )
        )

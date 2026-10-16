from django.core.management.base import BaseCommand

from users.models import Follow, Friendship, User


class Command(BaseCommand):
    help = "Recalculate followers, following, and friends counts"

    def handle(self, *args, **kwargs):
        for user in User.objects.all():
            profile = user.profile

            profile.followers_count = Follow.objects.filter(following=user).count()
            profile.following_count = Follow.objects.filter(follower=user).count()
            profile.friends_count = (
                Friendship.objects.filter(status=Friendship.Status.ACCEPTED)
                .filter(requester=user)
                .count()
                + Friendship.objects.filter(
                    status=Friendship.Status.ACCEPTED, receiver=user
                ).count()
            )

            profile.save()

        self.stdout.write(self.style.SUCCESS("Counts recalculated"))

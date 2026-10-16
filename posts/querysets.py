from django.db.models import Q

from users.models import Friendship


def visible_posts_for_user(user):
    """
    Returns a Q object representing posts visible to the given user.
    """
    if not user.is_authenticated:
        return Q(privacy="public")

    friend_ids = (
        Friendship.objects.filter(status=Friendship.Status.ACCEPTED)
        .filter(Q(requester=user) | Q(receiver=user))
        .values_list("requester_id", "receiver_id")
    )

    friend_ids = set(sum(friend_ids, ())) - {user.id}

    return (
        Q(privacy="public")
        | Q(author=user)
        | Q(privacy="friends_only", author_id__in=friend_ids)
    )

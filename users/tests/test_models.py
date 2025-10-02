import pytest
from django.contrib.auth import get_user_model

from users.models import Profile

User = get_user_model()


@pytest.mark.django_db
def test_create_user_and_profile():
    user = User.objects.create_user(email="test@example.com", password="strongpass123")
    assert user.email == "test@example.com"
    assert user.check_password("strongpass123")

    profile = Profile.objects.get(user=user)
    assert profile.user == user

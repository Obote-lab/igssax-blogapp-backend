import pytest
from django.contrib.auth import get_user_model

from users.models import Profile

User = get_user_model()


@pytest.fixture
def user_factory(db):
    """Factory for creating test users with profile"""

    def create_user(**kwargs):
        email = kwargs.get("email", "testuser@example.com")
        password = kwargs.get("password", "testpass123")
        first_name = kwargs.get("first_name", "Test")
        last_name = kwargs.get("last_name", "User")

        user = User.objects.create_user(
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
        )
        # ensure profile exists
        Profile.objects.get_or_create(user=user)
        return user

    return create_user

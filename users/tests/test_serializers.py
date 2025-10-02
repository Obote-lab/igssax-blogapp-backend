import pytest
from django.contrib.auth import get_user_model
from rest_framework.exceptions import ValidationError

from users.api.serializers import (ChangePasswordSerializer,
                                   GoogleLoginSuccessSerializer,
                                   GoogleSignUpSerializer,
                                   UserRegisterSerializer, UserSerializer)
from users.models import Profile

User = get_user_model()


@pytest.mark.django_db
def test_user_register_serializer_creates_user():
    data = {
        "email": "newuser@example.com",
        "first_name": "New",
        "last_name": "User",
        "password": "newstrongpass123",
    }
    serializer = UserRegisterSerializer(data=data)
    assert serializer.is_valid(), serializer.errors
    user = serializer.save()
    assert user.email == "newuser@example.com"
    assert Profile.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_change_password_serializer_validates_old_password(user_factory):
    user = user_factory(password="oldpassword123")
    serializer = ChangePasswordSerializer(
        data={
            "old_password": "oldpassword123",
            "new_password": "newpassword456",
            "new_password2": "newpassword456",
        },
        context={"request": type("obj", (), {"user": user})},
    )
    assert serializer.is_valid()


@pytest.mark.django_db
def test_google_signup_serializer_requires_token():
    serializer = GoogleSignUpSerializer(data={"email": "test@gmail.com"})
    assert not serializer.is_valid()
    assert "access_token" in serializer.errors


@pytest.mark.django_db
def test_google_login_success_serializer():
    data = {
        "user": {"id": 999, "email": "googleuser@example.com"},
        "google_id": "google-123",
    }
    serializer = GoogleLoginSuccessSerializer(data=data)
    assert serializer.is_valid(), serializer.errors

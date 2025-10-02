import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

User = get_user_model()


@pytest.mark.django_db
def test_register_view_creates_user():
    client = APIClient()
    url = reverse("register")
    data = {
        "email": "regtest@example.com",
        "first_name": "Reg",
        "last_name": "Test",
        "password": "testpass123",
    }
    response = client.post(url, data, format="json")
    assert response.status_code == status.HTTP_201_CREATED
    assert User.objects.filter(email="regtest@example.com").exists()


@pytest.mark.django_db
def test_login_returns_tokens(user_factory):
    user = user_factory(password="password123")
    client = APIClient()
    url = reverse("token_obtain_pair")
    response = client.post(
        url, {"email": user.email, "password": "password123"}, format="json"
    )
    assert "access" in response.data
    assert "refresh" in response.data


@pytest.mark.django_db
def test_user_profile_update(user_factory):
    user = user_factory()
    client = APIClient()
    client.force_authenticate(user=user)
    url = reverse("profile_update")

    response = client.patch(
        url, {"first_name": "UpdatedFirst", "last_name": "UpdatedLast"}, format="json"
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["profile"]["first_name"] == "UpdatedFirst"
    assert response.data["profile"]["last_name"] == "UpdatedLast"


@pytest.mark.django_db
def test_password_change(user_factory):
    user = user_factory(password="oldpass123")
    client = APIClient()
    client.force_authenticate(user=user)
    url = reverse("password_change")
    response = client.post(
        url,
        {
            "old_password": "oldpass123",
            "new_password": "newpass456",
            "new_password2": "newpass456",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_user_viewset_returns_authenticated_user(user_factory):
    user = user_factory()
    client = APIClient()
    client.force_authenticate(user=user)
    url = reverse("users-list")
    response = client.get(url)
    assert response.status_code == status.HTTP_200_OK
    assert response.data["results"][0]["email"] == user.email

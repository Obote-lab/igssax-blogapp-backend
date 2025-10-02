from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from .api.viewsets import (FriendshipViewSet, GoogleLoginView,
                           GoogleSignUpView, MyTokenObtainPairView,
                           PasswordChange, PasswordResetConfirmView,
                           PasswordResetRequestView, RegisterView,
                           SettingsViewSet, UserProfileUpdate, UserViewSet)

router = DefaultRouter()
router.register(r"users", UserViewSet, basename="users")
router.register(r"friendships", FriendshipViewSet, basename="friendships")

settings_viewset = SettingsViewSet.as_view(
    {
        "get": "retrieve",
        "patch": "partial_update",
    }
)

urlpatterns = [
    # JWT Auth
    path("auth/login/", MyTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    # Registration
    path("auth/register/", RegisterView.as_view(), name="register"),
    # Profile
    path("auth/profile/update/", UserProfileUpdate.as_view(), name="profile_update"),
    path("settings/", settings_viewset, name="user_settings"),
    # Password
    path("auth/password/change/", PasswordChange.as_view(), name="password_change"),
    path("auth/password/reset/",PasswordResetRequestView.as_view(),name="password_reset",),
    path("auth/password/reset/confirm/<str:uidb64>/<str:token>/",PasswordResetConfirmView.as_view(),name="password_reset_confirm", ),
    # Google OAuth
    path("auth/google/login/", GoogleLoginView.as_view(), name="google_login"),
    path("auth/google/signup/", GoogleSignUpView.as_view(), name="google_signup"),
    # Router endpoints (/users/, /friendships/) - ONLY ONCE
    path("", include(router.urls)),
]

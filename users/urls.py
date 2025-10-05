from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from .api.viewsets import (FriendshipViewSet, GoogleLoginView,
                           GoogleSignUpView, MyTokenObtainPairView,
                           PasswordChange, PasswordResetConfirmView,
                           PasswordResetRequestView, RegisterView,
                           SettingsViewSet, UserProfileUpdate, UserViewSet,
                           AccountUpdateView, BlockedUsersViewSet, PrivacySettingsView)

router = DefaultRouter()
router.register(r"users", UserViewSet, basename="users")
router.register(r"friendships", FriendshipViewSet, basename="friendships")
router.register(r"blocked-users", BlockedUsersViewSet, basename="blocked-users")

settings_viewset = SettingsViewSet.as_view(
    {
        "get": "retrieve",
        "patch": "partial_update",
    }
)

urlpatterns = [
    # Auth endpoints - consistent with frontend expectations
    path("auth/login/", MyTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("auth/register/", RegisterView.as_view(), name="register"),
    
    # Password management
    path("auth/password/change/", PasswordChange.as_view(), name="password_change"),
    path("auth/password/reset/", PasswordResetRequestView.as_view(), name="password_reset"),
    path("auth/password/reset/confirm/<str:uidb64>/<str:token>/", 
         PasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    
    # Google OAuth
    path("auth/google/login/", GoogleLoginView.as_view(), name="google_login"),
    path("auth/google/signup/", GoogleSignUpView.as_view(), name="google_signup"),
    
    # User profile & settings
    path("user/me/", AccountUpdateView.as_view(), name="account-update"),
    path("user/profile/update/", UserProfileUpdate.as_view(), name="profile_update"),
    path("settings/", settings_viewset, name="user_settings"),

    path("privacy-settings/", PrivacySettingsView.as_view(), name="privacy-settings"),
    
    # Include router URLs (users/, friendships/)
    path("", include(router.urls)),
]



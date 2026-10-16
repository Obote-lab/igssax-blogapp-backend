from rest_framework_simplejwt.tokens import RefreshToken


def build_token_response(user):
    """
    Standard JWT response used across the entire backend.
    """
    refresh = RefreshToken.for_user(user)

    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "access_expires": int(refresh.access_token.lifetime.total_seconds()),
        "refresh_expires": int(refresh.lifetime.total_seconds()),
    }

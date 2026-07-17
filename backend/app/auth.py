import secrets
from typing import Annotated

from fastapi import Header, HTTPException, status

from .config import get_settings


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized",
        headers={
            "WWW-Authenticate": "Bearer",
            "Cache-Control": "no-store",
        },
    )


async def require_cron_secret(
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    if authorization is None:
        raise _unauthorized()

    scheme, separator, supplied_secret = authorization.partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not supplied_secret:
        raise _unauthorized()

    expected_secret = get_settings().cron_secret.get_secret_value()
    if not secrets.compare_digest(supplied_secret, expected_secret):
        raise _unauthorized()

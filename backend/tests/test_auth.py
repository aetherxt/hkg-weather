import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import SecretStr

from app import auth


def install_settings(monkeypatch: pytest.MonkeyPatch, secret: str) -> None:
    settings = SimpleNamespace(cron_secret=SecretStr(secret))
    monkeypatch.setattr(auth, "get_settings", lambda: settings)


def test_cron_secret_accepts_valid_bearer_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_settings(monkeypatch, "a" * 32)

    asyncio.run(auth.require_cron_secret(f"Bearer {'a' * 32}"))


@pytest.mark.parametrize(
    "authorization",
    [
        None,
        "",
        "Basic credentials",
        "Bearer",
        "Bearer incorrect-secret",
    ],
)
def test_cron_secret_rejects_invalid_authorization(
    monkeypatch: pytest.MonkeyPatch,
    authorization: str | None,
) -> None:
    install_settings(monkeypatch, "a" * 32)

    with pytest.raises(HTTPException) as error:
        asyncio.run(auth.require_cron_secret(authorization))

    assert error.value.status_code == 401
    assert error.value.detail == "Unauthorized"
    assert error.value.headers == {
        "WWW-Authenticate": "Bearer",
        "Cache-Control": "no-store",
    }

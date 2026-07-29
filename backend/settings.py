"""Shared runtime settings loaded from backend/.env."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent


def load_backend_env() -> None:
    load_dotenv(BASE_DIR / ".env", override=False)


load_backend_env()


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def csv_env(name: str) -> set[str]:
    return {
        item.strip().lower()
        for item in os.getenv(name, "").split(",")
        if item.strip()
    }


def is_summary_paywall_disabled() -> bool:
    return env_bool("DISABLE_SUMMARY_PAYWALL") or env_bool("SUMMARY_PAYWALL_DISABLED")


def is_superuser_email(email: str | None) -> bool:
    if not email:
        return False
    normalized = email.strip().lower()
    builtin_email = os.getenv("BUILTIN_ACCOUNT_EMAIL", "").strip().lower()
    return normalized == builtin_email or normalized in csv_env("SUPERUSER_EMAILS")


def is_registration_enabled() -> bool:
    return env_bool("REGISTRATION_ENABLED", default=False)


def get_builtin_account_config() -> tuple[str, str]:
    return (
        os.getenv("BUILTIN_ACCOUNT_EMAIL", "").strip().lower(),
        os.getenv("BUILTIN_ACCOUNT_PASSWORD", ""),
    )


def is_payment_enabled() -> bool:
    return env_bool("PAYMENT_ENABLED", default=True)

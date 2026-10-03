"""
Django settings for the Mart POS backend.

Environment variables:
    DJANGO_SECRET_KEY   Secret key (required in production)
    DJANGO_DEBUG        "1" (default) or "0"
    DJANGO_ALLOWED_HOSTS Comma-separated list, default "*"
    DATABASE_URL        sqlite:///db.sqlite3 (default) or
                        postgres://user:pass@host:5432/dbname
    WHATSAPP_PROVIDER   "dummy" (default) or "meta"
    WHATSAPP_TOKEN      Meta Cloud API token (when provider=meta)
    WHATSAPP_PHONE_NUMBER_ID  Meta phone number ID (when provider=meta)
"""
import os
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "django-insecure-dev-only-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = [
    h.strip()
    for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",")
    if h.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "rest_framework.authtoken",
    "tenants",
    "catalog",
    "inventory",
    "billing",
    "khata",
    "notifications",
    "reports",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

AUTH_USER_MODEL = "tenants.User"


def _parse_database_url(url: str) -> dict:
    if url.startswith("postgres://") or url.startswith("postgresql://"):
        p = urlparse(url)
        return {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": (p.path or "").lstrip("/"),
            "USER": p.username or "",
            "PASSWORD": p.password or "",
            "HOST": p.hostname or "",
            "PORT": str(p.port or 5432),
        }
    # sqlite:///relative/path.db  or  sqlite:////absolute/path.db
    path = url.split("sqlite:///", 1)[1] if "sqlite:///" in url else "db.sqlite3"
    if not os.path.isabs(path):
        path = str(BASE_DIR / path)
    return {"ENGINE": "django.db.backends.sqlite3", "NAME": path}


DATABASES = {
    "default": _parse_database_url(os.environ.get("DATABASE_URL", "sqlite:///db.sqlite3"))
}

AUTH_PASSWORD_VALIDATORS = [] if DEBUG else [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Karachi"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
}

# Dev convenience: the React dev server talks to this API cross-origin.
CORS_ALLOW_ALL_ORIGINS = DEBUG

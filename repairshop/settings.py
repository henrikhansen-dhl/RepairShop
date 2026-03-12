import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def load_local_env_file() -> None:
    """Load key/value pairs from .env for local development."""
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


load_local_env_file()

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "replace-me")


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


# Local dev default is True so Django can serve static assets (including admin CSS).
DEBUG = env_bool("DJANGO_DEBUG", default=True)
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "jazzmin",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "shops",
    # Add your tenant-domain apps here (e.g. "repairs", "inventory").
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Keep this after AuthenticationMiddleware so request.user is available.
    "repairshop.middleware.TenantDatabaseMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "repairshop.urls"
WSGI_APPLICATION = "repairshop.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "repairshop.context_processors.shop_branding",
            ],
        },
    },
]

# Apps that must always use the shared/default database.
SHARED_APPS = {
    "admin",
    "auth",
    "contenttypes",
    "sessions",
    "messages",
    "staticfiles",
    "shops",
}


# PythonAnywhere MySQL example:
# Host often looks like: <username>.mysql.pythonanywhere-services.com
# DB names often look like: <username>$<dbname>
# Update env vars to match your account.
def mysql_db(name_env: str):
    return {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.getenv(name_env, ""),
        "USER": os.getenv("PA_DB_USER", ""),
        "PASSWORD": os.getenv("PA_DB_PASSWORD", ""),
        "HOST": os.getenv("PA_DB_HOST", ""),
        "PORT": os.getenv("PA_DB_PORT", "3306"),
        "OPTIONS": {
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        },
    }


def sqlite_db(filename: str):
    return {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / filename,
    }


required_mysql_env = [
    "PA_DB_HOST",
    "PA_DB_USER",
    "PA_DB_PASSWORD",
    "PA_DEFAULT_DB_NAME",
]
use_mysql = all(os.getenv(name) for name in required_mysql_env)

if use_mysql:
    DATABASES = {
        # Shared DB: auth/users/shop metadata.
        "default": mysql_db("PA_DEFAULT_DB_NAME"),

        # Pre-registered tenant DB aliases.
        "shop1_db": mysql_db("PA_SHOP1_DB_NAME"),
        "shop2_db": mysql_db("PA_SHOP2_DB_NAME"),
    }
else:
    # Local development fallback: no external DB credentials required.
    DATABASES = {
        "default": sqlite_db("db.sqlite3"),
        "shop1_db": sqlite_db("shop1.sqlite3"),
        "shop2_db": sqlite_db("shop2.sqlite3"),
    }


# Optional dynamic registration: add aliases discovered at startup.
# Format in env var TENANT_DB_ALIASES: shop3_db,shop4_db
for alias in [x.strip() for x in os.getenv("TENANT_DB_ALIASES", "").split(",") if x.strip()]:
    if use_mysql:
        env_name = f"PA_{alias.upper()}_NAME"
        DATABASES.setdefault(alias, mysql_db(env_name))
    else:
        DATABASES.setdefault(alias, sqlite_db(f"{alias}.sqlite3"))

DATABASE_ROUTERS = ["repairshop.db_router.TenantDatabaseRouter"]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "shop_dashboard"
LOGOUT_REDIRECT_URL = "landing"

JAZZMIN_SETTINGS = {
    "site_title": "RepairShop Admin",
    "site_header": "RepairShop",
    "site_brand": "RepairShop Admin",
    "site_logo_classes": "img-circle",
    "welcome_sign": "RepairShop administration",
    "copyright": "RepairShop",
    "search_model": [
        "auth.User",
        "shops.ShopProfile",
        "shops.ShopUserAccess",
        "shops.Customer",
        "shops.Invoice",
        "shops.RepairWorkOrder",
    ],
    "topmenu_links": [
        {"name": "Dashboard", "url": "admin:index", "permissions": ["auth.view_user"]},
        {"model": "auth.User"},
        {"app": "shops"},
    ],
    "icons": {
        "auth": "fas fa-users-cog",
        "auth.user": "fas fa-user",
        "shops.ShopProfile": "fas fa-store",
        "shops.ShopUserAccess": "fas fa-user-shield",
        "shops.ShopMasterData": "fas fa-id-card",
        "shops.Customer": "fas fa-address-book",
        "shops.CustomerCar": "fas fa-car",
        "shops.Invoice": "fas fa-file-invoice-dollar",
        "shops.InvoiceLine": "fas fa-receipt",
        "shops.InvoicePriceItem": "fas fa-tags",
        "shops.InvoiceNumberSeries": "fas fa-hashtag",
        "shops.RepairWorkOrder": "fas fa-screwdriver-wrench",
        "shops.RepairWorkOrderLine": "fas fa-list-check",
    },
    "navigation_expanded": True,
    "show_sidebar": True,
    "theme": "flatly",
}

JAZZMIN_UI_TWEAKS = {
    "theme": "flatly",
    "dark_mode_theme": "flatly",
    "navbar": "navbar-white navbar-light",
    "accent": "accent-info",
    "sidebar": "sidebar-light-info",
    "brand_colour": "navbar-info",
    "button_classes": {
        "primary": "btn-info",
        "secondary": "btn-outline-secondary",
        "info": "btn-outline-info",
        "warning": "btn-warning",
        "danger": "btn-danger",
        "success": "btn-success",
    },
}

LANGUAGE_CODE = "en"
LANGUAGES = [
    ("en", "English"),
    ("da", "Danish"),
    ("de", "German"),
]
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Email settings for invoice delivery
EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND",
    "django.core.mail.backends.filebased.EmailBackend" if DEBUG else "django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", default=True)
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", default=False)
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "no-reply@repairshop.local")
EMAIL_FILE_PATH = BASE_DIR / "tmp" / "sent_emails"

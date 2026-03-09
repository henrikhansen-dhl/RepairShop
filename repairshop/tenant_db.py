import os
from copy import deepcopy
from pathlib import Path

from django.conf import settings


def ensure_tenant_database_alias(alias: str) -> None:
    """
    Register a tenant DB alias at runtime if it is missing.

    Local development uses sqlite files per tenant alias.
    For MySQL, this expects an env variable: PA_<ALIAS>_NAME.
    """
    if not alias or alias in settings.DATABASES:
        return

    default_engine = settings.DATABASES["default"].get("ENGINE", "")
    default_cfg = deepcopy(settings.DATABASES["default"])

    if default_engine.endswith("sqlite3"):
        db_path = Path(settings.BASE_DIR) / f"{alias}.sqlite3"
        default_cfg["ENGINE"] = "django.db.backends.sqlite3"
        default_cfg["NAME"] = db_path
        settings.DATABASES[alias] = default_cfg
        return

    env_name = f"PA_{alias.upper()}_NAME"
    tenant_db_name = os.getenv(env_name)
    if not tenant_db_name:
        # Without a configured DB name we cannot safely register MySQL alias.
        return

    default_cfg["ENGINE"] = "django.db.backends.mysql"
    default_cfg["NAME"] = tenant_db_name
    settings.DATABASES[alias] = default_cfg

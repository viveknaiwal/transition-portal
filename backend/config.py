import os
from dataclasses import dataclass
from pathlib import Path

from constants import (
    DEFAULT_BACKEND_HOST,
    DEFAULT_BACKEND_PORT,
    DEFAULT_BIFROST_AUTH_API_URL,
    DEFAULT_BIFROST_CLIENT_ID,
    DEFAULT_BIFROST_USER_SERVICE_URL,
    DEFAULT_DATABASE_URL,
    DEFAULT_DEV_AUTH_EMAIL,
    DEFAULT_DARWINBOX_BATCH_SIZE,
    DEFAULT_DARWINBOX_CTC_FROM,
    DEFAULT_FRONTEND_ORIGIN,
    ENV_LOCAL,
    ENV_NAMES,
)


ROOT = Path(__file__).resolve().parent
ENV_DIR = ROOT / "env"


def _bool(value, default=False):
    if value is None or value == "":
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _int(value, default):
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def _env(name, default=""):
    value = os.getenv(name)
    return default if value is None or value == "" else value


def _load_env_file(path):
    if not path.exists():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def bootstrap_environment():
    env_name = os.getenv("APP_ENV") or os.getenv("ENV") or ENV_LOCAL
    env_name = env_name.lower()
    if env_name not in ENV_NAMES:
        env_name = ENV_LOCAL
    _load_env_file(ENV_DIR / f"{env_name}.env")
    _load_env_file(ROOT / ".env")
    return env_name


@dataclass(frozen=True)
class BifrostConfig:
    auth_api_url: str
    client_id: str
    redirect_uri: str
    user_service_url: str


@dataclass(frozen=True)
class DarwinboxConfig:
    master_url: str
    payroll_url: str
    username: str
    password: str
    master_api_key: str
    dataset_key: str
    payroll_api_key: str
    batch_size: int
    ctc_from: str

    def missing_required_keys(self):
        missing = []
        if not self.username:
            missing.append("DARWINBOX_USERNAME")
        if not self.password:
            missing.append("DARWINBOX_PASSWORD")
        if not self.master_api_key:
            missing.append("DARWINBOX_MASTER_API_KEY")
        if not self.dataset_key:
            missing.append("DARWINBOX_DATASET_KEY")
        return missing

    @property
    def configured(self):
        return not self.missing_required_keys()


@dataclass(frozen=True)
class AppConfig:
    app_env: str
    backend_root: Path
    backend_host: str
    backend_port: int
    database_url: str
    frontend_origin: str
    upload_root: Path
    dev_auth_enabled: bool
    dev_auth_email: str
    bifrost: BifrostConfig
    darwinbox: DarwinboxConfig

    @property
    def is_production(self):
        return self.app_env == "production"

    def validate(self):
        if self.is_production and self.dev_auth_enabled:
            raise RuntimeError("DEV_AUTH_ENABLED must be false in production")
        if self.is_production and self.database_url == DEFAULT_DATABASE_URL:
            raise RuntimeError("DATABASE_URL must be explicitly configured in production")
        return self


_CONFIG = None


def get_config(refresh=False):
    global _CONFIG
    if _CONFIG is not None and not refresh:
        return _CONFIG

    app_env = bootstrap_environment()
    frontend_origin = _env("FRONTEND_ORIGIN", DEFAULT_FRONTEND_ORIGIN).rstrip("/")
    upload_root = Path(_env("UPLOAD_ROOT", str(ROOT / "uploads"))).expanduser()
    if not upload_root.is_absolute():
        upload_root = ROOT / upload_root

    dev_auth_default = app_env != "production"
    bifrost_redirect = _env("BIFROST_REDIRECT_URI", f"{frontend_origin}/login")

    _CONFIG = AppConfig(
        app_env=app_env,
        backend_root=ROOT,
        backend_host=_env("BACKEND_HOST", DEFAULT_BACKEND_HOST),
        backend_port=_int(_env("BACKEND_PORT", str(DEFAULT_BACKEND_PORT)), DEFAULT_BACKEND_PORT),
        database_url=_env("DATABASE_URL", DEFAULT_DATABASE_URL),
        frontend_origin=frontend_origin,
        upload_root=upload_root,
        dev_auth_enabled=_bool(os.getenv("DEV_AUTH_ENABLED"), dev_auth_default),
        dev_auth_email=_env("DEV_AUTH_EMAIL", DEFAULT_DEV_AUTH_EMAIL).strip().lower(),
        bifrost=BifrostConfig(
            auth_api_url=_env("BIFROST_AUTH_API_URL", DEFAULT_BIFROST_AUTH_API_URL).rstrip("/"),
            client_id=_env("BIFROST_CLIENT_ID", DEFAULT_BIFROST_CLIENT_ID),
            redirect_uri=bifrost_redirect,
            user_service_url=_env("BIFROST_USER_SERVICE_URL", DEFAULT_BIFROST_USER_SERVICE_URL).rstrip("/"),
        ),
        darwinbox=DarwinboxConfig(
            master_url=_env("DARWINBOX_MASTER_URL", "https://cars24.darwinbox.in/masterapi/employee"),
            payroll_url=_env("DARWINBOX_PAYROLL_URL", "https://cars24.darwinbox.in/payrollapi/ctcbreakup"),
            username=_env("DARWINBOX_USERNAME", ""),
            password=_env("DARWINBOX_PASSWORD", ""),
            master_api_key=_env("DARWINBOX_MASTER_API_KEY", ""),
            dataset_key=_env("DARWINBOX_DATASET_KEY", ""),
            payroll_api_key=_env("DARWINBOX_PAYROLL_API_KEY", ""),
            batch_size=_int(_env("DARWINBOX_BATCH_SIZE", str(DEFAULT_DARWINBOX_BATCH_SIZE)), DEFAULT_DARWINBOX_BATCH_SIZE),
            ctc_from=_env("DARWINBOX_CTC_FROM", DEFAULT_DARWINBOX_CTC_FROM),
        ),
    ).validate()
    return _CONFIG

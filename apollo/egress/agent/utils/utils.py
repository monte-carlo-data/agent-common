import json
import logging
import os
import socket
import sys
from urllib3.connection import HTTPConnection
from typing import Dict, Optional, Any, List

BACKEND_SERVICE_URL = os.getenv(
    "BACKEND_SERVICE_URL",
    "https://artemis.getmontecarlo.com:443",
)
LOCAL = os.getenv("LOCAL", "false").lower() == "true"
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

X_MCD_ID = "x-mcd-id"
X_MCD_TOKEN = "x-mcd-token"

_HEALTH_ENV_VARS = [
    "PYTHON_VERSION",
    "SERVER_SOFTWARE",
]

logger = logging.getLogger(__name__)


def build_url(base_url: str, path: str) -> str:
    """Concatenate a base URL with a path, preserving the base URL's path component."""
    if not path.startswith("/"):
        path = "/" + path
    return base_url.rstrip("/") + path


class _JsonFormatter(logging.Formatter):
    """JSON log formatter that includes instance_id on every line."""

    def __init__(self, instance_id: Optional[str] = None):
        super().__init__()
        self._instance_id = instance_id

    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%SZ"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if self._instance_id:
            log_entry["instance_id"] = self._instance_id
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)


def init_logging(
    instance_id: Optional[str] = None,
    json_format: Optional[bool] = None,
):
    level = logging.DEBUG if DEBUG else logging.INFO
    if json_format is None:
        json_format = os.environ.get("MCD_LOG_FORMAT", "text").lower() == "json"
    if json_format:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_JsonFormatter(instance_id=instance_id))
        logging.root.addHandler(handler)
        logging.root.setLevel(level)
    else:
        logging.basicConfig(
            stream=sys.stdout,
            level=level,
            format="[%(asctime)s] %(levelname)s:%(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%SZ",
        )
    logging.getLogger("snowflake.connector.cursor").setLevel(logging.WARNING)


def enable_tcp_keep_alive():
    HTTPConnection.default_socket_options = HTTPConnection.default_socket_options + [  # type: ignore
        (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1),
    ]
    logger.info("TCP Keep-alive enabled")


def health_information(
    platform: str,
    trace_id: Optional[str] = None,
    additional_env_vars: Optional[List[str]] = None,
) -> Dict[str, Any]:
    health_info = {
        "platform": platform,
        "env": _env_dictionary(additional_env_vars),
    }
    if trace_id:
        health_info["trace_id"] = trace_id
    return health_info


def _env_dictionary(additional_env_vars: Optional[List[str]] = None) -> Dict:
    env: Dict[str, Optional[str]] = {
        "PYTHON_SYS_VERSION": sys.version,
        "CPU_COUNT": str(os.cpu_count()),
    }
    env_vars = (
        _HEALTH_ENV_VARS + additional_env_vars
        if additional_env_vars
        else _HEALTH_ENV_VARS
    )
    env.update(
        {env_var: os.getenv(env_var) for env_var in env_vars if os.getenv(env_var)}
    )
    return env

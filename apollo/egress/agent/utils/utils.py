import json
import logging
import os
import socket
import sys
import time
from urllib3.connection import HTTPConnection
from typing import Dict, Optional, Any, List

from apollo.common.agent.redact import AgentRedactUtilities

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


# Attributes every LogRecord carries by default. Anything else on the record was
# injected through `extra=` by the caller and is what we surface as "mcd".
_STANDARD_LOG_RECORD_ATTRIBUTES = frozenset(
    logging.LogRecord("", logging.INFO, "", 0, "", (), None).__dict__
) | {"message", "asctime"}


def _to_jsonable(value: Any) -> Any:
    """
    Coerce a logged value to JSON-native types: dicts and lists recurse, tuples
    and sets become lists, everything else (bytes, exceptions, datetimes, arbitrary
    objects) becomes its str(). Done before redaction so a secret inside an
    exception message or a PEM blob is visible to the redactor, and so both sinks
    can serialize the result with plain json.dumps.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_to_jsonable(v) for v in value]
    return str(value)


def get_log_record_extra(record: logging.LogRecord) -> Dict[str, Any]:
    """
    Return the attributes passed via `extra=` when the record was logged, coerced
    to JSON-native types and passed through the standard redaction rules. Those
    rules mask values whose key or content matches known credential patterns;
    they are best-effort, callers must still not put raw secrets in `extra=`.
    Empty when the record carries no custom attributes.
    """
    extra = {
        k: _to_jsonable(v)
        for k, v in record.__dict__.items()
        if k not in _STANDARD_LOG_RECORD_ATTRIBUTES
    }
    return AgentRedactUtilities.standard_redact(extra) if extra else {}


class _JsonFormatter(logging.Formatter):
    """JSON log formatter that includes instance_id on every line."""

    # "ts" is rendered with a Z suffix, so it must be UTC regardless of host TZ.
    converter = time.gmtime

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
        if extra := get_log_record_extra(record):
            log_entry["mcd"] = extra
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)
        # default=str keeps a stray non-serializable extra value from taking the
        # whole log line down with it.
        return json.dumps(log_entry, default=str)


def init_logging(
    instance_id: Optional[str] = None,
    json_format: Optional[bool] = None,
):
    level = logging.DEBUG if DEBUG else logging.INFO
    if json_format is None:
        json_format = os.environ.get("MCD_LOG_FORMAT", "text").lower() == "json"
    if json_format:
        logging.root.handlers.clear()
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

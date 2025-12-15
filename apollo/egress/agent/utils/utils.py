import logging
import os
import socket
import sys
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


def init_logging():
    logging.basicConfig(
        stream=sys.stdout,
        level=logging.DEBUG if DEBUG else logging.INFO,
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

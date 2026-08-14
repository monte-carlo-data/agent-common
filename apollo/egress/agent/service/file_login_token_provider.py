import json
import logging
import os
from json import JSONDecodeError
from typing import Any, Dict

from apollo.egress.agent.service.login_token_provider import (
    ATTR_NAME_TOKEN_FILE_PATH,
    AUTH_METHOD_TOKEN_FILE,
    LoginTokenProvider,
)
from apollo.egress.agent.utils.utils import X_MCD_ID, X_MCD_TOKEN

_MCD_ID_ATTR = "mcd_id"
_MCD_TOKEN_ATTR = "mcd_token"
_NO_TOKEN_ID = "no-token-id"
_NO_TOKEN_SECRET = "no-token-secret"

logger = logging.getLogger(__name__)


class FileLoginTokenProvider(LoginTokenProvider):
    authentication_method: str = AUTH_METHOD_TOKEN_FILE

    def __init__(self, file_path: str):
        self._file_path = file_path

    def get_credential_info(self) -> Dict[str, Any]:
        # The path is included so a missing or unreadable secret file is
        # self-evident: `no-token-id` plus the path the agent tried to read.
        return {
            **super().get_credential_info(),
            ATTR_NAME_TOKEN_FILE_PATH: self._file_path,
        }

    def get_token(self) -> Dict[str, str]:
        if os.path.exists(self._file_path):
            with open(self._file_path, "r") as f:
                key_str = f.read()
            try:
                key_json = json.loads(key_str)
                if _MCD_ID_ATTR in key_json and _MCD_TOKEN_ATTR in key_json:
                    return {
                        X_MCD_ID: key_json[_MCD_ID_ATTR],
                        X_MCD_TOKEN: key_json[_MCD_TOKEN_ATTR],
                    }
                else:
                    logger.warning(f"Invalid secret string, keys: {key_json.keys()}")
            except JSONDecodeError as ex:
                logger.error(f"Failed to parse Key JSON: {ex}")
        else:
            logger.warning("No token file found")

        return {
            X_MCD_ID: _NO_TOKEN_ID,
            X_MCD_TOKEN: _NO_TOKEN_SECRET,
        }

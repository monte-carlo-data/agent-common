import os
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from apollo.egress.agent.utils.utils import X_MCD_ID, X_MCD_TOKEN

_LOCAL_TOKEN_ID = os.getenv("LOCAL_TOKEN_ID", "local-token-id")
_LOCAL_TOKEN_SECRET = os.getenv("LOCAL_TOKEN_SECRET", "local-token-secret")

# Attribute names used to report the credential in health information and in
# failed reachability tests.
ATTR_NAME_KEY_ID = "authentication_key_id"
ATTR_NAME_AUTH_METHOD = "authentication_method"
ATTR_NAME_TOKEN_FILE_PATH = "token_file_path"

AUTH_METHOD_UNKNOWN = "unknown"
AUTH_METHOD_LOCAL_ENV = "local_env"
AUTH_METHOD_TOKEN_FILE = "token_file"


class LoginTokenProvider(ABC):
    #: Non-secret label describing how this provider authenticates.
    authentication_method: str = AUTH_METHOD_UNKNOWN

    @abstractmethod
    def get_token(self) -> Dict[str, str]:
        pass

    def get_credential_id(self) -> Optional[str]:
        """Return a non-secret id for the configured credential, for reporting only.

        Implementations MUST NOT acquire a credential to answer this: it is
        called on the startup path and when authentication is already failing,
        so a provider that fetches a token here would stall startup and report
        nothing useful when the fetch is what's broken. Report what the agent is
        *configured* with — read from the local file or environment — and return
        ``None`` rather than raising when that isn't available.
        """
        return None

    def get_credential_info(self) -> Dict[str, Any]:
        """Return a non-secret description of the credential in use.

        Never includes the token/secret itself — the id and the authentication
        method are enough to tell which credential an agent is sending, which
        is what an operator needs when the backend rejects it.
        """
        return {
            ATTR_NAME_KEY_ID: self.get_credential_id(),
            ATTR_NAME_AUTH_METHOD: self.authentication_method,
        }


class LocalLoginTokenProvider(LoginTokenProvider):
    authentication_method: str = AUTH_METHOD_LOCAL_ENV

    def get_credential_id(self) -> Optional[str]:
        return _LOCAL_TOKEN_ID

    def get_token(self) -> Dict[str, str]:
        return {
            X_MCD_ID: _LOCAL_TOKEN_ID,
            X_MCD_TOKEN: _LOCAL_TOKEN_SECRET,
        }

import os
from abc import ABC, abstractmethod
from typing import Dict

from apollo.egress.agent.utils.utils import X_MCD_ID, X_MCD_TOKEN

_LOCAL_TOKEN_ID = os.getenv("LOCAL_TOKEN_ID", "local-token-id")
_LOCAL_TOKEN_SECRET = os.getenv("LOCAL_TOKEN_SECRET", "local-token-secret")


class LoginTokenProvider(ABC):
    @abstractmethod
    def get_token(self) -> Dict[str, str]:
        pass


class LocalLoginTokenProvider(LoginTokenProvider):
    def get_token(self) -> Dict[str, str]:
        return {
            X_MCD_ID: _LOCAL_TOKEN_ID,
            X_MCD_TOKEN: _LOCAL_TOKEN_SECRET,
        }

import os
from typing import Optional, Dict

from apollo.common.agent.redact import is_sensitive_env_var_name
from apollo.egress.agent.config.config_persistence import ConfigurationPersistence


class LocalConfig(ConfigurationPersistence):
    def __init__(self, prefix: str):
        self._prefix = prefix

    def get_value(self, key: str) -> Optional[str]:
        return os.getenv(f"{self._prefix}_{key}")

    def set_value(self, key: str, value: str):
        raise NotImplementedError(
            "You cannot update config settings in a local environment, update env vars instead"
        )

    def get_all_values(self) -> Dict[str, str]:
        # Surfaced in the health endpoint, so credential-named vars are dropped.
        prefix = f"{self._prefix}_"
        return {
            key: value
            for key, value in os.environ.items()
            if key.startswith(prefix) and not is_sensitive_env_var_name(key)
        }

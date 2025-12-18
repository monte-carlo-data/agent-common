from typing import Dict, Any
from apollo.common.agent.constants import ATTRIBUTE_NAME_ERROR


class ResultUtils:
    @staticmethod
    def result_for_error_message(error_message: str) -> Dict[str, Any]:
        return {
            ATTRIBUTE_NAME_ERROR: error_message,
        }

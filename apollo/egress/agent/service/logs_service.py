from abc import ABC, abstractmethod
from typing import List, Dict, Any


class BaseLogsService(ABC):
    @abstractmethod
    def get_logs(self, limit: int) -> List[Dict[str, Any]]:
        raise NotImplementedError

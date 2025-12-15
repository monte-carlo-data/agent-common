from abc import ABC, abstractmethod
from typing import List


class BaseMetricsService(ABC):
    @abstractmethod
    def fetch_metrics(self) -> List[str]:
        raise NotImplementedError

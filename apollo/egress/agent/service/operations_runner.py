import logging
from dataclasses import dataclass
from typing import Callable, Dict, Any

from apollo.egress.agent.utils.queue_async_processor import QueueAsyncProcessor

logger = logging.getLogger(__name__)


@dataclass
class Operation:
    operation_id: str
    event: Dict[str, Any]


class OperationsRunner(QueueAsyncProcessor[Operation]):
    """
    This class is responsible for processing other operations (not queries) to be executed,
    like fetch_logs, fetch_metrics, etc.
    Currently, it uses a queue and the given number of threads to execute them.
    The handler is used to execute the operation.
    """

    def __init__(self, handler: Callable[[Operation], None], thread_count: int = 1):
        self._ops_handler = handler
        super().__init__(
            name="OperationsRunner",
            handler=self._handler_wrapper,
            thread_count=thread_count,
        )

    def _describe_param(self, operation: Operation) -> str:
        return operation.operation_id

    def _handler_wrapper(self, operation: Operation):
        # Lifecycle log (running/completed with operation_id and duration) is
        # emitted by the base class via ``_describe_param`` above.
        self._ops_handler(operation)

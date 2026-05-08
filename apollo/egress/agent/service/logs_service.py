from abc import ABC, abstractmethod
from typing import List, Dict, Any


class BaseLogsService(ABC):
    @abstractmethod
    def get_logs(self, limit: int) -> List[Dict[str, Any]]:
        """Return up to `limit` log records.

        Used for non-destructive on-demand pulls (e.g. when the orchestrator
        explicitly requests a sample of agent logs). Implementations may keep
        the records available for a subsequent destructive `drain()`.
        """
        raise NotImplementedError

    def supports_drain(self) -> bool:
        """Whether this implementation provides a destructive `drain()`.

        Default False. Implementations that hold an internal buffer that
        should be flushed and cleared in one go should override this to
        return True and implement `drain()`.
        """
        return False

    def drain(self) -> List[Dict[str, Any]]:
        """Return all buffered records and clear internal state.

        Only valid when `supports_drain()` returns True. Used for periodic
        push-everything semantics; `get_logs(limit)` is the non-destructive
        alternative used for on-demand backend pulls.
        """
        raise NotImplementedError("drain() not supported by this implementation")

    def close(self) -> None:
        """Release any resources held by this service.

        Default no-op. Implementations that hold a logging handler attached
        to the root logger should override to detach themselves on shutdown.

        Contract: implementations must not destroy buffered records here —
        only stop new arrivals (e.g. detach a handler) and release I/O
        resources. Callers (notably the shutdown path) drain *before* close,
        but a future implementation that nulls/clears the buffer in `close()`
        would still corrupt that ordering for any subsequent caller. The
        destructive flush path is `drain()`.
        """
        pass

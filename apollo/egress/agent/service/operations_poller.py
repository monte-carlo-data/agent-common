"""
Operations Poller for the agent pull model.

A single-threaded fetcher that:
- Polls the orchestrator for operations (GET /operation)
- Injects fetched operations into the existing _execute_operation flow
- Waits for work_available SSE notification or poll interval when idle

Piggybacking is handled separately by _results_publisher, which schedules
piggybacked operations back to _ops_runner after pushing results.
"""

import logging
import time
from threading import Condition, Thread
from typing import Callable, Dict, Optional

from apollo.egress.agent.backend.backend_client import BackendClient
from apollo.egress.agent.config.config_keys import CONFIG_POLL_INTERVAL_SECONDS
from apollo.egress.agent.config.config_manager import ConfigurationManager

logger = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL_SECONDS = 60

ATTR_NAME_PATH = "path"
ATTR_NAME_OPERATION_ID = "operation_id"


class OperationsPoller:
    """
    Single-threaded poller that fetches operations and injects them into
    the existing execution flow.

    Fetches operations:
    - On startup
    - When notified via SSE (work_available)
    - On periodic fallback interval (when idle)
    """

    def __init__(
        self,
        backend_client: BackendClient,
        config_manager: ConfigurationManager,
        operation_handler: Callable[[str, str, Dict], None],
        can_accept_work: Optional[Callable[[], bool]] = None,
    ):
        """
        Args:
            backend_client: Client for orchestrator API calls
            config_manager: Configuration manager
            operation_handler: Callback to handle operations for execution.
                               Signature: (path, operation_id, operation_dict) -> None
                               Typically bound to BaseEgressAgentService._handle_polled_operation
            can_accept_work: Optional callback that returns True if the agent can accept
                             more work. Used for backpressure when ops_runner queue is full.
                             If None, always accepts work.
        """
        self._backend_client = backend_client
        self._poll_interval = config_manager.get_int_value(
            CONFIG_POLL_INTERVAL_SECONDS, DEFAULT_POLL_INTERVAL_SECONDS
        )
        self._operation_handler = operation_handler
        self._can_accept_work = can_accept_work
        self._condition = Condition()
        self._running = False
        self._waiting = False
        self._thread: Optional[Thread] = None

    def start(self):
        """Start the polling thread."""
        self._running = True
        self._thread = Thread(
            target=self._run_loop,
            daemon=True,
            name="OperationsPoller",
        )
        self._thread.start()
        logger.info(
            "OperationsPoller started",
            extra={"poll_interval_seconds": self._poll_interval},
        )

    def stop(self):
        """Stop the polling thread."""
        with self._condition:
            self._running = False
            self._condition.notify_all()
        logger.info("OperationsPoller stopped")

    def notify_work_available(self):
        """Called when SSE work_available notification received.

        Wakes up the poller to fetch immediately.
        """
        with self._condition:
            poller_was_waiting = self._waiting
            self._condition.notify_all()
        logger.info(
            "Notified of available work",
            extra={"poller_was_waiting": poller_was_waiting},
        )

    def _run_loop(self):
        """Main polling loop: fetch operations and submit for execution."""
        while self._running:
            # Check backpressure - wait if ops_runner queue is full
            if self._can_accept_work and not self._can_accept_work():
                logger.debug("Backpressure: waiting for ops_runner capacity")
                self._send_heartbeat()
                self._wait_for_work()
                continue

            # Fetch and submit operations until queue is empty or backpressure
            operation = self._fetch_operation()
            while operation and self._running:
                self._submit_operation(operation)

                # Check backpressure before fetching more
                if self._can_accept_work and not self._can_accept_work():
                    logger.debug("Backpressure: stopping fetch loop")
                    break

                operation = self._fetch_operation()

            # No more work - wait for notification or timeout
            logger.info("Fetch loop idle, entering wait")
            self._wait_for_work()

    def _submit_operation(self, operation: Dict):
        """Submit an operation for execution via the existing flow."""
        path = operation.get(ATTR_NAME_PATH, "")
        operation_id = operation.get(ATTR_NAME_OPERATION_ID)

        if not path or not operation_id:
            logger.warning(f"Invalid operation received: {operation}")
            return

        logger.info(
            f"Submitting polled operation: {path}, operation_id: {operation_id}"
        )
        self._operation_handler(path, operation_id, operation)

    def _send_heartbeat(self):
        """Send a heartbeat to the orchestrator to signal liveness during backpressure."""
        try:
            self._backend_client.send_heartbeat()
        except Exception:
            logger.exception("Failed to send heartbeat")

    def _fetch_operation(self) -> Optional[Dict]:
        """Fetch next operation from orchestrator. Returns None if queue empty or on error."""
        try:
            operation = self._backend_client.get_next_operation()
            if operation:
                logger.debug(
                    "Fetched operation",
                    extra={"operation_id": operation.get(ATTR_NAME_OPERATION_ID)},
                )
            return operation
        except Exception:
            logger.exception("Failed to fetch operation, will retry on next poll")
            return None

    def _wait_for_work(self):
        """Wait for work_available notification or poll interval timeout."""
        with self._condition:
            wait_start = time.monotonic()
            self._waiting = True
            notified = self._condition.wait(timeout=self._poll_interval)
            self._waiting = False
            wait_seconds = round(time.monotonic() - wait_start, 3)
            if notified and self._running:
                logger.info(
                    "Woken by work_available notification",
                    extra={"wait_seconds": wait_seconds},
                )
            elif not notified:
                logger.info(
                    "Poll interval reached, checking for work",
                    extra={
                        "poll_interval_seconds": self._poll_interval,
                        "wait_seconds": wait_seconds,
                    },
                )

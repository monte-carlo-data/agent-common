import logging
from threading import Condition, Thread
from typing import Any, Callable, Dict, Optional

from apollo.egress.agent.backend.backend_client import BackendClient
from apollo.egress.agent.config.config_keys import CONFIG_POLL_INTERVAL_SECONDS
from apollo.egress.agent.config.config_manager import ConfigurationManager

logger = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL_SECONDS = 60


class OperationsPoller:
    """
    Manages the pull-based operation fetching loop.

    Pulls operations:
    - On startup
    - When notified via SSE (work_available)
    - On periodic fallback interval (when idle)
    - Immediately after submitting a result (via piggyback response)
    """

    def __init__(
        self,
        backend_client: BackendClient,
        config_manager: ConfigurationManager,
        operation_handler: Callable[[Dict], Any],
    ):
        self._backend_client = backend_client
        self._poll_interval = config_manager.get_int_value(
            CONFIG_POLL_INTERVAL_SECONDS, DEFAULT_POLL_INTERVAL_SECONDS
        )
        self._operation_handler = operation_handler
        self._condition = Condition()
        self._running = False
        self._has_pending_work = False  # Set by SSE notification

    def start(self):
        """Start the polling loop."""
        self._running = True
        Thread(target=self._run_loop, daemon=True).start()
        logger.info(
            "OperationsPoller started",
            extra={"poll_interval_seconds": self._poll_interval},
        )

    def stop(self):
        """Stop the polling loop."""
        with self._condition:
            self._running = False
            self._condition.notify_all()
        logger.info("OperationsPoller stopped")

    def notify_work_available(self):
        """Called when SSE work_available notification received."""
        with self._condition:
            self._has_pending_work = True
            self._condition.notify_all()
        logger.debug("Notified of work available")

    def _run_loop(self):
        """Main polling loop."""
        while self._running:
            operation = self._fetch_operation()

            while operation and self._running:
                # Process operation
                operation_id = operation.get("operation_id")
                if not operation_id:
                    logger.warning("Operation missing operation_id, skipping")
                    operation = None
                    continue

                logger.info(
                    "Processing operation",
                    extra={"operation_id": operation_id},
                )

                try:
                    result = self._operation_handler(operation)

                    # Submit result and get next operation (piggyback)
                    response = self._backend_client.push_results(
                        operation_id,
                        result,
                    )
                    operation = response.get("next_operation") if response else None

                    if operation:
                        logger.debug(
                            "Received piggybacked operation",
                            extra={"next_operation_id": operation.get("operation_id")},
                        )
                except Exception:
                    logger.exception(
                        "Failed to process operation",
                        extra={"operation_id": operation_id},
                    )
                    operation = None

            # No more work - wait for notification or timeout
            self._wait_for_work()

    def _fetch_operation(self) -> Optional[Dict]:
        """Fetch next operation from orchestrator. Returns None on failure."""
        try:
            operation = self._backend_client.get_next_operation()
            if operation:
                logger.debug(
                    "Fetched operation",
                    extra={"operation_id": operation.get("operation_id")},
                )
            return operation
        except Exception:
            logger.exception("Failed to fetch operation, will retry on next poll")
            return None

    def _wait_for_work(self):
        """Wait for work_available notification or poll interval timeout."""
        with self._condition:
            self._has_pending_work = False
            self._condition.wait(timeout=self._poll_interval)

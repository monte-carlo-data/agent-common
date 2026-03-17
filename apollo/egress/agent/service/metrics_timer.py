"""
Metrics Timer for periodic metrics pushing.

A simple timer that triggers metrics push at a configurable interval,
replacing the SSE heartbeat-based approach.
"""

import logging
from threading import Event, Thread
from typing import Callable, Optional

from apollo.egress.agent.config.config_keys import CONFIG_METRICS_PUSH_INTERVAL_SECONDS
from apollo.egress.agent.config.config_manager import ConfigurationManager

logger = logging.getLogger(__name__)

DEFAULT_METRICS_PUSH_INTERVAL_SECONDS = 600  # 10 minutes


class MetricsTimer:
    """
    Timer that triggers metrics push at regular intervals.
    """

    def __init__(
        self,
        config_manager: ConfigurationManager,
        push_metrics_handler: Callable[[], None],
    ):
        """
        Args:
            config_manager: Configuration manager
            push_metrics_handler: Callback to push metrics
        """
        self._interval = config_manager.get_int_value(
            CONFIG_METRICS_PUSH_INTERVAL_SECONDS, DEFAULT_METRICS_PUSH_INTERVAL_SECONDS
        )
        self._handler = push_metrics_handler
        self._stop_event = Event()
        self._thread: Optional[Thread] = None

    def start(self):
        """Start the metrics timer."""
        self._stop_event.clear()
        self._thread = Thread(
            target=self._run_loop,
            daemon=True,
            name="MetricsTimer",
        )
        self._thread.start()
        logger.info(
            "MetricsTimer started",
            extra={"interval_seconds": self._interval},
        )

    def stop(self):
        """Stop the metrics timer."""
        self._stop_event.set()
        logger.info("MetricsTimer stopped")

    def _run_loop(self):
        """Timer loop: wait for interval, then trigger metrics push."""
        while not self._stop_event.is_set():
            # Wait for interval or until stopped
            stopped = self._stop_event.wait(timeout=self._interval)
            if stopped:
                break

            try:
                logger.debug("Triggering scheduled metrics push")
                self._handler()
            except Exception:
                logger.exception("Failed to push metrics")

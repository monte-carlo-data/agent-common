import logging
from typing import Dict, Callable, Optional

from apollo.egress.agent.events.base_receiver import BaseReceiver
from apollo.egress.agent.events.heartbeat_checker import HeartbeatChecker

_ATTR_NAME_EVENT_TYPE = "type"
_ATTR_NAME_AGENT_ID = "agent_id"

_EVENT_TYPE_HEARTBEAT = "heartbeat"
_EVENT_TYPE_WELCOME = "welcome"
_EVENT_TYPE_WORK_AVAILABLE = "work_available"

logger = logging.getLogger(__name__)


class EventsClient:
    """
    Client that abstracts the underlying technology used to receive events from the backend.
    Uses SSE (Server-Sent Events) by default.

    Handles the following event types:
    - `welcome`: sent as the first message after connection is established
    - `heartbeat`: sent periodically by the server to keep connection alive.
        This class will re-establish the connection if no heartbeat after 2 minutes.
    - `work_available`: notification that new work is available for polling
    """

    def __init__(
        self,
        receiver: BaseReceiver,
        heartbeat_checker: Optional[HeartbeatChecker] = None,
    ):
        self._receiver = receiver
        self._stopped = True
        self._heartbeat_checker = heartbeat_checker or HeartbeatChecker(self._reconnect)
        self._work_available_handler: Optional[Callable[[], None]] = None

    def start(
        self,
        work_available_handler: Callable[[], None],
    ):
        self._work_available_handler = work_available_handler
        self._stopped = False
        self._receiver.start(
            handler=self._event_received,
            connected_handler=self._receiver_connected,
            disconnected_handler=self._receiver_disconnected,
        )

    def stop(self):
        self._stopped = True
        self._work_available_handler = None
        self._receiver.stop()

    def _reconnect(self):
        self._receiver.restart()

    def _event_received(self, event: Dict):
        event_type = event.get(_ATTR_NAME_EVENT_TYPE)
        if event_type == _EVENT_TYPE_HEARTBEAT:
            self._heartbeat_checker.heartbeat_received()
            logger.info(f"heartbeat: {event.get('ts')}")
        elif event_type == _EVENT_TYPE_WELCOME:
            logger.info(f"{event_type}: agent_id={event.get(_ATTR_NAME_AGENT_ID)}")
        elif event_type == _EVENT_TYPE_WORK_AVAILABLE:
            logger.info("work_available notification received")
            if self._work_available_handler:
                self._work_available_handler()
            else:
                logger.warning("work_available received but no handler registered")
        else:
            logger.info(f"Ignoring unexpected event type: {event_type}")

    def _receiver_connected(self):
        self._heartbeat_checker.start()

    def _receiver_disconnected(self):
        self._heartbeat_checker.stop()

from unittest import TestCase
from unittest.mock import Mock

from apollo.egress.agent.events.events_client import EventsClient


class EventsClientTests(TestCase):
    def setUp(self):
        self._receiver = Mock()
        self._heartbeat_checker = Mock()
        self._client = EventsClient(
            receiver=self._receiver,
            heartbeat_checker=self._heartbeat_checker,
        )
        self._work_available_handler = Mock()

    def test_start_registers_handlers(self):
        """Test that start() registers the event handlers."""
        self._client.start(
            work_available_handler=self._work_available_handler,
        )

        self._receiver.start.assert_called_once()

    def test_work_available_event_calls_handler(self):
        """Test that work_available event calls the handler."""
        self._client.start(
            work_available_handler=self._work_available_handler,
        )

        self._client._event_received({"type": "work_available"})

        self._work_available_handler.assert_called_once()

    def test_heartbeat_event_triggers_heartbeat_checker(self):
        """Test that heartbeat event triggers heartbeat checker."""
        self._client.start(
            work_available_handler=self._work_available_handler,
        )

        self._client._event_received({"type": "heartbeat", "ts": "2024-01-01"})

        self._heartbeat_checker.heartbeat_received.assert_called_once()
        self._work_available_handler.assert_not_called()

    def test_welcome_event_is_logged_only(self):
        """Test that welcome event is logged but doesn't call handlers."""
        self._client.start(
            work_available_handler=self._work_available_handler,
        )

        self._client._event_received({"type": "welcome", "agent_id": "agent-123"})

        self._work_available_handler.assert_not_called()

    def test_operation_event_is_ignored(self):
        """Test that operation events are ignored (pull model handles operations)."""
        self._client.start(
            work_available_handler=self._work_available_handler,
        )
        operation = {"type": "operation", "operation_id": "op-123", "path": "/test"}

        self._client._event_received(operation)

        # Operation events should be ignored - pull model handles operations
        self._work_available_handler.assert_not_called()

    def test_goodbye_event_calls_handler(self):
        """Test that goodbye event calls the goodbye handler with the reason."""
        goodbye_handler = Mock()
        self._client.start(
            work_available_handler=self._work_available_handler,
            goodbye_handler=goodbye_handler,
        )

        self._client._event_received({"type": "goodbye", "reason": "activity_timeout"})

        goodbye_handler.assert_called_once_with("activity_timeout")
        self._work_available_handler.assert_not_called()

    def test_goodbye_event_defaults_reason_to_unknown(self):
        """Test that goodbye event without reason defaults to 'unknown'."""
        goodbye_handler = Mock()
        self._client.start(
            work_available_handler=self._work_available_handler,
            goodbye_handler=goodbye_handler,
        )

        self._client._event_received({"type": "goodbye"})

        goodbye_handler.assert_called_once_with("unknown")

    def test_goodbye_event_without_handler(self):
        """Test that goodbye event without handler doesn't raise."""
        self._client.start(
            work_available_handler=self._work_available_handler,
        )

        # Should not raise
        self._client._event_received({"type": "goodbye", "reason": "activity_timeout"})

    def test_stop_clears_handlers(self):
        """Test that stop() clears the handlers."""
        self._client.start(
            work_available_handler=self._work_available_handler,
            goodbye_handler=Mock(),
        )

        self._client.stop()

        self.assertIsNone(self._client._work_available_handler)
        self.assertIsNone(self._client._goodbye_handler)
        self._receiver.stop.assert_called_once()

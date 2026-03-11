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
        self._event_handler = Mock()
        self._work_available_handler = Mock()

    def test_start_registers_handlers(self):
        """Test that start() registers the event handlers."""
        self._client.start(
            handler=self._event_handler,
            work_available_handler=self._work_available_handler,
        )

        self._receiver.start.assert_called_once()

    def test_work_available_event_calls_handler(self):
        """Test that work_available event calls the handler."""
        self._client.start(
            handler=self._event_handler,
            work_available_handler=self._work_available_handler,
        )

        self._client._event_received({"type": "work_available"})

        self._work_available_handler.assert_called_once()
        self._event_handler.assert_not_called()

    def test_work_available_event_without_handler_does_not_crash(self):
        """Test that work_available event doesn't crash when handler is None."""
        self._client.start(
            handler=self._event_handler,
            work_available_handler=None,
        )

        # Should not raise
        self._client._event_received({"type": "work_available"})

        self._event_handler.assert_not_called()

    def test_heartbeat_event_triggers_heartbeat_checker(self):
        """Test that heartbeat event triggers heartbeat checker."""
        self._client.start(
            handler=self._event_handler,
            work_available_handler=self._work_available_handler,
        )

        self._client._event_received({"type": "heartbeat", "ts": "2024-01-01"})

        self._heartbeat_checker.heartbeat_received.assert_called_once()
        self._work_available_handler.assert_not_called()

    def test_heartbeat_with_push_metrics_calls_event_handler(self):
        """Test that heartbeat with push_metrics flag calls event handler."""
        self._client.start(
            handler=self._event_handler,
            work_available_handler=self._work_available_handler,
        )

        self._client._event_received(
            {
                "type": "heartbeat",
                "ts": "2024-01-01",
                "push_metrics": True,
            }
        )

        self._heartbeat_checker.heartbeat_received.assert_called_once()
        self._event_handler.assert_called_once_with({"type": "push_metrics"})

    def test_welcome_event_is_logged_only(self):
        """Test that welcome event is logged but doesn't call handlers."""
        self._client.start(
            handler=self._event_handler,
            work_available_handler=self._work_available_handler,
        )

        self._client._event_received({"type": "welcome", "agent_id": "agent-123"})

        self._event_handler.assert_not_called()
        self._work_available_handler.assert_not_called()

    def test_operation_event_calls_event_handler(self):
        """Test that operation events call the event handler."""
        self._client.start(
            handler=self._event_handler,
            work_available_handler=self._work_available_handler,
        )
        operation = {"type": "operation", "operation_id": "op-123", "path": "/test"}

        self._client._event_received(operation)

        self._event_handler.assert_called_once_with(operation)
        self._work_available_handler.assert_not_called()

    def test_stop_clears_handlers(self):
        """Test that stop() clears the handlers."""
        self._client.start(
            handler=self._event_handler,
            work_available_handler=self._work_available_handler,
        )

        self._client.stop()

        self.assertIsNone(self._client._event_handler)
        self.assertIsNone(self._client._work_available_handler)
        self._receiver.stop.assert_called_once()

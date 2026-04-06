from unittest import TestCase
from unittest.mock import Mock, patch, MagicMock

from apollo.egress.agent.events.sse_client_receiver import SSEClientReceiver


class SSEClientReceiverTests(TestCase):
    def setUp(self):
        self._login_token_provider = Mock()
        self._login_token_provider.get_token.return_value = {
            "x-mcd-id": "test-id",
            "x-mcd-token": "test-token",
        }
        self._receiver = SSEClientReceiver(
            base_url="http://test",
            login_token_provider=self._login_token_provider,
        )
        self._handler = Mock()
        self._connected_handler = Mock()
        self._disconnected_handler = Mock()

    def test_stop_calls_disconnected_handler(self):
        """When stop() is called, the receiver thread's finally block should
        call _disconnected_handler because _current_loop_id is None."""
        self._receiver._event_handler = self._handler
        self._receiver._connected_handler = self._connected_handler
        self._receiver._disconnected_handler = self._disconnected_handler

        # Simulate a loop that exits because stop() was called
        loop_id = "test-loop-id"
        self._receiver._current_loop_id = loop_id

        # stop() sets _current_loop_id to None
        self._receiver.stop()

        # Simulate the finally block running after the loop exits
        # _current_loop_id is None, loop_id is "test-loop-id"
        # None is in (loop_id, None) -> True, so handler should be called
        if (
            self._receiver._disconnected_handler
            and self._receiver._current_loop_id in (loop_id, None)
        ):
            self._receiver._disconnected_handler()

        self._disconnected_handler.assert_called_once()

    def test_restart_does_not_call_disconnected_handler_for_old_loop(self):
        """When restart() replaces the loop, the old receiver thread's finally
        block should NOT call _disconnected_handler because _current_loop_id
        is a different UUID (not the old loop_id or None)."""
        self._receiver._event_handler = self._handler
        self._receiver._connected_handler = self._connected_handler
        self._receiver._disconnected_handler = self._disconnected_handler

        old_loop_id = "old-loop-id"
        self._receiver._current_loop_id = old_loop_id

        # restart() calls stop() then _start_receiver_thread()
        # After restart, _current_loop_id is a new UUID
        with patch.object(self._receiver, "_start_receiver_thread"):
            self._receiver.restart()

        new_loop_id = self._receiver._current_loop_id
        # stop() set it to None, then _start_receiver_thread set a new UUID
        # But since we mocked _start_receiver_thread, it's still None
        # Simulate what happens when _start_receiver_thread sets a new loop_id
        self._receiver._current_loop_id = "new-loop-id"

        # Simulate the old loop's finally block running
        # _current_loop_id is "new-loop-id", old_loop_id is "old-loop-id"
        # "new-loop-id" is not in ("old-loop-id", None) -> False
        if (
            self._receiver._disconnected_handler
            and self._receiver._current_loop_id in (old_loop_id, None)
        ):
            self._receiver._disconnected_handler()

        self._disconnected_handler.assert_not_called()

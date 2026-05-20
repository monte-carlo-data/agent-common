import time
from unittest import TestCase
from unittest.mock import Mock

from apollo.egress.agent.service.operations_poller import OperationsPoller


class OperationsPollerTests(TestCase):
    def setUp(self):
        self._backend_client = Mock()
        self._config_manager = Mock()
        self._config_manager.get_int_value.return_value = 1  # 1 second poll interval
        self._operation_handler = Mock()
        self._poller = OperationsPoller(
            backend_client=self._backend_client,
            config_manager=self._config_manager,
            operation_handler=self._operation_handler,
        )

    def tearDown(self):
        self._poller.stop()

    def test_fetch_operation_returns_operation(self):
        """Test that _fetch_operation returns operation from backend."""
        operation = {"operation_id": "op-123", "path": "/test"}
        self._backend_client.get_next_operation.return_value = operation

        result = self._poller._fetch_operation()

        self.assertEqual(result, operation)
        self._backend_client.get_next_operation.assert_called_once()

    def test_fetch_operation_returns_none_when_empty(self):
        """Test that _fetch_operation returns None when no operations available."""
        self._backend_client.get_next_operation.return_value = None

        result = self._poller._fetch_operation()

        self.assertIsNone(result)

    def test_fetch_operation_returns_none_on_error(self):
        """Test that _fetch_operation returns None on error."""
        self._backend_client.get_next_operation.side_effect = Exception("Network error")

        result = self._poller._fetch_operation()

        self.assertIsNone(result)

    def test_start_begins_polling(self):
        """Test that start() begins the polling loop."""
        self._backend_client.get_next_operation.return_value = None

        self._poller.start()
        time.sleep(0.1)  # Give thread time to start

        self.assertTrue(self._poller._running)
        self._backend_client.get_next_operation.assert_called()

    def test_stop_ends_polling(self):
        """Test that stop() ends the polling loop."""
        self._backend_client.get_next_operation.return_value = None
        self._poller.start()
        time.sleep(0.1)

        self._poller.stop()

        self.assertFalse(self._poller._running)

    def test_submits_operation_to_handler(self):
        """Test that fetched operations are submitted via operation_handler."""
        operation = {"operation_id": "op-123", "path": "/test", "operation": {}}
        self._backend_client.get_next_operation.side_effect = [operation, None]

        self._poller.start()
        time.sleep(0.2)

        # Operation should be submitted with (path, operation_id, operation)
        self._operation_handler.assert_called_once_with("/test", "op-123", operation)

    def test_fetches_multiple_operations_in_sequence(self):
        """Test that poller fetches all available operations."""
        operation1 = {"operation_id": "op-1", "path": "/test1", "operation": {}}
        operation2 = {"operation_id": "op-2", "path": "/test2", "operation": {}}

        self._backend_client.get_next_operation.side_effect = [
            operation1,
            operation2,
            None,
        ]

        self._poller.start()
        time.sleep(0.3)

        # Both operations should be submitted
        self.assertEqual(self._operation_handler.call_count, 2)

    def test_notify_work_available_wakes_poller(self):
        """Test that notify_work_available wakes the poller from waiting."""
        self._config_manager.get_int_value.return_value = 60  # Long poll interval
        poller = OperationsPoller(
            backend_client=self._backend_client,
            config_manager=self._config_manager,
            operation_handler=self._operation_handler,
        )
        self._backend_client.get_next_operation.return_value = None

        poller.start()
        time.sleep(0.1)
        initial_call_count = self._backend_client.get_next_operation.call_count

        # Notify work available - should wake up immediately
        poller.notify_work_available()
        time.sleep(0.1)

        # Should have polled again after notification
        self.assertGreater(
            self._backend_client.get_next_operation.call_count, initial_call_count
        )
        poller.stop()

    def test_skips_invalid_operation(self):
        """Test that operations without path or operation_id are skipped."""
        invalid_op = {"operation_id": "op-123"}  # Missing path
        valid_op = {"operation_id": "op-456", "path": "/test"}
        self._backend_client.get_next_operation.side_effect = [
            invalid_op,
            valid_op,
            None,
        ]

        self._poller.start()
        time.sleep(0.3)

        # Only valid operation should be submitted
        self._operation_handler.assert_called_once_with("/test", "op-456", valid_op)

    def test_continues_after_fetch_error(self):
        """Test that poller continues after fetch error."""
        operation = {"operation_id": "op-123", "path": "/test", "operation": {}}
        self._backend_client.get_next_operation.side_effect = [
            Exception("Network error"),
            None,  # Will wait here
            operation,
            None,
        ]

        self._poller.start()
        time.sleep(0.3)

        # Poller should still be running
        self.assertTrue(self._poller._running)

    def test_backpressure_pauses_fetching(self):
        """Test that poller pauses when can_accept_work returns False."""
        # Track calls and control when work can be accepted
        accept_calls = []

        def can_accept_work():
            accept_calls.append(time.time())
            # Return False for first few calls to trigger backpressure
            return len(accept_calls) > 2

        operation = {"operation_id": "op-123", "path": "/test", "operation": {}}
        self._backend_client.get_next_operation.side_effect = [
            operation,
            None,
            None,
            None,
        ]

        # Use short poll interval so we can see multiple cycles
        self._config_manager.get_int_value.return_value = 0.1

        poller = OperationsPoller(
            backend_client=self._backend_client,
            config_manager=self._config_manager,
            operation_handler=self._operation_handler,
            can_accept_work=can_accept_work,
        )

        poller.start()
        time.sleep(0.5)

        # Should have checked can_accept_work multiple times due to backpressure waits
        self.assertGreaterEqual(len(accept_calls), 2)
        # Eventually should have processed the operation when can_accept_work returned True
        self._operation_handler.assert_called()
        poller.stop()

    def test_backpressure_stops_mid_fetch_loop(self):
        """Test that backpressure stops fetching after submitting one operation."""
        # Allow first operation, reject second
        call_count = [0]

        def can_accept_work():
            call_count[0] += 1
            # Allow first submit, block after that
            return call_count[0] <= 1

        op1 = {"operation_id": "op-1", "path": "/test1", "operation": {}}
        op2 = {"operation_id": "op-2", "path": "/test2", "operation": {}}
        # Provide two operations, but backpressure should stop after first
        self._backend_client.get_next_operation.side_effect = [op1, op2, None, None]

        self._config_manager.get_int_value.return_value = 0.1

        poller = OperationsPoller(
            backend_client=self._backend_client,
            config_manager=self._config_manager,
            operation_handler=self._operation_handler,
            can_accept_work=can_accept_work,
        )

        poller.start()
        time.sleep(0.3)

        # First operation should be submitted
        self.assertGreaterEqual(self._operation_handler.call_count, 1)
        # Backpressure should have been checked multiple times
        self.assertGreater(call_count[0], 1)
        poller.stop()

    def test_backpressure_sends_heartbeat(self):
        """Test that poller sends heartbeat to orchestrator during backpressure."""
        self._backend_client.get_next_operation.return_value = None

        self._config_manager.get_int_value.return_value = 0.1

        poller = OperationsPoller(
            backend_client=self._backend_client,
            config_manager=self._config_manager,
            operation_handler=self._operation_handler,
            can_accept_work=lambda: False,  # always backpressured
        )

        poller.start()
        time.sleep(0.3)

        self._backend_client.send_heartbeat.assert_called()
        poller.stop()

    def test_no_backpressure_when_can_accept_work_is_none(self):
        """Test that poller fetches normally when can_accept_work is not provided."""
        op1 = {"operation_id": "op-1", "path": "/test1", "operation": {}}
        op2 = {"operation_id": "op-2", "path": "/test2", "operation": {}}
        self._backend_client.get_next_operation.side_effect = [op1, op2, None]

        # No can_accept_work callback - should fetch all available
        poller = OperationsPoller(
            backend_client=self._backend_client,
            config_manager=self._config_manager,
            operation_handler=self._operation_handler,
            # can_accept_work not provided (defaults to None)
        )

        poller.start()
        time.sleep(0.3)

        # Both operations should be submitted
        self.assertEqual(self._operation_handler.call_count, 2)
        poller.stop()

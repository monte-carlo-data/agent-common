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

from unittest import TestCase
from unittest.mock import Mock, patch, MagicMock

from apollo.egress.agent.service.base_egress_service import (
    BaseEgressAgentService,
    ATTR_NAME_OPERATION_ID,
    ATTR_NAME_PATH,
    ATTR_NAME_OPERATION,
)


class ConcreteEgressService(BaseEgressAgentService):
    """Concrete implementation for testing."""

    def _get_version(self):
        return "1.0.0"

    def _get_build_number(self):
        return "123"

    def _register_operations(self):
        pass

    def _internal_execute_agent_operation(self, operation_id, event):
        return {"result": "test"}


class BaseEgressServiceTests(TestCase):
    def setUp(self):
        self._config_manager = Mock()
        self._config_manager.get_int_value.return_value = 1
        self._config_manager.get_bool_value.return_value = True

        self._ops_runner = Mock()
        self._results_publisher = Mock()
        self._events_client = Mock()
        self._ack_sender = Mock()
        self._operations_poller = Mock()
        self._backend_client = Mock()

        with patch(
            "apollo.egress.agent.service.base_egress_service.BackendClient"
        ) as mock_backend:
            mock_backend.return_value = self._backend_client
            self._service = ConcreteEgressService(
                backend_service_url="http://test",
                platform="test",
                service_name="TestService",
                config_manager=self._config_manager,
                logs_service=None,
                metrics_service=Mock(),
                storage_service=Mock(),
                login_token_provider=Mock(),
                ops_runner=self._ops_runner,
                results_publisher=self._results_publisher,
                events_client=self._events_client,
                ack_sender=self._ack_sender,
                operations_poller=self._operations_poller,
                skip_logs=True,
            )

    def test_start_starts_operations_poller(self):
        """Test that start() starts the operations poller."""
        self._service.start()

        self._operations_poller.start.assert_called_once()

    def test_start_starts_events_client_when_sse_enabled(self):
        """Test that start() starts events client when SSE is enabled."""
        self._service._sse_enabled = True

        self._service.start()

        self._events_client.start.assert_called_once()
        # Verify work_available_handler is passed
        call_kwargs = self._events_client.start.call_args.kwargs
        self.assertIn("work_available_handler", call_kwargs)

    def test_start_skips_events_client_when_sse_disabled(self):
        """Test that start() skips events client when SSE is disabled."""
        self._service._sse_enabled = False

        self._service.start()

        self._events_client.start.assert_not_called()

    def test_stop_stops_operations_poller(self):
        """Test that stop() stops the operations poller."""
        self._service.stop()

        self._operations_poller.stop.assert_called_once()

    def test_metrics_timer_not_created_when_disabled(self):
        """Test that _metrics_timer is None when METRICS_TIMER_ENABLED=False."""
        self._config_manager.get_bool_value.return_value = False
        with patch(
            "apollo.egress.agent.service.base_egress_service.BackendClient"
        ) as mock_backend:
            mock_backend.return_value = self._backend_client
            service = ConcreteEgressService(
                backend_service_url="http://test",
                platform="test",
                service_name="Test",
                config_manager=self._config_manager,
                logs_service=None,
                metrics_service=Mock(),
                storage_service=Mock(),
                login_token_provider=Mock(),
                ops_runner=self._ops_runner,
                results_publisher=self._results_publisher,
                events_client=self._events_client,
                ack_sender=self._ack_sender,
                operations_poller=self._operations_poller,
                skip_logs=True,
            )

        self.assertIsNone(service._metrics_timer)

    def test_metrics_timer_created_when_enabled(self):
        """Test that _metrics_timer is created when METRICS_TIMER_ENABLED=True."""
        # setUp already sets get_bool_value to return True
        self.assertIsNotNone(self._service._metrics_timer)

    def test_start_does_not_fail_when_metrics_timer_disabled(self):
        """Test that start() works when metrics timer is disabled."""
        self._service._sse_enabled = False
        self._service._metrics_timer = None  # Simulate disabled

        # Should not raise
        self._service.start()

    def test_stop_stops_events_client_when_sse_enabled(self):
        """Test that stop() stops events client when SSE is enabled."""
        self._service._sse_enabled = True

        self._service.stop()

        self._events_client.stop.assert_called_once()

    def test_stop_skips_events_client_when_sse_disabled(self):
        """Test that stop() skips events client when SSE is disabled."""
        self._service._sse_enabled = False

        self._service.stop()

        self._events_client.stop.assert_not_called()

    def test_handle_polled_operation_schedules_ack(self):
        """Test that _handle_polled_operation schedules ACK."""
        self._service._execute_operation = Mock()

        self._service._handle_polled_operation("/test/path", "op-123", {"data": "test"})

        self._ack_sender.schedule_ack.assert_called_once_with("op-123")

    def test_handle_polled_operation_calls_execute_operation(self):
        """Test that _handle_polled_operation calls _execute_operation."""
        self._service._execute_operation = Mock()
        operation = {
            ATTR_NAME_OPERATION_ID: "op-123",
            ATTR_NAME_PATH: "/test/path",
            ATTR_NAME_OPERATION: {"data": "test"},
        }

        self._service._handle_polled_operation("/test/path", "op-123", operation)

        self._service._execute_operation.assert_called_once_with(
            "/test/path", "op-123", operation
        )

    def test_handle_piggybacked_operation_schedules_ack(self):
        """Test that _handle_piggybacked_operation schedules ACK."""
        self._service._execute_operation = Mock()
        operation = {
            ATTR_NAME_OPERATION_ID: "op-456",
            ATTR_NAME_PATH: "/piggybacked/path",
            ATTR_NAME_OPERATION: {"data": "piggybacked"},
        }

        self._service._handle_piggybacked_operation(operation)

        self._ack_sender.schedule_ack.assert_called_once_with("op-456")

    def test_handle_piggybacked_operation_calls_execute_operation(self):
        """Test that _handle_piggybacked_operation calls _execute_operation."""
        self._service._execute_operation = Mock()
        operation = {
            ATTR_NAME_OPERATION_ID: "op-456",
            ATTR_NAME_PATH: "/piggybacked/path",
            ATTR_NAME_OPERATION: {"data": "piggybacked"},
        }

        self._service._handle_piggybacked_operation(operation)

        self._service._execute_operation.assert_called_once_with(
            "/piggybacked/path", "op-456", operation
        )

    def test_handle_piggybacked_operation_skips_invalid(self):
        """Test that _handle_piggybacked_operation skips invalid operations."""
        self._service._execute_operation = Mock()

        # Missing path
        self._service._handle_piggybacked_operation({ATTR_NAME_OPERATION_ID: "op-123"})
        # Missing operation_id
        self._service._handle_piggybacked_operation({ATTR_NAME_PATH: "/test"})

        self._service._execute_operation.assert_not_called()

    def test_push_backend_results_handles_piggybacked_operation(self):
        """Test that _push_backend_results processes piggybacked operations."""
        self._service._handle_piggybacked_operation = Mock()
        next_op = {
            ATTR_NAME_OPERATION_ID: "next-op",
            ATTR_NAME_PATH: "/next/path",
        }
        self._backend_client.push_results.return_value = {"next_operation": next_op}

        self._service._push_backend_results("op-123", {"result": "test"}, None)

        self._service._handle_piggybacked_operation.assert_called_once_with(next_op)

    def test_push_backend_results_no_piggyback(self):
        """Test that _push_backend_results works when no piggybacked operation."""
        self._service._handle_piggybacked_operation = Mock()
        self._backend_client.push_results.return_value = {"operation_id": "op-123"}

        self._service._push_backend_results("op-123", {"result": "test"}, None)

        self._service._handle_piggybacked_operation.assert_not_called()

    def test_can_accept_work_returns_true_when_queue_empty(self):
        """Test _can_accept_work returns True when ops_runner queue is empty."""
        self._ops_runner.queue_depth.return_value = 0
        self._ops_runner.thread_count = 4

        result = self._service._can_accept_work()

        self.assertTrue(result)

    def test_can_accept_work_returns_true_when_queue_below_capacity(self):
        """Test _can_accept_work returns True when queue < thread_count."""
        self._ops_runner.queue_depth.return_value = 2
        self._ops_runner.thread_count = 4

        result = self._service._can_accept_work()

        self.assertTrue(result)

    def test_can_accept_work_returns_false_when_queue_at_capacity(self):
        """Test _can_accept_work returns False when queue == thread_count."""
        self._ops_runner.queue_depth.return_value = 4
        self._ops_runner.thread_count = 4

        result = self._service._can_accept_work()

        self.assertFalse(result)

    def test_can_accept_work_returns_false_when_queue_over_capacity(self):
        """Test _can_accept_work returns False when queue > thread_count."""
        self._ops_runner.queue_depth.return_value = 5
        self._ops_runner.thread_count = 4

        result = self._service._can_accept_work()

        self.assertFalse(result)

    @patch("apollo.egress.agent.service.base_egress_service.sys")
    def test_handle_goodbye_triggers_graceful_shutdown(self, mock_sys):
        """Test that _handle_goodbye notifies orchestrator, stops, and exits."""
        self._service._handle_goodbye("activity_timeout")

        self._backend_client.notify_shutdown.assert_called_once()
        self._operations_poller.stop.assert_called_once()
        mock_sys.exit.assert_called_once_with(0)

    @patch("apollo.egress.agent.service.base_egress_service.sys")
    def test_trigger_graceful_shutdown_continues_on_notify_failure(self, mock_sys):
        """Test that shutdown continues even if notify_shutdown fails."""
        self._backend_client.notify_shutdown.side_effect = Exception(
            "connection refused"
        )

        self._service._trigger_graceful_shutdown()

        # stop and exit still called despite notify failure
        self._operations_poller.stop.assert_called_once()
        mock_sys.exit.assert_called_once_with(0)

    @patch("apollo.egress.agent.service.base_egress_service.sys")
    def test_start_passes_goodbye_handler_to_events_client(self, mock_sys):
        """Test that start() passes goodbye_handler to EventsClient."""
        self._service._sse_enabled = True

        self._service.start()

        call_kwargs = self._events_client.start.call_args.kwargs
        self.assertIn("goodbye_handler", call_kwargs)
        self.assertEqual(call_kwargs["goodbye_handler"], self._service._handle_goodbye)

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
        call_kwargs = self._events_client.start.call_args
        self.assertIn("work_available_handler", call_kwargs.kwargs)

    def test_start_skips_events_client_when_sse_disabled(self):
        """Test that start() skips events client when SSE is disabled."""
        self._service._sse_enabled = False

        self._service.start()

        self._events_client.start.assert_not_called()

    def test_stop_stops_operations_poller(self):
        """Test that stop() stops the operations poller."""
        self._service.stop()

        self._operations_poller.stop.assert_called_once()

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

    def test_handle_polled_operation_returns_error_for_invalid_operation(self):
        """Test that _handle_polled_operation returns error for invalid operation."""
        result = self._service._handle_polled_operation({})

        self.assertEqual(result, {"error": "Invalid operation"})

    def test_handle_polled_operation_schedules_ack(self):
        """Test that _handle_polled_operation schedules ACK."""
        self._service._resolve_operation_method = Mock(
            return_value=(Mock(return_value={}), None)
        )
        operation = {
            ATTR_NAME_OPERATION_ID: "op-123",
            ATTR_NAME_PATH: "/test/path",
            ATTR_NAME_OPERATION: {"data": "test"},
        }

        self._service._handle_polled_operation(operation)

        self._ack_sender.schedule_ack.assert_called_once_with("op-123")

    def test_handle_polled_operation_downloads_size_exceeded_operation(self):
        """Test that _handle_polled_operation downloads size-exceeded operations."""
        self._service._resolve_operation_method = Mock(
            return_value=(Mock(return_value={}), None)
        )
        self._backend_client.download_operation.return_value = {"downloaded": "data"}
        operation = {
            ATTR_NAME_OPERATION_ID: "op-123",
            ATTR_NAME_PATH: "/test/path",
            ATTR_NAME_OPERATION: {"__mcd_size_exceeded__": True},
        }

        self._service._handle_polled_operation(operation)

        self._backend_client.download_operation.assert_called_once_with("op-123")

    def test_handle_polled_operation_calls_method_and_returns_result(self):
        """Test that _handle_polled_operation calls the resolved method."""
        expected_result = {"result": "success"}
        mock_method = Mock(return_value=expected_result)
        self._service._resolve_operation_method = Mock(return_value=(mock_method, None))
        operation = {
            ATTR_NAME_OPERATION_ID: "op-123",
            ATTR_NAME_PATH: "/test/path",
            ATTR_NAME_OPERATION: {"data": "test"},
        }

        result = self._service._handle_polled_operation(operation)

        self.assertEqual(result, expected_result)
        mock_method.assert_called_once()

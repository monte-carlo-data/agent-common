import signal

from unittest import TestCase
from unittest.mock import Mock, patch, MagicMock

from apollo.egress.agent.backend.backend_client import ATTR_NAME_ERROR
from apollo.egress.agent.service.base_egress_service import (
    BaseEgressAgentService,
    ATTR_NAME_BACKEND_URL,
    ATTR_NAME_LIMIT,
    ATTR_NAME_OPERATION_ID,
    ATTR_NAME_PATH,
    ATTR_NAME_OPERATION,
)
from apollo.egress.agent.service.login_token_provider import (
    ATTR_NAME_AUTH_METHOD,
    ATTR_NAME_KEY_ID,
    ATTR_NAME_TOKEN_FILE_PATH,
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

    def test_handle_polled_operation_calls_execute_operation(self):
        """Test that _handle_polled_operation calls _execute_operation."""
        self._service._execute_operation = Mock()
        operation = {"data": "test"}

        self._service._handle_polled_operation("/test/path", "op-123", operation)

        self._service._execute_operation.assert_called_once_with(
            "/test/path", "op-123", operation
        )

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

    @patch("apollo.egress.agent.service.base_egress_service.os")
    def test_handle_goodbye_triggers_graceful_shutdown(self, mock_os):
        """Test that _handle_goodbye notifies orchestrator, stops threads, and signals exit."""
        self._service._handle_goodbye("activity_timeout")

        self._backend_client.notify_shutdown.assert_called_once()
        self._operations_poller.stop.assert_called_once()
        mock_os.kill.assert_called_once_with(mock_os.getpid(), signal.SIGTERM)

    @patch("apollo.egress.agent.service.base_egress_service.os")
    def test_trigger_graceful_shutdown_only_runs_once(self, mock_os):
        """Test that _trigger_graceful_shutdown is guarded against double execution."""
        self._service._trigger_graceful_shutdown()
        self._service._trigger_graceful_shutdown()

        # notify and stop called only once
        self._backend_client.notify_shutdown.assert_called_once()
        self._operations_poller.stop.assert_called_once()

    def test_start_passes_goodbye_handler_to_events_client(self):
        """Test that start() passes goodbye_handler to EventsClient."""
        self._service._sse_enabled = True

        self._service.start()

        call_kwargs = self._events_client.start.call_args.kwargs
        self.assertIn("goodbye_handler", call_kwargs)
        self.assertEqual(call_kwargs["goodbye_handler"], self._service._handle_goodbye)

    def _build_service_with_logs(self, logs_service):
        with patch(
            "apollo.egress.agent.service.base_egress_service.BackendClient"
        ) as mock_backend:
            mock_backend.return_value = self._backend_client
            return ConcreteEgressService(
                backend_service_url="http://test",
                platform="test",
                service_name="TestService",
                config_manager=self._config_manager,
                logs_service=logs_service,
                metrics_service=Mock(),
                storage_service=Mock(),
                login_token_provider=Mock(),
                ops_runner=self._ops_runner,
                results_publisher=self._results_publisher,
                events_client=self._events_client,
                operations_poller=self._operations_poller,
                skip_logs=False,
            )

    def test_execute_push_logs_calls_drain_when_supported(self):
        logs_service = Mock()
        logs_service.supports_drain.return_value = True
        logs_service.drain.return_value = [{"timestamp": "t", "message": "m"}]
        service = self._build_service_with_logs(logs_service)
        service._execute_push_logs(_operation_id="op", event={})
        logs_service.drain.assert_called_once_with()
        logs_service.get_logs.assert_not_called()
        self._backend_client.execute_operation.assert_called_once_with(
            "/api/v1/agent/logs",
            "POST",
            {"logs": [{"timestamp": "t", "message": "m"}]},
        )

    def test_execute_push_logs_falls_back_to_get_logs_when_drain_unsupported(self):
        logs_service = Mock()
        logs_service.supports_drain.return_value = False
        logs_service.get_logs.return_value = [{"timestamp": "t", "message": "m"}]
        service = self._build_service_with_logs(logs_service)
        service._execute_push_logs(_operation_id="op", event={ATTR_NAME_LIMIT: 250})
        logs_service.drain.assert_not_called()
        logs_service.get_logs.assert_called_once_with(250)
        self._backend_client.execute_operation.assert_called_once_with(
            "/api/v1/agent/logs",
            "POST",
            {"logs": [{"timestamp": "t", "message": "m"}]},
        )

    def test_flush_logs_skips_post_when_empty(self):
        logs_service = Mock()
        logs_service.supports_drain.return_value = True
        logs_service.drain.return_value = []
        service = self._build_service_with_logs(logs_service)
        service._flush_logs()
        self._backend_client.execute_operation.assert_not_called()

    def test_stop_drains_then_closes_then_flushes_when_drain_supported(self):
        logs_service = Mock()
        logs_service.supports_drain.return_value = True
        # Track call order so we can assert drain happens before close.
        call_order: list[str] = []
        logs_service.drain.side_effect = lambda: (
            call_order.append("drain") or [{"timestamp": "t", "message": "m"}]
        )
        logs_service.close.side_effect = lambda: call_order.append("close")
        self._backend_client.execute_operation.side_effect = (
            lambda *a, **kw: call_order.append("post") or {}
        )
        service = self._build_service_with_logs(logs_service)
        service.stop()
        # Drain must run before close so records are captured before any
        # handler detachment, and POST runs last from the local list.
        self.assertEqual(call_order, ["drain", "close", "post"])
        self._backend_client.execute_operation.assert_called_once_with(
            "/api/v1/agent/logs",
            "POST",
            {"logs": [{"timestamp": "t", "message": "m"}]},
            timeout=service.SHUTDOWN_LOGS_FLUSH_TIMEOUT_SECONDS,
            skip_retries=service.SHUTDOWN_LOGS_FLUSH_SKIP_RETRIES,
        )

    def test_stop_still_closes_when_drain_raises(self):
        # Drain failure must not skip close() or short-circuit the rest of
        # shutdown — each step is independently guarded.
        logs_service = Mock()
        logs_service.supports_drain.return_value = True
        logs_service.drain.side_effect = RuntimeError("drain boom")
        service = self._build_service_with_logs(logs_service)
        service.stop()
        logs_service.close.assert_called_once_with()
        # Nothing to POST when drain failed — pending_logs is empty.
        self._backend_client.execute_operation.assert_not_called()

    def test_stop_still_posts_when_close_raises(self):
        # close() failure must not skip the POST — records were already
        # drained into the local list, so they're still shippable.
        logs_service = Mock()
        logs_service.supports_drain.return_value = True
        logs_service.drain.return_value = [{"timestamp": "t", "message": "m"}]
        logs_service.close.side_effect = RuntimeError("close boom")
        service = self._build_service_with_logs(logs_service)
        service.stop()
        logs_service.drain.assert_called_once_with()
        logs_service.close.assert_called_once_with()
        self._backend_client.execute_operation.assert_called_once_with(
            "/api/v1/agent/logs",
            "POST",
            {"logs": [{"timestamp": "t", "message": "m"}]},
            timeout=service.SHUTDOWN_LOGS_FLUSH_TIMEOUT_SECONDS,
            skip_retries=service.SHUTDOWN_LOGS_FLUSH_SKIP_RETRIES,
        )

    def test_stop_skips_flush_when_drain_unsupported(self):
        logs_service = Mock()
        logs_service.supports_drain.return_value = False
        service = self._build_service_with_logs(logs_service)
        service.stop()
        # close() still runs — non-drain services may still hold resources.
        logs_service.close.assert_called_once_with()
        # No final flush — non-destructive services are fed by other means
        # (e.g. external file tailers) that handle their own continuity.
        self._backend_client.execute_operation.assert_not_called()

    def test_stop_handles_no_logs_service(self):
        # No logs_service configured — stop() must not raise.
        self._service.stop()


class CredentialReportingTests(TestCase):
    """The reachability test and health info must say which credential was used.

    Auth failures are rejected at the backend gateway, so the agent's own
    output is the only place an operator can see the credential id.
    """

    def setUp(self):
        self._config_manager = Mock()
        self._config_manager.get_int_value.return_value = 1
        self._config_manager.get_bool_value.return_value = True

        self._backend_client = Mock()
        self._login_token_provider = Mock()
        self._login_token_provider.get_credential_info.return_value = {
            ATTR_NAME_KEY_ID: "no-token-id",
            ATTR_NAME_AUTH_METHOD: "token_file",
            ATTR_NAME_TOKEN_FILE_PATH: "/etc/secrets/mcd-agent-token/contents.json",
        }

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
                login_token_provider=self._login_token_provider,
                ops_runner=Mock(),
                results_publisher=Mock(),
                events_client=Mock(),
                operations_poller=Mock(),
                skip_logs=True,
            )

    def test_reachability_failure_includes_credential_info(self):
        self._backend_client.execute_operation.return_value = {
            ATTR_NAME_ERROR: "401 Client Error: Unauthorized"
        }

        result = self._service.run_reachability_test(trace_id="a-trace-id")

        self.assertEqual(
            {
                ATTR_NAME_ERROR: "401 Client Error: Unauthorized",
                ATTR_NAME_KEY_ID: "no-token-id",
                ATTR_NAME_AUTH_METHOD: "token_file",
                ATTR_NAME_TOKEN_FILE_PATH: "/etc/secrets/mcd-agent-token/contents.json",
                ATTR_NAME_BACKEND_URL: "http://test",
            },
            result,
        )

    def test_reachability_success_is_returned_unchanged(self):
        # The success payload comes from the backend; adding keys to it risks
        # colliding with what its consumers parse.
        self._backend_client.execute_operation.return_value = {"status": "ok"}

        result = self._service.run_reachability_test(trace_id="a-trace-id")

        self.assertEqual({"status": "ok"}, result)

    def test_reachability_failure_does_not_raise_when_reporting_fails(self):
        self._backend_client.execute_operation.return_value = {
            ATTR_NAME_ERROR: "401 Client Error: Unauthorized"
        }
        self._login_token_provider.get_credential_info.side_effect = ValueError("boom")

        result = self._service.run_reachability_test(trace_id="a-trace-id")

        # The error and the rest of the context still make it out.
        self.assertEqual(
            {
                ATTR_NAME_ERROR: "401 Client Error: Unauthorized",
                ATTR_NAME_BACKEND_URL: "http://test",
            },
            result,
        )

    def test_health_information_reports_credential_info(self):
        health_info = self._service.health_information(trace_id="a-trace-id")

        self.assertEqual("no-token-id", health_info[ATTR_NAME_KEY_ID])
        self.assertEqual("token_file", health_info[ATTR_NAME_AUTH_METHOD])
        self.assertEqual(
            "/etc/secrets/mcd-agent-token/contents.json",
            health_info[ATTR_NAME_TOKEN_FILE_PATH],
        )
        self.assertEqual("http://test", health_info[ATTR_NAME_BACKEND_URL])
        # Reporting must never read the token itself.
        self._login_token_provider.get_token.assert_not_called()

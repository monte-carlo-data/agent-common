from unittest import TestCase
from unittest.mock import Mock, patch

from apollo.egress.agent.backend.backend_client import BackendClient, INSTANCE_ID_HEADER


class BackendClientTests(TestCase):
    def setUp(self):
        self._login_token_provider = Mock()
        self._login_token_provider.get_token.return_value = {
            "x-mcd-id": "test-id",
            "x-mcd-token": "test-token",
        }
        self._client = BackendClient(
            backend_service_url="https://orchestrator.test",
            login_token_provider=self._login_token_provider,
        )

    def test_instance_id_is_generated(self):
        """Instance ID should be a non-empty string, unique per client."""
        self.assertIsInstance(self._client.instance_id, str)
        self.assertTrue(len(self._client.instance_id) > 0)

        other = BackendClient(
            backend_service_url="https://orchestrator.test",
            login_token_provider=self._login_token_provider,
        )
        self.assertNotEqual(self._client.instance_id, other.instance_id)

    def test_headers_include_instance_id(self):
        """All requests should include the instance ID header."""
        headers = self._client._headers()
        self.assertEqual(headers[INSTANCE_ID_HEADER], self._client.instance_id)
        self.assertEqual(headers["x-mcd-id"], "test-id")
        self.assertEqual(headers["x-mcd-token"], "test-token")

    def test_headers_include_extra(self):
        """Extra headers should be merged."""
        headers = self._client._headers(**{"Content-Type": "application/json"})
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertIn(INSTANCE_ID_HEADER, headers)

    @patch("requests.post")
    def test_send_heartbeat(self, mock_post):
        """send_heartbeat should POST to /api/v1/agent/heartbeat with correct headers."""
        mock_post.return_value.status_code = 200

        self._client.send_heartbeat()

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "https://orchestrator.test/api/v1/agent/heartbeat")
        self.assertIn(INSTANCE_ID_HEADER, kwargs["headers"])
        self.assertEqual(kwargs["timeout"], 10)

    @patch("requests.post")
    def test_notify_shutdown(self, mock_post):
        """notify_shutdown should POST to /api/v1/agent/shutdown with correct headers."""
        mock_post.return_value.status_code = 200

        self._client.notify_shutdown()

        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "https://orchestrator.test/api/v1/agent/shutdown")
        self.assertIn(INSTANCE_ID_HEADER, kwargs["headers"])
        self.assertEqual(kwargs["timeout"], 15)

    @patch("requests.post")
    def test_notify_shutdown_raises_on_failure(self, mock_post):
        """notify_shutdown should raise on HTTP errors."""
        mock_post.return_value.raise_for_status.side_effect = Exception("500")

        with self.assertRaises(Exception):
            self._client.notify_shutdown()


class BackendClientURLTests(TestCase):
    """Tests that BackendClient preserves the path component of the backend service URL."""

    def setUp(self):
        self._login_token_provider = Mock()
        self._login_token_provider.get_token.return_value = {"x-mcd-id": "test"}

    @patch("apollo.egress.agent.backend.backend_client.requests.put")
    def test_push_results_preserves_base_url_path(self, mock_put: Mock):
        mock_put.return_value = Mock(status_code=200)
        client = BackendClient(
            backend_service_url="http://server/custom-path",
            login_token_provider=self._login_token_provider,
        )

        client.push_results("op-123", {"key": "value"})

        called_url = mock_put.call_args[0][0]
        self.assertEqual(
            "http://server/custom-path/api/v1/agent/operations/op-123/result",
            called_url,
        )

    @patch("apollo.egress.agent.backend.backend_client.requests.put")
    def test_push_results_works_without_base_url_path(self, mock_put: Mock):
        mock_put.return_value = Mock(status_code=200)
        client = BackendClient(
            backend_service_url="http://server",
            login_token_provider=self._login_token_provider,
        )

        client.push_results("op-123", {"key": "value"})

        called_url = mock_put.call_args[0][0]
        self.assertEqual(
            "http://server/api/v1/agent/operations/op-123/result",
            called_url,
        )

    @patch("apollo.egress.agent.backend.backend_client.requests.put")
    def test_push_results_handles_trailing_slash(self, mock_put: Mock):
        mock_put.return_value = Mock(status_code=200)
        client = BackendClient(
            backend_service_url="http://server/custom-path/",
            login_token_provider=self._login_token_provider,
        )

        client.push_results("op-123", {"key": "value"})

        called_url = mock_put.call_args[0][0]
        self.assertEqual(
            "http://server/custom-path/api/v1/agent/operations/op-123/result",
            called_url,
        )

    @patch("apollo.egress.agent.backend.backend_client.requests.request")
    def test_execute_operation_preserves_base_url_path(self, mock_request: Mock):
        mock_request.return_value = Mock(status_code=200)
        mock_request.return_value.json.return_value = {"ok": True}
        client = BackendClient(
            backend_service_url="http://server/custom-path",
            login_token_provider=self._login_token_provider,
        )

        client.execute_operation("/api/v1/agent/metrics", "POST", {"data": 1})

        called_url = mock_request.call_args[1]["url"]
        self.assertEqual(
            "http://server/custom-path/api/v1/agent/metrics",
            called_url,
        )

    @patch("apollo.egress.agent.backend.backend_client.requests.request")
    def test_execute_operation_works_without_base_url_path(self, mock_request: Mock):
        mock_request.return_value = Mock(status_code=200)
        mock_request.return_value.json.return_value = {"ok": True}
        client = BackendClient(
            backend_service_url="http://server",
            login_token_provider=self._login_token_provider,
        )

        client.execute_operation("/api/v1/test/ping")

        called_url = mock_request.call_args[1]["url"]
        self.assertEqual(
            "http://server/api/v1/test/ping",
            called_url,
        )

    @patch("apollo.egress.agent.backend.backend_client.requests.request")
    def test_execute_operation_handles_path_without_leading_slash(
        self, mock_request: Mock
    ):
        mock_request.return_value = Mock(status_code=200)
        mock_request.return_value.json.return_value = {"ok": True}
        client = BackendClient(
            backend_service_url="http://server/custom-path",
            login_token_provider=self._login_token_provider,
        )

        client.execute_operation("api/v1/test/ping")

        called_url = mock_request.call_args[1]["url"]
        self.assertEqual(
            "http://server/custom-path/api/v1/test/ping",
            called_url,
        )

    @patch("apollo.egress.agent.backend.backend_client.requests.request")
    def test_download_operation_preserves_base_url_path(self, mock_request: Mock):
        mock_request.return_value = Mock(status_code=200)
        mock_request.return_value.json.return_value = {"operation": "data"}
        client = BackendClient(
            backend_service_url="http://server/custom-path",
            login_token_provider=self._login_token_provider,
        )

        client.download_operation("op-456")

        called_url = mock_request.call_args[1]["url"]
        self.assertEqual(
            "http://server/custom-path/api/v1/agent/operations/op-456/request",
            called_url,
        )

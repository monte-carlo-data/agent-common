from unittest import TestCase
from unittest.mock import Mock, patch

from apollo.egress.agent.backend.backend_client import BackendClient


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

import json
import logging
from typing import Dict, Any, Optional
import requests
from retry import retry

from apollo.common.agent.serde import AgentSerializer

from apollo.egress.agent.service.login_token_provider import LoginTokenProvider
from apollo.egress.agent.utils.utils import build_url

logger = logging.getLogger(__name__)


class BackendClient:
    """
    Client used to interact with the MC Backend (Orchestrator) service.
    """

    def __init__(
        self,
        backend_service_url: str,
        login_token_provider: LoginTokenProvider,
    ) -> None:
        self._backend_service_url = backend_service_url
        self._login_token_provider = login_token_provider

    def push_results(
        self, operation_id: str, result: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Pushes the result for a given operation.
        Returns response dict which may include 'next_operation' for piggybacking.
        """
        try:
            return self._push_results_with_retries(operation_id, result)
        except Exception as ex:
            logger.error(f"Failed to push results to backend: {ex}")
            return None

    @retry(tries=3, delay=1, backoff=2)
    def _push_results_with_retries(
        self, operation_id: str, result: Dict[str, Any]
    ) -> Dict[str, Any]:
        logger.info(f"Sending query results to backend, operation_id: {operation_id}")
        results_url = build_url(
            self._backend_service_url, f"/api/v1/agent/operations/{operation_id}/result"
        )
        result_str = json.dumps(
            {
                "result": result,
            },
            cls=AgentSerializer,
        )
        response = requests.put(
            results_url,
            data=result_str,
            headers={
                "Content-Type": "application/json",
                **self._login_token_provider.get_token(),
            },
            timeout=60,
        )
        response.raise_for_status()
        logger.info(
            f"Sent query results to backend, operation_id: {operation_id}, response: {response.status_code}"
        )
        return response.json()

    def execute_operation(
        self, path: str, method: str = "GET", body: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        return self._execute_operation_with_retries(path, method, body)

    @retry(tries=3, delay=1, backoff=2)
    def _execute_operation_with_retries(
        self, path: str, method: str = "GET", body: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Performs an operation on the backend service. For example `ping`.
        """
        try:
            url = build_url(self._backend_service_url, path)
            headers = self._login_token_provider.get_token()
            if body:
                headers["Content-Type"] = "application/json"
            response = requests.request(
                method=method,
                url=url,
                json=body,
                headers=headers,
            )
            logger.info(
                f"Sent backend request {path}, response: {response.status_code}"
            )
            response.raise_for_status()
            return response.json() or {"error": "empty response"}
        except Exception as ex:
            logger.error(f"Error sending request to backend: {ex}")
            return {
                "error": str(ex),
            }

    def download_operation(self, operation_id: str) -> Dict:
        """
        Download the full body for an operation, `SSE` has a limit in the size of the events, so
        when the operation exceeds that size we perform an additional request to get the full
        operation.
        """
        operation = self.execute_operation(
            f"/api/v1/agent/operations/{operation_id}/request"
        )
        if error_message := operation.get("error"):
            raise Exception(
                f"Failed to download operation {operation_id}: {error_message}"
            )
        return operation

    def get_next_operation(self) -> Optional[Dict[str, Any]]:
        """
        Fetch next operation from orchestrator queue.
        Used by the pull model where agents poll for work.
        Returns None if no operations are available.
        """
        url = build_url(self._backend_service_url, "/api/v1/agent/operation")
        response = requests.get(
            url,
            headers=self._login_token_provider.get_token(),
            timeout=30,
        )
        if response.status_code == 204:
            return None
        response.raise_for_status()
        return response.json()

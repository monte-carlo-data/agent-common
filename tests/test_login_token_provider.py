import json
import os
import tempfile
from typing import Dict
from unittest import TestCase

from apollo.egress.agent.service.file_login_token_provider import FileLoginTokenProvider
from apollo.egress.agent.service.login_token_provider import (
    ATTR_NAME_AUTH_METHOD,
    ATTR_NAME_KEY_ID,
    ATTR_NAME_TOKEN_FILE_PATH,
    AUTH_METHOD_LOCAL_ENV,
    AUTH_METHOD_TOKEN_FILE,
    AUTH_METHOD_UNKNOWN,
    LocalLoginTokenProvider,
    LoginTokenProvider,
)
from apollo.egress.agent.utils.utils import X_MCD_ID, X_MCD_TOKEN


class _NonReportingLoginTokenProvider(LoginTokenProvider):
    """Provider that doesn't implement the reporting accessors.

    Its ``get_token()`` is expensive and raises when credentials are missing —
    like the providers that authenticate against a remote token endpoint.
    """

    def __init__(self):
        self.get_token_calls = 0

    def get_token(self) -> Dict[str, str]:
        self.get_token_calls += 1
        raise ValueError("Monte Carlo token file not found")


class LocalLoginTokenProviderTests(TestCase):
    def test_credential_info_reports_local_token_id(self):
        provider = LocalLoginTokenProvider()

        self.assertEqual("local-token-id", provider.get_credential_id())
        self.assertEqual(
            {
                ATTR_NAME_KEY_ID: "local-token-id",
                ATTR_NAME_AUTH_METHOD: AUTH_METHOD_LOCAL_ENV,
            },
            provider.get_credential_info(),
        )


class FileLoginTokenProviderTests(TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._dir.cleanup)
        self._file_path = os.path.join(self._dir.name, "contents.json")

    def _write_token_file(self, contents: str):
        with open(self._file_path, "w") as f:
            f.write(contents)

    def test_credential_info_reports_mcd_id_and_never_the_token(self):
        self._write_token_file(json.dumps({"mcd_id": "an-id", "mcd_token": "a-secret"}))
        provider = FileLoginTokenProvider(file_path=self._file_path)

        credential_info = provider.get_credential_info()

        self.assertEqual(
            {
                ATTR_NAME_KEY_ID: "an-id",
                ATTR_NAME_AUTH_METHOD: AUTH_METHOD_TOKEN_FILE,
                ATTR_NAME_TOKEN_FILE_PATH: self._file_path,
            },
            credential_info,
        )
        self.assertNotIn("a-secret", json.dumps(credential_info))

    def test_credential_id_reports_no_token_id_when_file_is_missing(self):
        provider = FileLoginTokenProvider(file_path=self._file_path)

        self.assertEqual("no-token-id", provider.get_credential_id())
        self.assertEqual(
            self._file_path,
            provider.get_credential_info()[ATTR_NAME_TOKEN_FILE_PATH],
        )

    def test_credential_id_reports_no_token_id_when_file_is_unparseable(self):
        self._write_token_file("not json")
        provider = FileLoginTokenProvider(file_path=self._file_path)

        self.assertEqual("no-token-id", provider.get_credential_id())

    def test_get_token_still_returns_the_credentials(self):
        self._write_token_file(json.dumps({"mcd_id": "an-id", "mcd_token": "a-secret"}))
        provider = FileLoginTokenProvider(file_path=self._file_path)

        self.assertEqual(
            {X_MCD_ID: "an-id", X_MCD_TOKEN: "a-secret"},
            provider.get_token(),
        )


class NonReportingLoginTokenProviderTests(TestCase):
    def test_credential_id_is_none_when_the_provider_does_not_report_one(self):
        """Reporting must not raise: it is called precisely when auth is failing."""
        provider = _NonReportingLoginTokenProvider()

        self.assertIsNone(provider.get_credential_id())
        self.assertEqual(
            {ATTR_NAME_KEY_ID: None, ATTR_NAME_AUTH_METHOD: AUTH_METHOD_UNKNOWN},
            provider.get_credential_info(),
        )

    def test_reporting_never_acquires_a_credential(self):
        """The default must not call get_token(): that can be a remote fetch, on
        the startup path, for the credential that is already failing."""
        provider = _NonReportingLoginTokenProvider()

        provider.get_credential_id()
        provider.get_credential_info()

        self.assertEqual(0, provider.get_token_calls)

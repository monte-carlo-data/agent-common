from unittest import TestCase
from unittest.mock import patch

from apollo.egress.agent.config.local_config import LocalConfig


class LocalConfigTests(TestCase):
    def setUp(self):
        self._config = LocalConfig(prefix="MCD")

    def test_get_value_reads_prefixed_env_var(self):
        with patch.dict("os.environ", {"MCD_SOME_KEY": "value"}, clear=True):
            self.assertEqual("value", self._config.get_value("SOME_KEY"))

    def test_get_value_returns_none_when_missing(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertIsNone(self._config.get_value("SOME_KEY"))

    def test_set_value_raises(self):
        with self.assertRaises(NotImplementedError):
            self._config.set_value("key", "value")

    def test_get_all_values_returns_prefixed_entries(self):
        with patch.dict(
            "os.environ",
            {
                "MCD_A": "1",
                "MCD_B": "2",
                "OTHER": "x",
            },
            clear=True,
        ):
            self.assertEqual(
                {"MCD_A": "1", "MCD_B": "2"}, self._config.get_all_values()
            )

    def test_get_all_values_filters_sensitive_keys(self):
        # Regression: MCD_STORAGE_SECRET_KEY and similar sensitive env vars
        # must not be exposed via get_all_values (surfaced in health endpoint).
        with patch.dict(
            "os.environ",
            {
                "MCD_SAFE_SETTING": "visible",
                "MCD_STORAGE_SECRET_KEY": "shh",
                "MCD_DB_PASSWORD": "shh",
                "MCD_API_SECRET": "shh",
                "MCD_some_secret_lower": "shh",
            },
            clear=True,
        ):
            values = self._config.get_all_values()

        self.assertEqual({"MCD_SAFE_SETTING": "visible"}, values)

import datetime
import json
import logging
from unittest import TestCase
from unittest.mock import patch

from apollo.egress.agent.utils.utils import (
    _JsonFormatter,
    get_log_record_extra,
    init_logging,
)


class JsonFormatterTests(TestCase):
    def test_basic_format(self):
        """JSON formatter outputs valid JSON with expected fields."""
        formatter = _JsonFormatter(instance_id="test-instance")
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="test message",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)

        self.assertEqual(parsed["msg"], "test message")
        self.assertEqual(parsed["level"], "INFO")
        self.assertEqual(parsed["logger"], "test.logger")
        self.assertEqual(parsed["instance_id"], "test-instance")
        self.assertIn("ts", parsed)

    def test_format_without_instance_id(self):
        """JSON formatter omits instance_id when not provided."""
        formatter = _JsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="msg",
            args=(),
            exc_info=None,
        )
        parsed = json.loads(formatter.format(record))

        self.assertNotIn("instance_id", parsed)

    def test_format_with_exception(self):
        """JSON formatter includes exception info."""
        formatter = _JsonFormatter(instance_id="test")
        try:
            raise ValueError("test error")
        except ValueError:
            import sys

            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg="error occurred",
            args=(),
            exc_info=exc_info,
        )
        parsed = json.loads(formatter.format(record))

        self.assertIn("exception", parsed)
        self.assertIn("ValueError", parsed["exception"])

    def test_format_includes_extra_attributes(self):
        """Attributes passed via `extra=` are emitted under the "mcd" key."""
        formatter = _JsonFormatter(instance_id="test")
        record = logging.getLogger("test").makeRecord(
            "test",
            logging.INFO,
            "agent.py",
            1,
            "Executing operation: snowflake/query",
            (),
            None,
            extra={
                "mcd_trace_id": "trace-1",
                "mcd_operation_name": "query",
                "operation": {"type": "query", "query": "select 1"},
            },
        )
        parsed = json.loads(formatter.format(record))

        self.assertEqual(
            parsed["mcd"],
            {
                "mcd_trace_id": "trace-1",
                "mcd_operation_name": "query",
                "operation": {"type": "query", "query": "select 1"},
            },
        )
        # standard LogRecord attributes are not mistaken for extras
        self.assertNotIn("levelname", parsed["mcd"])
        self.assertNotIn("created", parsed["mcd"])

    def test_format_omits_extra_when_absent(self):
        """No "mcd" key when the record carries no custom attributes."""
        formatter = _JsonFormatter()
        record = logging.getLogger("test").makeRecord(
            "test", logging.INFO, "", 0, "plain", (), None
        )
        parsed = json.loads(formatter.format(record))

        self.assertNotIn("mcd", parsed)

    def test_format_redacts_sensitive_extra_attributes(self):
        """Extras go through the standard redaction before hitting stdout."""
        formatter = _JsonFormatter()
        record = logging.getLogger("test").makeRecord(
            "test",
            logging.INFO,
            "",
            0,
            "msg",
            (),
            None,
            extra={
                # UUID-shaped: the redactor's value regex would match it, only
                # the exact key name keeps it. Assert it round-trips.
                "mcd_trace_id": "3f8b1c2e-9a4d-4f1b-8c7a-1d2e3f4a5b6c",
                "credentials": {"password": "hunter2"},
                "connect_args": {"host": "db.internal", "user": "admin"},
            },
        )
        parsed = json.loads(formatter.format(record))

        self.assertEqual(
            parsed["mcd"]["mcd_trace_id"], "3f8b1c2e-9a4d-4f1b-8c7a-1d2e3f4a5b6c"
        )
        self.assertEqual(parsed["mcd"]["credentials"], "__redacted__")
        self.assertEqual(parsed["mcd"]["connect_args"]["host"], "db.internal")
        self.assertEqual(parsed["mcd"]["connect_args"]["user"], "__redacted__")

    def test_format_redacts_non_string_extra_values(self):
        """Values that are not JSON-native are stringified before redaction, so
        an exception message or a PEM blob carrying a secret is still masked."""
        formatter = _JsonFormatter()
        record = logging.getLogger("test").makeRecord(
            "test",
            logging.INFO,
            "",
            0,
            "msg",
            (),
            None,
            extra={
                "err": Exception("login failed for token abc-super-secret"),
                "pem": b"-----BEGIN PRIVATE KEY-----\nMIIE...",
                "nested": {"err": ValueError("bad password: hunter2")},
            },
        )
        parsed = json.loads(formatter.format(record))

        self.assertEqual(parsed["mcd"]["err"], "__redacted__")
        self.assertEqual(parsed["mcd"]["pem"], "__redacted__")
        self.assertEqual(parsed["mcd"]["nested"]["err"], "__redacted__")

    def test_format_handles_non_serializable_extra(self):
        """A non-JSON-serializable extra value must not break the log line."""
        formatter = _JsonFormatter()
        record = logging.getLogger("test").makeRecord(
            "test", logging.INFO, "", 0, "msg", (), None, extra={"when": object()}
        )
        parsed = json.loads(formatter.format(record))

        self.assertEqual(parsed["msg"], "msg")
        self.assertIsInstance(parsed["mcd"]["when"], str)

    def test_get_log_record_extra_coerces_to_json_native_types(self):
        """Tuples, sets and arbitrary objects become lists/strings so both sinks
        can serialize the result with plain json.dumps."""
        record = logging.getLogger("test").makeRecord(
            "test",
            logging.INFO,
            "",
            0,
            "msg",
            (),
            None,
            extra={
                "positional": ("select 1", (1, 2)),
                "flags": {"a"},
                "started_at": datetime.datetime(2026, 9, 9, 12, 0, 0),
                "count": 3,
                "ratio": 0.5,
                "enabled": True,
                "nothing": None,
            },
        )
        extra = get_log_record_extra(record)

        self.assertEqual(extra["positional"], ["select 1", [1, 2]])
        self.assertEqual(extra["flags"], ["a"])
        self.assertEqual(extra["started_at"], "2026-09-09 12:00:00")
        self.assertEqual(extra["count"], 3)
        self.assertEqual(extra["ratio"], 0.5)
        self.assertIs(extra["enabled"], True)
        self.assertIsNone(extra["nothing"])
        json.dumps(extra)

    def test_format_timestamp_is_utc(self):
        """`ts` carries a Z suffix, so it must be rendered in UTC, not local time."""
        formatter = _JsonFormatter()
        record = logging.getLogger("test").makeRecord(
            "test", logging.INFO, "", 0, "msg", (), None
        )
        record.created = 1757369400  # 2025-09-08T22:10:00Z
        parsed = json.loads(formatter.format(record))

        self.assertEqual(parsed["ts"], "2025-09-08T22:10:00Z")


class InitLoggingTests(TestCase):
    def setUp(self):
        # Clear root handlers before each test
        logging.root.handlers.clear()

    def tearDown(self):
        logging.root.handlers.clear()

    def test_json_format_adds_json_handler(self):
        """init_logging with json_format=True adds a JSON formatter handler."""
        init_logging(instance_id="test-instance", json_format=True)

        self.assertEqual(len(logging.root.handlers), 1)
        handler = logging.root.handlers[0]
        self.assertIsInstance(handler.formatter, _JsonFormatter)

    def test_text_format_uses_basic_config(self):
        """init_logging with json_format=False uses basicConfig text format."""
        init_logging(json_format=False)

        self.assertGreaterEqual(len(logging.root.handlers), 1)
        self.assertNotIsInstance(logging.root.handlers[0].formatter, _JsonFormatter)

    @patch.dict("os.environ", {"MCD_LOG_FORMAT": "json"})
    def test_env_var_json(self):
        """MCD_LOG_FORMAT=json enables JSON format."""
        init_logging(instance_id="test")

        self.assertEqual(len(logging.root.handlers), 1)
        self.assertIsInstance(logging.root.handlers[0].formatter, _JsonFormatter)

    @patch.dict("os.environ", {"MCD_LOG_FORMAT": "text"})
    def test_env_var_text(self):
        """MCD_LOG_FORMAT=text keeps text format."""
        init_logging()

        self.assertGreaterEqual(len(logging.root.handlers), 1)
        self.assertNotIsInstance(logging.root.handlers[0].formatter, _JsonFormatter)

    def test_repeated_init_does_not_duplicate_handlers(self):
        """Calling init_logging twice with JSON format should not duplicate handlers."""
        init_logging(instance_id="first", json_format=True)
        init_logging(instance_id="second", json_format=True)

        self.assertEqual(len(logging.root.handlers), 1)

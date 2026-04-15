import json
import logging
from unittest import TestCase
from unittest.mock import patch

from apollo.egress.agent.utils.utils import _JsonFormatter, init_logging


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

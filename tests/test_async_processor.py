from typing import Optional
from unittest import TestCase

from apollo.egress.agent.utils.queue_async_processor import QueueAsyncProcessor


class AsyncProcessorTets(TestCase):
    def test_exception_handling(self):
        # failing to execute an operation shouldn't stop the processor
        processor: Optional[QueueAsyncProcessor[str]] = None
        invocations = []

        def handler(param: str):
            invocations.append(param)
            if param == "fail":
                raise Exception("test")
            elif param == "stop":
                if processor:
                    processor._running = False
            else:
                pass

        processor = QueueAsyncProcessor("test", handler, 1)
        processor.schedule("fail")
        processor.schedule("ok")
        processor.schedule("stop")
        processor._running = True
        processor._run(0)

        self.assertEqual(3, len(invocations))

    def test_queue_depth_returns_correct_count(self):
        """Test that queue_depth returns the number of pending items."""
        processor = QueueAsyncProcessor("test", lambda x: None, 2)

        self.assertEqual(0, processor.queue_depth())

        processor.schedule("item1")
        self.assertEqual(1, processor.queue_depth())

        processor.schedule("item2")
        self.assertEqual(2, processor.queue_depth())

        processor.schedule("item3")
        self.assertEqual(3, processor.queue_depth())

    def test_thread_count_returns_configured_count(self):
        """Test that thread_count property returns the configured thread count."""
        processor1 = QueueAsyncProcessor("test", lambda x: None, 1)
        self.assertEqual(1, processor1.thread_count)

        processor4 = QueueAsyncProcessor("test", lambda x: None, 4)
        self.assertEqual(4, processor4.thread_count)

        processor10 = QueueAsyncProcessor("test", lambda x: None, 10)
        self.assertEqual(10, processor10.thread_count)

    # ── lifecycle log content ─────────────────────────────────────────

    def test_default_describer_omits_suffix(self):
        """With no ``_describe_param`` override, lifecycle logs have no ': <desc>' suffix."""
        processor = QueueAsyncProcessor("test", lambda x: None, 1)
        with self.assertLogs(
            "apollo.egress.agent.utils.queue_async_processor", level="INFO"
        ) as cm:
            processor._invoke_handler("test #0", "ok")

        running = next(m for m in cm.output if "running operation" in m)
        completed = next(m for m in cm.output if "completed operation" in m)
        self.assertIn("test #0: running operation", running)
        self.assertNotIn("running operation: ", running)  # no suffix
        self.assertIn("test #0: completed operation", completed)
        self.assertIn("duration_s=", completed)

    def test_describer_appears_in_lifecycle_logs(self):
        """An overridden ``_describe_param`` adds a ': <desc>' suffix to lifecycle logs."""

        class DescribedProcessor(QueueAsyncProcessor[str]):
            def _describe_param(self, param: str) -> str:
                return f"id={param}"

        processor = DescribedProcessor("test", lambda x: None, 1)
        with self.assertLogs(
            "apollo.egress.agent.utils.queue_async_processor", level="INFO"
        ) as cm:
            processor._invoke_handler("test #0", "abc")

        running = next(m for m in cm.output if "running operation" in m)
        completed = next(m for m in cm.output if "completed operation" in m)
        self.assertIn("test #0: running operation: id=abc", running)
        self.assertIn("test #0: completed operation: id=abc", completed)
        self.assertIn("duration_s=", completed)

    def test_exception_log_includes_description_and_duration(self):
        """Failures emit a single ``Failed to run operation`` log with description and duration."""

        class DescribedProcessor(QueueAsyncProcessor[str]):
            def _describe_param(self, param: str) -> str:
                return f"id={param}"

        def failing(_param: str) -> None:
            raise ValueError("boom")

        processor = DescribedProcessor("test", failing, 1)
        with self.assertLogs(
            "apollo.egress.agent.utils.queue_async_processor", level="INFO"
        ) as cm:
            processor._invoke_handler("test #0", "abc")

        failure_logs = [m for m in cm.output if "Failed to run operation" in m]
        self.assertEqual(1, len(failure_logs), cm.output)
        self.assertIn("id=abc", failure_logs[0])
        self.assertIn("duration_s=", failure_logs[0])

    def test_completed_log_duration_is_nonnegative_float(self):
        """``duration_s`` in the completed-operation log parses as a non-negative float."""
        import re

        processor = QueueAsyncProcessor("test", lambda x: None, 1)
        with self.assertLogs(
            "apollo.egress.agent.utils.queue_async_processor", level="INFO"
        ) as cm:
            processor._invoke_handler("test #0", "ok")

        completed = next(m for m in cm.output if "completed operation" in m)
        match = re.search(r"duration_s=([0-9.]+)", completed)
        self.assertIsNotNone(match, completed)
        self.assertGreaterEqual(float(match.group(1)), 0.0)  # type: ignore[union-attr]

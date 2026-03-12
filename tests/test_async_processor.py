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

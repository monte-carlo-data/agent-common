import time
from unittest import TestCase
from unittest.mock import Mock

from apollo.egress.agent.service.metrics_timer import MetricsTimer


class MetricsTimerTests(TestCase):
    def setUp(self):
        self._config_manager = Mock()
        self._config_manager.get_int_value.return_value = 1  # 1 second interval
        self._push_metrics_handler = Mock()

    def tearDown(self):
        # Ensure timer is stopped after each test
        pass

    def test_start_creates_thread(self):
        """Test that start() creates and starts the timer thread."""
        timer = MetricsTimer(
            config_manager=self._config_manager,
            push_metrics_handler=self._push_metrics_handler,
        )

        timer.start()
        time.sleep(0.1)

        self.assertIsNotNone(timer._thread)
        self.assertTrue(timer._thread.is_alive())
        timer.stop()

    def test_stop_stops_thread(self):
        """Test that stop() stops the timer thread."""
        timer = MetricsTimer(
            config_manager=self._config_manager,
            push_metrics_handler=self._push_metrics_handler,
        )

        timer.start()
        time.sleep(0.1)
        timer.stop()
        time.sleep(0.1)

        self.assertTrue(timer._stop_event.is_set())

    def test_triggers_handler_after_interval(self):
        """Test that handler is called after interval."""
        self._config_manager.get_int_value.return_value = 0.2  # 200ms interval
        timer = MetricsTimer(
            config_manager=self._config_manager,
            push_metrics_handler=self._push_metrics_handler,
        )

        timer.start()
        time.sleep(0.5)  # Wait for at least one interval
        timer.stop()

        # Handler should have been called at least once
        self.assertGreaterEqual(self._push_metrics_handler.call_count, 1)

    def test_handler_exception_does_not_crash_timer(self):
        """Test that exception in handler doesn't crash the timer."""
        self._config_manager.get_int_value.return_value = 0.1  # 100ms interval
        self._push_metrics_handler.side_effect = Exception("Test error")
        timer = MetricsTimer(
            config_manager=self._config_manager,
            push_metrics_handler=self._push_metrics_handler,
        )

        timer.start()
        time.sleep(0.3)  # Wait for multiple intervals
        timer.stop()

        # Handler should have been called multiple times despite exceptions
        self.assertGreaterEqual(self._push_metrics_handler.call_count, 2)

    def test_stop_interrupts_wait(self):
        """Test that stop() interrupts the timer immediately."""
        self._config_manager.get_int_value.return_value = 60  # Long interval
        timer = MetricsTimer(
            config_manager=self._config_manager,
            push_metrics_handler=self._push_metrics_handler,
        )

        timer.start()
        time.sleep(0.1)

        start_time = time.time()
        timer.stop()
        elapsed = time.time() - start_time

        # Stop should return quickly, not wait for the 60s interval
        self.assertLess(elapsed, 1.0)

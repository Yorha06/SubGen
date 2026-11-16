import subprocess
import sys
import threading
import time
import unittest

from subtitle_app.utils.process import run_cancellable


class ProcessCancellationTests(unittest.TestCase):
    def test_cancellation_terminates_running_child_process(self):
        cancel_event = threading.Event()
        timer = threading.Timer(0.2, cancel_event.set)
        timer.start()
        started = time.monotonic()
        try:
            with self.assertRaises(InterruptedError):
                run_cancellable(
                    [sys.executable, "-c", "import time; time.sleep(10)"],
                    cancel_event,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
        finally:
            timer.cancel()

        self.assertLess(time.monotonic() - started, 5)


if __name__ == "__main__":
    unittest.main()

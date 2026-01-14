import unittest
import sys
from time import sleep

from PyQt5.QtCore import QThreadPool, pyqtSlot
from PyQt5.QtTest import QSignalSpy

# Import the module under test
from krita_comfyui.workers.worker import Worker


class TestWorker(unittest.TestCase):
    """Unit tests for the `Worker` class."""

    @classmethod
    def setUpClass(cls):
        # Ensure a global thread pool exists before any tests run.
        cls.pool = QThreadPool()

    def _run_worker_and_wait(self, worker: Worker):
        """
        Helper that starts the QRunnable and blocks until it finishes or errors out.
        Returns the result or raises an exception if the worker emitted an error signal.
        """
        finished_spy = QSignalSpy(worker.signals.finished)
        error_spy = QSignalSpy(worker.signals.error)

        self.pool.start(worker)

        # Wait up to 2 seconds for either signal
        timeout_ms = 2000
        while not (len(finished_spy) or len(error_spy)):
            if timeout_ms <= 0:
                break
            sleep(0.01)
            timeout_ms -= 10

        self.pool.clear()
        if finished_spy:
            return finished_spy[0][0]  # the emitted result
        if error_spy:
            raise RuntimeError(error_spy[0][0])  # re‑raise as RuntimeError for test readability
        self.fail("Worker did not emit finished or error signal within timeout.")

    def test_successful_execution(self):
        """The worker should execute a normal function and emit the result."""

        def add(a, b):
            return a + b

        worker = Worker(add, 2, 3)
        result = self._run_worker_and_wait(worker)
        self.assertEqual(result, 5)

    def test_error_emission(self):
        """The worker should catch exceptions and emit an error signal."""

        def raise_exc():
            raise ValueError("boom")

        worker = Worker(raise_exc)
        with self.assertRaises(RuntimeError) as ctx:
            self._run_worker_and_wait(worker)

        self.assertIn("boom", str(ctx.exception))

    def test_args_and_kwargs_passed(self):
        """Verify that positional and keyword arguments are forwarded correctly."""
        collected = []

        @pyqtSlot()
        def capture(a, b=0):
            collected.append((a, b))

        worker = Worker(capture, 10, b=20)
        self._run_worker_and_wait(worker)

        # The capture slot is executed in the worker thread; ensure we waited long enough.
        self.assertIn((10, 20), collected)

    def test_multiple_workers(self):
        """Running several workers concurrently should work without interference."""
        results = []

        def identity(x):
            return x

        workers = [Worker(identity, i) for i in range(5)]
        for w in workers:
            self.pool.start(w)

        # Use QSignalSpy on each worker to collect results
        spies = {w: QSignalSpy(w.signals.finished) for w in workers}
        timeout_ms = 2000
        while any(len(spy) == 0 for spy in spies.values()):
            if timeout_ms <= 0:
                break
            sleep(0.01)
            timeout_ms -= 10

        for w, spy in spies.items():
            # The spy must have received at least one signal
            self.assertGreater(len(spy), 0, f"Worker {w} did not finish")
            results.append(spy[0][0])  # first emitted result

        self.assertCountEqual(results, list(range(5)))

    def tearDown(self):
        """Ensure the thread pool is clean after each test."""
        # Wait a tiny bit to allow any stray threads to finish
        sleep(0.05)
        # No explicit teardown needed; QThreadPool cleans up automatically.


if __name__ == "__main__":
    # Running the tests directly from the command line.
    unittest.main(argv=[sys.argv[0]], verbosity=2)

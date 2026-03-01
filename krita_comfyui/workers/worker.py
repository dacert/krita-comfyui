import time

from PyQt5.QtCore import QObject, QRunnable, pyqtSignal


class WorkerSignals(QObject):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)


class Worker(QRunnable):
    """
    Wrapper for running a callable in the global QThreadPool.
    Emits `finished` with the return value or `error` if an exception occurs.
    """

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    def run(self):
        """
        Execute the wrapped function in a worker thread.
        Emits the result asynchronously to ensure all signal connections are active.
        """
        try:
            result = self.fn(*self.args, **self.kwargs)
            time.sleep(0.001)
            self.signals.finished.emit(result)
        except Exception as e:
            self.signals.error.emit(str(e))

import time
import threading
from src.server.logging_config import get_logger

logger = get_logger(__name__)

class CountupTimer:
    def __init__(self):
        self.lock = threading.Lock()
        self.start_time = None
        self.target_duration = 0  # seconds
        self.running = False
        self.elapsed_at_stop = 0

    def start(self):
        with self.lock:
            if not self.running:
                # Resume from where we stopped
                self.start_time = time.time() - self.elapsed_at_stop
                self.running = True
                logger.info(f"Timer started, resuming from {self.elapsed_at_stop}s")

    def reset(self, seconds):
        with self.lock:
            self.target_duration = seconds
            self.start_time = time.time()
            self.elapsed_at_stop = 0
            logger.info(f"Timer reset to {seconds}s")

    def stop(self):
        with self.lock:
            if self.running and self.start_time:
                self.elapsed_at_stop = int(time.time() - self.start_time)
            self.running = False
            logger.info(f"Timer stopped at {self.elapsed_at_stop}s")

    def set_elapsed(self, elapsed_seconds: int):
        with self.lock:
            try:
                elapsed = int(elapsed_seconds)
            except (TypeError, ValueError):
                return
            if elapsed < 0:
                elapsed = 0

            self.elapsed_at_stop = elapsed

            # If running, re-anchor start_time to match the provided elapsed.
            if self.running:
                self.start_time = time.time() - self.elapsed_at_stop

    def get_elapsed(self):
        with self.lock:
            if self.running and self.start_time:
                return int(time.time() - self.start_time)
            # When stopped, return frozen elapsed time
            return self.elapsed_at_stop

    def get_target(self):
        with self.lock:
            return self.target_duration
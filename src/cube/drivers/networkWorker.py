'''
Background network sender.

Connecting to WiFi and sending HTTPS requests can block for seconds. This
class does that work in a second thread so the main loop keeps handling taps
and LEDs. The ESP32-C3 has one core, so the two threads take turns. Blocking
socket calls and sleeps let the main thread run while the worker waits.

Rules:
- Only the worker thread uses WiFi and the network.
- Only the main thread uses I2C (LEDs, IMU). The worker never touches them.
- The main thread reads replies with take_results() and acts on them.
'''

import _thread
import time

WORKER_STACK_BYTES = 16 * 1024  # HTTPS (mbedtls) needs a deep stack.


class NetworkWorker:
    def __init__(self, node, connect_timeout_s=10):
        self.node = node
        self.connect_timeout_s = connect_timeout_s

        self._lock = _thread.allocate_lock()   # Guards _jobs and _results.
        self._wake = _thread.allocate_lock()   # Released to wake the worker.
        self._wake.acquire()                   # Start locked: nothing to do yet.
        self._jobs = []
        self._results = []
        self.busy = False

        previous = _thread.stack_size(WORKER_STACK_BYTES)
        _thread.start_new_thread(self._run, ())
        _thread.stack_size(previous)  # Restore the default for any later threads.

    # ---------- Called from the main thread ----------
    def send(self, command, preset_time, sync=False, wifi_off_after=True):
        """Queue a start/stop/reset POST. Returns immediately."""
        self._submit(("send", command, preset_time, sync, wifi_off_after))

    def wifi_off(self):
        """Queue turning the radio off (done in the worker to avoid races)."""
        self._submit(("wifi_off",))

    def idle(self):
        """True when nothing is queued or in progress."""
        with self._lock:
            return not self._jobs and not self.busy

    def take_results(self):
        """Return and clear finished sends as (action, sync, reply) tuples.
        reply is the server's JSON, or None if the send failed."""
        with self._lock:
            results = self._results
            self._results = []
        return results

    def _submit(self, job):
        with self._lock:
            self._jobs.append(job)
        try:
            self._wake.release()
        except RuntimeError:
            pass  # Already awake; it will find this job too.

    # ---------- Worker thread ----------
    def _run(self):
        while True:
            self._wake.acquire()  # Sleeps here until a job is submitted.
            while True:
                with self._lock:
                    if not self._jobs:
                        self.busy = False
                        break
                    job = self._jobs.pop(0)
                    self.busy = True
                try:
                    self._do(job)
                except Exception as e:
                    # Never let the thread die; report and carry on.
                    print("Network worker error:", e)

    def _do(self, job):
        if job[0] == "wifi_off":
            self.node.disconnect_wifi()
            return

        _, command, preset_time, sync, wifi_off_after = job
        action = command.get("action")
        reply = None
        try:
            self.node.connect_wifi(timeout=self.connect_timeout_s)
            reply = self.node.send_command(command, presetTime=preset_time)
        except Exception as e:
            print("Failed to send", action, ":", e)

        if wifi_off_after:
            self.node.disconnect_wifi()

        with self._lock:
            self._results.append((action, sync, reply))

import tkinter as tk
from tkinter import scrolledtext
import requests
import threading
import json

SERVER_URL = "https://thecube-api-3nmm.onrender.com/api/task/control"


# ----- Dark Mode Colors -----
BG_COLOR = "#1e1e1e"
FG_COLOR = "#ffffff"
ACCENT_COLOR = "#ff8c00"      # Orange
ACCENT_DIM = "#a65a00"        # Dim orange for OFF
BUTTON_BG = "#2d2d2d"
BUTTON_ACTIVE = "#3a3a3a"
TEXT_BG = "#252526"
ALERT_COLOR = "#ff3333"


class CubeSimulatorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("THE CUBE SIMULATOR")
        self.root.configure(bg=BG_COLOR)

        # ---- Cube Identity ----
        self.cube_uuid =  "test-cube-uuid-001"

        # ---- State ----
        self.state = "stopped"
        self.elapsed_seconds = 0
        self.timer_job = None
        self.task_time_seconds = 0
        self.alert_active = False

        # ===== LED Indicator =====
        led_frame = tk.Frame(root, bg=BG_COLOR)
        led_frame.pack(anchor="nw", padx=10, pady=5)

        tk.Label(led_frame, text="LED", bg=BG_COLOR, fg=FG_COLOR, font=("Helvetica", 10, "bold")).pack(anchor="w")

        self.led_canvas = tk.Canvas(led_frame, width=60, height=60, highlightthickness=0, bg=BG_COLOR)
        self.led_canvas.pack()
        self.led_rect = self.led_canvas.create_rectangle(5, 5, 55, 55, fill=ACCENT_DIM, outline="")
        self.led_text = self.led_canvas.create_text(30, 30, text="OFF", fill=FG_COLOR, font=("Helvetica", 10, "bold"))

        # Alert label (hidden initially)
        self.alert_label = tk.Label(root, text="", bg=BG_COLOR, fg=ALERT_COLOR, font=("Helvetica", 12, "bold"))
        self.alert_label.pack(anchor="nw", padx=10)

        # ===== Title Banner =====
        banner = tk.Label(
            root,
            text="THE CUBE SIMULATOR",
            font=("Helvetica", 20, "bold"),
            pady=10,
            bg=BG_COLOR,
            fg=FG_COLOR
        )
        banner.pack()

        # ===== Task Info Display =====
        info_frame = tk.Frame(root, bg=BG_COLOR)
        info_frame.pack(pady=5)

        tk.Label(info_frame, text="Task:", bg=BG_COLOR, fg=FG_COLOR).grid(row=0, column=0, padx=5, sticky="e")
        self.task_name_var = tk.StringVar(value="Unknown")
        tk.Label(info_frame, textvariable=self.task_name_var, width=20, anchor="w",
                 bg=BG_COLOR, fg=ACCENT_COLOR, font=("Helvetica", 11, "bold")).grid(row=0, column=1, padx=5)

        tk.Label(info_frame, text="Time:", bg=BG_COLOR, fg=FG_COLOR).grid(row=1, column=0, padx=5, sticky="e")
        self.task_time_var = tk.StringVar(value="00:00")
        tk.Label(info_frame, textvariable=self.task_time_var, width=20, anchor="w",
                 bg=BG_COLOR, fg=ACCENT_COLOR, font=("Helvetica", 11, "bold")).grid(row=1, column=1, padx=5)

        # ===== Count Up Timer Display =====
        tk.Label(info_frame, text="Elapsed:", bg=BG_COLOR, fg=FG_COLOR).grid(row=2, column=0, padx=5, sticky="e")
        self.elapsed_var = tk.StringVar(value="00:00")
        tk.Label(info_frame, textvariable=self.elapsed_var, width=20, anchor="w",
                 bg=BG_COLOR, fg=ACCENT_COLOR, font=("Helvetica", 11, "bold")).grid(row=2, column=1, padx=5)

        tk.Label(info_frame, text="Color:", bg=BG_COLOR, fg=FG_COLOR).grid(row=3, column=0, padx=5, sticky="e")
        self.task_color_canvas = tk.Canvas(info_frame, width=20, height=20, highlightthickness=1, bg=BG_COLOR)
        self.task_color_canvas.grid(row=3, column=1, sticky="w", padx=5)
        self.task_color_rect = self.task_color_canvas.create_rectangle(1, 1, 19, 19, fill=BUTTON_BG, outline=ACCENT_COLOR)
        self.task_color_var = tk.StringVar(value="N/A")
        tk.Label(info_frame, textvariable=self.task_color_var, bg=BG_COLOR, fg=ACCENT_COLOR, font=("Helvetica", 11, "bold")).grid(row=3, column=2, padx=5, sticky="w")

        # ===== Buttons =====
        button_frame = tk.Frame(root, bg=BG_COLOR)
        button_frame.pack(pady=10)

        tk.Button(button_frame, text="Start", width=10, command=self.on_start,
                  bg=BUTTON_BG, fg=FG_COLOR, activebackground=BUTTON_ACTIVE,
                  activeforeground=FG_COLOR, relief="flat").grid(row=0, column=0, padx=5)

        tk.Button(button_frame, text="Stop", width=10, command=self.on_stop,
                  bg=BUTTON_BG, fg=FG_COLOR, activebackground=BUTTON_ACTIVE,
                  activeforeground=FG_COLOR, relief="flat").grid(row=0, column=1, padx=5)

        tk.Button(button_frame, text="Reset", width=10, command=self.on_reset,
                  bg=BUTTON_BG, fg=FG_COLOR, activebackground=BUTTON_ACTIVE,
                  activeforeground=FG_COLOR, relief="flat").grid(row=0, column=2, padx=5)

        # ===== Display Window =====
        self.display = scrolledtext.ScrolledText(
            root, width=60, height=15,
            bg=TEXT_BG, fg=FG_COLOR, insertbackground=FG_COLOR,
            relief="flat", borderwidth=0
        )
        self.display.pack(pady=10)

        self.log("Client ready.")

        # Auto-fetch config
        self.on_reset()


    # ---------- LED Control ----------
    def set_led(self, on: bool):
        if on:
            self.led_canvas.itemconfig(self.led_rect, fill=ACCENT_COLOR)
            self.led_canvas.itemconfig(self.led_text, text="ON")
        else:
            self.led_canvas.itemconfig(self.led_rect, fill=ACCENT_DIM)
            self.led_canvas.itemconfig(self.led_text, text="OFF")

    def _normalize_task_color(self, color):
        if not color or not isinstance(color, str):
            return None

        text = color.strip().lstrip('#')
        if len(text) == 6:
            if all(ch in '0123456789abcdefABCDEF' for ch in text):
                return f"#{text.upper()}"
            return None

        if len(text) == 8:
            try:
                r = int(text[0:2], 16)
                g = int(text[2:4], 16)
                b = int(text[4:6], 16)
                w = int(text[6:8], 16)
            except ValueError:
                return None
            r = min(255, r + w)
            g = min(255, g + w)
            b = min(255, b + w)
            return f"#{r:02X}{g:02X}{b:02X}"

        if len(text) == 4:
            try:
                r = int(text[0], 16) * 17
                g = int(text[1], 16) * 17
                b = int(text[2], 16) * 17
                w = int(text[3], 16) * 17
            except ValueError:
                return None
            r = min(255, r + w)
            g = min(255, g + w)
            b = min(255, b + w)
            return f"#{r:02X}{g:02X}{b:02X}"

        return None

    def set_task_color(self, color):
        normalized = self._normalize_task_color(color)
        if normalized:
            try:
                self.task_color_canvas.itemconfig(self.task_color_rect, fill=normalized)
                self.task_color_var.set(color)
            except tk.TclError:
                self.task_color_canvas.itemconfig(self.task_color_rect, fill=BUTTON_BG)
                self.task_color_var.set("Invalid")
        else:
            self.task_color_canvas.itemconfig(self.task_color_rect, fill=BUTTON_BG)
            self.task_color_var.set("N/A")


    # ---------- Timer Logic ----------
    def start_timer(self):
        if self.timer_job is None:
            self._tick()


    def _tick(self):
        self.elapsed_seconds += 1
        self.update_elapsed_display()

        # Check alert condition
        if self.task_time_seconds and self.elapsed_seconds >= self.task_time_seconds and not self.alert_active:
            self.alert_label.config(text="ALERT!")
            self.alert_active = True

        self.timer_job = self.root.after(1000, self._tick)


    def stop_timer(self):
        if self.timer_job is not None:
            self.root.after_cancel(self.timer_job)
            self.timer_job = None


    def reset_timer(self):
        self.stop_timer()
        self.elapsed_seconds = 0
        self.update_elapsed_display()
        self.alert_label.config(text="")
        self.alert_active = False


    def update_elapsed_display(self):
        m = self.elapsed_seconds // 60
        s = self.elapsed_seconds % 60
        self.elapsed_var.set(f"{m:02d}:{s:02d}")


    # ---------- Button Handlers ----------
    def on_start(self):
        if self.state != "reset":
            return

        payload = {"action": "start"}
        self.send_request(payload)

        self.state = "running"
        self.set_led(True)
        self.start_timer()


    def on_stop(self):
        if self.state != "running":
            return

        payload = {
            "action": "stop",
            "elapsed_seconds": self.elapsed_seconds
        }
        self.send_request(payload)

        self.state = "stopped"
        self.set_led(False)
        self.stop_timer()


    def on_reset(self):
        if self.state == "running":
            return

        payload = {"action": "reset"}
        self.send_request(payload)

        self.reset_timer()
        self.set_led(False)
        self.state = "reset"


    # ---------- Networking ----------
    def send_request(self, payload):
        threading.Thread(target=self._request_worker, args=(payload,), daemon=True).start()


    def _request_worker(self, payload):
        try:
            headers = {
                "X-API-KEY": self.cube_uuid,
                "Content-Type": "application/json"
            }

            response = requests.post(
                SERVER_URL,
                json=payload,
                headers=headers
            )

            if response.headers.get("Content-Type", "").startswith("application/json"):
                data = response.json()
                self.root.after(0, self.handle_server_response, data)
                self.log(f"Server: {json.dumps(data)}")
            else:
                self.log(f"Server returned non-JSON: {response.text}")

        except Exception as e:
            self.log(f"Request error: {e}")


    def handle_server_response(self, data):
        task_name = data.get("task_name")
        task_time = data.get("task_time")

        if task_name is not None:
            self.task_name_var.set(task_name)

        if isinstance(task_time, int):
            self.task_time_seconds = task_time
            minutes = task_time // 60
            seconds = task_time % 60
            self.task_time_var.set(f"{minutes:02d}:{seconds:02d}")

        task_color = data.get("task_color")
        self.set_task_color(task_color)


    # ---------- Display ----------
    def log(self, message):
        self.display.insert(tk.END, message + "\n")
        self.display.see(tk.END)


if __name__ == "__main__":
    root = tk.Tk()
    app = CubeSimulatorGUI(root)
    root.mainloop()

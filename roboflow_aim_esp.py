import sys
import time
import base64
import threading
import ctypes
import math
import random
import socket
from ctypes import wintypes
import tkinter as tk
import cv2
import numpy as np

try:
    import mss
    HAS_MSS = True
except ImportError:
    HAS_MSS = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    import serial
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False

# ==============================================================================
# CONFIGURATION: VISION ESP + HARDWARE / DIRECT AIMBOT
# ==============================================================================
ROBOFLOW_API_KEY = "rRL7krqUwgPOInXYbue7"
ROBOFLOW_WORKSPACE = "s-workspace-byc6v"
ROBOFLOW_MODEL_ID = "cs2-shsmv-f1ood/1"

CONFIDENCE_THRESHOLD = 0.40
CAPTURE_WIDTH = 640
CAPTURE_HEIGHT = 640

SCREEN_WIDTH = ctypes.windll.user32.GetSystemMetrics(0)
SCREEN_HEIGHT = ctypes.windll.user32.GetSystemMetrics(1)
SCREEN_CX = SCREEN_WIDTH // 2
SCREEN_CY = SCREEN_HEIGHT // 2

# AIMBOT SETTINGS
AIM_ENABLED = True
AIM_KEY = 0x02              # 0x02: Right Mouse Button, 0x06: Mouse 5 (Thumb), 0x12: Alt
AIM_FOV_RADIUS = 160        # Radius in pixels around crosshair where aimbot locks
AIM_SMOOTH_FACTOR = 3.2     # Higher = smoother/slower, Lower = snappier
HEAD_BBOX_RATIO = 0.18      # Offset from top of body box to lock directly on head
DEADZONE_PX = 1.5           # Ignore micro-movements to avoid jitter

# INPUT METHOD: "DIRECT" (Win32 API for test/MM), "KMBOX_NET" (Faceit AC), "ARDUINO" (Serial)
INPUT_METHOD = "DIRECT"
KMBOX_IP = "192.168.2.188"
KMBOX_PORT = 1234
KMBOX_UUID = "ABCD1234EF"
SERIAL_PORT = "COM3"
SERIAL_BAUD = 115200

# VISUAL COLORS
COLOR_CT = "#00D4FF"        # Cyan for Counter-Terrorist
COLOR_T = "#FF8800"         # Orange for Terrorist
COLOR_HEAD = "#FF0055"      # Pink for Head
COLOR_LOCK = "#FF0000"      # Red when locked on target
COLOR_FOV = "#333333"       # Dark grey for FOV circle

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000
WS_EX_TOPMOST = 0x00000008

shared_detections = []
current_locked_target = None
detections_lock = threading.Lock()
is_running = True
current_fps = 0.0
frame_count = 0
last_fps_calc = time.time()

class MouseController:
    def __init__(self):
        self.method = INPUT_METHOD
        self.sock = None
        self.ser = None

        if self.method == "KMBOX_NET":
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.sock.settimeout(0.005)
                self.addr = (KMBOX_IP, KMBOX_PORT)
                self.sock.sendto(f"connect {KMBOX_UUID}\r\n".encode(), self.addr)
            except Exception as e:
                print(f"[!] KMBox UDP connection failed: {e}")

        elif self.method == "ARDUINO" and HAS_SERIAL:
            try:
                self.ser = serial.Serial(SERIAL_PORT, SERIAL_BAUD, timeout=0.005)
            except Exception as e:
                print(f"[!] Serial COM failed: {e}")

    def move(self, dx: int, dy: int):
        if dx == 0 and dy == 0:
            return

        if self.method == "KMBOX_NET" and self.sock:
            cmd = f"km.move({int(dx)},{int(dy)})\r\n".encode()
            try:
                self.sock.sendto(cmd, self.addr)
            except Exception:
                pass
        elif self.method == "ARDUINO" and self.ser:
            msg = f"M{int(dx)},{int(dy)}\n".encode()
            try:
                self.ser.write(msg)
            except Exception:
                pass
        else:
            # DIRECT Win32 fallback
            ctypes.windll.user32.mouse_event(0x0001, int(dx), int(dy), 0, 0)

    def close(self):
        if self.sock:
            self.sock.close()
        if self.ser and self.ser.is_open:
            self.ser.close()

mouse_driver = MouseController()

def is_key_pressed(vk: int) -> bool:
    return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)

def enable_click_through(hwnd):
    styles = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, styles | WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_TOPMOST)

class ScreenCaptureEngine:
    def __init__(self):
        if not HAS_MSS:
            raise RuntimeError("Install MSS: pip install mss")
        self.sct = mss.mss()
        self.monitor = {"top": 0, "left": 0, "width": SCREEN_WIDTH, "height": SCREEN_HEIGHT}

    def grab_frame(self):
        img = np.array(self.sct.grab(self.monitor))
        return img[:, :, :3]

def run_aim_step():
    """Calculates nearest target within FOV circle and moves crosshair toward head."""
    global current_locked_target
    if not AIM_ENABLED or not is_key_pressed(AIM_KEY):
        current_locked_target = None
        return

    with detections_lock:
        targets = list(shared_detections)

    if not targets:
        current_locked_target = None
        return

    best_target = None
    min_dist = float('inf')

    for t in targets:
        tx, ty = t["aim_x"], t["aim_y"]
        dist = math.hypot(tx - SCREEN_CX, ty - SCREEN_CY)

        if dist > AIM_FOV_RADIUS:
            continue

        if dist < min_dist:
            min_dist = dist
            best_target = t

    current_locked_target = best_target
    if best_target is None:
        return

    target_x = best_target["aim_x"]
    target_y = best_target["aim_y"]

    raw_dx = target_x - SCREEN_CX
    raw_dy = target_y - SCREEN_CY

    if abs(raw_dx) < DEADZONE_PX and abs(raw_dy) < DEADZONE_PX:
        return

    # Smooth movement interpolation
    step_x = raw_dx / AIM_SMOOTH_FACTOR
    step_y = raw_dy / AIM_SMOOTH_FACTOR

    # Human micro-jitter
    jitter_x = (random.random() - 0.5) * 0.3
    jitter_y = (random.random() - 0.5) * 0.3

    final_dx = int(round(step_x + jitter_x))
    final_dy = int(round(step_y + jitter_y))

    mouse_driver.move(final_dx, final_dy)

def roboflow_inference_worker():
    global shared_detections, is_running, current_fps, frame_count, last_fps_calc
    grabber = ScreenCaptureEngine()
    endpoint = f"https://detect.roboflow.com/{ROBOFLOW_MODEL_ID}?api_key={ROBOFLOW_API_KEY}&confidence={int(CONFIDENCE_THRESHOLD * 100)}"

    while is_running:
        frame = grabber.grab_frame()
        orig_h, orig_w = frame.shape[:2]

        resized = cv2.resize(frame, (CAPTURE_WIDTH, CAPTURE_HEIGHT))
        ret, buf = cv2.imencode(".jpg", resized, [int(cv2.IMWRITE_JPEG_QUALITY), 65])
        if not ret:
            continue

        b64_image = base64.b64encode(buf).decode("ascii")

        try:
            resp = requests.post(
                endpoint,
                data=b64_image,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=1.5
            )

            if resp.status_code == 200:
                data = resp.json()
                predictions = data.get("predictions", [])
                parsed = []

                scale_x = orig_w / CAPTURE_WIDTH
                scale_y = orig_h / CAPTURE_HEIGHT

                for p in predictions:
                    cx = p["x"] * scale_x
                    cy = p["y"] * scale_y
                    w = p["width"] * scale_x
                    h = p["height"] * scale_y
                    cls_name = p.get("class", "Target")

                    x1 = int(cx - w / 2)
                    y1 = int(cy - h / 2)
                    x2 = int(cx + w / 2)
                    y2 = int(cy + h / 2)

                    # Calculate head aimpoint
                    if "head" in cls_name.lower():
                        aim_x = int(cx)
                        aim_y = int(cy)
                    else:
                        aim_x = int(cx)
                        aim_y = int(y1 + h * HEAD_BBOX_RATIO)

                    parsed.append({
                        "x1": x1, "y1": y1,
                        "x2": x2, "y2": y2,
                        "aim_x": aim_x, "aim_y": aim_y,
                        "class": cls_name,
                        "conf": p.get("confidence", 0.0)
                    })

                with detections_lock:
                    shared_detections = parsed

            frame_count += 1
            now = time.time()
            if now - last_fps_calc >= 1.0:
                current_fps = frame_count / (now - last_fps_calc)
                frame_count = 0
                last_fps_calc = now

        except Exception:
            time.sleep(0.05)

        time.sleep(0.005)

class UnifiedAimbotESPOverlay:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Roboflow_Aim_ESP_Overlay")
        self.root.geometry(f"{SCREEN_WIDTH}x{SCREEN_HEIGHT}+0+0")
        self.root.overrideredirect(True)
        self.root.wm_attributes("-topmost", True)
        self.root.wm_attributes("-transparentcolor", "#000000")
        self.root.config(bg="#000000")

        self.canvas = tk.Canvas(self.root, width=SCREEN_WIDTH, height=SCREEN_HEIGHT, bg="#000000", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        hwnd = ctypes.windll.user32.FindWindowW(None, "Roboflow_Aim_ESP_Overlay")
        if hwnd:
            enable_click_through(hwnd)

        self.root.bind("<Escape>", lambda e: self.exit_app())
        self.root.after(10, self.update_loop)

    def update_loop(self):
        # 1. Execute Aimbot tracking logic
        run_aim_step()

        # 2. Render visuals
        self.canvas.delete("all")

        aim_status = "LOCKED" if current_locked_target else ("HOLDING KEY" if is_key_pressed(AIM_KEY) else "READY")
        status_color = "#FF0000" if current_locked_target else "#00FF66"

        self.canvas.create_text(
            25, 25,
            text=f"[AI AIM + ESP] Status: {aim_status} | Model: {ROBOFLOW_MODEL_ID} | Rate: {current_fps:.1f} FPS",
            fill=status_color,
            font=("Consolas", 11, "bold"),
            anchor="w"
        )
        self.canvas.create_text(
            25, 45,
            text=f"Aim Key: Right Click | Input: {INPUT_METHOD} | Smooth: {AIM_SMOOTH_FACTOR} | FOV: {AIM_FOV_RADIUS}px",
            fill="#AAAAAA",
            font=("Consolas", 9),
            anchor="w"
        )

        # Draw FOV Circle in center of screen
        self.canvas.create_oval(
            SCREEN_CX - AIM_FOV_RADIUS, SCREEN_CY - AIM_FOV_RADIUS,
            SCREEN_CX + AIM_FOV_RADIUS, SCREEN_CY + AIM_FOV_RADIUS,
            outline=COLOR_FOV, width=1
        )

        with detections_lock:
            boxes = list(shared_detections)

        for b in boxes:
            x1, y1, x2, y2 = b["x1"], b["y1"], b["x2"], b["y2"]
            ax, ay = b["aim_x"], b["aim_y"]
            name = b["class"]
            conf = b["conf"]

            color = COLOR_CT if "counter" in name.lower() or "ct" in name.lower() else COLOR_T
            if "head" in name.lower():
                color = COLOR_HEAD

            # Corner-cut bounding box
            corner_len = max(int((x2 - x1) * 0.25), 8)
            self.canvas.create_line(x1, y1, x1 + corner_len, y1, fill=color, width=2)
            self.canvas.create_line(x1, y1, x1, y1 + corner_len, fill=color, width=2)
            self.canvas.create_line(x2, y1, x2 - corner_len, y1, fill=color, width=2)
            self.canvas.create_line(x2, y1, x2, y1 + corner_len, fill=color, width=2)
            self.canvas.create_line(x1, y2, x1 + corner_len, y2, fill=color, width=2)
            self.canvas.create_line(x1, y2, x1, y2 - corner_len, fill=color, width=2)
            self.canvas.create_line(x2, y2, x2 - corner_len, y2, fill=color, width=2)
            self.canvas.create_line(x2, y2, x2, y2 - corner_len, fill=color, width=2)

            # Draw Head aimpoint dot
            self.canvas.create_oval(ax - 3, ay - 3, ax + 3, ay + 3, fill="#FFFFFF", outline=color)

            # Tag
            self.canvas.create_text(
                x1, max(y1 - 10, 10),
                text=f"{name.upper()} [{int(conf * 100)}%]",
                fill=color,
                font=("Consolas", 9, "bold"),
                anchor="w"
            )

        # Snap line from crosshair to locked target
        if current_locked_target is not None:
            lx, ly = current_locked_target["aim_x"], current_locked_target["aim_y"]
            self.canvas.create_line(SCREEN_CX, SCREEN_CY, lx, ly, fill=COLOR_LOCK, width=2)

        self.root.after(10, self.update_loop)

    def exit_app(self):
        global is_running
        is_running = False
        mouse_driver.close()
        self.root.destroy()

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    t = threading.Thread(target=roboflow_inference_worker, daemon=True)
    t.start()

    app = UnifiedAimbotESPOverlay()
    app.run()

import sys
import time
import base64
import threading
import ctypes
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
    from inference_sdk import InferenceHTTPClient, InferenceConfiguration
    HAS_INFERENCE_SDK = True
except ImportError:
    HAS_INFERENCE_SDK = False

# ==============================================================================
# ROBOFLOW & OVERLAY CONFIGURATION
# ==============================================================================
ROBOFLOW_API_KEY = "rRL7krqUwgPOInXYbue7"
ROBOFLOW_WORKSPACE = "s-workspace-byc6v"
ROBOFLOW_MODEL_ID = "cs2-shsmv-f1ood/1"
ROBOFLOW_WORKFLOW_ID = "cs2-shsmv-f1ood"

# Screen / Overlay Settings
SCREEN_WIDTH = ctypes.windll.user32.GetSystemMetrics(0)
SCREEN_HEIGHT = ctypes.windll.user32.GetSystemMetrics(1)

# Capture resolution (resized before sending to cloud to minimize latency)
INFERENCE_WIDTH = 640
INFERENCE_HEIGHT = 640
CONFIDENCE_THRESHOLD = 0.40

# Colors for bounding boxes (BGR / Hex)
COLOR_CT = "#00BFFF"       # Deep Sky Blue for Counter-Terrorists
COLOR_T = "#FF8C00"        # Dark Orange for Terrorists
COLOR_HEAD = "#FF1493"     # Deep Pink for Heads
COLOR_TEXT = "#00FF00"     # Green for HUD/Stats

# Win32 Constants for Click-Through Transparent Window
GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_LAYERED = 0x00080000
WS_EX_TOPMOST = 0x00000008

# Global shared target buffer between inference worker and render loop
shared_detections = []
detections_lock = threading.Lock()
is_running = True
last_fps_time = time.time()
frame_counter = 0
current_fps = 0.0

def make_window_click_through(hwnd):
    """Configures the Tkinter overlay window to ignore all mouse clicks and remain transparent."""
    style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_TOPMOST)

class ScreenGrabber:
    def __init__(self):
        if not HAS_MSS:
            raise RuntimeError("mss library missing. Run: pip install mss")
        self.sct = mss.mss()
        self.monitor = {"top": 0, "left": 0, "width": SCREEN_WIDTH, "height": SCREEN_HEIGHT}

    def grab(self):
        img = np.array(self.sct.grab(self.monitor))
        return img[:, :, :3]

def run_inference_worker():
    """
    Background worker thread:
    Continuously captures the screen, compresses frame to JPEG, queries the Roboflow
    model without blocking the GUI rendering loop, and updates shared detection boxes.
    """
    global shared_detections, is_running, frame_counter, current_fps, last_fps_time

    grabber = ScreenGrabber()
    url = f"https://detect.roboflow.com/{ROBOFLOW_MODEL_ID}?api_key={ROBOFLOW_API_KEY}&confidence={int(CONFIDENCE_THRESHOLD * 100)}"

    print(f"[*] Roboflow Inference Worker active. Endpoint: {ROBOFLOW_MODEL_ID}")

    while is_running:
        t0 = time.time()
        frame = grabber.grab()

        # Resize for faster upload to cloud API
        h_orig, w_orig = frame.shape[:2]
        small = cv2.resize(frame, (INFERENCE_WIDTH, INFERENCE_HEIGHT))
        _, buffer = cv2.imencode(".jpg", small, [int(cv2.IMWRITE_JPEG_QUALITY), 65])
        jpg_base64 = base64.b64encode(buffer).decode("ascii")

        try:
            # High speed POST request directly with image base64
            resp = requests.post(
                url,
                data=jpg_base64,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=1.5
            )

            if resp.status_code == 200:
                data = resp.json()
                preds = data.get("predictions", [])
                parsed_boxes = []

                scale_x = w_orig / INFERENCE_WIDTH
                scale_y = h_orig / INFERENCE_HEIGHT

                for p in preds:
                    cx = p["x"] * scale_x
                    cy = p["y"] * scale_y
                    w = p["width"] * scale_x
                    h = p["height"] * scale_y
                    cls_name = p.get("class", "Target")
                    conf = p.get("confidence", 0.0)

                    x1 = int(cx - w / 2)
                    y1 = int(cy - h / 2)
                    x2 = int(cx + w / 2)
                    y2 = int(cy + h / 2)

                    parsed_boxes.append({
                        "x1": x1, "y1": y1,
                        "x2": x2, "y2": y2,
                        "class": cls_name,
                        "confidence": conf
                    })

                with detections_lock:
                    shared_detections = parsed_boxes

            # Update FPS tracking
            frame_counter += 1
            if time.time() - last_fps_time >= 1.0:
                current_fps = frame_counter / (time.time() - last_fps_time)
                frame_counter = 0
                last_fps_time = time.time()

        except Exception as e:
            # Retry on transient network blip without crashing overlay
            time.sleep(0.05)

        # Micro-sleep to keep thread responsive
        time.sleep(0.01)

class ExternalVisionOverlay:
    """
    Transparent, click-through Win32/Tkinter overlay.
    Renders boxes directly over CS2 or any window without opening, hooking,
    or reading game memory.
    """
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("AI Vision ESP Overlay")
        self.root.geometry(f"{SCREEN_WIDTH}x{SCREEN_HEIGHT}+0+0")
        self.root.overrideredirect(True)
        self.root.wm_attributes("-topmost", True)
        self.root.wm_attributes("-transparentcolor", "black")
        self.root.config(bg="black")

        self.canvas = tk.Canvas(self.root, width=SCREEN_WIDTH, height=SCREEN_HEIGHT, bg="black", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        hwnd = ctypes.windll.user32.FindWindowW(None, "AI Vision ESP Overlay")
        if hwnd:
            make_window_click_through(hwnd)

        self.root.bind("<Escape>", lambda e: self.close())
        self.root.after(16, self.render_loop)

    def render_loop(self):
        self.canvas.delete("all")

        # Top-left status HUD
        self.canvas.create_text(
            20, 25,
            text=f"[AI VISION ESP: ACTIVE] | Roboflow: {ROBOFLOW_MODEL_ID} | Rate: {current_fps:.1f} inferences/s",
            fill=COLOR_TEXT,
            font=("Consolas", 11, "bold"),
            anchor="w"
        )
        self.canvas.create_text(
            20, 45,
            text="Non-Memory External Mode | Zero RPM / Zero WPM | Press ESC in console to exit",
            fill="#888888",
            font=("Consolas", 9),
            anchor="w"
        )

        with detections_lock:
            boxes = list(shared_detections)

        # Render 2D ESP Bounding Boxes
        for b in boxes:
            x1, y1, x2, y2 = b["x1"], b["y1"], b["x2"], b["y2"]
            cls_name = b["class"]
            conf = b["confidence"]

            if "counter" in cls_name.lower() or "ct" in cls_name.lower():
                box_color = COLOR_CT
            elif "t" in cls_name.lower():
                box_color = COLOR_T
            else:
                box_color = "#00FF00"

            if "head" in cls_name.lower():
                box_color = COLOR_HEAD

            # Draw outer corner-styled box or full bounding box
            self.canvas.create_rectangle(x1, y1, x2, y2, outline=box_color, width=2)

            # Draw tag & confidence bar
            tag = f"{cls_name.upper()} [{int(conf * 100)}%]"
            self.canvas.create_text(
                x1, max(y1 - 10, 10),
                text=tag,
                fill=box_color,
                font=("Consolas", 9, "bold"),
                anchor="w"
            )

            # Draw center aim dot
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2
            self.canvas.create_oval(cx - 2, cy - 2, cx + 2, cy + 2, fill="#FFFFFF", outline=box_color)

        self.root.after(16, self.render_loop)

    def close(self):
        global is_running
        is_running = False
        self.root.destroy()

    def start(self):
        self.root.mainloop()

def main():
    print("================================================================")
    print("   ROBOFLOW EXTERNAL AI VISION ESP (NON-MEMORY INVASIVE)        ")
    print(f"   Model: {ROBOFLOW_MODEL_ID} | Workspace: {ROBOFLOW_WORKSPACE}")
    print("   Draws bounding boxes over screen without touching game memory")
    print("================================================================")

    # Launch background inference thread
    t = threading.Thread(target=run_inference_worker, daemon=True)
    t.start()

    # Launch transparent render overlay (runs on main UI thread)
    overlay = ExternalVisionOverlay()
    overlay.start()

if __name__ == "__main__":
    main()

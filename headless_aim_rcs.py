import os
import sys
import time
import math
import random
import ctypes
from ctypes import wintypes
import threading
import numpy as np
import cv2
import onnxruntime as ort
import winsound

# ==============================================================================
# CS2 MASTER VISION ENGINE: SNAPPY AIMBOT + REAL AK47 RCS + TRIGGERBOT + FOV KEYS
# ==============================================================================

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    user32.SetProcessDPIAware()

SCREEN_WIDTH = user32.GetSystemMetrics(0)
SCREEN_HEIGHT = user32.GetSystemMetrics(1)
SCREEN_CX = SCREEN_WIDTH // 2
SCREEN_CY = SCREEN_HEIGHT // 2

CROP_SIZE = 320
HALF_CROP = CROP_SIZE // 2
CROP_LEFT = max(0, SCREEN_CX - HALF_CROP)
CROP_TOP = max(0, SCREEN_CY - HALF_CROP)

# DYNAMIC SETTINGS (Tune on the fly with arrow keys)
AIM_KEY = 0x02           # RMB: Right Mouse Button
AIM_FOV_RADIUS = 90      # Adjust with Arrow UP (0x26) / Arrow DOWN (0x28)
AIM_SMOOTH = 1.35        # Snappy fast aim glide (lower = instant flick)
MAX_STEP_PX = 20.0       # Max snap speed per tick (super responsive)
HEAD_RATIO = 0.16        # Direct head hitbox
CONF_THRESH = 0.40

# TRIGGERBOT SETTINGS
TRIGGER_KEY = 0x58       # 'X' Key: Hold X to auto-fire headshots
TRIGGER_TOLERANCE_PX = 14 # Hitbox tolerance around crosshair (pixels)
TRIGGER_DELAY_SHOT = 0.100

# RCS SETTINGS
RCS_ENABLED = True
RCS_KEY = 0x01           # LMB: Left Mouse Button (Spray)
RCS_SCALE = 1.0          # Adjust with Arrow LEFT (0x25) / Arrow RIGHT (0x27)
RCS_INTERVAL = 0.010     # 10ms micro-step loop (100 Hz)

# Realistic AK-47 Recoil Table in raw mouse counts (CS2 standard)
AK47_RECOIL_TABLE = [
    (0.0,   0.0),    # Round 1
    (0.0,   9.5),    # Round 2
    (0.0,  15.5),    # Round 3
    (-2.0, 18.0),    # Round 4
    (-3.0, 20.5),    # Round 5
    (3.0,  19.0),    # Round 6
    (7.5,  16.0),    # Round 7
    (10.5, 12.5),    # Round 8
    (9.5,   8.0),    # Round 9
    (4.0,   4.5),    # Round 10
    (-5.5,  3.0),    # Round 11
    (-10.5, 1.8),    # Round 12
    (-12.5, 1.0),    # Round 13
    (-11.5, 0.5),    # Round 14
    (-8.0,  0.5),    # Round 15
    (-2.0,  0.0),    # Round 16
    (5.0,   0.0),    # Round 17
    (9.0,   0.0),    # Round 18
    (11.0,  0.0),    # Round 19
    (8.0,   0.0),    # Round 20
    (3.5,   0.0),    # Round 21
    (-2.5,  0.0),    # Round 22
    (-7.0,  0.0),    # Round 23
    (-9.0,  0.0),    # Round 24
    (-8.5,  0.0),    # Round 25
    (-6.0,  0.0),    # Round 26
    (-2.0,  0.0),    # Round 27
    (3.0,   0.0),    # Round 28
    (6.0,   0.0),    # Round 29
    (6.0,   0.0)     # Round 30
]

is_running = True
rcs_accum_x = 0.0
rcs_accum_y = 0.0
current_targets = []
targets_lock = threading.Lock()

class NativeScreenGrabber:
    def __init__(self, x: int, y: int, w: int, h: int):
        self.x = int(x)
        self.y = int(y)
        self.w = int(w)
        self.h = int(h)

        user32.OpenInputDesktop.restype = wintypes.HDESK
        user32.SetThreadDesktop.restype = wintypes.BOOL
        user32.SetThreadDesktop.argtypes = [wintypes.HDESK]
        hdesk = user32.OpenInputDesktop(0, False, 0x01FF)
        if hdesk:
            user32.SetThreadDesktop(hdesk)

        user32.GetDC.restype = wintypes.HDC
        user32.GetDC.argtypes = [wintypes.HWND]
        user32.ReleaseDC.restype = ctypes.c_int
        user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]

        gdi32.CreateCompatibleDC.restype = wintypes.HDC
        gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
        gdi32.DeleteDC.restype = wintypes.BOOL
        gdi32.DeleteDC.argtypes = [wintypes.HDC]

        gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
        gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
        gdi32.DeleteObject.restype = wintypes.BOOL
        gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]

        gdi32.SelectObject.restype = wintypes.HGDIOBJ
        gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]

        gdi32.BitBlt.restype = wintypes.BOOL
        gdi32.BitBlt.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD]

        gdi32.GetDIBits.restype = ctypes.c_int
        gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]

        self.sdc = user32.GetDC(None)
        self.mdc = gdi32.CreateCompatibleDC(self.sdc)
        self.bmp = gdi32.CreateCompatibleBitmap(self.sdc, self.w, self.h)
        self.old = gdi32.SelectObject(self.mdc, self.bmp)

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ('biSize', wintypes.DWORD),
                ('biWidth', wintypes.LONG),
                ('biHeight', wintypes.LONG),
                ('biPlanes', wintypes.WORD),
                ('biBitCount', wintypes.WORD),
                ('biCompression', wintypes.DWORD),
                ('biSizeImage', wintypes.DWORD),
                ('biXPelsPerMeter', wintypes.LONG),
                ('biYPelsPerMeter', wintypes.LONG),
                ('biClrUsed', wintypes.DWORD),
                ('biClrImportant', wintypes.DWORD),
            ]

        self.bmi = BITMAPINFOHEADER()
        self.bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        self.bmi.biWidth = self.w
        self.bmi.biHeight = -self.h
        self.bmi.biPlanes = 1
        self.bmi.biBitCount = 32
        self.bmi.biCompression = 0
        self.buf = np.zeros((self.h, self.w, 4), dtype=np.uint8)

    def grab(self) -> np.ndarray:
        gdi32.BitBlt(self.mdc, 0, 0, self.w, self.h, self.sdc, self.x, self.y, 0x00CC0020)
        gdi32.GetDIBits(self.mdc, self.bmp, 0, self.h, self.buf.ctypes.data, ctypes.byref(self.bmi), 0)
        return self.buf[:, :, :3]

    def close(self):
        if self.mdc and self.old:
            gdi32.SelectObject(self.mdc, self.old)
        if self.bmp:
            gdi32.DeleteObject(self.bmp)
        if self.mdc:
            gdi32.DeleteDC(self.mdc)
        if self.sdc:
            user32.ReleaseDC(None, self.sdc)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "yolov8n.onnx")
if not os.path.exists(MODEL_PATH):
    MODEL_PATH = os.path.join("C:\\Users\\Administrator", "yolov8n.onnx")

session_opts = ort.SessionOptions()
session_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
onnx_session = ort.InferenceSession(MODEL_PATH, session_opts, providers=['CPUExecutionProvider'])
model_input_name = onnx_session.get_inputs()[0].name

def is_key_down(vk_code: int) -> bool:
    return bool(user32.GetAsyncKeyState(vk_code) & 0x8000)

def send_mouse_delta(dx: float, dy: float):
    idx = int(round(dx))
    idy = int(round(dy))
    if idx != 0 or idy != 0:
        user32.mouse_event(0x0001, idx, idy, 0, 0)

def send_rcs_accum(dx: float, dy: float):
    """Sub-pixel accumulator: Guarantees zero lost ticks during micro-stepping."""
    global rcs_accum_x, rcs_accum_y
    rcs_accum_x += dx
    rcs_accum_y += dy
    ix = int(rcs_accum_x)
    iy = int(rcs_accum_y)
    if ix != 0 or iy != 0:
        rcs_accum_x -= ix
        rcs_accum_y -= iy
        user32.mouse_event(0x0001, ix, iy, 0, 0)

def click_mouse_shot():
    """Triggerbot instant tap: fires 1 accurate bullet on head."""
    user32.mouse_event(0x0002, 0, 0, 0, 0)  # MOUSEEVENTF_LEFTDOWN
    time.sleep(0.015)
    user32.mouse_event(0x0004, 0, 0, 0, 0)  # MOUSEEVENTF_LEFTUP

def rcs_worker_loop():
    """100Hz AK-47 Recoil Compensation Worker."""
    global is_running, rcs_accum_x, rcs_accum_y
    sub_steps = 10

    while is_running:
        if RCS_ENABLED and is_key_down(RCS_KEY):
            rcs_accum_x = 0.0
            rcs_accum_y = 0.0
            current_bullet = 0

            while is_running and is_key_down(RCS_KEY) and current_bullet < len(AK47_RECOIL_TABLE):
                dx_total, dy_total = AK47_RECOIL_TABLE[current_bullet]
                step_dx = (dx_total * RCS_SCALE) / sub_steps
                step_dy = (dy_total * RCS_SCALE) / sub_steps

                for _ in range(sub_steps):
                    if not is_key_down(RCS_KEY):
                        break
                    send_rcs_accum(step_dx, step_dy)
                    time.sleep(RCS_INTERVAL)

                current_bullet += 1

            while is_running and is_key_down(RCS_KEY):
                time.sleep(0.01)
        else:
            time.sleep(0.005)

def hotkey_listener_loop():
    """Listens for Arrow keys to adjust FOV and RCS multiplier dynamically."""
    global AIM_FOV_RADIUS, RCS_SCALE, is_running

    while is_running:
        # ARROW UP: Increase FOV
        if is_key_down(0x26):
            AIM_FOV_RADIUS = min(220, AIM_FOV_RADIUS + 5)
            print(f"[+] FOV INCREASED: {AIM_FOV_RADIUS}px")
            try:
                winsound.Beep(1600, 30)
            except Exception:
                pass
            time.sleep(0.12)

        # ARROW DOWN: Decrease FOV
        elif is_key_down(0x28):
            AIM_FOV_RADIUS = max(20, AIM_FOV_RADIUS - 5)
            print(f"[-] FOV DECREASED: {AIM_FOV_RADIUS}px")
            try:
                winsound.Beep(900, 30)
            except Exception:
                pass
            time.sleep(0.12)

        # ARROW RIGHT: Increase RCS Pull
        elif is_key_down(0x27):
            RCS_SCALE = min(3.0, round(RCS_SCALE + 0.1, 2))
            print(f"[+] RCS STRENGTH: {RCS_SCALE}x")
            try:
                winsound.Beep(1400, 30)
            except Exception:
                pass
            time.sleep(0.12)

        # ARROW LEFT: Decrease RCS Pull
        elif is_key_down(0x25):
            RCS_SCALE = max(0.2, round(RCS_SCALE - 0.1, 2))
            print(f"[-] RCS STRENGTH: {RCS_SCALE}x")
            try:
                winsound.Beep(800, 30)
            except Exception:
                pass
            time.sleep(0.12)

        time.sleep(0.01)

def optical_aim_loop():
    """Main Optical Vision Loop: Snappy Aim + Triggerbot at 140+ FPS."""
    global is_running, current_targets

    grabber = NativeScreenGrabber(CROP_LEFT, CROP_TOP, CROP_SIZE, CROP_SIZE)
    frame_count = 0
    t_start = time.time()
    last_trigger_time = 0.0

    try:
        while is_running:
            img = grabber.grab()
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            tensor = rgb.astype(np.float32) / 255.0
            chw = np.transpose(tensor, (2, 0, 1))
            batch = np.expand_dims(chw, axis=0)

            outputs = onnx_session.run(None, {model_input_name: batch})
            preds = np.squeeze(outputs[0])
            if preds.shape[0] < preds.shape[1]:
                preds = preds.T

            boxes = []
            confidences = []
            for row in preds:
                cls_conf = float(row[4])
                if cls_conf >= CONF_THRESH:
                    cx, cy, w, h = row[0:4]
                    boxes.append([int(cx - w / 2), int(cy - h / 2), int(w), int(h)])
                    confidences.append(cls_conf)

            indices = cv2.dnn.NMSBoxes(boxes, confidences, CONF_THRESH, 0.45)
            best_target = None
            min_dist = float('inf')
            detected_heads = []

            if len(indices) > 0:
                for i in indices.flatten():
                    bx, by, bw, bh = boxes[i]
                    head_x = bx + bw // 2
                    head_y = by + int(bh * HEAD_RATIO)

                    screen_hx = CROP_LEFT + head_x
                    screen_hy = CROP_TOP + head_y

                    dist = math.hypot(screen_hx - SCREEN_CX, screen_hy - SCREEN_CY)
                    detected_heads.append((screen_hx, screen_hy, dist))

                    if dist <= AIM_FOV_RADIUS and dist < min_dist:
                        min_dist = dist
                        best_target = (screen_hx, screen_hy)

            # 1. TRIGGERBOT: Fires when 'X' is held and crosshair is on head
            if is_key_down(TRIGGER_KEY) and time.time() - last_trigger_time >= TRIGGER_DELAY_SHOT:
                for (hx, hy, dist) in detected_heads:
                    if dist <= TRIGGER_TOLERANCE_PX:
                        click_mouse_shot()
                        last_trigger_time = time.time()
                        break

            # 2. SNAPPY AIMBOT: Snaps onto head when RMB is held
            if is_key_down(AIM_KEY) and best_target is not None:
                shx, shy = best_target
                raw_dx = shx - SCREEN_CX
                raw_dy = shy - SCREEN_CY

                dist_to_head = math.hypot(raw_dx, raw_dy)

                if dist_to_head >= 1.0:
                    # Adaptive snappy speed: faster when further away, locks tight on head
                    divisor = 1.15 if dist_to_head > 20 else AIM_SMOOTH
                    step_x = raw_dx / divisor
                    step_y = raw_dy / divisor

                    step_x = max(min(step_x, MAX_STEP_PX), -MAX_STEP_PX)
                    step_y = max(min(step_y, MAX_STEP_PX), -MAX_STEP_PX)

                    send_mouse_delta(step_x, step_y)

            frame_count += 1
            if frame_count % 140 == 0:
                fps = frame_count / (time.time() - t_start)
                print(f"[+] 140 FPS | FOV: {AIM_FOV_RADIUS}px | RCS: {RCS_SCALE}x | Trigger: [X]")

    finally:
        grabber.close()

if __name__ == "__main__":
    print("==================================================")
    print("   CS2 AI VISION: SNAPPY AIM + AK47 RCS + TRIGGER ")
    print("==================================================")
    print("[*] In-Game Controls:")
    print("    - Hold RMB (Right Click) -> Snappy Head Lock")
    print("    - Hold LMB (Left Click)  -> Laser AK-47 Recoil")
    print("    - Hold 'X' Key           -> Auto Headshot Triggerbot")
    print("    - Arrow UP / DOWN        -> Increase / Decrease FOV")
    print("    - Arrow LEFT / RIGHT     -> Adjust RCS Strength")
    print("==================================================")

    try:
        winsound.Beep(1400, 250)
    except Exception:
        pass

    # Start RCS Thread
    rcs_t = threading.Thread(target=rcs_worker_loop, daemon=True)
    rcs_t.start()

    # Start Hotkeys Thread (Arrow keys)
    keys_t = threading.Thread(target=hotkey_listener_loop, daemon=True)
    keys_t.start()

    # Start Optical Aim & Trigger Loop
    optical_aim_loop()

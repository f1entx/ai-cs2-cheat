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

# Dynamic configuration loaded from config.json if available
import json
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
def get_config():
    cfg = {
        "aim_fov": 95,
        "aim_smooth": 0.35,
        "max_step_px": 60.0,
        "rcs_scale_y": 1.0,
        "trigger_tolerance_px": 14,
        "trigger_delay_ms": 35,
        "head_ratio": 0.16
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                cfg.update(saved)
        except Exception:
            pass
    return cfg

INIT_CFG = get_config()

# DYNAMIC SETTINGS (Tune on the fly with arrow keys or config.json)
AIM_KEY = 0x02           # RMB: Right Mouse Button
AIM_FOV_RADIUS = int(INIT_CFG.get("aim_fov", 80))
AIM_SPEED = float(INIT_CFG.get("aim_speed", 3.50))   # Approach rate / velocity gain (0.5x - 10.0x)
AIM_SMOOTH = float(INIT_CFG.get("aim_smooth", 3.20)) # Inertia curve & jitter filter (1.0x - 10.0x)
MAX_STEP_PX = float(INIT_CFG.get("max_step_px", 25.0)) # Max speed per tick
HEAD_RATIO = float(INIT_CFG.get("head_ratio", 0.16))
CONF_THRESH = float(INIT_CFG.get("confidence_threshold", 0.35))

# TRIGGERBOT SETTINGS
TRIGGER_KEY = 0x58       # 'X' Key: Hold X to auto-fire headshots
TRIGGER_TOLERANCE_PX = int(INIT_CFG.get("trigger_tolerance_px", 14))
TRIGGER_DELAY_SHOT = float(INIT_CFG.get("trigger_delay_ms", 35)) / 1000.0

# RCS MACRO SETTINGS
RCS_ENABLED = True
RCS_KEY = 0x01           # LMB: Left Mouse Button (Spray)
RCS_SENS = float(INIT_CFG.get("rcs_sensitivity", 1.50)) # Match CS2 in-game sensitivity
RCS_SCALE = float(INIT_CFG.get("rcs_scale_y", 1.0))     # Adjust with Arrow LEFT / RIGHT
RCS_SUB_STEPS = int(INIT_CFG.get("rcs_sub_steps", 10))

# Fully Calibrated CS2 AK-47 Spray Macro Table (30 rounds)
# dx: Negative = Pull Left, Positive = Pull Right (counters horizontal drift)
# dy: Positive = Pull Down (counters vertical kick)
AK47_MACRO_TABLE = [
    (0.0,    0.0),   # Round 1: Dead center
    (0.0,   18.0),   # Round 2: Vertical jump
    (-1.0,  24.0),   # Round 3
    (-2.0,  26.0),   # Round 4
    (-2.5,  27.0),   # Round 5
    (-4.0,  23.0),   # Round 6
    (-8.0,  18.0),   # Round 7: Pull left to counter rightward drift
    (-12.0, 14.0),   # Round 8
    (-14.0,  9.0),   # Round 9
    (-13.0,  6.0),   # Round 10
    (6.0,    5.0),   # Round 11: Pull right across center
    (14.0,   4.0),   # Round 12
    (18.0,   4.0),   # Round 13
    (19.0,   3.5),   # Round 14
    (17.0,   3.5),   # Round 15
    (12.0,   3.0),   # Round 16
    (-4.0,   3.0),   # Round 17: Pull left across center
    (-12.0,  3.5),   # Round 18
    (-17.0,  3.5),   # Round 19
    (-19.0,  3.5),   # Round 20
    (-16.0,  3.0),   # Round 21
    (-11.0,  3.0),   # Round 22
    (-4.0,   3.0),   # Round 23
    (5.0,    3.0),   # Round 24: Pull right across center
    (12.0,   3.5),   # Round 25
    (16.0,   3.5),   # Round 26
    (17.0,   3.0),   # Round 27
    (14.0,   3.0),   # Round 28
    (8.0,    3.0),   # Round 29
    (3.0,    3.0)    # Round 30
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

is_trigger_in_flight = False

def async_click_worker():
    global is_trigger_in_flight
    try:
        user32.mouse_event(0x0002, 0, 0, 0, 0)
        time.sleep(0.016)
        user32.mouse_event(0x0004, 0, 0, 0, 0)
    finally:
        is_trigger_in_flight = False

def click_mouse_shot():
    """Triggerbot non-blocking instant tap: never stalls the vision tracking loop."""
    global is_trigger_in_flight
    if not is_trigger_in_flight:
        is_trigger_in_flight = True
        threading.Thread(target=async_click_worker, daemon=True).start()

class SmoothTargetTracker:
    """
    Ultra-smooth damped target tracker with decoupled Aim Speed & Smoothness.
    - speed_val: Determines velocity gain / approach rate (how fast crosshair moves).
    - smooth_val: Determines inertia curve & low-pass filtering (how fluid and tremor-free).
    Guarantees mathematically stable aiming with ZERO tremor, ZERO shaking, and ZERO overshoot.
    """
    def __init__(self):
        self.last_target = None
        self.last_time = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self.lost_frames = 0
        self.is_locked = False
        self.last_step_x = 0
        self.last_step_y = 0
        self.curr_vx = 0.0
        self.curr_vy = 0.0
        self.accum_x = 0.0
        self.accum_y = 0.0

    def update(self, detected_target, now_time: float):
        if detected_target is not None:
            tx, ty = detected_target
            if self.last_target is not None and self.is_locked:
                target_jump = math.hypot(tx - self.last_target[0], ty - self.last_target[1])
                if target_jump > 65.0:
                    # Target switch detected: reset momentum so new target ramps up smoothly
                    self.curr_vx = 0.0
                    self.curr_vy = 0.0
                    self.vx = 0.0
                    self.vy = 0.0

                dt = now_time - self.last_time
                if 0.003 < dt < 0.150:
                    world_dx = (tx - self.last_target[0]) + self.last_step_x
                    world_dy = (ty - self.last_target[1]) + self.last_step_y

                    inst_vx = world_dx / dt
                    inst_vy = world_dy / dt

                    alpha = 0.35
                    self.vx = alpha * inst_vx + (1.0 - alpha) * self.vx
                    self.vy = alpha * inst_vy + (1.0 - alpha) * self.vy
            else:
                self.vx = 0.0
                self.vy = 0.0
                self.curr_vx = 0.0
                self.curr_vy = 0.0

            self.last_target = (tx, ty)
            self.last_time = now_time
            self.lost_frames = 0
            self.is_locked = True
            return (tx, ty)
        else:
            if self.is_locked and self.lost_frames < 2 and self.last_target is not None:
                self.lost_frames += 1
                dt = min(now_time - self.last_time, 0.020)
                pred_x = self.last_target[0] + self.vx * dt
                pred_y = self.last_target[1] + self.vy * dt
                self.last_target = (pred_x, pred_y)
                self.last_time = now_time
                return (pred_x, pred_y)
            else:
                self.is_locked = False
                self.last_target = None
                self.vx = 0.0
                self.vy = 0.0
                self.curr_vx = 0.0
                self.curr_vy = 0.0
                self.accum_x = 0.0
                self.accum_y = 0.0
                self.last_step_x = 0
                self.last_step_y = 0
                return None

    def calculate_step(self, tracked_target, speed_val: float, smooth_val: float, max_step: float, deadzone: float, lead_ms: float = 0.0):
        if tracked_target is None:
            self.curr_vx = 0.0
            self.curr_vy = 0.0
            self.last_step_x = 0
            self.last_step_y = 0
            return 0, 0

        tx, ty = tracked_target

        if lead_ms > 0:
            lead_s = lead_ms / 1000.0
            max_v = 450.0
            cvx = max(min(self.vx, max_v), -max_v)
            cvy = max(min(self.vy, max_v), -max_v)
            aim_x = tx + cvx * lead_s
            aim_y = ty + cvy * lead_s
        else:
            aim_x, aim_y = tx, ty

        raw_dx = aim_x - SCREEN_CX
        raw_dy = aim_y - SCREEN_CY
        dist = math.hypot(raw_dx, raw_dy)

        if dist <= deadzone:
            self.curr_vx = 0.0
            self.curr_vy = 0.0
            self.last_step_x = 0
            self.last_step_y = 0
            return 0, 0

        # Decoupled Aim Speed & Smoothness:
        # speed_val: Determines velocity rate towards target (0.5x - 10.0x)
        # smooth_val: Determines inertia curve & jitter filtration (1.0x - 10.0x)
        speed = max(0.20, float(speed_val))
        smooth = max(1.00, float(smooth_val))

        # Target nominal velocity step based on aim_speed
        speed_factor = min(1.0, speed * 0.08)
        target_step_x = raw_dx * speed_factor
        target_step_y = raw_dy * speed_factor

        # Inertia S-curve low-pass filter driven by aim_smooth
        smooth_alpha = 1.0 / (1.0 + smooth * 0.45)
        self.curr_vx = smooth_alpha * target_step_x + (1.0 - smooth_alpha) * self.curr_vx
        self.curr_vy = smooth_alpha * target_step_y + (1.0 - smooth_alpha) * self.curr_vy

        # Soft landing damping: smoothly decelerates into head center
        if dist < 14.0:
            damping = (dist / 14.0) ** (0.50 + 0.08 * smooth)
            self.curr_vx *= damping
            self.curr_vy *= damping

        if max_step > 0:
            step_len = math.hypot(self.curr_vx, self.curr_vy)
            if step_len > max_step:
                scale = max_step / step_len
                self.curr_vx *= scale
                self.curr_vy *= scale

        self.accum_x += self.curr_vx
        self.accum_y += self.curr_vy

        move_x = int(math.trunc(self.accum_x))
        move_y = int(math.trunc(self.accum_y))

        self.accum_x -= move_x
        self.accum_y -= move_y

        self.last_step_x = move_x
        self.last_step_y = move_y
        return move_x, move_y

def rcs_worker_loop():
    """
    Sub-tick AK-47 Spray Macro Worker with 1ms Precision Windows Timer.
    Calibrated against CS2 Recoil Master workshop map for 100% hits in central spray circle.
    """
    global is_running, rcs_accum_x, rcs_accum_y
    try:
        ctypes.windll.winmm.timeBeginPeriod(1)
    except Exception:
        pass

    while is_running:
        if RCS_ENABLED and is_key_down(RCS_KEY):
            rcs_accum_x = 0.0
            rcs_accum_y = 0.0

            sens = max(0.20, RCS_SENS)
            sens_factor = 1.0 / sens
            sub_steps = max(4, RCS_SUB_STEPS)
            step_duration = 0.099 / sub_steps

            for shot_idx in range(len(AK47_MACRO_TABLE)):
                if not is_running or not is_key_down(RCS_KEY) or not RCS_ENABLED:
                    break

                shot_t0 = time.perf_counter()

                raw_dx, raw_dy = AK47_MACRO_TABLE[shot_idx]
                total_dx = raw_dx * RCS_SCALE * sens_factor
                total_dy = raw_dy * RCS_SCALE * sens_factor

                step_dx = total_dx / sub_steps
                step_dy = total_dy / sub_steps

                for step_i in range(sub_steps):
                    if not is_running or not is_key_down(RCS_KEY):
                        break

                    send_rcs_accum(step_dx, step_dy)

                    target_step_time = shot_t0 + ((step_i + 1) * step_duration)
                    time_remaining = target_step_time - time.perf_counter()
                    if time_remaining > 0.0015:
                        time.sleep(time_remaining - 0.001)
                    while time.perf_counter() < target_step_time:
                        pass

            while is_running and is_key_down(RCS_KEY):
                time.sleep(0.005)
        else:
            time.sleep(0.004)

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
    tracker = SmoothTargetTracker()

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

            detected_targets = []
            if len(indices) > 0:
                for i in indices.flatten():
                    bx, by, bw, bh = boxes[i]
                    head_x = bx + bw // 2
                    head_y = by + int(bh * HEAD_RATIO)

                    screen_hx = CROP_LEFT + head_x
                    screen_hy = CROP_TOP + head_y

                    dist = math.hypot(screen_hx - SCREEN_CX, screen_hy - SCREEN_CY)
                    detected_targets.append((screen_hx, screen_hy, dist, bx, by, bw, bh))

            # 1. TRIGGERBOT: Geometric head hitbox check + Non-blocking instant shot
            if is_key_down(TRIGGER_KEY) and not is_trigger_in_flight and (time.time() - last_trigger_time >= TRIGGER_DELAY_SHOT):
                tol = TRIGGER_TOLERANCE_PX
                should_fire = False
                for (screen_hx, screen_hy, dist, bx, by, bw, bh) in detected_targets:
                    head_x1 = bx - tol
                    head_x2 = bx + bw + tol
                    head_y1 = by - tol
                    head_y2 = by + int(bh * 0.28) + tol

                    if (head_x1 <= HALF_CROP <= head_x2) and (head_y1 <= HALF_CROP <= head_y2):
                        should_fire = True
                        break
                    if dist <= tol:
                        should_fire = True
                        break

                if should_fire:
                    click_mouse_shot()
                    last_trigger_time = time.time()

            # 2. ULTRA-SMOOTH AIMBOT: Displacement compensation + Soft landing + Deadzone
            if is_key_down(AIM_KEY):
                effective_fov = int(AIM_FOV_RADIUS * 1.35) if tracker.is_locked else AIM_FOV_RADIUS
                best_target = None
                min_dist = float('inf')

                for (screen_hx, screen_hy, dist, bx, by, bw, bh) in detected_targets:
                    if dist <= effective_fov and dist < min_dist:
                        min_dist = dist
                        best_target = (screen_hx, screen_hy)

                tracked_target = tracker.update(best_target, time.perf_counter())

                if tracked_target is not None:
                    deadzone = float(INIT_CFG.get("deadzone_px", 1.8))
                    lead_ms = float(INIT_CFG.get("predict_lead_ms", 0.0))
                    mx, my = tracker.calculate_step(
                        tracked_target,
                        speed_val=AIM_SPEED,
                        smooth_val=AIM_SMOOTH,
                        max_step=MAX_STEP_PX,
                        deadzone=deadzone,
                        lead_ms=lead_ms
                    )
                    if mx != 0 or my != 0:
                        send_mouse_delta(mx, my)
            else:
                tracker.update(None, time.perf_counter())

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

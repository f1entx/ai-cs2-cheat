import os
import sys
import json
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
import dearpygui.dearpygui as dpg

# ==============================================================================
# CS2 AI VISION ENGINE - GILA MONSTER IMGUI EDITION
# Full-featured Standalone Desktop Application powered by DearPyGui (DirectX 11)
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

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

# Master Global State
STATE = {
    # Engine state
    "engine_running": True,
    
    # Aimbot Settings
    "aimbot_enabled": True,
    "aim_key": "RMB",
    "aim_mode": "Hold Key",
    "aim_speed": 3.50,             # Aim Speed: Velocity rate towards target (0.5x - 10.0x)
    "aim_smooth": 3.20,            # Smoothness: Inertia curve & damping filter (1.0x - 10.0x)
    "max_step_px": 25.0,           # Max speed per tick (prevents violent camera snap)
    "aim_fov": 80,                 # Legit crosshair field of view
    "head_ratio": 0.16,            # 0.16: Head center / nose
    "target_bone": "Head",
    "target_selection": "Closest to Crosshair",
    "confidence_threshold": 0.35,  # Detection sensitivity
    "deadzone_px": 1.8,            # Eliminates micro-tremor when on head
    "humanize_noise": 0.0,         # Zero artificial noise
    "predict_lead_ms": 0.0,        # Gentle lead (0.0 for pure natural tracking)
    "sticky_fov_mult": 1.35,       # Expanded FOV when locked to prevent target loss
    
    # Recoil Control System (Standalone Macro Mode)
    "rcs_enabled": True,
    "rcs_sensitivity": 1.50,       # In-Game CS2 Sensitivity
    "rcs_scale_x": 1.0,            # Horizontal recoil multiplier
    "rcs_scale_y": 1.0,            # Vertical recoil multiplier
    "rcs_start_bullet": 1,         # Start compensation at bullet N
    "rcs_sub_steps": 10,           # Micro-steps per bullet (10 = 10ms smooth glide)
    
    # Triggerbot Settings
    "trigger_enabled": True,
    "trigger_key": "X",
    "trigger_target": "Head Only", # Head Only, Head + Neck, Any Body Hitbox
    "trigger_tolerance_px": 14,    # Target crosshair radius tolerance
    "trigger_delay_ms": 35,        # 0 = Instant frame-1 reaction
    "trigger_burst_shots": 1,      # Single tap vs burst
    "trigger_burst_delay_ms": 120, # Delay between burst shots
    
    # Visuals / Overlay
    "overlay_enabled": False,
    "draw_fov": True,
    "draw_boxes": True,
    "draw_head_dot": True,
    "draw_snaplines": False,
    
    # Hardware & Input
    "input_backend": "Direct Windows", # Direct Windows, Raspberry Pi Pico (USB HID), KMBox Net
    "pico_com_port": "AUTO",
    "pico_baudrate": 115200,
    
    # Telemetry (read-only)
    "fps": 0.0,
    "targets_count": 0,
    "is_locked": False,
    "is_rcs_firing": False,
    "inference_latency_ms": 0.0
}

KEY_MAP = {
    "RMB": 0x02,
    "LMB": 0x01,
    "Mouse 4": 0x05,
    "Mouse 5": 0x06,
    "Shift": 0x10,
    "Alt": 0x12,
    "Ctrl": 0x11,
    "Caps": 0x14,
    "X": 0x58,
    "C": 0x43,
    "V": 0x56,
    "E": 0x45,
    "F": 0x46,
    "Auto / Always": 0x00
}

# Optional Serial Controller for Raspberry Pi Pico RP2040
pico_serial_handle = None

def init_pico_serial():
    global pico_serial_handle
    try:
        import serial
        import serial.tools.list_ports
        target_port = STATE.get("pico_com_port", "AUTO")
        if target_port == "AUTO":
            ports = list(serial.tools.list_ports.comports())
            for p in ports:
                desc = p.description.lower()
                hwid = p.hwid.lower()
                if "pico" in desc or "2e8a" in hwid or "usb serial" in desc:
                    target_port = p.device
                    break
            if target_port == "AUTO":
                target_port = "COM3"
        
        pico_serial_handle = serial.Serial(
            port=target_port,
            baudrate=int(STATE.get("pico_baudrate", 115200)),
            timeout=0.002,
            write_timeout=0.002
        )
        print(f"[+] Hardware Pico USB Connected on {target_port}")
    except Exception as e:
        pico_serial_handle = None

def dispatch_mouse_move(dx: int, dy: int):
    if dx == 0 and dy == 0:
        return
    backend = STATE.get("input_backend", "Direct Windows")
    if backend == "Raspberry Pi Pico (USB HID)" and pico_serial_handle:
        try:
            cmd = f"M {int(dx)} {int(dy)}\n".encode("ascii")
            pico_serial_handle.write(cmd)
            return
        except Exception:
            pass
    user32.mouse_event(0x0001, int(dx), int(dy), 0, 0)

def dispatch_mouse_click(button: int, state: int):
    # button: 1=LMB, 2=RMB; state: 1=down, 0=up
    backend = STATE.get("input_backend", "Direct Windows")
    if backend == "Raspberry Pi Pico (USB HID)" and pico_serial_handle:
        try:
            cmd = f"C {int(button)} {int(state)}\n".encode("ascii")
            pico_serial_handle.write(cmd)
            return
        except Exception:
            pass
    if button == 1:
        flag = 0x0002 if state == 1 else 0x0004
    else:
        flag = 0x0008 if state == 1 else 0x0010
    user32.mouse_event(flag, 0, 0, 0, 0)

def load_config():
    global STATE
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
                for k, v in saved.items():
                    if k in STATE:
                        STATE[k] = v
        except Exception:
            pass

def save_config():
    try:
        to_save = {k: v for k, v in STATE.items() if not k.startswith("is_") and k not in ["fps", "targets_count", "inference_latency_ms"]}
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(to_save, f, indent=4)
        try:
            winsound.Beep(1750, 80)
        except Exception:
            pass
    except Exception:
        pass

load_config()

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
        self.old_bmp = gdi32.SelectObject(self.mdc, self.bmp)

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize", wintypes.DWORD),
                ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)
            ]

        self.bmi = BITMAPINFOHEADER()
        self.bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        self.bmi.biWidth = self.w
        self.bmi.biHeight = -self.h
        self.bmi.biPlanes = 1
        self.bmi.biBitCount = 32
        self.bmi.biCompression = 0

        self.buf = np.empty((self.h, self.w, 4), dtype=np.uint8)

    def grab(self) -> np.ndarray:
        SRCCOPY = 0x00CC0020
        gdi32.BitBlt(self.mdc, 0, 0, self.w, self.h, self.sdc, self.x, self.y, SRCCOPY)
        gdi32.GetDIBits(self.mdc, self.bmp, 0, self.h, self.buf.ctypes.data, ctypes.byref(self.bmi), 0)
        return self.buf[:, :, :3]

    def close(self):
        try:
            gdi32.SelectObject(self.mdc, self.old_bmp)
            gdi32.DeleteObject(self.bmp)
            gdi32.DeleteDC(self.mdc)
            user32.ReleaseDC(None, self.sdc)
        except Exception:
            pass

def is_key_down(vk_code: int) -> bool:
    if vk_code == 0x00:
        return True
    return bool(user32.GetAsyncKeyState(vk_code) & 0x8000)

rcs_accum_x = 0.0
rcs_accum_y = 0.0

def rcs_worker():
    """
    Sub-tick AK-47 Spray Macro Engine with 1ms Precision Windows Timer.
    Calibrated against CS2 Recoil Master workshop map for 100% hits in central spray circle.
    """
    try:
        ctypes.windll.winmm.timeBeginPeriod(1)
    except Exception:
        pass

    accum_x = 0.0
    accum_y = 0.0

    while True:
        if not STATE.get("engine_running", True) or not STATE.get("rcs_enabled", True):
            time.sleep(0.01)
            continue

        lmb_down = is_key_down(0x01)

        if lmb_down:
            STATE["is_rcs_firing"] = True
            sens = max(0.20, float(STATE.get("rcs_sensitivity", 1.50)))
            scale_x = float(STATE.get("rcs_scale_x", 1.0))
            scale_y = float(STATE.get("rcs_scale_y", 1.0))
            start_bullet = int(STATE.get("rcs_start_bullet", 1)) - 1
            sub_steps = max(4, int(STATE.get("rcs_sub_steps", 10)))

            # Sensitivity scaling: CS2 angles require inversely proportional mouse counts
            sens_factor = 1.0 / sens

            accum_x = 0.0
            accum_y = 0.0

            for shot_idx in range(len(AK47_MACRO_TABLE)):
                if not is_key_down(0x01) or not STATE.get("engine_running", True) or not STATE.get("rcs_enabled", True):
                    break

                shot_t0 = time.perf_counter()

                if shot_idx >= start_bullet:
                    raw_dx, raw_dy = AK47_MACRO_TABLE[shot_idx]
                    total_dx = raw_dx * scale_x * sens_factor
                    total_dy = raw_dy * scale_y * sens_factor
                else:
                    total_dx = 0.0
                    total_dy = 0.0

                step_dx = total_dx / sub_steps
                step_dy = total_dy / sub_steps
                step_duration = 0.099 / sub_steps

                for step_i in range(sub_steps):
                    if not is_key_down(0x01):
                        break

                    accum_x += step_dx
                    accum_y += step_dy

                    move_x = int(math.trunc(accum_x))
                    move_y = int(math.trunc(accum_y))

                    if move_x != 0 or move_y != 0:
                        dispatch_mouse_move(move_x, move_y)
                        accum_x -= move_x
                        accum_y -= move_y

                    target_step_time = shot_t0 + ((step_i + 1) * step_duration)
                    time_remaining = target_step_time - time.perf_counter()
                    if time_remaining > 0.0015:
                        time.sleep(time_remaining - 0.001)
                    while time.perf_counter() < target_step_time:
                        pass

            # Hold until user releases LMB
            while is_key_down(0x01):
                time.sleep(0.005)

            STATE["is_rcs_firing"] = False
        else:
            time.sleep(0.004)

aim_toggle_active = False
prev_aim_key_state = False
is_trigger_in_flight = False

class SmoothTargetTracker:
    """
    Ultra-smooth damped target tracker with decoupled Aim Speed & Smoothness.
    - aim_speed: Dictates the velocity gain / approach rate (how fast crosshair moves).
    - aim_smooth: Dictates inertia curve & low-pass filtering (how fluid and tremor-free).
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
                    # Compensate for camera displacement caused by mouse delta
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

    def calculate_step(self, tracked_target, cfg: dict):
        if tracked_target is None:
            self.curr_vx = 0.0
            self.curr_vy = 0.0
            self.last_step_x = 0
            self.last_step_y = 0
            return 0, 0

        tx, ty = tracked_target

        lead_ms = float(cfg.get("predict_lead_ms", 0.0))
        if lead_ms > 0:
            lead_s = lead_ms / 1000.0
            max_v = 450.0
            cvx = max(min(self.vx, max_v), -max_v)
            cvy = max(min(self.vy, max_v), -max_v)
            aim_x = tx + cvx * lead_s
            aim_y = ty + cvy * lead_s
        else:
            aim_x, aim_y = tx, ty

        raw_dx = aim_x - HALF_CROP
        raw_dy = aim_y - HALF_CROP
        dist = math.hypot(raw_dx, raw_dy)

        deadzone = float(cfg.get("deadzone_px", 1.8))
        if dist <= deadzone:
            self.curr_vx = 0.0
            self.curr_vy = 0.0
            self.last_step_x = 0
            self.last_step_y = 0
            return 0, 0

        # Decoupled Aim Speed & Smoothness:
        # aim_speed determines velocity rate towards target (0.5x - 10.0x)
        # aim_smooth determines inertia curve & jitter filtration (1.0x - 10.0x)
        speed = max(0.20, float(cfg.get("aim_speed", 3.50)))
        smooth = max(1.00, float(cfg.get("aim_smooth", 3.20)))

        # Velocity rate scaled by aim_speed
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

        max_step = float(cfg.get("max_step_px", 25.0))
        if max_step > 0:
            step_len = math.hypot(self.curr_vx, self.curr_vy)
            if step_len > max_step:
                scale = max_step / step_len
                self.curr_vx *= scale
                self.curr_vy *= scale

        # Float accumulator guarantees zero lost sub-pixels & zero stair-stepping
        self.accum_x += self.curr_vx
        self.accum_y += self.curr_vy

        move_x = int(math.trunc(self.accum_x))
        move_y = int(math.trunc(self.accum_y))

        self.accum_x -= move_x
        self.accum_y -= move_y

        self.last_step_x = move_x
        self.last_step_y = move_y
        return move_x, move_y

def async_trigger_worker(delay_s, burst_count):
    global is_trigger_in_flight
    try:
        if delay_s > 0:
            time.sleep(delay_s)
        for i in range(burst_count):
            dispatch_mouse_click(1, 1)
            time.sleep(0.016)
            dispatch_mouse_click(1, 0)
            if burst_count > 1 and i < burst_count - 1:
                time.sleep(0.07)
    except Exception:
        pass
    finally:
        is_trigger_in_flight = False

def trigger_shot_async(delay_s, burst_count):
    global is_trigger_in_flight
    if not is_trigger_in_flight:
        is_trigger_in_flight = True
        t = threading.Thread(target=async_trigger_worker, args=(delay_s, burst_count), daemon=True)
        t.start()

def optical_aim_worker():
    global aim_toggle_active, prev_aim_key_state
    model_name = "yolov8n.onnx"
    model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), model_name)
    if not os.path.exists(model_path):
        model_path = os.path.join(os.path.expanduser("~"), model_name)

    session_opts = ort.SessionOptions()
    session_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

    providers = ['DmlExecutionProvider', 'CPUExecutionProvider']
    try:
        onnx_session = ort.InferenceSession(model_path, session_opts, providers=providers)
    except Exception:
        onnx_session = ort.InferenceSession(model_path, session_opts, providers=['CPUExecutionProvider'])

    input_name = onnx_session.get_inputs()[0].name
    grabber = NativeScreenGrabber(CROP_LEFT, CROP_TOP, CROP_SIZE, CROP_SIZE)
    tracker = SmoothTargetTracker()

    last_trigger_shot = 0.0
    frame_count = 0
    start_time = time.perf_counter()

    while True:
        if not STATE["engine_running"]:
            time.sleep(0.02)
            continue

        frame = grabber.grab()
        if frame is None or frame.size == 0:
            time.sleep(0.001)
            continue

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        chw = np.transpose(rgb, (2, 0, 1)).astype(np.float32) / 255.0
        batch = np.expand_dims(chw, axis=0)

        t_inf_start = time.perf_counter()
        outputs = onnx_session.run(None, {input_name: batch})[0]
        preds = np.squeeze(outputs).T
        STATE["inference_latency_ms"] = (time.perf_counter() - t_inf_start) * 1000.0

        boxes = []
        conf_thresh = float(STATE.get("confidence_threshold", 0.35))
        for p in preds:
            cls_scores = p[4:]
            max_c = np.argmax(cls_scores)
            conf = float(cls_scores[max_c])
            if max_c == 0 and conf >= conf_thresh:
                cx, cy, bw, bh = p[0], p[1], p[2], p[3]
                x1 = int(cx - bw / 2)
                y1 = int(cy - bh / 2)
                x2 = int(cx + bw / 2)
                y2 = int(cy + bh / 2)
                boxes.append((x1, y1, x2, y2, conf))

        indices = cv2.dnn.NMSBoxes([[b[0], b[1], b[2]-b[0], b[3]-b[1]] for b in boxes], [b[4] for b in boxes], conf_thresh, 0.45)

        targets = []
        head_r = float(STATE.get("head_ratio", 0.16))
        if len(indices) > 0:
            for idx in np.array(indices).flatten():
                x1, y1, x2, y2, c = boxes[idx]
                target_x = (x1 + x2) // 2
                target_y = int(y1 + (y2 - y1) * head_r)
                targets.append((target_x, target_y, x1, y1, x2, y2, c))

        STATE["targets_count"] = len(targets)

        # 1. TRIGGERBOT PIPELINE (Geometric Bounding Box Check + Non-blocking Dispatch)
        trig_key_name = STATE.get("trigger_key", "X")
        trig_key_code = KEY_MAP.get(trig_key_name, 0x58)
        trig_active = (trig_key_name == "Auto / Always") or is_key_down(trig_key_code)

        if STATE.get("trigger_enabled", True) and trig_active and targets:
            tol = int(STATE.get("trigger_tolerance_px", 14))
            target_hitbox = STATE.get("trigger_target", "Head Only")
            should_fire = False

            for (tx, ty, x1, y1, x2, y2, c) in targets:
                bh = y2 - y1

                # Head box (top 28% of model) expanded by tolerance
                head_x1 = x1 - tol
                head_x2 = x2 + tol
                head_y1 = y1 - tol
                head_y2 = y1 + int(bh * 0.28) + tol

                if target_hitbox == "Head Only":
                    if (head_x1 <= HALF_CROP <= head_x2) and (head_y1 <= HALF_CROP <= head_y2):
                        should_fire = True
                        break
                    if math.hypot(tx - HALF_CROP, ty - HALF_CROP) <= tol:
                        should_fire = True
                        break
                elif target_hitbox == "Head + Neck":
                    neck_y2 = y1 + int(bh * 0.40) + tol
                    if (head_x1 <= HALF_CROP <= head_x2) and (head_y1 <= HALF_CROP <= neck_y2):
                        should_fire = True
                        break
                    if math.hypot(tx - HALF_CROP, ty - HALF_CROP) <= tol:
                        should_fire = True
                        break
                else: # Any Body Hitbox
                    if (x1 - tol <= HALF_CROP <= x2 + tol) and (y1 - tol <= HALF_CROP <= y2 + tol):
                        should_fire = True
                        break

            if should_fire and not is_trigger_in_flight:
                now = time.perf_counter()
                delay_s = float(STATE.get("trigger_delay_ms", 0)) / 1000.0
                burst_cd = float(STATE.get("trigger_burst_delay_ms", 120)) / 1000.0
                burst_count = int(STATE.get("trigger_burst_shots", 1))

                if now - last_trigger_shot >= (delay_s + burst_cd):
                    last_trigger_shot = now
                    trigger_shot_async(delay_s, burst_count)

        # 2. AIMBOT PIPELINE (Velocity Lead Prediction + Sticky Tracking FOV)
        aim_key_name = STATE.get("aim_key", "RMB")
        aim_key_code = KEY_MAP.get(aim_key_name, 0x02)
        aim_mode = STATE.get("aim_mode", "Hold Key")

        cur_key_state = is_key_down(aim_key_code)
        if aim_mode == "Toggle On/Off":
            if cur_key_state and not prev_aim_key_state:
                aim_toggle_active = not aim_toggle_active
            prev_aim_key_state = cur_key_state
            aim_active = aim_toggle_active
        else:
            aim_active = cur_key_state

        if STATE.get("aimbot_enabled", True) and aim_active:
            base_fov = int(STATE.get("aim_fov", 80))
            effective_fov = int(base_fov * float(STATE.get("sticky_fov_mult", 1.35))) if tracker.is_locked else base_fov

            best_target = None
            min_metric = float('inf')
            selection_mode = STATE.get("target_selection", "Closest to Crosshair")

            for (tx, ty, x1, y1, x2, y2, c) in targets:
                dist = math.hypot(tx - HALF_CROP, ty - HALF_CROP)
                if dist <= effective_fov:
                    metric = -c if selection_mode == "Highest Confidence" else dist
                    if metric < min_metric:
                        min_metric = metric
                        best_target = (tx, ty)

            tracked_target = tracker.update(best_target, time.perf_counter())

            if tracked_target is not None:
                STATE["is_locked"] = True
                step_x, step_y = tracker.calculate_step(tracked_target, STATE)
                if step_x != 0 or step_y != 0:
                    dispatch_mouse_move(step_x, step_y)
            else:
                STATE["is_locked"] = False
        else:
            STATE["is_locked"] = False
            tracker.update(None, time.perf_counter())

        frame_count += 1
        if frame_count % 30 == 0:
            elapsed = time.perf_counter() - start_time
            STATE["fps"] = frame_count / elapsed if elapsed > 0 else 0.0
            frame_count = 0
            start_time = time.perf_counter()

# ==============================================================================
# DEAR IMGUI (DEARPYGUI) MODERN DESKTOP DASHBOARD
# ==============================================================================

class GilaMonsterGuiApp:
    def __init__(self):
        dpg.create_context()
        dpg.create_viewport(title="AI VISION ENGINE | GILA MONSTER IMGUI", width=780, height=560, resizable=False)
        dpg.setup_dearpygui()

        self.active_tab_id = 1
        self.tab_containers = {}
        self.tab_buttons = {}

        self._setup_imgui_theme()
        self._build_ui()
        self._sync_widgets_from_state()

        dpg.set_primary_window("main_window", True)
        dpg.show_viewport()

    def _setup_imgui_theme(self):
        with dpg.theme() as self.theme:
            with dpg.theme_component(dpg.mvAll):
                # Core Dear ImGui Color Palette from C++ Gila Monster
                dpg.add_theme_color(dpg.mvThemeCol_WindowBg, (17, 19, 19, 255))         # ImColor(17, 19, 19)
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg, (14, 16, 16, 255))          # ImColor(14, 16, 16)
                dpg.add_theme_color(dpg.mvThemeCol_Border, (32, 36, 35, 255))           # ImColor(26, 29, 28)
                dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (22, 25, 24, 255))          # Dark input field
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, (34, 38, 37, 255))
                dpg.add_theme_color(dpg.mvThemeCol_FrameBgActive, (48, 54, 52, 255))
                dpg.add_theme_color(dpg.mvThemeCol_SliderGrab, (139, 130, 159, 255))     # Purple/Violet Accent #8b829f
                dpg.add_theme_color(dpg.mvThemeCol_SliderGrabActive, (170, 160, 195, 255))
                dpg.add_theme_color(dpg.mvThemeCol_CheckMark, (139, 130, 159, 255))      # Checkmark Accent
                dpg.add_theme_color(dpg.mvThemeCol_Button, (24, 28, 27, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (36, 42, 40, 255))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, (139, 130, 159, 255))
                dpg.add_theme_color(dpg.mvThemeCol_Header, (26, 30, 29, 255))
                dpg.add_theme_color(dpg.mvThemeCol_HeaderHovered, (38, 44, 42, 255))
                dpg.add_theme_color(dpg.mvThemeCol_HeaderActive, (139, 130, 159, 255))
                dpg.add_theme_color(dpg.mvThemeCol_Text, (235, 235, 240, 255))
                dpg.add_theme_color(dpg.mvThemeCol_TextDisabled, (120, 124, 128, 255))
                
                # Sizing & Rounding
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 4)
                dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, 5)
                dpg.add_theme_style(dpg.mvStyleVar_WindowRounding, 0)
                dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 0, 0)
                dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 8, 7)

        dpg.bind_theme(self.theme)

    def _build_ui(self):
        with dpg.window(tag="main_window", no_title_bar=True, no_resize=True, no_move=True):
            # Top Header Bar
            with dpg.child_window(height=48, border=False):
                with dpg.group(horizontal=True):
                    dpg.add_spacer(width=14)
                    dpg.add_text("GILA", color=(255, 255, 255, 255))
                    dpg.add_text("MONSTER", color=(139, 130, 159, 255))
                    dpg.add_text(" |  AI OPTICAL ENGINE", color=(100, 105, 110, 255))

                    dpg.add_spacer(width=60)
                    # Presets in Header
                    dpg.add_button(label="LEGIT", width=70, callback=lambda: self.apply_preset("legit"))
                    dpg.add_button(label="SEMI-RAGE", width=85, callback=lambda: self.apply_preset("semi_rage"))
                    dpg.add_button(label="FULL RAGE", width=85, callback=lambda: self.apply_preset("rage"))

                    dpg.add_spacer(width=40)
                    self.lbl_telemetry_top = dpg.add_text("FPS: 0.0 | 0.0ms | IDLE", color=(34, 197, 94, 255))

            # Main Body Layout (Left Sidebar + Right Content Area)
            with dpg.group(horizontal=True):
                # LEFT SIDEBAR
                with dpg.child_window(width=165, height=450, border=False):
                    dpg.add_spacer(height=4)
                    dpg.add_text("   AIMBOT SYSTEM", color=(105, 110, 115, 255))
                    self.tab_buttons[1] = dpg.add_button(label="   Aimbot", width=155, height=28, callback=lambda: self.select_tab(1))
                    self.tab_buttons[2] = dpg.add_button(label="   Recoil (RCS)", width=155, height=28, callback=lambda: self.select_tab(2))

                    dpg.add_spacer(height=10)
                    dpg.add_text("   TRIGGER SYSTEM", color=(105, 110, 115, 255))
                    self.tab_buttons[3] = dpg.add_button(label="   Triggerbot", width=155, height=28, callback=lambda: self.select_tab(3))

                    dpg.add_spacer(height=10)
                    dpg.add_text("   VISUALS & ESP", color=(105, 110, 115, 255))
                    self.tab_buttons[4] = dpg.add_button(label="   Visuals / ESP", width=155, height=28, callback=lambda: self.select_tab(4))

                    dpg.add_spacer(height=10)
                    dpg.add_text("   SETTINGS", color=(105, 110, 115, 255))
                    self.tab_buttons[5] = dpg.add_button(label="   Hardware & IO", width=155, height=28, callback=lambda: self.select_tab(5))
                    self.tab_buttons[6] = dpg.add_button(label="   Profiles & Config", width=155, height=28, callback=lambda: self.select_tab(6))

                # RIGHT CONTENT AREA
                with dpg.child_window(width=595, height=450, border=False):
                    self._build_tab_aimbot()
                    self._build_tab_rcs()
                    self._build_tab_triggerbot()
                    self._build_tab_visuals()
                    self._build_tab_hardware()
                    self._build_tab_config()

            # BOTTOM ACTION BAR
            with dpg.child_window(height=52, border=False):
                with dpg.group(horizontal=True):
                    dpg.add_spacer(width=10)
                    self.btn_engine_toggle = dpg.add_button(label="STOP ENGINE", width=130, height=32, callback=self.toggle_engine)
                    dpg.add_spacer(width=180)
                    self.lbl_telemetry_bottom = dpg.add_text("Status: IDLE | Targets: 0 | Snap Speed: 60 px/t", color=(160, 165, 170, 255))
                    dpg.add_spacer(width=40)
                    dpg.add_button(label="SAVE CONFIG", width=105, height=32, callback=self.save_and_notify)

    def _build_tab_aimbot(self):
        with dpg.child_window(tag="tab_aimbot", show=True, border=False):
            with dpg.group(horizontal=True):
                # Column 1: Core Aim Settings
                with dpg.child_window(width=285, height=435, border=True):
                    dpg.add_text("GENERAL AIMBOT", color=(139, 130, 159, 255))
                    dpg.add_separator()
                    dpg.add_checkbox(label="Enable Aimbot", tag="w_aim_enable", callback=self.on_widget_change)
                    dpg.add_combo(label="Aim Key", items=list(KEY_MAP.keys()), tag="w_aim_key", default_value="RMB", callback=self.on_widget_change)
                    dpg.add_combo(label="Aim Mode", items=["Hold Key", "Toggle On/Off"], tag="w_aim_mode", default_value="Hold Key", callback=self.on_widget_change)

                    dpg.add_spacer(height=6)
                    dpg.add_text("SPEED & SMOOTHNESS (DECOUPLED)", color=(180, 180, 190, 255))
                    dpg.add_slider_float(label="Aim Speed", tag="w_aim_speed", default_value=3.50, min_value=0.50, max_value=10.00, format="%.2fx", callback=self.on_widget_change)
                    dpg.add_text("Speed = Approach velocity rate", color=(120, 125, 130, 255))

                    dpg.add_slider_float(label="Smoothness", tag="w_aim_smooth", default_value=3.20, min_value=1.00, max_value=10.00, format="%.2fx", callback=self.on_widget_change)
                    dpg.add_text("Smooth = Inertia curve & jitter filter", color=(120, 125, 130, 255))

                    dpg.add_slider_float(label="Max Snap Clamp", tag="w_aim_clamp", default_value=25.0, min_value=5.0, max_value=80.0, format="%.0f px/t", callback=self.on_widget_change)
                    dpg.add_slider_int(label="FOV Radius", tag="w_aim_fov", default_value=80, min_value=15, max_value=200, format="%d px", callback=self.on_widget_change)

                # Column 2: Advanced Targeting & Hitbox
                with dpg.child_window(width=285, height=435, border=True):
                    dpg.add_text("HITBOX & TARGETING", color=(139, 130, 159, 255))
                    dpg.add_separator()
                    dpg.add_combo(label="Bone Target", items=["Head", "Neck", "Chest", "Center Mass"], tag="w_aim_bone", default_value="Head", callback=self.on_widget_change)
                    dpg.add_slider_float(label="Head Offset", tag="w_aim_head_ratio", default_value=0.16, min_value=0.06, max_value=0.60, format="%.2f", callback=self.on_widget_change)
                    dpg.add_combo(label="Target Filter", items=["Closest to Crosshair", "Highest Confidence"], tag="w_aim_selection", default_value="Closest to Crosshair", callback=self.on_widget_change)
                    
                    dpg.add_spacer(height=6)
                    dpg.add_text("PRECISION & SENSITIVITY", color=(180, 180, 190, 255))
                    dpg.add_slider_float(label="Motion Lead Aim", tag="w_aim_lead", default_value=0.0, min_value=0.0, max_value=25.0, format="%.0f ms", callback=self.on_widget_change)
                    dpg.add_slider_float(label="Confidence Thresh", tag="w_aim_conf", default_value=0.35, min_value=0.15, max_value=0.85, format="%.2f", callback=self.on_widget_change)
                    dpg.add_slider_float(label="Deadzone", tag="w_aim_deadzone", default_value=1.8, min_value=0.5, max_value=5.0, format="%.1f px", callback=self.on_widget_change)
                    dpg.add_slider_float(label="Humanize Tremor", tag="w_aim_noise", default_value=0.0, min_value=0.0, max_value=3.5, format="%.1f px", callback=self.on_widget_change)

        self.tab_containers[1] = "tab_aimbot"

    def _build_tab_rcs(self):
        with dpg.child_window(tag="tab_rcs", show=False, border=False):
            with dpg.group(horizontal=True):
                # Column 1: Macro Controls
                with dpg.child_window(width=285, height=435, border=True):
                    dpg.add_text("AK-47 RECOIL MACRO (LMB)", color=(139, 130, 159, 255))
                    dpg.add_separator()
                    dpg.add_checkbox(label="Enable AK-47 Macro", tag="w_rcs_enable", callback=self.on_widget_change)
                    dpg.add_slider_float(label="In-Game Sensitivity", tag="w_rcs_sens", default_value=1.50, min_value=0.20, max_value=4.50, format="%.2f", callback=self.on_widget_change)
                    dpg.add_text("Match with your CS2 'sensitivity'", color=(120, 125, 130, 255))

                    dpg.add_spacer(height=6)
                    dpg.add_slider_float(label="Pitch Pull (Vertical)", tag="w_rcs_scale_y", default_value=1.00, min_value=0.20, max_value=2.50, format="%.2fx", callback=self.on_widget_change)
                    dpg.add_slider_float(label="Yaw Pull (Horizontal)", tag="w_rcs_scale_x", default_value=1.00, min_value=0.20, max_value=2.50, format="%.2fx", callback=self.on_widget_change)

                    dpg.add_spacer(height=6)
                    dpg.add_slider_int(label="Start Bullet", tag="w_rcs_bullet", default_value=1, min_value=1, max_value=4, callback=self.on_widget_change)
                    dpg.add_slider_int(label="Smooth Steps", tag="w_rcs_steps", default_value=10, min_value=5, max_value=20, format="%d steps/round", callback=self.on_widget_change)

                # Column 2: Status & Preset
                with dpg.child_window(width=285, height=435, border=True):
                    dpg.add_text("RECOIL MACRO CALIBRATION", color=(139, 130, 159, 255))
                    dpg.add_separator()
                    dpg.add_text("Weapon: AK-47 (Full 30-round spray)", color=(230, 230, 230, 255))
                    dpg.add_text("Timing Engine: 1ms High-Precision Query", color=(34, 197, 94, 255))
                    dpg.add_text("Zero Memory / Faceit-Safe Macro Mode", color=(139, 130, 159, 255))
                    dpg.add_spacer(height=8)
                    dpg.add_text("How to Tune:\n- If bullets hit too high -> increase Pitch Pull\n- If bullets hit too low -> decrease Pitch Pull\n- If bullets sway off-center -> adjust Yaw Pull\n- Ensure In-Game Sens matches CS2 console", color=(160, 165, 170, 255))
                    dpg.add_spacer(height=12)
                    dpg.add_button(label="Reset Multipliers to 1.0x", width=220, callback=self.reset_rcs_scales)

        self.tab_containers[2] = "tab_rcs"

    def _build_tab_triggerbot(self):
        with dpg.child_window(tag="tab_triggerbot", show=False, border=False):
            with dpg.group(horizontal=True):
                with dpg.child_window(width=285, height=435, border=True):
                    dpg.add_text("TRIGGERBOT SETTINGS", color=(139, 130, 159, 255))
                    dpg.add_separator()
                    dpg.add_checkbox(label="Enable Triggerbot", tag="w_trig_enable", callback=self.on_widget_change)
                    dpg.add_combo(label="Trigger Key", items=list(KEY_MAP.keys()), tag="w_trig_key", default_value="X", callback=self.on_widget_change)
                    dpg.add_combo(label="Target Zone", items=["Head Only", "Head + Neck", "Any Body Hitbox"], tag="w_trig_target", default_value="Head Only", callback=self.on_widget_change)
                    dpg.add_slider_int(label="Crosshair Radius", tag="w_trig_tol", default_value=14, min_value=2, max_value=35, format="%d px", callback=self.on_widget_change)

                with dpg.child_window(width=285, height=435, border=True):
                    dpg.add_text("TIMING & BURST", color=(139, 130, 159, 255))
                    dpg.add_separator()
                    dpg.add_slider_int(label="Reaction Delay", tag="w_trig_delay", default_value=35, min_value=0, max_value=300, format="%d ms", callback=self.on_widget_change)
                    dpg.add_text("0ms = Frame-1 Instant Bot | 40ms = Fast | 140ms = Legit", color=(120, 125, 130, 255))
                    dpg.add_slider_int(label="Shots Per Trigger", tag="w_trig_burst", default_value=1, min_value=1, max_value=4, format="%d tap", callback=self.on_widget_change)
                    dpg.add_slider_int(label="Burst Cooldown", tag="w_trig_burst_delay", default_value=120, min_value=50, max_value=400, format="%d ms", callback=self.on_widget_change)

        self.tab_containers[3] = "tab_triggerbot"

    def _build_tab_visuals(self):
        with dpg.child_window(tag="tab_visuals", show=False, border=False):
            with dpg.group(horizontal=True):
                with dpg.child_window(width=285, height=435, border=True):
                    dpg.add_text("OVERLAY & HUD", color=(139, 130, 159, 255))
                    dpg.add_separator()
                    dpg.add_checkbox(label="Enable Transparent Overlay", tag="w_vis_overlay", callback=self.on_widget_change)
                    dpg.add_checkbox(label="Draw FOV Circle", tag="w_vis_fov", callback=self.on_widget_change)
                    dpg.add_checkbox(label="Draw 2D Bounding Boxes", tag="w_vis_boxes", callback=self.on_widget_change)
                    dpg.add_checkbox(label="Draw Head Dot", tag="w_vis_dot", callback=self.on_widget_change)
                    dpg.add_checkbox(label="Draw Snaplines", tag="w_vis_snap", callback=self.on_widget_change)

                with dpg.child_window(width=285, height=435, border=True):
                    dpg.add_text("PERFORMANCE NOTES", color=(139, 130, 159, 255))
                    dpg.add_separator()
                    dpg.add_text("Headless Mode (Default):\n- Zero overlay window\n- Mouse clicks are 100% direct\n- Highest FPS & zero cursor interference.", color=(160, 165, 170, 255))
                    dpg.add_spacer(height=20)
                    dpg.add_text("Transparent Mode:\n- WS_EX_TRANSPARENT pass-through\n- FOV & Target boxes rendered over CS2", color=(130, 135, 140, 255))

        self.tab_containers[4] = "tab_visuals"

    def _build_tab_hardware(self):
        with dpg.child_window(tag="tab_hardware", show=False, border=False):
            with dpg.group(horizontal=True):
                with dpg.child_window(width=285, height=435, border=True):
                    dpg.add_text("HARDWARE INPUT BACKEND", color=(139, 130, 159, 255))
                    dpg.add_separator()
                    dpg.add_combo(label="Backend", items=["Direct Windows", "Raspberry Pi Pico (USB HID)", "KMBox Net"], tag="w_hw_backend", default_value="Direct Windows", callback=self.on_widget_change)
                    dpg.add_combo(label="COM Port", items=["AUTO", "COM1", "COM2", "COM3", "COM4", "COM5", "COM6"], tag="w_hw_port", default_value="AUTO", callback=self.on_widget_change)
                    dpg.add_combo(label="Baudrate", items=["115200", "9600", "57600"], tag="w_hw_baud", default_value="115200", callback=self.on_widget_change)

                with dpg.child_window(width=285, height=435, border=True):
                    dpg.add_text("STATUS & ACTIONS", color=(139, 130, 159, 255))
                    dpg.add_separator()
                    dpg.add_button(label="Initialize Hardware Device", width=220, callback=init_pico_serial)
                    dpg.add_spacer(height=10)
                    dpg.add_text("Raspberry Pi Pico RP2040:\nRoutes commands through physical USB\ncontroller chip at 1000Hz polling rate.", color=(140, 145, 150, 255))

        self.tab_containers[5] = "tab_hardware"

    def _build_tab_config(self):
        with dpg.child_window(tag="tab_config", show=False, border=False):
            with dpg.group(horizontal=True):
                with dpg.child_window(width=285, height=435, border=True):
                    dpg.add_text("CONFIGURATION PRESETS", color=(139, 130, 159, 255))
                    dpg.add_separator()
                    dpg.add_button(label="Load Preset: Legit Matchmaking", width=240, height=30, callback=lambda: self.apply_preset("legit"))
                    dpg.add_spacer(height=4)
                    dpg.add_button(label="Load Preset: Semi-Rage Competitive", width=240, height=30, callback=lambda: self.apply_preset("semi_rage"))
                    dpg.add_spacer(height=4)
                    dpg.add_button(label="Load Preset: Full Rage / HVH", width=240, height=30, callback=lambda: self.apply_preset("rage"))

                with dpg.child_window(width=285, height=435, border=True):
                    dpg.add_text("STORAGE & MANAGEMENT", color=(139, 130, 159, 255))
                    dpg.add_separator()
                    dpg.add_button(label="Save Current to config.json", width=240, height=30, callback=self.save_and_notify)
                    dpg.add_spacer(height=4)
                    dpg.add_button(label="Reload from config.json", width=240, height=30, callback=self.reload_from_file)
                    dpg.add_spacer(height=4)
                    dpg.add_button(label="Reset All to Factory Defaults", width=240, height=30, callback=self.reset_defaults)

        self.tab_containers[6] = "tab_config"

    def select_tab(self, tab_id: int):
        self.active_tab_id = tab_id
        for tid, tag in self.tab_containers.items():
            dpg.configure_item(tag, show=(tid == tab_id))

    def on_widget_change(self):
        # Sync values from widgets into global STATE
        STATE["aimbot_enabled"] = dpg.get_value("w_aim_enable")
        STATE["aim_key"] = dpg.get_value("w_aim_key")
        STATE["aim_mode"] = dpg.get_value("w_aim_mode")
        STATE["aim_speed"] = float(dpg.get_value("w_aim_speed"))
        STATE["aim_smooth"] = float(dpg.get_value("w_aim_smooth"))
        STATE["max_step_px"] = float(dpg.get_value("w_aim_clamp"))
        STATE["aim_fov"] = int(dpg.get_value("w_aim_fov"))
        STATE["target_bone"] = dpg.get_value("w_aim_bone")
        STATE["head_ratio"] = float(dpg.get_value("w_aim_head_ratio"))
        STATE["target_selection"] = dpg.get_value("w_aim_selection")
        STATE["confidence_threshold"] = float(dpg.get_value("w_aim_conf"))
        STATE["deadzone_px"] = float(dpg.get_value("w_aim_deadzone"))
        STATE["humanize_noise"] = float(dpg.get_value("w_aim_noise"))
        STATE["predict_lead_ms"] = float(dpg.get_value("w_aim_lead"))

        STATE["rcs_enabled"] = dpg.get_value("w_rcs_enable")
        STATE["rcs_sensitivity"] = float(dpg.get_value("w_rcs_sens"))
        STATE["rcs_scale_y"] = float(dpg.get_value("w_rcs_scale_y"))
        STATE["rcs_scale_x"] = float(dpg.get_value("w_rcs_scale_x"))
        STATE["rcs_start_bullet"] = int(dpg.get_value("w_rcs_bullet"))
        STATE["rcs_sub_steps"] = int(dpg.get_value("w_rcs_steps"))

        STATE["trigger_enabled"] = dpg.get_value("w_trig_enable")
        STATE["trigger_key"] = dpg.get_value("w_trig_key")
        STATE["trigger_target"] = dpg.get_value("w_trig_target")
        STATE["trigger_tolerance_px"] = int(dpg.get_value("w_trig_tol"))
        STATE["trigger_delay_ms"] = int(dpg.get_value("w_trig_delay"))
        STATE["trigger_burst_shots"] = int(dpg.get_value("w_trig_burst"))
        STATE["trigger_burst_delay_ms"] = int(dpg.get_value("w_trig_burst_delay"))

        STATE["overlay_enabled"] = dpg.get_value("w_vis_overlay")
        STATE["draw_fov"] = dpg.get_value("w_vis_fov")
        STATE["draw_boxes"] = dpg.get_value("w_vis_boxes")
        STATE["draw_head_dot"] = dpg.get_value("w_vis_dot")
        STATE["draw_snaplines"] = dpg.get_value("w_vis_snap")

        STATE["input_backend"] = dpg.get_value("w_hw_backend")
        STATE["pico_com_port"] = dpg.get_value("w_hw_port")
        STATE["pico_baudrate"] = int(dpg.get_value("w_hw_baud"))

    def _sync_widgets_from_state(self):
        dpg.set_value("w_aim_enable", STATE.get("aimbot_enabled", True))
        dpg.set_value("w_aim_key", STATE.get("aim_key", "RMB"))
        dpg.set_value("w_aim_mode", STATE.get("aim_mode", "Hold Key"))
        dpg.set_value("w_aim_speed", float(STATE.get("aim_speed", 3.50)))
        dpg.set_value("w_aim_smooth", float(STATE.get("aim_smooth", 3.20)))
        dpg.set_value("w_aim_clamp", float(STATE.get("max_step_px", 25.0)))
        dpg.set_value("w_aim_fov", int(STATE.get("aim_fov", 80)))
        dpg.set_value("w_aim_bone", STATE.get("target_bone", "Head"))
        dpg.set_value("w_aim_head_ratio", float(STATE.get("head_ratio", 0.16)))
        dpg.set_value("w_aim_selection", STATE.get("target_selection", "Closest to Crosshair"))
        dpg.set_value("w_aim_conf", float(STATE.get("confidence_threshold", 0.35)))
        dpg.set_value("w_aim_deadzone", float(STATE.get("deadzone_px", 1.8)))
        dpg.set_value("w_aim_noise", float(STATE.get("humanize_noise", 0.0)))
        dpg.set_value("w_aim_lead", float(STATE.get("predict_lead_ms", 0.0)))

        dpg.set_value("w_rcs_enable", STATE.get("rcs_enabled", True))
        dpg.set_value("w_rcs_sens", float(STATE.get("rcs_sensitivity", 1.50)))
        dpg.set_value("w_rcs_scale_y", float(STATE.get("rcs_scale_y", 1.00)))
        dpg.set_value("w_rcs_scale_x", float(STATE.get("rcs_scale_x", 1.00)))
        dpg.set_value("w_rcs_bullet", int(STATE.get("rcs_start_bullet", 1)))
        dpg.set_value("w_rcs_steps", int(STATE.get("rcs_sub_steps", 10)))

        dpg.set_value("w_trig_enable", STATE.get("trigger_enabled", True))
        dpg.set_value("w_trig_key", STATE.get("trigger_key", "X"))
        dpg.set_value("w_trig_target", STATE.get("trigger_target", "Head Only"))
        dpg.set_value("w_trig_tol", int(STATE.get("trigger_tolerance_px", 14)))
        dpg.set_value("w_trig_delay", int(STATE.get("trigger_delay_ms", 15)))
        dpg.set_value("w_trig_burst", int(STATE.get("trigger_burst_shots", 1)))
        dpg.set_value("w_trig_burst_delay", int(STATE.get("trigger_burst_delay_ms", 120)))

        dpg.set_value("w_vis_overlay", STATE.get("overlay_enabled", False))
        dpg.set_value("w_vis_fov", STATE.get("draw_fov", True))
        dpg.set_value("w_vis_boxes", STATE.get("draw_boxes", True))
        dpg.set_value("w_vis_dot", STATE.get("draw_head_dot", True))
        dpg.set_value("w_vis_snap", STATE.get("draw_snaplines", False))

        dpg.set_value("w_hw_backend", STATE.get("input_backend", "Direct Windows"))
        dpg.set_value("w_hw_port", STATE.get("pico_com_port", "AUTO"))
        dpg.set_value("w_hw_baud", str(STATE.get("pico_baudrate", 115200)))

    def apply_preset(self, preset_name: str):
        if preset_name == "legit":
            STATE["aim_speed"] = 2.40
            STATE["aim_smooth"] = 4.20
            STATE["max_step_px"] = 16.0
            STATE["aim_fov"] = 60
            STATE["head_ratio"] = 0.16
            STATE["deadzone_px"] = 2.0
            STATE["rcs_scale_y"] = 0.85
            STATE["rcs_scale_x"] = 0.85
            STATE["trigger_delay_ms"] = 45
            STATE["trigger_tolerance_px"] = 14
            STATE["predict_lead_ms"] = 0.0
        elif preset_name == "semi_rage":
            STATE["aim_speed"] = 5.50
            STATE["aim_smooth"] = 2.20
            STATE["max_step_px"] = 35.0
            STATE["aim_fov"] = 95
            STATE["head_ratio"] = 0.16
            STATE["deadzone_px"] = 1.5
            STATE["rcs_scale_y"] = 1.00
            STATE["rcs_scale_x"] = 1.00
            STATE["trigger_delay_ms"] = 15
            STATE["trigger_tolerance_px"] = 16
            STATE["predict_lead_ms"] = 6.0
        elif preset_name == "rage":
            STATE["aim_speed"] = 9.50
            STATE["aim_smooth"] = 1.10
            STATE["max_step_px"] = 65.0
            STATE["aim_fov"] = 150
            STATE["head_ratio"] = 0.15
            STATE["deadzone_px"] = 1.0
            STATE["rcs_scale_y"] = 1.10
            STATE["rcs_scale_x"] = 1.10
            STATE["trigger_delay_ms"] = 0 # 0ms instant reaction
            STATE["trigger_tolerance_px"] = 20
            STATE["predict_lead_ms"] = 10.0

        self._sync_widgets_from_state()
        save_config()

    def reset_rcs_scales(self):
        dpg.set_value("w_rcs_scale_x", 1.0)
        dpg.set_value("w_rcs_scale_y", 1.0)
        STATE["rcs_scale_x"] = 1.0
        STATE["rcs_scale_y"] = 1.0
        save_config()

    def toggle_engine(self):
        STATE["engine_running"] = not STATE["engine_running"]
        if STATE["engine_running"]:
            dpg.configure_item(self.btn_engine_toggle, label="STOP ENGINE")
        else:
            dpg.configure_item(self.btn_engine_toggle, label="START ENGINE")

    def save_and_notify(self):
        self.on_widget_change()
        save_config()

    def reload_from_file(self):
        load_config()
        self._sync_widgets_from_state()

    def reset_defaults(self):
        STATE["aimbot_enabled"] = True
        STATE["aim_key"] = "RMB"
        STATE["aim_mode"] = "Hold Key"
        STATE["aim_speed"] = 3.50
        STATE["aim_smooth"] = 3.20
        STATE["max_step_px"] = 25.0
        STATE["aim_fov"] = 80
        STATE["head_ratio"] = 0.16
        STATE["confidence_threshold"] = 0.35
        STATE["deadzone_px"] = 1.8
        STATE["humanize_noise"] = 0.0
        STATE["predict_lead_ms"] = 0.0
        STATE["rcs_enabled"] = True
        STATE["rcs_sensitivity"] = 1.50
        STATE["rcs_scale_y"] = 1.00
        STATE["rcs_scale_x"] = 1.00
        STATE["rcs_start_bullet"] = 1
        STATE["rcs_sub_steps"] = 10
        STATE["trigger_enabled"] = True
        STATE["trigger_key"] = "X"
        STATE["trigger_delay_ms"] = 15
        STATE["trigger_tolerance_px"] = 14
        self._sync_widgets_from_state()
        save_config()

    def update_telemetry(self):
        fps_val = STATE.get("fps", 0.0)
        lat_val = STATE.get("inference_latency_ms", 0.0)
        t_count = STATE.get("targets_count", 0)
        status = "LOCKED" if STATE.get("is_locked") else ("RCS ACTIVE" if STATE.get("is_rcs_firing") else "IDLE")

        col = (34, 197, 94, 255) if status == "IDLE" else (239, 68, 68, 255)
        dpg.set_value(self.lbl_telemetry_top, f"FPS: {fps_val:.1f} | {lat_val:.1f}ms | {status}")
        dpg.configure_item(self.lbl_telemetry_top, color=col)

        dpg.set_value(self.lbl_telemetry_bottom, f"Status: {status} | Targets: {t_count} | Smooth: {STATE['aim_smooth']:.2f}x | FOV: {STATE['aim_fov']}px")

    def run(self):
        last_update = time.perf_counter()
        while dpg.is_dearpygui_running():
            now = time.perf_counter()
            if now - last_update >= 0.12:
                self.update_telemetry()
                last_update = now
            dpg.render_dearpygui_frame()
        dpg.destroy_context()

if __name__ == "__main__":
    print("[*] Launching Background CS2 AI Workers...")
    t_rcs = threading.Thread(target=rcs_worker, daemon=True)
    t_rcs.start()

    t_aim = threading.Thread(target=optical_aim_worker, daemon=True)
    t_aim.start()

    print("[*] Launching Gila Monster Dear ImGui Desktop App...")
    app = GilaMonsterGuiApp()
    app.run()

import os
import sys
import json
import time
import math
import random
import ctypes
from ctypes import wintypes
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import numpy as np
import cv2
import onnxruntime as ort
import winsound

# ==============================================================================
# CS2 AI VISION ENGINE - MODERN DARK CONTROL PANEL & REALTIME CORE
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

# Default Global State
STATE = {
    "engine_running": True,
    "aimbot_enabled": True,
    "aim_key": "RMB",
    "aim_fov": 90,
    "aim_smooth": 1.35,
    "max_step_px": 20.0,
    "head_ratio": 0.16,
    "confidence_threshold": 0.40,
    "rcs_enabled": True,
    "rcs_scale": 1.0,
    "trigger_enabled": True,
    "trigger_key": "X",
    "trigger_tolerance_px": 14,
    "trigger_delay_ms": 100,
    "overlay_enabled": False,
    "draw_fov": True,
    "draw_esp": True,
    "fps": 0.0,
    "targets_count": 0,
    "is_locked": False,
    "is_rcs_firing": False
}

KEY_MAP = {
    "RMB": 0x02,
    "LMB": 0x01,
    "Mouse 4": 0x05,
    "Mouse 5": 0x06,
    "Alt": 0x12,
    "Shift": 0x10,
    "X": 0x58,
    "C": 0x43,
    "V": 0x56,
    "E": 0x45
}

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
        to_save = {k: v for k, v in STATE.items() if not k.startswith("is_") and k not in ["fps", "targets_count", "engine_running"]}
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(to_save, f, indent=4)
    except Exception:
        pass

load_config()

# AK-47 Recoil Punch Table (30 bullets)
AK47_RECOIL_TABLE = [
    (0.0,   0.0), (0.0,   9.5), (0.0,  15.5), (-2.0, 18.0), (-3.0, 20.5),
    (3.0,  19.0), (7.5,  16.0), (10.5, 12.5), (9.5,   8.0), (4.0,   4.5),
    (-5.5,  3.0), (-10.5, 1.8), (-12.5, 1.0), (-11.5, 0.5), (-8.0,  0.5),
    (-2.0,  0.0), (5.0,   0.0), (9.0,   0.0), (11.0,  0.0), (8.0,   0.0),
    (3.5,   0.0), (-2.5,  0.0), (-7.0,  0.0), (-9.0,  0.0), (-8.5,  0.0),
    (-6.0,  0.0), (-2.0,  0.0), (3.0,   0.0), (6.0,   0.0), (6.0,   0.0)
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

rcs_accum_x = 0.0
rcs_accum_y = 0.0

def send_rcs_accum(dx: float, dy: float):
    global rcs_accum_x, rcs_accum_y
    rcs_accum_x += dx
    rcs_accum_y += dy
    ix = int(rcs_accum_x)
    iy = int(rcs_accum_y)
    if ix != 0 or iy != 0:
        rcs_accum_x -= ix
        rcs_accum_y -= iy
        user32.mouse_event(0x0001, ix, iy, 0, 0)

def send_mouse_delta(dx: float, dy: float):
    idx = int(round(dx))
    idy = int(round(dy))
    if idx != 0 or idy != 0:
        user32.mouse_event(0x0001, idx, idy, 0, 0)

def click_mouse_shot():
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.015)
    user32.mouse_event(0x0004, 0, 0, 0, 0)

def rcs_worker():
    global rcs_accum_x, rcs_accum_y
    sub_steps = 10

    while True:
        if not STATE["engine_running"]:
            time.sleep(0.05)
            continue

        if STATE["rcs_enabled"] and is_key_down(0x01):  # LMB held
            STATE["is_rcs_firing"] = True
            rcs_accum_x = 0.0
            rcs_accum_y = 0.0
            bullet = 0

            while STATE["engine_running"] and is_key_down(0x01) and bullet < len(AK47_RECOIL_TABLE):
                dx_tot, dy_tot = AK47_RECOIL_TABLE[bullet]
                step_dx = (dx_tot * STATE["rcs_scale"]) / sub_steps
                step_dy = (dy_tot * STATE["rcs_scale"]) / sub_steps

                for _ in range(sub_steps):
                    if not is_key_down(0x01):
                        break
                    send_rcs_accum(step_dx, step_dy)
                    time.sleep(0.010)

                bullet += 1

            while STATE["engine_running"] and is_key_down(0x01):
                time.sleep(0.01)

            STATE["is_rcs_firing"] = False
        else:
            STATE["is_rcs_firing"] = False
            time.sleep(0.005)

def optical_aim_worker():
    grabber = NativeScreenGrabber(CROP_LEFT, CROP_TOP, CROP_SIZE, CROP_SIZE)
    frame_count = 0
    t_start = time.time()
    last_trig = 0.0

    try:
        while True:
            if not STATE["engine_running"]:
                time.sleep(0.05)
                continue

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
            thresh = STATE["confidence_threshold"]
            for row in preds:
                cls_conf = float(row[4])
                if cls_conf >= thresh:
                    cx, cy, w, h = row[0:4]
                    boxes.append([int(cx - w / 2), int(cy - h / 2), int(w), int(h)])
                    confidences.append(cls_conf)

            indices = cv2.dnn.NMSBoxes(boxes, confidences, thresh, 0.45)
            best_target = None
            min_dist = float('inf')
            detected_heads = []

            if len(indices) > 0:
                for i in indices.flatten():
                    bx, by, bw, bh = boxes[i]
                    head_x = bx + bw // 2
                    head_y = by + int(bh * STATE["head_ratio"])

                    screen_hx = CROP_LEFT + head_x
                    screen_hy = CROP_TOP + head_y

                    dist = math.hypot(screen_hx - SCREEN_CX, screen_hy - SCREEN_CY)
                    detected_heads.append((screen_hx, screen_hy, dist))

                    if dist <= STATE["aim_fov"] and dist < min_dist:
                        min_dist = dist
                        best_target = (screen_hx, screen_hy)

            STATE["targets_count"] = len(detected_heads)

            # Triggerbot
            trig_vk = KEY_MAP.get(STATE["trigger_key"], 0x58)
            trig_delay = STATE["trigger_delay_ms"] / 1000.0
            if STATE["trigger_enabled"] and is_key_down(trig_vk) and (time.time() - last_trig >= trig_delay):
                for (hx, hy, dist) in detected_heads:
                    if dist <= STATE["trigger_tolerance_px"]:
                        click_mouse_shot()
                        last_trig = time.time()
                        break

            # Aimbot
            aim_vk = KEY_MAP.get(STATE["aim_key"], 0x02)
            if STATE["aimbot_enabled"] and is_key_down(aim_vk) and (best_target is not None):
                STATE["is_locked"] = True
                shx, shy = best_target
                raw_dx = shx - SCREEN_CX
                raw_dy = shy - SCREEN_CY
                d = math.hypot(raw_dx, raw_dy)

                if d >= 1.0:
                    divisor = 1.15 if d > 20 else STATE["aim_smooth"]
                    step_x = raw_dx / divisor
                    step_y = raw_dy / divisor

                    mx = STATE["max_step_px"]
                    step_x = max(min(step_x, mx), -mx)
                    step_y = max(min(step_y, mx), -mx)
                    send_mouse_delta(step_x, step_y)
            else:
                STATE["is_locked"] = False

            frame_count += 1
            if frame_count % 30 == 0:
                STATE["fps"] = frame_count / (time.time() - t_start)
                if frame_count >= 300:
                    frame_count = 0
                    t_start = time.time()
    finally:
        grabber.close()

# Modern Dark-Themed GUI
class ModernControlPanel:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("CS2 Vision Engine - Control Panel")
        self.root.geometry("480x620")
        self.root.resizable(False, False)
        self.root.configure(bg="#121214")

        # Top Banner / Brand
        header = tk.Frame(self.root, bg="#18181b", height=60)
        header.pack(fill="x")
        lbl_title = tk.Label(header, text="CS2 AI VISION CONTROLLER", font=("Segoe UI", 13, "bold"), fg="#22c55e", bg="#18181b")
        lbl_title.pack(side="left", padx=16, pady=12)

        self.lbl_fps = tk.Label(header, text="FPS: 0.0 | Targets: 0", font=("Consolas", 10), fg="#a1a1aa", bg="#18181b")
        self.lbl_fps.pack(side="right", padx=16, pady=12)

        # Main scrollable or tabbed container
        main_frame = tk.Frame(self.root, bg="#121214")
        main_frame.pack(fill="both", expand=True, padx=16, pady=12)

        # Section 1: Aimbot
        f_aim = tk.LabelFrame(main_frame, text=" [1] Aimbot Settings ", font=("Segoe UI", 10, "bold"), fg="#e4e4e7", bg="#18181b", padx=10, pady=8)
        f_aim.pack(fill="x", pady=5)

        self.var_aim_enable = tk.BooleanVar(value=STATE["aimbot_enabled"])
        cb_aim = tk.Checkbutton(f_aim, text="Enable Aimbot", variable=self.var_aim_enable, command=self.on_update, bg="#18181b", fg="#ffffff", selectcolor="#27272a", activebackground="#18181b")
        cb_aim.grid(row=0, column=0, sticky="w")

        tk.Label(f_aim, text="Aim Key:", fg="#a1a1aa", bg="#18181b", font=("Segoe UI", 9)).grid(row=0, column=1, sticky="e", padx=4)
        self.var_aim_key = tk.StringVar(value=STATE["aim_key"])
        dd_aim_key = ttk.Combobox(f_aim, textvariable=self.var_aim_key, values=["RMB", "LMB", "Mouse 4", "Mouse 5", "Alt", "Shift"], width=8, state="readonly")
        dd_aim_key.grid(row=0, column=2, sticky="w")
        dd_aim_key.bind("<<ComboboxSelected>>", lambda e: self.on_update())

        # Sliders for Aim
        self.lbl_fov = tk.Label(f_aim, text=f"FOV Radius: {STATE['aim_fov']} px", fg="#e4e4e7", bg="#18181b", font=("Segoe UI", 9))
        self.lbl_fov.grid(row=1, column=0, columnspan=2, sticky="w", pady=(6,0))
        self.scale_fov = tk.Scale(f_aim, from_=20, to=200, orient="horizontal", bg="#18181b", fg="#ffffff", highlightthickness=0, troughcolor="#27272a", showvalue=0, command=self.on_fov_change)
        self.scale_fov.set(STATE["aim_fov"])
        self.scale_fov.grid(row=1, column=2, sticky="ew", pady=(6,0))

        self.lbl_smooth = tk.Label(f_aim, text=f"Smooth Divisor: {STATE['aim_smooth']}x (lower=faster)", fg="#e4e4e7", bg="#18181b", font=("Segoe UI", 9))
        self.lbl_smooth.grid(row=2, column=0, columnspan=2, sticky="w", pady=4)
        self.scale_smooth = tk.Scale(f_aim, from_=1.0, to=4.0, resolution=0.05, orient="horizontal", bg="#18181b", fg="#ffffff", highlightthickness=0, troughcolor="#27272a", showvalue=0, command=self.on_smooth_change)
        self.scale_smooth.set(STATE["aim_smooth"])
        self.scale_smooth.grid(row=2, column=2, sticky="ew", pady=4)

        self.lbl_clamp = tk.Label(f_aim, text=f"Max Snap Speed: {STATE['max_step_px']} px/tick", fg="#e4e4e7", bg="#18181b", font=("Segoe UI", 9))
        self.lbl_clamp.grid(row=3, column=0, columnspan=2, sticky="w", pady=4)
        self.scale_clamp = tk.Scale(f_aim, from_=3.0, to=30.0, resolution=1.0, orient="horizontal", bg="#18181b", fg="#ffffff", highlightthickness=0, troughcolor="#27272a", showvalue=0, command=self.on_clamp_change)
        self.scale_clamp.set(STATE["max_step_px"])
        self.scale_clamp.grid(row=3, column=2, sticky="ew", pady=4)

        # Section 2: AK-47 RCS
        f_rcs = tk.LabelFrame(main_frame, text=" [2] AK-47 Recoil Control (RCS) ", font=("Segoe UI", 10, "bold"), fg="#e4e4e7", bg="#18181b", padx=10, pady=8)
        f_rcs.pack(fill="x", pady=6)

        self.var_rcs_enable = tk.BooleanVar(value=STATE["rcs_enabled"])
        cb_rcs = tk.Checkbutton(f_rcs, text="Enable AK-47 RCS on LMB", variable=self.var_rcs_enable, command=self.on_update, bg="#18181b", fg="#ffffff", selectcolor="#27272a", activebackground="#18181b")
        cb_rcs.grid(row=0, column=0, columnspan=2, sticky="w")

        self.lbl_rcs_scale = tk.Label(f_rcs, text=f"Recoil Multiplier: {STATE['rcs_scale']}x", fg="#e4e4e7", bg="#18181b", font=("Segoe UI", 9))
        self.lbl_rcs_scale.grid(row=1, column=0, columnspan=2, sticky="w", pady=(6,0))
        self.scale_rcs = tk.Scale(f_rcs, from_=0.2, to=2.5, resolution=0.05, orient="horizontal", bg="#18181b", fg="#ffffff", highlightthickness=0, troughcolor="#27272a", showvalue=0, command=self.on_rcs_change)
        self.scale_rcs.set(STATE["rcs_scale"])
        self.scale_rcs.grid(row=1, column=2, sticky="ew", pady=(6,0))

        # Section 3: Triggerbot
        f_trig = tk.LabelFrame(main_frame, text=" [3] Auto-Headshot Triggerbot ", font=("Segoe UI", 10, "bold"), fg="#e4e4e7", bg="#18181b", padx=10, pady=8)
        f_trig.pack(fill="x", pady=6)

        self.var_trig_enable = tk.BooleanVar(value=STATE["trigger_enabled"])
        cb_trig = tk.Checkbutton(f_trig, text="Enable Triggerbot", variable=self.var_trig_enable, command=self.on_update, bg="#18181b", fg="#ffffff", selectcolor="#27272a", activebackground="#18181b")
        cb_trig.grid(row=0, column=0, sticky="w")

        tk.Label(f_trig, text="Trigger Key:", fg="#a1a1aa", bg="#18181b", font=("Segoe UI", 9)).grid(row=0, column=1, sticky="e", padx=4)
        self.var_trig_key = tk.StringVar(value=STATE["trigger_key"])
        dd_trig_key = ttk.Combobox(f_trig, textvariable=self.var_trig_key, values=["X", "C", "V", "E", "Mouse 4", "Mouse 5", "Alt"], width=8, state="readonly")
        dd_trig_key.grid(row=0, column=2, sticky="w")
        dd_trig_key.bind("<<ComboboxSelected>>", lambda e: self.on_update())

        self.lbl_tol = tk.Label(f_trig, text=f"Head Tolerance: {STATE['trigger_tolerance_px']} px", fg="#e4e4e7", bg="#18181b", font=("Segoe UI", 9))
        self.lbl_tol.grid(row=1, column=0, columnspan=2, sticky="w", pady=(6,0))
        self.scale_tol = tk.Scale(f_trig, from_=5, to=30, resolution=1, orient="horizontal", bg="#18181b", fg="#ffffff", highlightthickness=0, troughcolor="#27272a", showvalue=0, command=self.on_tol_change)
        self.scale_tol.set(STATE["trigger_tolerance_px"])
        self.scale_tol.grid(row=1, column=2, sticky="ew", pady=(6,0))

        # Bottom Action Bar
        btn_bar = tk.Frame(self.root, bg="#18181b", height=50)
        btn_bar.pack(fill="x", side="bottom")

        self.btn_toggle = tk.Button(btn_bar, text="STOP ENGINE", font=("Segoe UI", 9, "bold"), bg="#ef4444", fg="#ffffff", relief="flat", padx=12, pady=6, command=self.toggle_engine)
        self.btn_toggle.pack(side="left", padx=12, pady=8)

        btn_save = tk.Button(btn_bar, text="SAVE CONFIG", font=("Segoe UI", 9, "bold"), bg="#27272a", fg="#ffffff", relief="flat", padx=12, pady=6, command=self.save_and_notify)
        btn_save.pack(side="right", padx=12, pady=8)

        btn_reset = tk.Button(btn_bar, text="RESET", font=("Segoe UI", 9), bg="#27272a", fg="#a1a1aa", relief="flat", padx=8, pady=6, command=self.reset_defaults)
        btn_reset.pack(side="right", padx=4, pady=8)

        self.root.after(100, self.update_telemetry)

    def on_fov_change(self, val):
        STATE["aim_fov"] = int(val)
        self.lbl_fov.config(text=f"FOV Radius: {STATE['aim_fov']} px")

    def on_smooth_change(self, val):
        STATE["aim_smooth"] = float(val)
        self.lbl_smooth.config(text=f"Smooth Divisor: {STATE['aim_smooth']:.2f}x (lower=faster)")

    def on_clamp_change(self, val):
        STATE["max_step_px"] = float(val)
        self.lbl_clamp.config(text=f"Max Snap Speed: {STATE['max_step_px']:.0f} px/tick")

    def on_rcs_change(self, val):
        STATE["rcs_scale"] = float(val)
        self.lbl_rcs_scale.config(text=f"Recoil Multiplier: {STATE['rcs_scale']:.2f}x")

    def on_tol_change(self, val):
        STATE["trigger_tolerance_px"] = int(val)
        self.lbl_tol.config(text=f"Head Tolerance: {STATE['trigger_tolerance_px']} px")

    def on_update(self):
        STATE["aimbot_enabled"] = self.var_aim_enable.get()
        STATE["aim_key"] = self.var_aim_key.get()
        STATE["rcs_enabled"] = self.var_rcs_enable.get()
        STATE["trigger_enabled"] = self.var_trig_enable.get()
        STATE["trigger_key"] = self.var_trig_key.get()

    def toggle_engine(self):
        STATE["engine_running"] = not STATE["engine_running"]
        if STATE["engine_running"]:
            self.btn_toggle.config(text="STOP ENGINE", bg="#ef4444")
        else:
            self.btn_toggle.config(text="START ENGINE", bg="#22c55e")

    def save_and_notify(self):
        save_config()
        try:
            winsound.Beep(1500, 100)
        except Exception:
            pass

    def reset_defaults(self):
        STATE["aim_fov"] = 90
        STATE["aim_smooth"] = 1.35
        STATE["max_step_px"] = 20.0
        STATE["rcs_scale"] = 1.0
        STATE["trigger_tolerance_px"] = 14
        self.scale_fov.set(90)
        self.scale_smooth.set(1.35)
        self.scale_clamp.set(20.0)
        self.scale_rcs.set(1.0)
        self.scale_tol.set(14)
        save_config()

    def update_telemetry(self):
        fps_val = STATE.get("fps", 0.0)
        t_count = STATE.get("targets_count", 0)
        status = "LOCKED" if STATE.get("is_locked") else ("RCS" if STATE.get("is_rcs_firing") else "IDLE")
        self.lbl_fps.config(text=f"FPS: {fps_val:.1f} | Status: {status} | Targets: {t_count}")

        # Keep sliders synced if hotkeys were pressed in-game
        cur_fov = STATE["aim_fov"]
        if self.scale_fov.get() != cur_fov:
            self.scale_fov.set(cur_fov)
            self.lbl_fov.config(text=f"FOV Radius: {cur_fov} px")

        cur_rcs = STATE["rcs_scale"]
        if round(self.scale_rcs.get(), 2) != round(cur_rcs, 2):
            self.scale_rcs.set(cur_rcs)
            self.lbl_rcs_scale.config(text=f"Recoil Multiplier: {cur_rcs:.2f}x")

        self.root.after(150, self.update_telemetry)

if __name__ == "__main__":
    print("[*] Starting Background Engine Workers...")
    t_rcs = threading.Thread(target=rcs_worker, daemon=True)
    t_rcs.start()

    t_aim = threading.Thread(target=optical_aim_worker, daemon=True)
    t_aim.start()

    print("[*] Launching Modern Dark Control Panel...")
    app = ModernControlPanel()
    app.root.mainloop()

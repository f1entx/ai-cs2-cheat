import os
import sys
import time
import math
import random
import ctypes
from ctypes import wintypes
import threading
import tkinter as tk
import numpy as np
import cv2
import onnxruntime as ort
import winsound

# ==============================================================================
# CS2 MASTER VISION ENGINE: SNAPPY AIMBOT + REAL AK47 RCS + TRIGGERBOT + ESP
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

# DYNAMIC SETTINGS
AIM_KEY = 0x02           # RMB: Right Mouse Button
AIM_FOV_RADIUS = 90      # Adjust with Arrow UP (0x26) / Arrow DOWN (0x28)
AIM_SMOOTH = 1.35        # Snappy fast aim glide
MAX_STEP_PX = 20.0       # Max snap speed per tick
HEAD_RATIO = 0.16        # Direct head hitbox
CONF_THRESH = 0.40

# TRIGGERBOT SETTINGS
TRIGGER_KEY = 0x58       # 'X' Key: Hold X to auto-fire headshots
TRIGGER_TOLERANCE_PX = 14
TRIGGER_DELAY_SHOT = 0.100

# RCS SETTINGS
RCS_ENABLED = True
RCS_KEY = 0x01           # LMB: Left Mouse Button (Spray)
RCS_SCALE = 1.0          # Adjust with Arrow LEFT / RIGHT
RCS_INTERVAL = 0.010     # 10ms micro-step loop (100 Hz)

AK47_RECOIL_TABLE = [
    (0.0,   0.0), (0.0,   9.5), (0.0,  15.5), (-2.0, 18.0), (-3.0, 20.5),
    (3.0,  19.0), (7.5,  16.0), (10.5, 12.5), (9.5,   8.0), (4.0,   4.5),
    (-5.5,  3.0), (-10.5, 1.8), (-12.5, 1.0), (-11.5, 0.5), (-8.0,  0.5),
    (-2.0,  0.0), (5.0,   0.0), (9.0,   0.0), (11.0,  0.0), (8.0,   0.0),
    (3.5,   0.0), (-2.5,  0.0), (-7.0,  0.0), (-9.0,  0.0), (-8.5,  0.0),
    (-6.0,  0.0), (-2.0,  0.0), (3.0,   0.0), (6.0,   0.0), (6.0,   0.0)
]

shared_targets = []
shared_locked = None
data_lock = threading.Lock()
is_running = True
current_fps = 0.0
is_rcs_active = False
overlay_visible = True
rcs_accum_x = 0.0
rcs_accum_y = 0.0

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
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.015)
    user32.mouse_event(0x0004, 0, 0, 0, 0)

def rcs_worker_loop():
    global is_running, is_rcs_active, rcs_accum_x, rcs_accum_y
    sub_steps = 10

    while is_running:
        if RCS_ENABLED and is_key_down(RCS_KEY):
            is_rcs_active = True
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

            is_rcs_active = False
        else:
            is_rcs_active = False
            time.sleep(0.005)

def hotkey_listener_loop():
    global AIM_FOV_RADIUS, RCS_SCALE, is_running

    while is_running:
        if is_key_down(0x26):  # UP
            AIM_FOV_RADIUS = min(220, AIM_FOV_RADIUS + 5)
            print(f"[+] FOV INCREASED: {AIM_FOV_RADIUS}px")
            try:
                winsound.Beep(1600, 30)
            except Exception:
                pass
            time.sleep(0.12)
        elif is_key_down(0x28):  # DOWN
            AIM_FOV_RADIUS = max(20, AIM_FOV_RADIUS - 5)
            print(f"[-] FOV DECREASED: {AIM_FOV_RADIUS}px")
            try:
                winsound.Beep(900, 30)
            except Exception:
                pass
            time.sleep(0.12)
        elif is_key_down(0x27):  # RIGHT (RCS +)
            RCS_SCALE = min(3.0, round(RCS_SCALE + 0.1, 2))
            print(f"[+] RCS STRENGTH: {RCS_SCALE}x")
            try:
                winsound.Beep(1400, 30)
            except Exception:
                pass
            time.sleep(0.12)
        elif is_key_down(0x25):  # LEFT (RCS -)
            RCS_SCALE = max(0.2, round(RCS_SCALE - 0.1, 2))
            print(f"[-] RCS STRENGTH: {RCS_SCALE}x")
            try:
                winsound.Beep(800, 30)
            except Exception:
                pass
            time.sleep(0.12)

        time.sleep(0.01)

def optical_aim_loop():
    global shared_targets, shared_locked, is_running, current_fps

    grabber = NativeScreenGrabber(CROP_LEFT, CROP_TOP, CROP_SIZE, CROP_SIZE)
    frame_count = 0
    fps_timer = time.time()
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
            parsed_targets = []
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

                    target_data = {
                        "crop_box": (bx, by, bx + bw, by + bh),
                        "screen_head": (screen_hx, screen_hy),
                        "dist": dist,
                        "conf": confidences[i]
                    }
                    parsed_targets.append(target_data)

                    if dist <= AIM_FOV_RADIUS and dist < min_dist:
                        min_dist = dist
                        best_target = target_data

            with data_lock:
                shared_targets = parsed_targets
                shared_locked = best_target

            # 1. TRIGGERBOT ('X' key)
            if is_key_down(TRIGGER_KEY) and time.time() - last_trigger_time >= TRIGGER_DELAY_SHOT:
                for (hx, hy, dist) in detected_heads:
                    if dist <= TRIGGER_TOLERANCE_PX:
                        click_mouse_shot()
                        last_trigger_time = time.time()
                        break

            # 2. SNAPPY AIMBOT (RMB)
            if is_key_down(AIM_KEY) and best_target is not None:
                shx, shy = best_target["screen_head"]
                raw_dx = shx - SCREEN_CX
                raw_dy = shy - SCREEN_CY

                dist_to_head = math.hypot(raw_dx, raw_dy)

                if dist_to_head >= 1.0:
                    divisor = 1.15 if dist_to_head > 20 else AIM_SMOOTH
                    step_x = raw_dx / divisor
                    step_y = raw_dy / divisor

                    step_x = max(min(step_x, MAX_STEP_PX), -MAX_STEP_PX)
                    step_y = max(min(step_y, MAX_STEP_PX), -MAX_STEP_PX)

                    send_mouse_delta(step_x, step_y)

            frame_count += 1
            now = time.time()
            if now - fps_timer >= 1.0:
                current_fps = frame_count / (now - fps_timer)
                frame_count = 0
                fps_timer = now
    finally:
        grabber.close()

class TransparentVisionHUD:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Local_AI_Vision_HUD")
        self.root.geometry(f"{SCREEN_WIDTH}x{SCREEN_HEIGHT}+0+0")
        self.root.overrideredirect(True)
        self.root.wm_attributes("-topmost", True)
        self.root.wm_attributes("-transparentcolor", "#000000")
        self.root.wm_attributes("-disabled", True)
        self.root.config(bg="#000000")

        self.canvas = tk.Canvas(self.root, width=SCREEN_WIDTH, height=SCREEN_HEIGHT, bg="#000000", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self.root.update_idletasks()
        child_hwnd = self.root.winfo_id()
        parent_hwnd = user32.GetParent(child_hwnd)
        target_hwnds = [h for h in [parent_hwnd, child_hwnd] if h]

        GWL_EXSTYLE = -20
        GWL_STYLE = -16
        EX_FLAGS = 0x00000020 | 0x00080000 | 0x08000000 | 0x00000080

        for h in target_hwnds:
            cur_ex = user32.GetWindowLongW(h, GWL_EXSTYLE)
            user32.SetWindowLongW(h, GWL_EXSTYLE, cur_ex | EX_FLAGS)
            cur_style = user32.GetWindowLongW(h, GWL_STYLE)
            user32.SetWindowLongW(h, GWL_STYLE, cur_style | 0x08000000)

        self.root.after(16, self.redraw)

    def redraw(self):
        global overlay_visible
        self.canvas.delete("all")

        if is_key_down(0x71):  # F2
            overlay_visible = not overlay_visible
            time.sleep(0.2)

        if not overlay_visible:
            self.root.after(30, self.redraw)
            return

        with data_lock:
            targets = list(shared_targets)
            locked = shared_locked

        is_aiming = is_key_down(AIM_KEY)
        is_triggering = is_key_down(TRIGGER_KEY)
        aim_status = "LOCKED [AIMING]" if (locked and is_aiming) else ("HOLDING RMB" if is_aiming else "STANDBY")
        rcs_status = "RCS FIRING [SPRAYING]" if is_rcs_active else "RCS READY"
        trig_status = "TRIGGER: AUTO-HEAD [X]" if is_triggering else "TRIGGER: IDLE [X]"
        status_color = "#FF0044" if (locked and is_aiming) else "#00FF66"

        self.canvas.create_text(
            25, 25,
            text=f"[AI VISION] {aim_status} | {rcs_status} | {trig_status} | {current_fps:.1f} FPS",
            fill=status_color, font=("Consolas", 11, "bold"), anchor="w"
        )
        self.canvas.create_text(
            25, 45,
            text=f"RMB: Fast Aim | LMB: AK47 RCS ({RCS_SCALE}x) | X: Trigger | FOV: {AIM_FOV_RADIUS}px (Up/Down)",
            fill="#AAAAAA", font=("Consolas", 9), anchor="w"
        )

        # Dynamic FOV Circle in center of screen
        self.canvas.create_oval(
            SCREEN_CX - AIM_FOV_RADIUS, SCREEN_CY - AIM_FOV_RADIUS,
            SCREEN_CX + AIM_FOV_RADIUS, SCREEN_CY + AIM_FOV_RADIUS,
            outline="#00FFFF", width=2
        )
        self.canvas.create_oval(
            SCREEN_CX - 2, SCREEN_CY - 2,
            SCREEN_CX + 2, SCREEN_CY + 2,
            fill="#00FFFF", outline="#FFFFFF"
        )

        for t in targets:
            bx1, by1, bx2, by2 = t["crop_box"]
            shx, shy = t["screen_head"]

            sx1 = CROP_LEFT + bx1
            sy1 = CROP_TOP + by1
            sx2 = CROP_LEFT + bx2
            sy2 = CROP_TOP + by2

            self.canvas.create_rectangle(sx1, sy1, sx2, sy2, outline="#00FF66", width=1)
            self.canvas.create_oval(shx - 4, shy - 4, shx + 4, shy + 4, fill="#FF0044", outline="#FFFFFF")

        if locked and is_aiming:
            lx, ly = locked["screen_head"]
            self.canvas.create_line(SCREEN_CX, SCREEN_CY, lx, ly, fill="#FF0044", width=2)

        self.root.after(16, self.redraw)

    def quit(self):
        global is_running
        is_running = False
        self.root.destroy()

if __name__ == "__main__":
    try:
        winsound.Beep(1400, 200)
    except Exception:
        pass

    rcs_thread = threading.Thread(target=rcs_worker_loop, daemon=True)
    rcs_thread.start()

    hotkey_thread = threading.Thread(target=hotkey_listener_loop, daemon=True)
    hotkey_thread.start()

    aim_thread = threading.Thread(target=optical_aim_loop, daemon=True)
    aim_thread.start()

    hud = TransparentVisionHUD()
    hud.root.mainloop()

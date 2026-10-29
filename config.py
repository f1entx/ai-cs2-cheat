# Configuration for AI Vision Faceit Engine
import os

# Screen capture
SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080
FOV_SIZE = 320  # Capture region: 320x320 centered on screen
FPS_TARGET = 144

# Detection / Model
MODEL_PATH = "weights/cs2_yolov8n.onnx"  # Exported to TensorRT engine or ONNX
CONF_THRESHOLD = 0.45
IOU_THRESHOLD = 0.50
TARGET_CLASSES = [0, 1]  # 0: head, 1: body (CT/T player models)
HEAD_OFFSET_RATIO = 0.20  # Aim near top of bounding box if only body detected

# Aiming & Smoothing
AIM_KEY = 0x02  # Right mouse button (VK_RBUTTON) or 0x06 (VK_XBUTTON2)
AIM_FOV_RADIUS = 90  # Radius in pixels within FOV window where aim activates
SMOOTH_FACTOR_X = 0.35  # PID/Interpolation smoothing (lower = smoother)
SMOOTH_FACTOR_Y = 0.30
DEADZONE_PIXELS = 1.5

# Input Method: "KMBOX_NET", "KMBOX_BPRO", "ARDUINO", or "DIRECT"
# For Faceit AC, always use KMBOX_NET or ARDUINO hardware passthrough
INPUT_METHOD = "KMBOX_NET"

# KMBox Net UDP Configuration
KMBOX_NET_IP = "192.168.2.188"
KMBOX_NET_PORT = 1234
KMBOX_NET_UUID = "ABCD1234EF"

# KMBox B+ Pro / Arduino Serial Configuration
SERIAL_PORT = "COM3"
SERIAL_BAUDRATE = 115200

# ESP Mode: "OFF", "OVERLAY_WINDOW", "SECOND_MONITOR_WEB"
# Faceit AC scans local desktop compositions; SECOND_MONITOR_WEB or HDMI Fuser is safest
ESP_MODE = "SECOND_MONITOR_WEB"
WEB_STREAM_PORT = 5000

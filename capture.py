import numpy as np
import ctypes
from ctypes import wintypes
import config

try:
    import dxcam
    HAS_DXCAM = True
except ImportError:
    HAS_DXCAM = False

try:
    import mss
    HAS_MSS = True
except ImportError:
    HAS_MSS = False

class ScreenCaptureEngine:
    """
    Ultra-low latency DXGI Desktop Duplication capture.
    Captures only the center bounding region (FOV_SIZE x FOV_SIZE) around the crosshair
    to minimize memory copy overhead and maximize inference FPS.
    """
    def __init__(self):
        self.width = config.SCREEN_WIDTH
        self.height = config.SCREEN_HEIGHT
        self.fov = config.FOV_SIZE

        self.left = (self.width - self.fov) // 2
        self.top = (self.height - self.fov) // 2
        self.right = self.left + self.fov
        self.bottom = self.top + self.fov
        self.region = (self.left, self.top, self.right, self.bottom)

        self.camera = None
        self.mss_inst = None
        self._init_backend()

    def _init_backend(self):
        if HAS_DXCAM:
            try:
                self.camera = dxcam.create(device_idx=0, output_idx=0)
                self.camera.start(target_fps=config.FPS_TARGET, region=self.region)
                return
            except Exception as e:
                print(f"[!] DXCam init failed, fallback to MSS: {e}")

        if HAS_MSS:
            self.mss_inst = mss.mss()
            self.monitor = {
                "top": self.top,
                "left": self.left,
                "width": self.fov,
                "height": self.fov
            }

    def grab(self) -> np.ndarray:
        if self.camera is not None:
            frame = self.camera.get_latest_frame()
            if frame is not None:
                return frame

        if self.mss_inst is not None:
            raw = self.mss_inst.grab(self.monitor)
            # Convert BGRA to BGR
            img = np.array(raw)
            return img[:, :, :3]

        # Synthetic fallback if no display backend available
        return np.zeros((self.fov, self.fov, 3), dtype=np.uint8)

    def release(self):
        if self.camera is not None:
            self.camera.stop()
        if self.mss_inst is not None:
            self.mss_inst.close()

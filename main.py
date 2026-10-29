import time
import ctypes
import cv2
import config
from capture import ScreenCaptureEngine
from detector import TargetDetector
from mouse import HardwareMouseController
from aimbot import AimbotEngine
from esp_stream import start_esp_server, update_esp_frame

def is_key_down(vk_code: int) -> bool:
    return bool(ctypes.windll.user32.GetAsyncKeyState(vk_code) & 0x8000)

def main():
    print("==================================================")
    print("   AI Vision External Engine for Faceit AC        ")
    print("   - Non-memory invasive (Zero RPM / Zero WPM)    ")
    print("   - DXGI Screen Capture + YOLO ONNX/TensorRT     ")
    print(f"   - Input Passthrough: {config.INPUT_METHOD}     ")
    print("==================================================")

    # Initialize modules
    capture = ScreenCaptureEngine()
    detector = TargetDetector()
    mouse = HardwareMouseController()
    aimbot = AimbotEngine(mouse)

    if config.ESP_MODE == "SECOND_MONITOR_WEB":
        start_esp_server(config.WEB_STREAM_PORT)

    frame_count = 0
    start_time = time.time()

    try:
        while True:
            t0 = time.perf_counter()
            frame = capture.grab()

            if frame is None or frame.size == 0:
                time.sleep(0.001)
                continue

            # Run neural network inference
            targets = detector.infer(frame)

            # Trigger aim tracking when aim hotkey is held
            if is_key_down(config.AIM_KEY):
                aimbot.update(targets)

            # Update ESP web broadcast or preview
            if config.ESP_MODE == "SECOND_MONITOR_WEB":
                update_esp_frame(frame, targets)

            frame_count += 1
            if frame_count % 100 == 0:
                elapsed = time.time() - start_time
                fps = frame_count / elapsed
                print(f"[+] Performance: {fps:.1f} FPS | Detections: {len(targets)}")

            # Cap frame pacing if needed
            dt = time.perf_counter() - t0
            sleep_time = (1.0 / config.FPS_TARGET) - dt
            if sleep_time > 0:
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        print("\n[*] Stopping AI engine...")
    finally:
        capture.release()
        mouse.close()

if __name__ == "__main__":
    main()

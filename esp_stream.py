import cv2
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import config

latest_frame_jpeg = None
frame_lock = threading.Lock()

class MJPEGStreamHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global latest_frame_jpeg
        if self.path == '/stream.mjpg':
            self.send_response(200)
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=frame')
            self.end_headers()
            while True:
                with frame_lock:
                    if latest_frame_jpeg is None:
                        continue
                    data = latest_frame_jpeg
                try:
                    self.wfile.write(b'--frame\r\n')
                    self.send_header('Content-Type', 'image/jpeg')
                    self.send_header('Content-Length', str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    self.wfile.write(b'\r\n')
                except Exception:
                    break
        else:
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            html = f"""
            <html>
                <head><title>Faceit AI ESP Second Screen</title></head>
                <body style="background:#111; color:#eee; text-align:center; font-family:sans-serif;">
                    <h2>AI Visual Model ESP Feed (Second Screen / Mobile)</h2>
                    <img src="/stream.mjpg" style="border: 2px solid #00ff88; max-width: 640px;" />
                </body>
            </html>
            """
            self.wfile.write(html.encode())

    def log_message(self, format, *args):
        return

def start_esp_server(port=config.WEB_STREAM_PORT):
    server = HTTPServer(('0.0.0.0', port), MJPEGStreamHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    print(f"[*] ESP Web Stream started on http://localhost:{port}")

def update_esp_frame(frame, targets):
    global latest_frame_jpeg
    disp = frame.copy()
    center = config.FOV_SIZE // 2

    # Draw FOV Circle
    cv2.circle(disp, (center, center), config.AIM_FOV_RADIUS, (60, 60, 60), 1)

    # Draw Detections
    for t in targets:
        x1, y1, x2, y2 = t["box"]
        tx, ty = t["target_point"]
        cls_id = t["cls"]
        conf = t["conf"]

        color = (0, 0, 255) if cls_id == 0 else (0, 255, 0)
        label = f"Head: {conf:.2f}" if cls_id == 0 else f"Body: {conf:.2f}"

        cv2.rectangle(disp, (x1, y1), (x2, y2), color, 2)
        cv2.circle(disp, (tx, ty), 3, (0, 255, 255), -1)
        cv2.putText(disp, label, (x1, max(y1 - 6, 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)

    ret, encoded = cv2.imencode('.jpg', disp, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
    if ret:
        with frame_lock:
            latest_frame_jpeg = encoded.tobytes()

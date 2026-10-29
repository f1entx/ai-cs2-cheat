import socket
import serial
import time
import math
import ctypes
import config

class HardwareMouseController:
    """
    Hardware mouse input emulation.
    Faceit AC hooks MouClassServiceCallback and blocks synthetic Ring 3 inputs (SendInput/mouse_event).
    Physical microcontroller hardware (KMBox Net, KMBox B+, Arduino Leonardo HID) bypasses driver hooks.
    """
    def __init__(self):
        self.method = config.INPUT_METHOD
        self.sock = None
        self.serial_conn = None
        self._init_hardware()

    def _init_hardware(self):
        if self.method == "KMBOX_NET":
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.sock.settimeout(0.01)
                self.addr = (config.KMBOX_NET_IP, config.KMBOX_NET_PORT)
                # Handshake packet for KMBox Net
                handshake = f"connect {config.KMBOX_NET_UUID}\r\n".encode()
                self.sock.sendto(handshake, self.addr)
            except Exception as e:
                print(f"[!] KMBox Net init warning: {e}")

        elif self.method in ["KMBOX_BPRO", "ARDUINO"]:
            try:
                self.serial_conn = serial.Serial(
                    port=config.SERIAL_PORT,
                    baudrate=config.SERIAL_BAUDRATE,
                    timeout=0.005
                )
                time.sleep(1.0)
            except Exception as e:
                print(f"[!] Serial device init warning: {e}")

    def move(self, dx: int, dy: int):
        if dx == 0 and dy == 0:
            return

        if self.method == "KMBOX_NET" and self.sock:
            # KMBox Net binary packet format: cmd_type (4B), dx (4B), dy (4B)
            # Standard ASCII command protocol support:
            cmd = f"km.move({int(dx)},{int(dy)})\r\n".encode()
            try:
                self.sock.sendto(cmd, self.addr)
            except Exception:
                pass

        elif self.method in ["KMBOX_BPRO", "ARDUINO"] and self.serial_conn:
            # Arduino / KMBox B+ serial packet: "M<dx>,<dy>\n"
            msg = f"M{int(dx)},{int(dy)}\n".encode()
            try:
                self.serial_conn.write(msg)
            except Exception:
                pass

        elif self.method == "DIRECT":
            # Fallback for testing on offline servers without anti-cheat active
            ctypes.windll.user32.mouse_event(0x0001, int(dx), int(dy), 0, 0)

    def close(self):
        if self.sock:
            self.sock.close()
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()

import time
import math
import serial
import serial.tools.list_ports

class PicoMouseController:
    """
    High-throughput USB HID Serial Driver for Raspberry Pi Pico (RP2040).
    Dispatches movement and click reports directly over USB-CDC to the Pico microcontroller.
    """
    def __init__(self, port: str = None, baudrate: int = 115200):
        self.port = port
        self.baudrate = baudrate
        self.serial_conn = None
        self.connect()

    def find_pico_port(self) -> str:
        """Automatically scans COM ports for Raspberry Pi Pico or USB Serial devices."""
        ports = list(serial.tools.list_ports.comports())
        for p in ports:
            desc = p.description.lower()
            hwid = p.hwid.lower()
            if "pico" in desc or "2e8a" in hwid or "usb serial" in desc:
                return p.device
        return "COM3"

    def connect(self):
        if not self.port:
            self.port = self.find_pico_port()

        try:
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=0.002,
                write_timeout=0.002
            )
            time.sleep(0.5)
            print(f"[+] Connected to Raspberry Pi Pico on {self.port}")
        except Exception as e:
            print(f"[!] Warning: Could not open Pico on {self.port}: {e}")
            self.serial_conn = None

    def move(self, dx: int, dy: int):
        if self.serial_conn is None or (dx == 0 and dy == 0):
            return

        cmd = f"M {int(dx)} {int(dy)}\n".encode("ascii")
        try:
            self.serial_conn.write(cmd)
        except Exception:
            pass

    def click(self, button: int = 1, state: int = 1):
        if self.serial_conn is None:
            return

        cmd = f"C {int(button)} {int(state)}\n".encode("ascii")
        try:
            self.serial_conn.write(cmd)
        except Exception:
            pass

    def trigger_shot(self, hold_ms: float = 25.0):
        self.click(button=1, state=1)
        time.sleep(hold_ms / 1000.0)
        self.click(button=1, state=0)

    def close(self):
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()

if __name__ == "__main__":
    pico = PicoMouseController()
    pico.move(10, 10)
    pico.trigger_shot()

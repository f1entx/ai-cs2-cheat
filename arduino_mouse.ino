# Arduino Leonardo / SparkFun Pro Micro (ATmega32U4)
# Hardware USB HID Mouse Passthrough for Faceit AC
# Connects to PC via USB as a genuine composite HID mouse device

#include <Mouse.h>

void setup() {
  Serial.begin(115200);
  Serial.setTimeout(1);
  Mouse.begin();
}

void loop() {
  if (Serial.available() > 0) {
    char header = Serial.read();
    if (header == 'M') {
      int dx = Serial.parseInt();
      int dy = Serial.parseInt();
      // Read until newline
      while (Serial.available() > 0 && Serial.peek() != '\n') {
        Serial.read();
      }
      if (Serial.peek() == '\n') Serial.read();

      // Clamp values to signed 8-bit range
      dx = constrain(dx, -127, 127);
      dy = constrain(dy, -127, 127);

      Mouse.move(dx, dy, 0);
    }
  }
}

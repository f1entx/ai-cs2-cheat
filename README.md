# AI Vision Optical Engine (Zero-Memory Computer Vision Pipeline)
A high-performance, real-time computer vision and neural target tracking pipeline for FPS environments (Counter-Strike 2). Engineered specifically as a non-invasive, purely optical external system.
---
## Technical Architecture & Core Principles
Unlike traditional game utilities that interact with process memory or internal game structures, this engine operates strictly as an external visual observer:
- Zero Memory Read (Zero RPM): Never calls OpenProcess, ReadProcessMemory, or creates handles to the target game executable. Game memory remains 100% untouched.
- Zero Memory Write (Zero WPM): Never injects DLLs, hooks game engine functions, patches instructions, or modifies VTables.
- Pure Optical Feed: Operates entirely on raw screen pixels obtained through hardware-accelerated Windows Graphics/GDI capture pipelines.
- Sub-10ms Inference: Employs an ultra-lightweight YOLO neural network running locally via ONNX Runtime / DirectML with Tensor-level acceleration.
- Modular Hardware Input: Supports both native user-mode input and physical hardware passthrough (KMBox Net, Arduino, Raspberry Pi Pico) to maintain physical USB separation.
---
## System Overview

  

[ Screen Viewport ]
|
v
[ NativeScreenGrabber ]  --> Low-latency 320x320 center crop (180+ FPS)
|
v
[ YOLO Neural Model ]   --> Real-time object detection (<7ms latency)
|
v
[ Target Tracking Core] --> Humanized smoothing, deadzone & PID correction
|
v
[ Input Dispatcher ]    --> Hardware USB HID / Direct Input


  
---
## Key Features
- High-Velocity Screen Capture: Direct Win32 GDI Desktop Duplication delivering consistent 180+ FPS capture rates with minimal CPU overhead.
- Neural Target Identification: ONNX Runtime execution engine detecting player models and head regions in real time.
- Intelligent Tracking & PID Smoothing: Smooth coordinate interpolation preventing sharp robotic snapping and emulating natural human aim kinematics.
- Dynamic Recoil Control System (RCS): Dynamic recoil compensation pattern with float-level sub-pixel accumulation.
- Optical Trigger Mechanism: Instantaneous target intersection triggerbot with millisecond-precision actuation timing.
- Modern Dark Control Panel: Integrated Tkinter TTK GUI dashboard providing real-time slider adjustments, hotkey bindings, and telemetry (FPS, target count, engine status).
---
## Project Structure

  

├── gui_panel.py          # Modern Dark GUI dashboard with live configuration sync
├── headless_aim_rcs.py   # Pure headless engine (zero window, zero cursor capture)
├── local_aim_esp.py      # Optional transparent HUD/ESP overlay with click-through
├── config.json           # Real-time persistent configuration parameters
├── yolov8n.onnx          # Optimized 320x320 neural network weights
├── start.bat             # Master console launcher menu
└── pico_mouse.py         # Hardware serial driver for Raspberry Pi Pico RP2040


  
---
## Getting Started
### Prerequisites
- Windows 10 / 11 (64-bit)
- Python 3.10 or 3.11
- DirectX 12 / DirectML compatible GPU or multi-core CPU
### Installation
1. Clone the repository:
```bash
git clone https://github.com/your-username/ai-vision-engine.git
cd ai-vision-engine

  

  
Install dependencies:

  

  
bash
pip install -r requirements.txt

  

  
Launch the engine:

  

  
bash
start.bat

  

  
Technical Disclaimer

  

This software is developed strictly for educational, academic, and computer vision research purposes. It demonstrates the capabilities of modern lightweight neural networks running real-time object detection over live graphical viewports without software memory hooks.

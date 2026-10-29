import math
import random
import config

class PIDController:
    """
    PID Smoothing controller for human-like mouse micro-adjustments
    Prevents linear snap detection by Faceit server-side behavioral analysis.
    """
    def __init__(self, kp: float, ki: float, kd: float):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.prev_error = 0.0
        self.integral = 0.0

    def compute(self, error: float) -> float:
        self.integral += error
        # Clamp integral windup
        self.integral = max(min(self.integral, 20.0), -20.0)
        derivative = error - self.prev_error
        self.prev_error = error
        return self.kp * error + self.ki * self.integral + self.kd * derivative

    def reset(self):
        self.prev_error = 0.0
        self.integral = 0.0

class AimbotEngine:
    def __init__(self, mouse_controller):
        self.mouse = mouse_controller
        self.fov_center = config.FOV_SIZE // 2
        self.pid_x = PIDController(kp=config.SMOOTH_FACTOR_X, ki=0.01, kd=0.05)
        self.pid_y = PIDController(kp=config.SMOOTH_FACTOR_Y, ki=0.01, kd=0.05)

    def select_best_target(self, targets):
        """
        Finds the closest target to screen center (crosshair).
        Prefers head over body when distance difference is minimal.
        """
        if not targets:
            return None

        best_target = None
        min_dist = float('inf')

        for t in targets:
            tx, ty = t["target_point"]
            dist = math.hypot(tx - self.fov_center, ty - self.fov_center)

            if dist > config.AIM_FOV_RADIUS:
                continue

            # Bias towards head detections
            if t["cls"] == 0:
                dist *= 0.75

            if dist < min_dist:
                min_dist = dist
                best_target = t

        return best_target

    def update(self, targets):
        target = self.select_best_target(targets)
        if target is None:
            self.pid_x.reset()
            self.pid_y.reset()
            return

        tx, ty = target["target_point"]
        raw_dx = tx - self.fov_center
        raw_dy = ty - self.fov_center

        # Check deadzone to prevent micro-jitter
        if abs(raw_dx) < config.DEADZONE_PIXELS and abs(raw_dy) < config.DEADZONE_PIXELS:
            return

        # PID smooth calculation
        step_x = self.pid_x.compute(raw_dx)
        step_y = self.pid_y.compute(raw_dy)

        # Micro-jitter / humanizer variance
        jitter_x = (random.random() - 0.5) * 0.4
        jitter_y = (random.random() - 0.5) * 0.4

        final_dx = int(round(step_x + jitter_x))
        final_dy = int(round(step_y + jitter_y))

        self.mouse.move(final_dx, final_dy)

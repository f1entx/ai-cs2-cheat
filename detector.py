import numpy as np
import cv2
import config

try:
    import onnxruntime as ort
    HAS_ORT = True
except ImportError:
    HAS_ORT = False

class TargetDetector:
    """
    YOLO ONNX Runtime / TensorRT Inference Engine.
    Executes detection over cropped screen frame, returning target bounding boxes
    and center coordinates relative to screen crosshair.
    """
    def __init__(self, model_path: str = config.MODEL_PATH):
        self.model_path = model_path
        self.session = None
        self.input_name = None
        self.input_shape = (1, 3, config.FOV_SIZE, config.FOV_SIZE)
        self._init_session()

    def _init_session(self):
        if not HAS_ORT:
            print("[!] onnxruntime not found. Using CPU fallback simulation.")
            return

        providers = ['CUDAExecutionProvider', 'DmlExecutionProvider', 'CPUExecutionProvider']
        so = ort.SessionOptions()
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        try:
            self.session = ort.InferenceSession(self.model_path, so, providers=providers)
            self.input_name = self.session.get_inputs()[0].name
        except Exception as e:
            print(f"[!] Model session load failed: {e}. Running in stub mode.")

    def preprocess(self, img: np.ndarray) -> np.ndarray:
        # Resize to model input shape if not matching
        h, w = img.shape[:2]
        target_w, target_h = config.FOV_SIZE, config.FOV_SIZE
        if (w, h) != (target_w, target_h):
            resized = cv2.resize(img, (target_w, target_h))
        else:
            resized = img

        # BGR to RGB, normalize [0, 1], HWC to CHW
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        normalized = rgb.astype(np.float32) / 255.0
        chw = np.transpose(normalized, (2, 0, 1))
        batch = np.expand_dims(chw, axis=0)
        return batch

    def infer(self, frame: np.ndarray):
        """
        Runs inference and returns list of targets:
        [ {'box': (x1, y1, x2, y2), 'cls': id, 'conf': score, 'target_point': (x, y)}, ... ]
        Coordinates are relative to the FOV crop.
        """
        if self.session is None:
            return []

        inp = self.preprocess(frame)
        outputs = self.session.run(None, {self.input_name: inp})
        raw = outputs[0]  # shape: [1, 4 + num_classes, num_anchors]

        # Post-process YOLO outputs
        predictions = np.squeeze(raw)
        if predictions.shape[0] < predictions.shape[1]:
            predictions = predictions.T

        boxes = []
        confidences = []
        class_ids = []

        for row in predictions:
            scores = row[4:]
            class_id = int(np.argmax(scores))
            confidence = float(scores[class_id])

            if confidence >= config.CONF_THRESHOLD and class_id in config.TARGET_CLASSES:
                cx, cy, w, h = row[0:4]
                x1 = int(cx - w / 2)
                y1 = int(cy - h / 2)
                boxes.append([x1, y1, int(w), int(h)])
                confidences.append(confidence)
                class_ids.append(class_id)

        indices = cv2.dnn.NMSBoxes(boxes, confidences, config.CONF_THRESHOLD, config.IOU_THRESHOLD)
        targets = []

        if len(indices) > 0:
            for idx in indices.flatten():
                bx, by, bw, bh = boxes[idx]
                cls_id = class_ids[idx]
                score = confidences[idx]

                # If class is head (class 0), aim at center of head box
                # If class is body (class 1), aim at upper third (head offset)
                if cls_id == 0:
                    tx = bx + bw // 2
                    ty = by + bh // 2
                else:
                    tx = bx + bw // 2
                    ty = by + int(bh * config.HEAD_OFFSET_RATIO)

                targets.append({
                    "box": (bx, by, bx + bw, by + bh),
                    "cls": cls_id,
                    "conf": score,
                    "target_point": (tx, ty)
                })

        return targets

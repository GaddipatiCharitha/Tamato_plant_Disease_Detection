import os
from io import BytesIO
from collections import deque

import numpy as np
from PIL import Image


def load_labels(path: str = "labels.txt") -> list:
    """Load labels from a text file, one label per line.

    Returns an empty list if the file doesn't exist.
    """
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f.readlines() if line.strip()]


def preprocess_image(image_bytes: bytes,
                     target_size: tuple = (224, 224),
                     dtype: np.dtype = np.float32,
                     quantization: tuple | None = None) -> np.ndarray:
    """Convert image bytes -> model input tensor.

    - `image_bytes` can be raw JPEG/PNG bytes.
    - `target_size` is (width, height).
    - If `dtype` is float32, image is normalized to [-1, 1] (MobileNetV2 style).
    - If `dtype` is integer and `quantization`=(scale, zero_point) is provided,
      the image will be quantized accordingly.

    Returns a numpy array shaped (1, H, W, 3) with the requested dtype.
    """
    img = Image.open(BytesIO(image_bytes)).convert("RGB")
    img = img.resize(target_size, Image.BILINEAR)
    arr = np.asarray(img).astype(np.float32)

    # MobileNetV2 expects inputs in [-1, 1]
    if np.issubdtype(dtype, np.floating):
        arr = (arr / 127.5) - 1.0
        out = arr.astype(dtype)
    else:
        # integer dtype path (e.g., uint8) with optional quantization
        if quantization is not None:
            scale, zero_point = quantization
            if scale == 0:
                # avoid division by zero
                out = arr.astype(dtype)
            else:
                q = (arr / scale) + zero_point
                q = np.clip(np.round(q), np.iinfo(dtype).min, np.iinfo(dtype).max)
                out = q.astype(dtype)
        else:
            out = arr.astype(dtype)

    out = np.expand_dims(out, axis=0)
    return out


def softmax(x: np.ndarray) -> np.ndarray:
    e_x = np.exp(x - np.max(x))
    return e_x / np.sum(e_x, axis=-1, keepdims=True)


class PredictionSmoother:
    """Smooth raw probability vectors by averaging over a short window.

    Usage (compatible with `app.py`): `sm_label, sm_conf = smoother.update(probs, labels)`
    """
    def __init__(self, window_size: int = 5):
        self.window_size = window_size
        self.buffer: deque = deque(maxlen=window_size)

    def update(self, probs: np.ndarray, labels: list) -> tuple:
        """Add `probs` (1D array) to buffer and return (label, confidence).

        Returns the label string and the confidence (0..1) from the averaged probs.
        """
        probs = np.asarray(probs).astype(np.float32).reshape(-1)
        self.buffer.append(probs)
        avg = np.mean(np.stack(list(self.buffer), axis=0), axis=0)
        idx = int(np.argmax(avg))
        label = labels[idx] if idx < len(labels) else str(idx)
        conf = float(avg[idx])
        return label, conf

    def reset(self) -> None:
        self.buffer.clear()

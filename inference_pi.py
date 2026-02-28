import numpy as np
import cv2
import os
import sys
from collections import deque

try:
    import tflite_runtime.interpreter as tflite
except ImportError:
    print("tflite_runtime not found. Install with: pip install tflite-runtime")
    sys.exit(1)

def load_labels(labels_path='labels.txt'):
    """Load class labels from labels.txt file"""
    labels = []
    with open(labels_path, 'r') as f:
        labels = [line.strip() for line in f.readlines()]
    return labels

def preprocess_image(frame, target_size=(224, 224)):
    """Preprocess image for MobileNetV2 inference"""
    img_resized = cv2.resize(frame, target_size, interpolation=cv2.INTER_LINEAR)
    img_normalized = img_resized.astype(np.float32) / 127.5 - 1.0
    img_expanded = np.expand_dims(img_normalized, axis=0)
    return img_expanded.astype(np.uint8)

def softmax(x):
    """Apply softmax to get probabilities"""
    e_x = np.exp(x - np.max(x))
    return e_x / e_x.sum(axis=-1, keepdims=True)

class PredictionSmoother:
    """Smoothing predictions using majority vote buffer"""
    def __init__(self, buffer_size=5):
        self.buffer = deque(maxlen=buffer_size)
    
    def add_prediction(self, class_id):
        """Add prediction to buffer"""
        self.buffer.append(class_id)
    
    def get_smoothed_prediction(self):
        """Get smoothed prediction using majority voting"""
        if len(self.buffer) == 0:
            return None
        from collections import Counter
        counts = Counter(self.buffer)
        return counts.most_common(1)[0][0]

model_path = 'model/tomato_mobilenet_int8.tflite'

if not os.path.exists(model_path):
    print(f"Error: Model not found at {model_path}")
    sys.exit(1)

if not os.path.exists('labels.txt'):
    print("Error: labels.txt not found")
    sys.exit(1)

interpreter = tflite.Interpreter(model_path=model_path)
interpreter.allocate_tensors()

input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()

labels = load_labels('labels.txt')
smoother = PredictionSmoother(buffer_size=5)

cap = cv2.VideoCapture(0)

if not cap.isOpened():
    print("Error: Could not open camera")
    sys.exit(1)

cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
cap.set(cv2.CAP_PROP_FPS, 15)

frame_count = 0
inference_interval = 5

print("Starting inference... Press 'q' to quit")
print(f"Classes: {', '.join(labels)}")

while True:
    ret, frame = cap.read()
    if not ret:
        break
    
    frame_count += 1
    
    if frame_count % inference_interval != 0:
        cv2.imshow('Tomato Disease Detection', frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
        continue
    
    preprocessed = preprocess_image(frame)
    
    interpreter.set_tensor(input_details[0]['index'], preprocessed)
    interpreter.invoke()
    output_data = interpreter.get_tensor(output_details[0]['index'])
    
    output_float = output_data.astype(np.float32)
    output_float = (output_float - 128) / 128.0
    
    probabilities = softmax(output_float[0])
    class_id = np.argmax(probabilities)
    confidence = float(probabilities[class_id])
    
    smoother.add_prediction(class_id)
    smoothed_class_id = smoother.get_smoothed_prediction()
    
    if smoothed_class_id is not None:
        disease_name = labels[smoothed_class_id]
        display_confidence = float(probabilities[smoothed_class_id])
    else:
        disease_name = labels[class_id]
        display_confidence = confidence
    
    display_text = f"{disease_name}: {display_confidence:.2%}"
    
    cv2.putText(
        frame,
        display_text,
        (10, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (0, 255, 0),
        2
    )
    
    cv2.imshow('Tomato Disease Detection', frame)
    
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
print("Inference stopped")

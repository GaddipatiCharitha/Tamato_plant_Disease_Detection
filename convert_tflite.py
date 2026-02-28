import tensorflow as tf
import numpy as np
import os
from tensorflow.keras.preprocessing.image import ImageDataGenerator

def representative_dataset_gen():
    dataset_path = 'dataset/train'
    datagen = ImageDataGenerator(rescale=1.0/255.0)
    
    batch_size = 10
    batch_count = 0
    max_batches = 100
    
    for batch in datagen.flow_from_directory(
        dataset_path,
        target_size=(224, 224),
        batch_size=batch_size,
        class_mode='categorical',
        shuffle=True
    ):
        if batch_count >= max_batches:
            break
        
        yield [tf.convert_to_tensor(batch[0], dtype=tf.float32)]
        batch_count += 1

model_path = 'model/tomato_model'
output_tflite = 'model/tomato_mobilenet_int8.tflite'

print(f"Loading SavedModel from {model_path}...")
concrete_func = tf.saved_model.load(model_path).signatures[
    tf.saved_model.DEFAULT_SERVING_SIGNATURE_DEF_KEY
]

def representative_data():
    for data in representative_dataset_gen():
        yield data

print("Converting to TFLite with INT8 quantization...")
converter = tf.lite.TFLiteConverter.from_saved_model(model_path)
converter.optimizations = [tf.lite.Optimize.DEFAULT]
converter.representative_dataset = representative_data
converter.target_spec.supported_ops = [
    tf.lite.OpsSet.TFLITE_BUILTINS_INT8
]
converter.inference_input_type = tf.uint8
converter.inference_output_type = tf.uint8

tflite_model = converter.convert()

with open(output_tflite, 'wb') as f:
    f.write(tflite_model)

print(f"TFLite model saved to {output_tflite}")
print(f"Model size: {len(tflite_model) / (1024 * 1024):.2f} MB")

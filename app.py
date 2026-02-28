from fastapi import FastAPI, Request, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

import asyncio
import numpy as np
import base64
import os
import time
from datetime import datetime

from database import (
    init_db,
    log_prediction,
    update_feedback,
    get_stats,
    get_history,
    export_csv,
    get_detailed_stats,
    get_model_performance,
)

from utils import load_labels, preprocess_image, softmax, PredictionSmoother

# ================= PATHS =================

APP_ROOT = os.path.dirname(__file__)

MODEL_PATH = os.path.join(APP_ROOT, "model", "tomato_mobilenet_int8.tflite")
LABELS_PATH = os.path.join(APP_ROOT, "labels.txt")
PREDICTIONS_DIR = os.path.join(APP_ROOT, "predictions")
DB_PATH = os.path.join(APP_ROOT, "predictions.db")

MODEL_VERSION = "v1.0-tflite-int8"

# ================= APP =================

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static folders
app.mount("/static", StaticFiles(directory=os.path.join(APP_ROOT, "static")), name="static")
app.mount("/predictions", StaticFiles(directory=PREDICTIONS_DIR), name="predictions")

templates = Jinja2Templates(directory=os.path.join(APP_ROOT, "templates"))

# ================= GLOBALS =================

interpreter = None
input_details = None
output_details = None
labels = []
smoother = None
DEMO_MODE = False


# ================= STARTUP =================

@app.on_event("startup")
async def startup_event():
    global interpreter, input_details, output_details, labels, smoother, DEMO_MODE

    os.makedirs(PREDICTIONS_DIR, exist_ok=True)
    init_db(DB_PATH)

    labels = load_labels(LABELS_PATH)

    if not labels:
        labels = ["Healthy", "Early_blight", "Late_blight"]

    if not os.path.exists(MODEL_PATH):
        DEMO_MODE = True
        interpreter = None
        input_details = {"shape": [1, 224, 224, 3], "dtype": np.float32, "index": 0}
        output_details = {"index": 0, "quantization": (0.0, 0)}

    else:
        try:
            import tflite_runtime.interpreter as tflite_rt
            Interpreter = tflite_rt.Interpreter
        except:
            from tensorflow.lite import Interpreter

        interpreter = Interpreter(model_path=MODEL_PATH)
        interpreter.allocate_tensors()
        input_details = interpreter.get_input_details()[0]
        output_details = interpreter.get_output_details()[0]

    smoother = PredictionSmoother(window_size=5)


# ================= TEMPLATE ROUTES =================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "title": "Tomato Detector", "page": "home"},
    )


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "title": "Dashboard", "page": "dashboard"},
    )


@app.get("/history-page", response_class=HTMLResponse)
async def history_page(request: Request):
    return templates.TemplateResponse(
        "history.html",
        {"request": request, "title": "History", "page": "history"},
    )


@app.get("/analytics", response_class=HTMLResponse)
async def analytics_page(request: Request):
    return templates.TemplateResponse(
        "analytics.html",
        {"request": request, "title": "Analytics", "page": "analytics"},
    )


@app.get("/model", response_class=HTMLResponse)
async def model_page(request: Request):
    return templates.TemplateResponse(
        "model.html",
        {"request": request, "title": "Model Info", "page": "model"},
    )


@app.get("/about", response_class=HTMLResponse)
async def about_page(request: Request):
    return templates.TemplateResponse(
        "about.html",
        {"request": request, "title": "About", "page": "about"},
    )


# ================= INFERENCE =================

async def run_inference(image_bytes: bytes):

    start = time.perf_counter()

    if DEMO_MODE or interpreter is None:
        probs = softmax(np.random.rand(len(labels)))
        return probs, (time.perf_counter() - start) * 1000

    target_h = input_details["shape"][1]
    target_w = input_details["shape"][2]
    dtype = np.dtype(input_details["dtype"])

    input_data = preprocess_image(
        image_bytes,
        target_size=(target_w, target_h),
        dtype=dtype,
        quantization=input_details.get("quantization", (0.0, 0)),
    )

    loop = asyncio.get_running_loop()

    def invoke():
        interpreter.set_tensor(input_details["index"], input_data)
        interpreter.invoke()
        output = interpreter.get_tensor(output_details["index"])
        return output.reshape(-1).astype(np.float32)

    output = await loop.run_in_executor(None, invoke)

    probs = softmax(output)
    inference_time = (time.perf_counter() - start) * 1000

    return probs, inference_time


# ================= PREDICT =================

@app.post("/predict")
async def predict(file: UploadFile = File(...)):
    content = await file.read()

    probs, inference_time = await run_inference(content)

    idx = int(np.argmax(probs))
    label = labels[idx]

    sm_label, sm_conf = smoother.update(probs, labels)

    filename = f"pred_{int(time.time()*1000)}.jpg"
    image_path = os.path.join(PREDICTIONS_DIR, filename)

    with open(image_path, "wb") as f:
        f.write(content)

    rec_id = log_prediction(
        DB_PATH,
        image_path,
        label,
        float(sm_conf),
        float(inference_time),
        datetime.utcnow(),
    )

    return JSONResponse({
        "id": rec_id,
        "disease": sm_label,
        "confidence": round(sm_conf * 100, 2),
        "inference_time_ms": round(inference_time, 2),
        "model_version": MODEL_VERSION,
        "low_confidence": sm_conf < 0.4,
    })


@app.post("/predict-frame")
async def predict_frame(payload: dict):
    """Predict from base64 encoded image frame (camera capture)."""
    try:
        frame_b64 = payload.get("frame")
        if not frame_b64:
            raise HTTPException(400, "No frame data")
        
        # Remove data: URL prefix if present
        if "," in frame_b64:
            frame_b64 = frame_b64.split(",", 1)[1]
        
        content = base64.b64decode(frame_b64)
        probs, inference_time = await run_inference(content)

        idx = int(np.argmax(probs))
        label = labels[idx]

        sm_label, sm_conf = smoother.update(probs, labels)

        filename = f"pred_{int(time.time()*1000)}.jpg"
        image_path = os.path.join(PREDICTIONS_DIR, filename)

        with open(image_path, "wb") as f:
            f.write(content)

        rec_id = log_prediction(
            DB_PATH,
            image_path,
            label,
            float(sm_conf),
            float(inference_time),
            datetime.utcnow(),
        )

        return JSONResponse({
            "id": rec_id,
            "disease": sm_label,
            "confidence": round(sm_conf * 100, 2),
            "inference_time_ms": round(inference_time, 2),
            "model_version": MODEL_VERSION,
            "low_confidence": sm_conf < 0.4,
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


# ================= FEEDBACK =================

@app.post("/feedback/{pred_id}")
async def feedback(pred_id: int, payload: dict):

    true_label = payload.get("true_label")
    if not true_label:
        raise HTTPException(400, "true_label required")

    update_feedback(DB_PATH, pred_id, true_label, 1)

    stats = get_stats(DB_PATH)
    return {"status": "ok", "accuracy": stats.get("accuracy")}


# ================= APIs =================

@app.get("/stats")
async def stats_api():
    s = get_stats(DB_PATH)
    s["model_version"] = MODEL_VERSION
    return s


@app.get("/detailed-stats")
async def detailed_stats_api():
    """Get detailed analytics including class-wise accuracy and confidence breakdown"""
    return get_detailed_stats(DB_PATH)


@app.get("/model-performance")
async def model_performance_api():
    """Get comprehensive model performance metrics"""
    return get_model_performance(DB_PATH)


@app.get("/model-info")
async def model_info_api():
    """Get model information and specifications"""
    global interpreter, input_details, output_details, DEMO_MODE
    
    input_shape = input_details.get("shape", [1, 224, 224, 3]) if input_details else [1, 224, 224, 3]
    quantized = False
    quant_scale = 0.0
    quant_zero_point = 0
    
    if output_details and "quantization" in output_details:
        quant_info = output_details.get("quantization", (0.0, 0))
        quant_scale = quant_info[0] if isinstance(quant_info, (list, tuple)) else 0.0
        quant_zero_point = quant_info[1] if isinstance(quant_info, (list, tuple)) else 0
        quantized = quant_scale > 0
    
    return {
        "model_version": MODEL_VERSION,
        "architecture": "MobileNetV2",
        "format": "TensorFlow Lite (INT8 Quantized)",
        "input_shape": input_shape,
        "quantized": quantized,
        "quantization_scale": quant_scale,
        "quantization_zero_point": quant_zero_point,
        "dataset": "PlantVillage Tomato Disease Dataset",
        "classes": labels,
        "optimization": "Edge CPU Inference for Raspberry Pi 4",
        "inference_engine": "TensorFlow Lite Runtime" if DEMO_MODE is False else "Demo Mode (Random)",
        "demo_mode": DEMO_MODE
    }


@app.get("/history")
async def history_api():
    return get_history(DB_PATH, limit=200)


@app.get("/export/csv")
async def export_csv_route():
    return {"csv": export_csv(DB_PATH)}


# ================= RUN =================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000)
import sqlite3
import csv
from datetime import datetime
from typing import List, Dict, Any


def init_db(db_path: str):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute('''
    CREATE TABLE IF NOT EXISTS PredictionLog(
        id INTEGER PRIMARY KEY,
        image_path TEXT,
        predicted_label TEXT,
        confidence REAL,
        true_label TEXT,
        is_correct INTEGER,
        inference_time REAL,
        created_at TIMESTAMP
    )
    ''')
    conn.commit()
    conn.close()


def log_prediction(db_path: str, image_path: str, predicted_label: str, confidence: float, inference_time: float, created_at: datetime) -> int:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO PredictionLog (image_path, predicted_label, confidence, true_label, is_correct, inference_time, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (image_path, predicted_label, confidence, None, None, inference_time, created_at.isoformat()))
    conn.commit()
    rec_id = cur.lastrowid
    conn.close()
    return rec_id


def update_feedback(db_path: str, rec_id: int, true_label: str, is_correct: int):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute('''
        UPDATE PredictionLog SET true_label = ?, is_correct = ? WHERE id = ?
    ''', (true_label, int(is_correct), rec_id))
    conn.commit()
    conn.close()


def get_history(db_path: str, limit: int = 100) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute('SELECT id, image_path, predicted_label, confidence, true_label, is_correct, inference_time, created_at FROM PredictionLog ORDER BY created_at DESC LIMIT ?', (limit,))
    rows = cur.fetchall()
    conn.close()
    cols = ["id", "image_path", "predicted_label", "confidence", "true_label", "is_correct", "inference_time", "created_at"]
    return [dict(zip(cols, r)) for r in rows]


def get_stats(db_path: str) -> Dict[str, Any]:
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM PredictionLog')
    total = cur.fetchone()[0]
    cur.execute('SELECT AVG(confidence) FROM PredictionLog')
    avg_conf = cur.fetchone()[0] or 0.0
    cur.execute('SELECT SUM(is_correct), COUNT(is_correct) FROM PredictionLog WHERE is_correct IS NOT NULL')
    row = cur.fetchone()
    correct = row[0] or 0
    counted = row[1] or 0
    accuracy = (correct / counted * 100.0) if counted > 0 else None

    # class distribution
    cur.execute('SELECT predicted_label, COUNT(*) FROM PredictionLog GROUP BY predicted_label')
    dist = {r[0]: r[1] for r in cur.fetchall()}

    # health score heuristic: accuracy weighted and avg confidence
    if accuracy is None:
        health_score = int(min(100, avg_conf * 100))
    else:
        health_score = int((accuracy * 0.7) + (min(100, avg_conf * 100) * 0.3))

    conn.close()
    return {
        "total_predictions": total,
        "accuracy": accuracy if accuracy is not None else None,
        "avg_confidence": float(avg_conf),
        "health_score": health_score,
        "class_distribution": dist
    }


def get_detailed_stats(db_path: str) -> Dict[str, Any]:
    """Get comprehensive analytics including class-wise accuracy and confidence breakdown"""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    # Total with feedback
    cur.execute('SELECT COUNT(*) FROM PredictionLog WHERE true_label IS NOT NULL')
    total_with_feedback = cur.fetchone()[0]
    
    # Class-wise accuracy
    cur.execute('''
        SELECT predicted_label, 
               COUNT(*) as total,
               SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) as correct,
               AVG(confidence) as avg_conf
        FROM PredictionLog 
        WHERE true_label IS NOT NULL
        GROUP BY predicted_label
        ORDER BY total DESC
    ''')
    class_stats = []
    for row in cur.fetchall():
        class_name, total, correct, avg_conf = row
        correct = correct or 0
        accuracy = (correct / total * 100) if total > 0 else 0
        class_stats.append({
            "class": class_name,
            "total": total,
            "correct": correct,
            "accuracy": round(accuracy, 2),
            "avg_confidence": round(avg_conf or 0, 4)
        })
    
    # Inference time stats
    cur.execute('SELECT MIN(inference_time), MAX(inference_time), AVG(inference_time) FROM PredictionLog')
    inf_row = cur.fetchone()
    min_inf = inf_row[0] or 0
    max_inf = inf_row[1] or 0
    avg_inf = inf_row[2] or 0
    
    # Confidence distribution
    cur.execute('''
        SELECT 
            SUM(CASE WHEN confidence >= 0.9 THEN 1 ELSE 0 END) as high,
            SUM(CASE WHEN confidence >= 0.7 AND confidence < 0.9 THEN 1 ELSE 0 END) as medium,
            SUM(CASE WHEN confidence < 0.7 THEN 1 ELSE 0 END) as low
        FROM PredictionLog
    ''')
    conf_row = cur.fetchone()
    
    conn.close()
    return {
        "summary": {
            "total_with_feedback": total_with_feedback,
            "inference_time_ms": {
                "min": round(min_inf, 2),
                "max": round(max_inf, 2),
                "avg": round(avg_inf, 2)
            },
            "confidence_distribution": {
                "high_90_to_100": conf_row[0] or 0,
                "medium_70_to_90": conf_row[1] or 0,
                "low_below_70": conf_row[2] or 0
            }
        },
        "class_statistics": class_stats
    }


def get_model_performance(db_path: str) -> Dict[str, Any]:
    """Get model performance metrics"""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    cur.execute('SELECT COUNT(*) FROM PredictionLog')
    total_predictions = cur.fetchone()[0]
    
    cur.execute('SELECT COUNT(*) FROM PredictionLog WHERE true_label IS NOT NULL')
    predictions_with_feedback = cur.fetchone()[0]
    
    cur.execute('SELECT COUNT(*) FROM PredictionLog WHERE is_correct = 1')
    correct_predictions = cur.fetchone()[0]
    
    accuracy = (correct_predictions / predictions_with_feedback * 100) if predictions_with_feedback > 0 else 0
    
    cur.execute('SELECT AVG(confidence) FROM PredictionLog')
    avg_confidence = cur.fetchone()[0] or 0
    
    cur.execute('SELECT AVG(inference_time) FROM PredictionLog')
    avg_inference_time = cur.fetchone()[0] or 0
    
    conn.close()
    return {
        "total_predictions": total_predictions,
        "predictions_with_feedback": predictions_with_feedback,
        "correct_predictions": correct_predictions,
        "accuracy_percent": round(accuracy, 2),
        "avg_confidence_percent": round(avg_confidence * 100, 2),
        "avg_inference_time_ms": round(avg_inference_time, 2),
        "feedback_rate": round((predictions_with_feedback / total_predictions * 100) if total_predictions > 0 else 0, 2)
    }


def export_csv(db_path: str) -> str:
    rows = get_history(db_path, limit=10000)
    if not rows:
        return ""
    output = []
    header = ["id", "image_path", "predicted_label", "confidence", "true_label", "is_correct", "inference_time", "created_at"]
    output.append(header)
    for r in rows:
        output.append([r.get(c) for c in header])
    # convert to CSV string
    from io import StringIO
    sio = StringIO()
    writer = csv.writer(sio)
    for row in output:
        writer.writerow(row)
    return sio.getvalue()

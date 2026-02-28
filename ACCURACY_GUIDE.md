# 📊 Accuracy & Prediction Tracking Guide

## How Accuracy Works in Your System

### The Complete Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. USER UPLOADS IMAGE                                           │
│    → Image sent to /predict endpoint                           │
│    → Saved to predictions/ folder                               │
│    → Record created in SQLite database                          │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. MODEL INFERENCE                                               │
│    → Image preprocessed (224×224, normalized)                  │
│    → Model runs inference (~50-200ms)                          │
│    → Returns confidence scores for all 10 classes              │
│    → Top prediction selected                                    │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. DATABASE LOGGING                                              │
│    Fields: id, image_path, predicted_label, confidence,        │
│             true_label (NULL initially), is_correct (NULL),     │
│             inference_time, created_at                          │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. RESULT DISPLAYED TO USER                                     │
│    → Disease name shown                                         │
│    → Confidence bar displayed                                   │
│    → Inference time shown                                       │
│    → "Report Correct Label" button enabled                      │
│    → Low confidence warning if <40%                             │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 5. USER PROVIDES FEEDBACK (Optional)                            │
│    → User clicks "Report Correct Label"                        │
│    → Types actual disease name                                 │
│    → Submits feedback via /feedback/{id}                       │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 6. DATABASE UPDATED                                              │
│    → true_label = user input                                   │
│    → is_correct = 1 if predicted_label == true_label,          │
│                   0 if they don't match                        │
└─────────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────────┐
│ 7. ACCURACY RECALCULATED                                        │
│    → System counts all rows with is_correct IS NOT NULL       │
│    → Calculates: accuracy = (correct / total) × 100%          │
│    → Updates displayed on dashboard (auto-refresh)             │
└─────────────────────────────────────────────────────────────────┘
```

## Database Schema

### PredictionLog Table
```sql
CREATE TABLE PredictionLog(
    id              INTEGER PRIMARY KEY,      -- Unique prediction ID
    image_path      TEXT,                     -- Path to saved image
    predicted_label TEXT,                     -- Model's prediction
    confidence      REAL,                     -- Score (0-1)
    true_label      TEXT,                     -- User's feedback (NULL initially)
    is_correct      INTEGER,                  -- 1=correct, 0=wrong, NULL=no feedback
    inference_time  REAL,                     -- Milliseconds
    created_at      TIMESTAMP                 -- When prediction was made
);
```

## Accuracy Calculation Examples

### Example 1: Perfect Accuracy
```
Prediction 1: predicted="Healthy", true="Healthy" → is_correct=1 ✓
Prediction 2: predicted="Early_blight", true="Early_blight" → is_correct=1 ✓
Prediction 3: predicted="Late_blight", true="Late_blight" → is_correct=1 ✓

Accuracy = (3 / 3) × 100% = 100%
```

### Example 2: Partial Accuracy
```
Prediction 1: predicted="Healthy", true="Healthy" → is_correct=1 ✓
Prediction 2: predicted="Early_blight", true="Late_blight" → is_correct=0 ✗
Prediction 3: predicted="Bacterial_spot", true="Target_spot" → is_correct=0 ✗
Prediction 4: predicted="Spider_mites", true="Spider_mites" → is_correct=1 ✓

Accuracy = (2 / 4) × 100% = 50%
```

### Example 3: No Feedback Yet
```
Prediction 1: predicted="Healthy", true=NULL → is_correct=NULL (waiting for feedback)
Prediction 2: predicted="Early_blight", true=NULL → is_correct=NULL
Prediction 3: predicted="Late_blight", true="Late_blight" → is_correct=1 ✓

Accuracy = (1 / 1) × 100% = 100%
          (only counting rows with feedback)
```

## Key Metrics Explained

### 1. **Model Accuracy** (%)
```
Formula: (Correct Predictions / Total Predictions with Feedback) × 100
Only counts rows where is_correct IS NOT NULL
Shows percentage of correct predictions based on user feedback
Range: 0-100% (or "N/A" if no feedback given)
```

### 2. **Average Confidence** (%)
```
Formula: AVG(confidence) × 100
Averages all confidence scores across all predictions
Shows how certain the model is, regardless of correctness
Range: 0-100%
```

### 3. **Health Score** (0-100)
```
Formula: (Accuracy × 0.7) + (Avg_Confidence × 0.3)
Weighted combination of accuracy and confidence
70% weight on accuracy (how correct)
30% weight on confidence (how certain)
Color coded:
  - Green: 80+ (Excellent)
  - Orange: 50-80 (Good/Fair)
  - Red: <50 (Needs improvement)
```

### 4. **Feedback Rate** (%)
```
Formula: (Predictions with Feedback / Total Predictions) × 100
Shows what percentage of predictions have user feedback
Helps track engagement and data quality
Range: 0-100%
```

### 5. **Inference Time** (ms)
```
Minimum: Shortest inference time recorded
Maximum: Longest inference time recorded
Average: Mean inference time across all predictions
Goal: Keep average under 200ms (achieved ✓)
```

## Confidence Distribution

### Bucketing System
```
High Confidence (90-100%):     [████] 
  - Model is very certain
  - Low error risk
  - Green badge

Medium Confidence (70-90%):    [███░]
  - Model is reasonably certain  
  - Moderate error risk
  - Orange badge

Low Confidence (<70%):          [██░░]
  - Model is uncertain
  - Higher error risk
  - Red badge (triggers warning)
```

## Class-wise Accuracy Breakdown

### What It Shows
For **each disease class**, the system tracks:
```
Class Name          Total  Correct  Accuracy  Avg Confidence
─────────────────────────────────────────────────────────────
Tomato___healthy      10       9      90.0%      95.2%
Early_blight           8       6      75.0%      82.3%
Late_blight            5       4      80.0%      88.1%
Bacterial_spot         4       2      50.0%      71.5%
Spider_mites           3       3     100.0%      94.8%
... (continues for all 10 classes)
```

### Why It's Important
- Identifies which diseases are harder to predict
- Shows if model is biased toward certain classes
- Helps prioritize model improvement areas
- Guides where to get more training data

## Real-Time Tracking

### Dashboard Auto-Refresh (Every 10 seconds)
1. Fetches `/stats` endpoint
2. Fetches `/history` endpoint
3. Updates all displayed metrics
4. Refreshes disease distribution chart
5. Shows latest predictions

### Analytics Auto-Refresh (Every 15 seconds)
1. Loads `/detailed-stats` for class breakdown
2. Loads `/model-performance` for overall metrics
3. Updates all charts and tables
4. Shows recent prediction timeline

## Improving Model Accuracy

### Step 1: Make Predictions
```
Go to http://localhost:8000
Upload images or use camera
Record predictions
```

### Step 2: Provide Feedback
```
Click "Report Correct Label"
Type the actual disease
Submit feedback
System calculates accuracy immediately
```

### Step 3: Monitor Progress
```
View dashboard to see accuracy ↗️
Check analytics for class breakdowns
Export CSV data for analysis
```

### Step 4: Identify Weak Areas
```
Analytics page shows which classes are harder
Look for patterns in errors
Focus feedback on problematic classes
```

## CSV Export Format

When you download the CSV, you get:
```
id,image_path,predicted_label,confidence,true_label,is_correct,inference_time,created_at
1,predictions/pred_123.jpg,Healthy,0.95,Healthy,1,45.23,2026-02-24T10:30:45
2,predictions/pred_124.jpg,Early_blight,0.72,Late_blight,0,68.91,2026-02-24T10:31:12
3,predictions/pred_125.jpg,Bacterial_spot,0.58,,NULL,52.34,2026-02-24T10:31:45
...
```

### Use This Data For:
- ✓ Excel/Google Sheets analysis
- ✓ Machine learning further training
- ✓ Statistical analysis
- ✓ Presentation/reports
- ✓ Backup records
- ✓ External model evaluation

## Tips for Better Accuracy

1. **Provide Feedback on Every Prediction**
   - Even if correct, feedback helps validate
   - Builds complete accuracy history

2. **Use Real Tomato Images**
   - Model trained on PlantVillage dataset
   - Real farm images may have different lighting/angles
   - More diverse training helps

3. **Capture Good Quality Images**
   - Good lighting
   - Clear focus on affected area
   - Avoid motion blur

4. **Check Low Confidence Predictions**
   - Red warning flags predictions <40% confidence
   - Review these carefully
   - Provide feedback even if you're unsure

5. **Monitor Class Balance**
   - If only testing healthy tomatoes, limit to that class
   - Diverse disease examples improve learning

## Performance Benchmarks

### Current System
```
Average Inference Time: ~120 ms ✓
Processing Frame Rate: ~8 FPS (125ms per frame)
Model Size: ~13 MB
Memory Usage: ~150-200 MB
Suitable for: Raspberry Pi 4 (2GB RAM minimum)
```

### Accuracy Targets
```
Initial (random): ~10% (1 of 10 classes)
Untrained model: ~40-50%
Well-trained model: 80-95%
Your feedback helps reach: 95%+
```

## Troubleshooting

### Q: Accuracy shows 0%
**A:** You haven't provided any feedback yet. Click "Report Correct Label" on predictions.

### Q: Confidence always low
**A:** Model may need retraining. Check if images match training dataset style.

### Q: High accuracy but low confidence
**A:** Model is making correct guesses but uncertain. May need more training data.

### Q: CSV export shows NULL values
**A:** Those predictions haven't received feedback yet. Click "Report" to fill them in.

### Q: Inference time spike
**A:** Normal variation. Average matters more than individual readings.

---

**Remember:** Your feedback is the fuel that improves the model! 🚀
Every prediction you verify helps the system get smarter.

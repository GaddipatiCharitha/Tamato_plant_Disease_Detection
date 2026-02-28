# Activate virtualenv and run the FastAPI server
Set-StrictMode -Version Latest
if (Test-Path .\tomato_env\Scripts\Activate.ps1) {
    & .\tomato_env\Scripts\Activate.ps1
}
# Run uvicorn with module to ensure correct interpreter
python -m uvicorn app:app --host 0.0.0.0 --port 8000

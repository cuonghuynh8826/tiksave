# TikSave

## Nội dung
- `main.py`: backend FastAPI, API xem thông tin và tải video / âm thanh.
- `static/index.html`: giao diện frontend đã nối với API.
- `requirements.txt`: thư viện Python cần cài.

## Chạy local trên Windows
Cần Python 3.10+ và FFmpeg.

```powershell
winget install ffmpeg
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Mở `http://127.0.0.1:8000`


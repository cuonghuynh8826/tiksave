# TikSave — website tải video TikTok (bản chạy local)

## Nội dung
- `main.py`: backend FastAPI, API xem thông tin và tải video / âm thanh.
- `static/index.html`: giao diện frontend đã nối với API.
- `requirements.txt`: thư viện Python cần cài.

## Chạy trên Windows
Cần Python 3.10+ và FFmpeg (có `ffmpeg.exe` và `ffprobe.exe` trong PATH).

```powershell
scoop install python
scoop install ffmpeg
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Mở `http://127.0.0.1:8000`. Kiểm tra backend tại `http://127.0.0.1:8000/health`.

Nếu lệnh `python` hoạt động thì không cần lệnh `py`. Bản này dùng Uvicorn cơ bản để tránh cài thêm PyYAML/C++ Build Tools không cần thiết.

## API
- `GET /health` — kiểm tra server.
- `POST /api/info` JSON `{"url":"https://www.tiktok.com/..."}` — thông tin video.
- `POST /api/download` JSON `{"url":"https://www.tiktok.com/...","media_type":"video"}` — tải MP4.
- `POST /api/download` JSON `{"url":"https://www.tiktok.com/...","media_type":"audio"}` — trích xuất MP3.

## Lưu ý
- Bản HTML bạn tải lên là trang nguồn của ứng dụng Base44: nó tham chiếu đến bundle JS/CSS nằm trên máy chủ Base44, chứ không chứa mã giao diện React đầy đủ. Vì vậy giao diện được dựng lại để kết nối trực tiếp với backend Python thay vì phụ thuộc Base44.
- Backend chỉ nhận URL TikTok và không thiết lập cookie/đăng nhập hay vượt kiểm soát truy cập. Hỗ trợ tải phụ thuộc vào thay đổi của TikTok và yt-dlp.
- Tùy chọn MP3 cần FFmpeg. Giới hạn tệp là 200 MiB.
- Tùy chọn “không watermark” không được cam kết: việc loại watermark phụ thuộc vào nguồn/định dạng mà TikTok cung cấp. Bản này không hứa loại bỏ watermark bằng thủ thuật.
- Chỉ tải nội dung bạn có quyền sử dụng; không dùng cho nội dung riêng tư hoặc để né biện pháp kiểm soát truy cập.
- Trước khi công khai lên Internet, cần bổ sung giới hạn tốc độ, giới hạn số tác vụ đồng thời, kiểm soát chi phí, logging an toàn và chính sách quyền riêng tư.

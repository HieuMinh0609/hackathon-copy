# AI Buddy

Ứng dụng desktop offline hỗ trợ onboarding dự án: chat RAG, checklist môi trường,
kiểm tra IP/port và cài phần mềm sau khi người dùng xác nhận.

## Kiến trúc

```text
Flet frontend -> HTTP/JSON server đã cấu hình -> FastAPI backend
                                             |-- PostgreSQL
                                             |-- Ollama
                                             `-- ChromaDB local
```

- `frontend/`: Flet, DTO và HTTP client; không truy cập DB/RAG/subprocess.
- `backend/`: API JSON local cùng `core/`, `services/`, `rag/` nội bộ.
- `main.py`: launcher khởi động Uvicorn trong background rồi mở Flet.
- Tài liệu mỗi dự án nằm tại `documents/projects/<PROJECT_CODE>/` và không được trộn giữa các dự án.
- Ingest chạy background; Flet polling trạng thái JSON để hiển thị progress theo từng batch.

Khi chạy local, backend chỉ bind `127.0.0.1`. Trong container, Uvicorn lắng nghe
`0.0.0.0` nội bộ để Docker chuyển tiếp cổng, nhưng Compose mặc định chỉ publish tại
`127.0.0.1` của server. Dữ liệu không được gửi lên cloud.

## Phân quyền

Quyền được gán theo role key và phạm vi:

- `TEAM_LEAD`: là cấp duy nhất được tạo dự án; quản lý toàn hệ thống và tất cả template.
- `PROJECT_LEAD`: quản lý template, tài liệu và thành viên của các dự án được giao; không được tạo dự án.
- `MEMBER`: chỉ xem và thực thi checklist của chính mình.

`roles` chỉ chứa ba quyền trên. Quyền hệ thống nằm ở `users.role_id`; chức danh như Backend Developer hoặc QA Engineer nằm ở `users.job_title`. Quyền riêng của từng dự án nằm ở assignment user–project, vì vậy cùng một user có thể là lead ở dự án này nhưng là member ở dự án khác; chức danh không tự cấp quyền quản trị.

Chi tiết schema và luồng kiểm tra quyền xem tại [documents/onboarding/project_role_authorization_flow.md](documents/onboarding/project_role_authorization_flow.md).

## Theo dõi thành viên có nguy cơ

Dashboard của leader hiển thị tổng số thành viên có nguy cơ/quá hạn trên từng thẻ dự án. Dialog quản lý thành viên hiển thị badge, nguyên nhân và bộ lọc trạng thái. Backend tính rủi ro từ deadline và độ lệch giữa tiến độ thực tế/kỳ vọng; frontend không tự suy diễn.

Chi tiết API, quy tắc tính và luồng UI xem tại [documents/onboarding/leader_risk_flow.md](documents/onboarding/leader_risk_flow.md).

## Chạy trên Windows

### 1. Chuẩn bị

Cài các công cụ sau:

- Python **3.11 trở lên**; có thể dùng Python Launcher (`py.exe`) hoặc lệnh `python`/`python3` trong `PATH`.
- Docker Desktop để chạy PostgreSQL.
- Ollama để chạy LLM và embedding hoàn toàn trên máy local.

Script tự chọn bản Python 3 phù hợp có sẵn trên máy. Có thể kiểm tra bằng:

```powershell
py -0p
```

### 2. Cài môi trường Python

Mở PowerShell hoặc Command Prompt tại thư mục dự án rồi chạy:

```powershell
.\run_windows.bat setup
```

Nếu cần dùng Python package index nội bộ, có thể truyền thêm `-i` và `--trusted-host`:

```powershell
.\run_windows.bat setup -i https://mirror.example/simple --trusted-host mirror.example
```

Hai tùy chọn này cũng dùng được với `setup-global`. Nếu không truyền, script sử dụng cấu hình pip mặc định trên máy.

Script sẽ tạo `.venv`, hỏi xác nhận trước khi cài dependency và tạo `.env` từ `.env.example` nếu chưa có. Mở `.env` và kiểm tra lại cấu hình PostgreSQL, đặc biệt là `POSTGRES_PASSWORD`.

Nếu cần chạy bằng Python cài global, không dùng `.venv`, thực hiện:

```powershell
.\run_windows.bat setup-global
.\run_windows.bat global
```

Chế độ này cài dependency trực tiếp vào Python global đã được tự động phát hiện và sẽ hỏi xác nhận trước khi cài. Khuyến nghị dùng chế độ `.venv` để tránh xung đột thư viện giữa các dự án.

### 3. Khởi động PostgreSQL

Đảm bảo Docker Desktop đang chạy, sau đó chạy:

```powershell
docker compose up -d db
.\.venv\Scripts\python.exe scripts\init_database.py --check
```

### 4. Khởi động Ollama

Mở Ollama, hoặc chạy `ollama serve` trong một cửa sổ terminal riêng, rồi tải hai model ở lần chạy đầu tiên:

```powershell
ollama pull qwen2.5:7b
ollama pull bge-m3
```

### 5. Nạp tài liệu ban đầu

```powershell
.\.venv\Scripts\python.exe scripts\ingest_document.py
```

Tài liệu tải lên từ giao diện của từng dự án sẽ được lưu riêng tại `documents/projects/<PROJECT_CODE>/` và tiến độ xử lý được cập nhật trên giao diện.

### 6. Chạy ứng dụng

```powershell
.\run_windows.bat
```

Lệnh này khởi động backend API local và ứng dụng desktop Flet. Các chế độ được hỗ trợ:

| Lệnh | Chức năng |
|---|---|
| `.\run_windows.bat` | Chạy toàn bộ ứng dụng; ưu tiên `.venv`, nếu chưa có thì tự dùng Python trên máy |
| `.\run_windows.bat setup` | Tạo môi trường và cài dependency |
| `.\run_windows.bat global` | Chạy bằng Python global được tự động phát hiện, không dùng `.venv` |
| `.\run_windows.bat setup-global` | Cài dependency vào Python global được tự động phát hiện |
| `.\run_windows.bat backend` | Chỉ chạy backend API, tự chọn `.venv` hoặc Python trên máy |
| `.\run_windows.bat test` | Chạy toàn bộ test, tự chọn `.venv` hoặc Python trên máy |
| `.\run_windows.bat help` | Xem trợ giúp |

### Lỗi thường gặp

- Báo không tìm thấy Python: cài Python 3.11 trở lên, thêm vào `PATH` rồi kiểm tra lại bằng `python --version` hoặc `py -0p`.
- Không kết nối được database: kiểm tra Docker Desktop, `docker compose ps` và các biến `POSTGRES_*` trong `.env`.
- Không gọi được AI: kiểm tra Ollama đang chạy tại `http://localhost:11434` và hai model đã được tải.
- Cổng API bị chiếm: đổi `LOCAL_API_PORT` trong `.env`, sau đó chạy lại ứng dụng.

## Chạy riêng khi phát triển

```powershell
.\.venv\Scripts\python.exe -m backend.main
.\.venv\Scripts\python.exe -m frontend.main
```

API docs local: `http://127.0.0.1:8765/api/docs`.

## Triển khai backend bằng Docker

Docker image chỉ chứa FastAPI, agent/RAG và các service backend; không chứa Flet frontend,
test, `.env` hay dữ liệu runtime.

1. Sao chép `.env.example` thành `.env`, đặt `POSTGRES_PASSWORD` mạnh và kiểm tra:

```dotenv
BACKEND_PUBLISH_HOST=127.0.0.1
BACKEND_PORT=8765
BACKEND_OLLAMA_BASE_URL=http://host.docker.internal:11434
```

2. Build và chạy backend cùng PostgreSQL:

```bash
docker compose up -d --build backend
docker compose ps
curl http://127.0.0.1:8765/api/v1/health/live
```

`backend_data`, `backend_logs`, `backend_documents` và `pgdata` là named volume; cần backup
các volume database/data/documents này định kỳ. Tài liệu mẫu trong image được Docker sao chép
vào volume documents ở lần tạo đầu tiên.
Ollama có thể chạy trên host qua `host.docker.internal`, hoặc đổi
`BACKEND_OLLAMA_BASE_URL` sang URL Ollama nội bộ phù hợp.

Khuyến nghị đặt reverse proxy HTTPS (Nginx/Caddy) trước `127.0.0.1:8765`. Nếu chỉ dùng
trong LAN và muốn publish trực tiếp, đặt `BACKEND_PUBLISH_HOST=0.0.0.0`, đồng thời giới hạn
port bằng firewall/VPN. Không công khai API thẳng ra Internet khi chưa có TLS và kiểm soát mạng.

## Build ứng dụng frontend desktop

Frontend đóng gói dùng [frontend_app.py](frontend_app.py), chỉ kết nối tới backend đã cấu hình
và không tự khởi động Uvicorn local. Cài dependency build rồi chạy trên đúng hệ điều hành đích:

```powershell
pip install -r requirements-frontend.txt
.\scripts\build_frontend.ps1 -Target windows -Version 1.0.0 -BuildNumber 1
```

Nếu PowerShell chặn script theo Execution Policy, dùng:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\build_frontend.ps1 -Target windows
```

Hoặc gọi script Python đa nền tảng:

```bash
python scripts/build_frontend.py --target linux --version 1.0.0 --build-number 1
python scripts/build_frontend.py --target macos --version 1.0.0 --build-number 1
```

Artifact nằm trong `dist/frontend/<target>/`. Flet/Flutter thường yêu cầu build trên đúng OS
đích; lần build đầu có thể cần mạng để lấy toolchain, còn ứng dụng runtime vẫn hoạt động theo
mô hình offline/intranet. Khi mở app, nhập URL backend ở màn hình kết nối, ví dụ
`https://aibuddy.internal` hoặc `http://192.168.1.20:8765`.

Chỉ kiểm tra staging mà không chạy compiler:

```powershell
.\scripts\build_frontend.ps1 -PrepareOnly
```

## Test

```powershell
.\run_windows.bat test
```

Test dùng SQLite tạm và không yêu cầu PostgreSQL, Ollama hoặc internet.

### Nút Auto trong checklist dự án

Bấm **Auto** để kiểm tra lần lượt các mục tự động của dự án: phiên bản phần mềm
(ví dụ `git --version`, `python --version`), Wi-Fi, host/port và port trống.
Thanh tiến độ cập nhật sau từng kết quả thật; chi tiết phiên bản hoặc lỗi hiện ngay
trong thẻ checklist. Có thể bấm nút kiểm tra ở từng mục để chạy lại.
Auto không cài phần mềm và dừng ở mục `MANUAL` chưa được xác nhận.

Khi nhập CSV/JSON, dùng `check_type: WIFI` với `params: {}` để kiểm tra Wi-Fi.
Mục này nên không bắt buộc vì máy có thể dùng mạng dây. Wi-Fi đã kết nối không đồng nghĩa
Internet/VPN hoạt động. File CSV mẫu đã có mục Wi-Fi và tham số kiểm tra phiên bản chuẩn;
các checklist cũ chứa `command: "git --version"` vẫn được hỗ trợ.

### Cài phần mềm sau khi kiểm tra

Sau Auto, chọn **Cài đặt** ở mục phần mềm chưa đạt → xem chính xác lệnh →
**Đồng ý cài đặt**. Chọn **Hủy** sẽ không chạy lệnh. Ứng dụng chạy nền,
hiện kết quả trong chat và tự kiểm tra lại phiên bản; nếu chưa đạt, mục vẫn báo lỗi/cảnh báo.

Cần có trình quản lý gói phù hợp (winget/Chocolatey, Homebrew hoặc apt) và mục
`params.install` trong checklist. File mẫu có sẵn cấu hình cho Git, Python và Docker.
Nếu thiếu cấu hình/công cụ, ứng dụng báo để liên hệ IT. Công cụ cài có thể cần mạng;
quyền Administrator/UAC/sudo do hệ điều hành quyết định, không phải quyền admin trong ứng dụng.
Không nhập mật khẩu quản trị vào chat. Nếu PATH chưa cập nhật sau khi cài, mở lại ứng dụng rồi kiểm tra lại.

Tiến trình cài đặt trong checklist hiển thị bốn bước: **Chuẩn bị lệnh → Bạn cấp phép →
Chạy lệnh cài đặt → Kiểm tra lại phiên bản**. Mỗi bước có trạng thái chờ/đang chạy/hoàn tất/lỗi/đã hủy.
Ứng dụng không giả lập phần trăm tải gói; khi lệnh đang chạy, bước tương ứng hiển thị vòng quay.
Chỉ đánh dấu toàn bộ hoàn tất khi việc cài đặt và kiểm tra phiên bản đều đạt.

### Checklist theo thứ tự

Các bước được đánh số theo thứ tự dự án. Hoàn thành bước 1 mới mở bước 2;
bước hoàn thành hiển thị ✓ màu xanh lá. Mỗi thẻ hiển thị chi tiết chuẩn bị,
thực thi phép kiểm tra và ghi nhận kết quả khi bấm kiểm tra riêng hoặc Auto.

Auto tiếp tục từ bước chưa hoàn thành đầu tiên và dừng ngay khi bước không đạt
(kể cả cảnh báo), hoặc cần bạn xác nhận thủ công. Khắc phục/xác nhận bước đó rồi bấm Auto
để tiếp tục. Nếu bỏ xác nhận bước trước, các bước sau khóa lại nhưng giữ kết quả đã có.
Máy dùng mạng dây có thể cần quản trị viên chỉnh mục Wi-Fi trong checklist trước khi tiếp tục.

### Cài từ đường dẫn App Catalog

Nút **Cài đặt** trong checklist lấy đúng bộ cài ở `INSTALLER_PREFIX` + `installer_path`
và dùng `install_args` đã lưu. Bạn xem lệnh rồi bấm **Đồng ý cài đặt**; Windows có thể
hiện thêm hộp thoại UAC. Ứng dụng đợi tiến trình kết thúc và kiểm tra lại phiên bản,
không coi việc vừa mở cửa sổ bộ cài là hoàn thành.

Hỗ trợ `.exe`/`.msi` trên Windows, `.pkg` trên macOS và `.deb` trên Linux.
Bộ cài thiếu hoặc sai hệ điều hành sẽ báo lỗi, không âm thầm chọn một tệp khác.

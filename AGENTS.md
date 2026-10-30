# AGENTS.md - Quy tắc toàn dự án AI Buddy

> **Quên gì thì đọc file này.** Áp dụng cho cả developer và AI coding assistant.
> Khi sửa kiến trúc/quy ước, cập nhật file này trong cùng PR.

## 1. Dự án là gì
Ứng dụng desktop **chạy hoàn toàn offline** giúp thành viên mới onboarding vào dự án:
chat hỏi đáp tài liệu (RAG), checklist môi trường, kiểm tra IP/port, cài phần mềm có xác nhận.

| Thành phần | Công nghệ |
|---|---|
| Ngôn ngữ | **Python 3.11** |
| UI desktop | **Flet `0.28.3`** (đã ghim, **không nâng** lên 0.80+ vì đổi API) |
| Backend local | **FastAPI + Uvicorn**, chỉ bind `127.0.0.1`, giao tiếp JSON |
| LLM | Ollama + Qwen-2.5 (`qwen2.5:7b`), embedding `bge-m3` |
| Agent | LangChain (`langchain-ollama`) |
| Vector DB | ChromaDB (`data/chromadb/`) |
| Database | SQLAlchemy 2 → **PostgreSQL** (chạy `docker compose up -d db`) |
| Mạng | `socket` + `subprocess` (**không** dùng `telnet`) |

## 2. Lệnh hay dùng
```powershell
.\.venv\Scripts\activate
pip install -r requirements.txt
python scripts/init_database.py [--check]   # tạo bảng + seed checklist / kiểm tra kết nối DB
python scripts/ingest_document.py [--reset] # nạp documents/ vào ChromaDB
python main.py                              # chạy backend local + app desktop
python -m backend.main                     # chỉ chạy API khi phát triển
pytest                                      # chạy test (phải xanh trước khi commit)
docker compose up -d db                     # Postgres local (cần POSTGRES_PASSWORD trong .env)
docker compose up -d --build backend        # backend container + Postgres trên server
python scripts/build_frontend.py --target windows # đóng gói frontend-only trên OS đích
```

## 3. Kiến trúc & hướng phụ thuộc
```
frontend/ ──HTTP/JSON──► backend/api ──► backend/core/agents ──► backend/services ──► backend/core/utils, backend/rag
  (Flet)                 (FastAPI)     (LangChain)      (nghiệp vụ)       (hạ tầng)
```
- **Frontend và backend chỉ giao tiếp qua HTTP/JSON.** Local mặc định dùng `127.0.0.1`; app đóng gói có thể dùng URL server do người dùng cấu hình. `frontend/` không import `backend/`, SQLAlchemy hay ChromaDB.
- **Chỉ phụ thuộc xuống dưới.** Backend/core/services không import `flet` hay `frontend/`.
- UI không chứa logic nghiệp vụ; gọi qua `FrontendContext` và các gateway trong `frontend/context.py`.
- FastAPI là adapter; nghiệp vụ vẫn nối dependency qua `AppContext` (`backend/core/context.py`, dựng bằng `build_context()`).
- Thêm dependency mới → nối trong `build_context()`, không tạo singleton rải rác.
- Thư mục: `config/` cấu hình dữ liệu · `frontend/` giao diện/API client · `backend/core/agents/` luồng agent ·
  `backend/services/` nghiệp vụ · `backend/rag/` ingest-retrieve · `data/` dữ liệu cục bộ · `documents/` tài liệu thô · `scripts/` · `tests/`.

## 4. Quy tắc BẮT BUỘC (an toàn & bảo mật)
1. **Hỏi trước khi thực thi.** Lệnh thay đổi máy người dùng (cài phần mềm...) chỉ chạy sau khi họ bấm xác nhận
   (`confirm_install_dialog`). `build_install_plan()` chỉ *tạo kế hoạch*; chỉ `run_install_plan()` mới chạy.
2. **Không bao giờ** `shell=True`, không nối chuỗi người dùng vào lệnh. Dùng `subprocess.run([list], ...)`.
   Mã gói cài đặt phải qua regex whitelist (`_PKG_ID_RE`).
3. **Offline.** Không gọi API/cloud bên ngoài, không tải dữ liệu lên mạng. LLM chỉ qua Ollama local.
4. **Không commit secret.** Mật khẩu/URL DB chỉ ở `.env` (đã `.gitignore`). Cập nhật `.env.example` khi thêm biến mới.
   Không ghi mật khẩu vào `user_settings.json`, log hay UI (dùng `describe()` để che mật khẩu).
5. **Không dùng `telnet`** (Windows hay tắt sẵn). Dùng `network_utils.tcp_connect()`.
6. Không chạy script lạ, không sửa schema DB dev bằng tay.
7. Backend local giữ `API_HOST=127.0.0.1`. Container được phép bind `0.0.0.0` **bên trong container** để Docker forward port; Compose mặc định chỉ publish tại loopback của host. Muốn mở LAN phải cấu hình firewall/VPN hoặc reverse proxy HTTPS rõ ràng.

## 5. Cấu hình
- Thứ tự ưu tiên: `config/llm_config.yaml` < `.env` < `data/user_settings.json` (trang Cài đặt).
- Luôn lấy qua `get_settings()`; **không hardcode** URL/model/đường dẫn/port.
- Đổi đường dẫn data: dùng property của `Settings` (`db_path`, `chroma_dir`...), không nối chuỗi tay.
- Checklist mặc định nằm ở `config/checklist_items.yaml` (host/port/version là **placeholder**, sửa cho dự án thật).
  Loại hỗ trợ: `software` · `port_free` · `host_reachable` · `wifi` · `manual`.
- Prompt nằm ở `config/prompt_templates.yaml`, chỉ dùng `{placeholder}` đã khai báo, **không** viết `{ }` khác
  (vì dùng `str.format`). Lấy bằng `get_prompt(name, **kwargs)`.

## 6. Database
- Mọi truy vấn dùng `sqlalchemy.text()` với **tham số có tên** (`:key`), **không** `?` / `%s`, **không** f-string SQL.
  Dùng chuẩn PostgreSQL (`ON CONFLICT ... DO UPDATE`).
- Dùng `backend.services.db.get_connection(url)` (tự commit/rollback). Không mở kết nối thủ công.
- Đổi schema → sửa `SCHEMA` trong `backend/services/db.py` theo hướng `CREATE TABLE IF NOT EXISTS`; nếu cần migrate dữ liệu cũ thì viết script riêng.
- Test **luôn dùng SQLite tạm** (fixture `settings` ở `tests/conftest.py`), không bao giờ đụng Postgres thật.

## 7. Agent / LLM
- Gọi LLM qua `LLMClient` (`backend/core/llm.py`). Không `import ChatOllama` rải rác.
- `LLMClient.ask()` ném `LLMUnavailable` khi Ollama chưa chạy → **agent phải bắt và có đường lui** (kết quả rule-based),
  không để UI sập.
- Định tuyến ở `detect_intent()` là **theo luật, không tốn LLM**. Thêm intent mới → thêm test vào `tests/test_agent_router.py`.
- Câu trả lời cho người dùng: **tiếng Việt**, ngắn gọn; không bịa — thiếu tài liệu thì nói rõ là chưa có.
- Agent trả `AgentReply`; hành động cần xác nhận đặt vào `pending_install`, **UI** mới là nơi hỏi và gọi `confirm_install()`.

## 8. RAG Đa Ngôn Ngữ (VI / EN / KR) & Xử Lý Đa Luồng
- Role của tài liệu = **thư mục con đầu tiên** dưới `documents/` (`onboarding`, `backend_developer`, `frontend_developer`, `hr`).
  Truy xuất chỉ lấy `onboarding` + role hiện tại (`Settings.role_filter`).
- Tài liệu từng dự án lưu riêng tại `documents/projects/<PROJECT_CODE>/`; tên project code chỉ gồm chữ, số, `.`, `_`, `-`.
  Khi ingest theo project, chunk bắt buộc có `project_code` và role `onboarding`; không fallback sang tài liệu project khác.
- Định dạng nạp được: `.pdf` (PyMuPDF `pymupdf`), `.docx` (`python-docx`), `.md`, `.txt`. Đọc chuẩn UTF-8, bảo toàn nguyên vẹn font Tiếng Việt và Hangul (Hàn Quốc).
- Chunker: `split_documents()` cắt Recursive theo câu đa ngôn ngữ (`\n\n`, `.\n`, `.\r\n`, `. `, `? `, `! `, `\n`), chunk size ~700 tokens (1500 ký tự) giữ trọn vẹn ngữ pháp.
- Ingest: Chia lô an toàn 32 - 64 chunks/batch (tránh tràn VRAM Ollama `bge-m3` 1024 chiều), xử lý đa luồng qua `ThreadPoolExecutor` (2 - 4 workers), đồng bộ ghi xuống ChromaDB (`data/chromadb/`) và cập nhật `progress(i, total, msg)` cho Progress Bar Flet mượt mà.
- Truy vấn: `retrieve()` & `retrieve_with_scores()` trích xuất ngữ cảnh liên quan, định dạng context chuẩn hóa cho Ollama `qwen2.5:7b` đọc hiểu chéo tài liệu gốc (VI/EN/KR) và sinh phản hồi tiếng Việt.

## 9. UI (Flet 0.28.3 - Clean Modern Light Theme)
- Luồng màn hình: **`ConnectionScreen`** (health check/cấu hình server) ──► **`LoginScreen`** ──► **`DashboardScreen`** (chọn project) ──► **`WorkspaceScreen`** (Chat AI + Checklist Drawer + Docs Management).
- Màu/kiểu lấy từ `frontend/theme.py`, không viết mã màu rải rác.
- Font chữ: **Be Vietnam Pro** (hỗ trợ tiếng Việt tốt), file nằm ở `frontend/assets/fonts/` và đăng ký trong `frontend/main.py`.
  Phải **đóng gói file font cục bộ** (app offline) — không trỏ `page.fonts` tới URL Google Fonts/CDN. Thêm font mới → kèm file license (OFL).
- **Việc nặng (mạng, subprocess, LLM, ingest) phải chạy qua `page.run_thread(...)`**, không chặn UI thread.
- Progress ingest dùng background job API + polling JSON; backend cập nhật theo batch, frontend không giả lập phần trăm.
- Control chỉ `.update()` khi đã gắn vào page (`if self.page:`). Dữ liệu tải lúc hiển thị đặt ở `did_mount()`.
- Hộp thoại dùng `page.open(dlg)` / `page.close(dlg)`.
- Thông báo cho người dùng đi qua `NotificationService` (snackbar), không `print`.
- API **không tồn tại ở 0.28.3**: `ft.ActionChip` (dùng `ft.Chip(on_click=...)`). Kiểm tra trước khi dùng control lạ.

## 10. Phong cách code
- `from __future__ import annotations` ở đầu mỗi module; type hint đầy đủ (cú pháp 3.11: `list[str]`, `X | None`).
- Docstring/comment tiếng Việt, giải thích **vì sao** chứ không lặp lại code. **Giữ nguyên** comment/docstring không liên quan khi sửa file.
- Chuỗi hiển thị cho người dùng: tiếng Việt. Tên biến/hàm/class: tiếng Anh `snake_case` / `PascalCase`.
- Lỗi một mục không được làm hỏng cả luồng (xem `verify_item`, `ingest_files`): bắt ở biên, trả thông báo thân thiện.
- Script trong `scripts/` phải `sys.stdout.reconfigure(encoding="utf-8")` (console Windows cp1252 sẽ lỗi tiếng Việt/emoji).
- Không thêm thư viện nếu stdlib đủ dùng; thêm thì ghi vào `requirements.txt` (ghim khoảng version).

## 11. Test
- `pytest` phải **xanh** trước khi commit/PR. Mục tiêu coverage logic nghiệp vụ ≥ 70%.
- Test **không** được phụ thuộc Ollama, Postgres hay internet. Dùng `tmp_path`, socket cục bộ, `monkeypatch`.
- Code mới ở `backend/core/utils`, `backend/services`, `backend/core/agents` kèm test trong `tests/`. Bug sửa xong → thêm test tái hiện.
- Test không có host thật nào ngoài `127.0.0.1` / `host.invalid`.

## 12. Git & quy trình
- Branch: `feature/<ten-task>`, `fix/<ten-bug>`. Mọi thay đổi qua Pull Request, **≥ 1 reviewer**.
- Commit theo Conventional Commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`.
- Không commit: `.env`, `.venv/`, `data/database/*.db`, `data/chromadb/*`, `data/exports/*`, file build.
- Cập nhật trạng thái task hằng ngày trước 10:00.
- Cần quyền truy cập IP/port → làm theo `documents/onboarding/ip_access_process.md`.

## 13. Checklist khi thêm tính năng
- [ ] Đúng tầng (xem mục 3), không import ngược.
- [ ] Không hardcode cấu hình; biến môi trường mới có trong `.env.example`.
- [ ] Việc nguy hiểm có bước xác nhận người dùng.
- [ ] Có xử lý khi Ollama/DB/mạng không sẵn sàng.
- [ ] Có test, `pytest` xanh.
- [ ] Cập nhật `AGENTS.md` / `documents/` nếu đổi quy ước.

### Công thức thêm nhanh
- **Loại kiểm tra checklist mới:** thêm `_check_xxx` + đăng ký trong `checkers` ở `backend/services/verification_service.py`, thêm mục vào `config/checklist_items.yaml`, thêm test.
- **Agent mới:** tạo `backend/core/agents/xxx_agent.py` với `handle(message) -> AgentReply`, nối vào `AiBuddyAgent` và `build_context()`, thêm luật vào `detect_intent()` + test.
- **Trang UI mới:** tạo `frontend/pages/xxx_page.py` (class kế thừa Flet control, nhận `FrontendContext`), thêm gateway/API JSON nếu cần dữ liệu nghiệp vụ.
- **API mới:** thêm route dưới `/api/v1`, request/response Pydantic và test; không trả object ORM/dataclass trực tiếp qua biên HTTP.

### Kiểm tra Auto checklist
- Auto chạy từng mục SOFTWARE/WIFI/HOST_REACHABLE/PORT_FREE của dự án qua API trong `page.run_thread`, cập nhật kết quả thật sau mỗi mục; dừng ở MANUAL chưa hoàn thành, không tự cài đặt.
- WIFI đọc trạng thái bằng netsh (Windows), networksetup (macOS), nmcli (Linux), có timeout; không gọi Internet và không suy diễn Wi-Fi đã kết nối thành Internet/VPN hoạt động.
- Kết quả chi tiết Auto lưu tại UI trong phiên workspace; trạng thái vẫn cập nhật qua ChecklistService. Chỉ xác nhận kiểm tra phiên bản đạt khi lệnh thành công và đọc được phiên bản.

### Cài phần mềm từ kết quả checklist
- Mục SOFTWARE chưa đạt có nút Cài đặt: lấy plan từ API, hiển thị lệnh trong `confirm_install_dialog`, chỉ chạy sau nút Đồng ý. Hủy không chạy lệnh; xác nhận chỉ dùng một lần.
- Token cài đặt gắn với tài khoản và key checklist, hết hạn sau 10 phút; API thực thi plan đã lưu phía server, không nhận command từ UI. Mỗi lần thử lại phải tạo/xác nhận plan mới.
- Không chạy đồng thời hai lệnh cài; chạy nền, báo lỗi quyền/timeout và kiểm tra lại trước khi đánh dấu đạt. Linux dùng `sudo -n`, không thu thập mật khẩu và không tự cấp quyền quản trị.
- LLM/RAG vẫn offline. Công cụ quản lý gói có thể cần mạng theo nguồn đã cấu hình; hộp thoại cài đặt phải nói rõ điều này trước khi người dùng đồng ý.
- UI cài đặt dùng `InstallProgress` với bốn bước chuẩn bị/cấp phép/cài/kiểm tra, cập nhật theo kết quả thật; lỗi và hủy giữ nguyên bước dừng, không giả lập phần trăm. `AgentReply.install_ok` là kết quả có cấu trúc, không suy đoán thành công qua chuỗi chat.

### Checklist tuần tự
- Thứ tự theo `sort_order`, sau đó `template_task_id`; đánh số 1..N trong từng dự án. Chỉ `passed`/`COMPLETED` được xem là hoàn thành; lỗi/cảnh báo/thủ công chưa xác nhận đều chặn bước sau.
- UI khóa mọi thao tác của bước chưa tới lượt. Backend kiểm tra điều kiện trước API verify, xác nhận thủ công và cài đặt; không chỉ dựa vào nút disabled.
- Auto bỏ qua bước đã hoàn thành, dừng ở lỗi/cảnh báo hoặc bước thủ công đang chờ; bấm lại để tiếp tục. Bỏ xác nhận bước trước sẽ khóa lại các bước sau, không tự xóa kết quả cũ.
- Thẻ hoàn thành có dấu ✓ và nền/chữ xanh lá. `CheckRun` hiển thị chi tiết chuẩn bị/thực thi/đánh giá trong từng thẻ, cho cả kiểm tra đơn và Auto; không giả lập tiến độ bên trong subprocess.

### Phân quyền template và thực thi
- Bảng `roles` dùng duy nhất `key_role` với ba khóa ổn định: `TEAM_LEAD`, `PROJECT_LEAD`, `MEMBER`; không có `role_code`. `users.role_id` lưu quyền hệ thống; `users.job_title` lưu chức danh/cấp bậc chuyên môn; không có `users.access_role_id`.
- Task trong `onboarding_template_tasks` dùng chung cho mọi thành viên của dự án; bảng này không có `role_id` hoặc `document_link`.
- Chỉ `TEAM_LEAD` từ `users.role_id` được tạo dự án và quản lý toàn cục. Quyền trong từng dự án luôn lấy từ `user_checklists.project_role_id`; tuyệt đối không suy quyền dự án từ `job_title` hay dữ liệu frontend.
- Cùng một user có thể là `PROJECT_LEAD` trong dự án A và `MEMBER` trong dự án B; thay đổi quyền dự án không được làm thay đổi `users.role_id`, `users.job_title` hoặc reset deadline.
- Backend bắt buộc kiểm tra permission từ session; không tin `X-User-Email` hay dữ liệu quyền do frontend gửi lên.
- `MEMBER` chỉ xem và thực thi checklist đã được giao; frontend ẩn thao tác quản trị nhưng backend vẫn phải chặn để không thể bypass qua API.
- `TEAM_LEAD` là admin toàn cục. `PROJECT_LEAD` không được thêm hoặc xóa một `TEAM_LEAD` khỏi dự án; chỉ `TEAM_LEAD` được quản lý membership của các tài khoản `TEAM_LEAD`.

### Thời hạn onboarding theo dự án
- Mỗi dự án có `duration_days` (mặc định 20, hợp lệ 1–3650 ngày).
- Khi Team Lead/Project Lead thêm member, `user_checklists.started_at` và `due_at` được ghi riêng cho member đó; hạn = thời điểm thêm + `duration_days` của dự án.
- Thêm lại hoặc đổi role của member đã thuộc dự án không được reset `started_at`/`due_at`. Thay đổi thời lượng dự án không hồi tố các hạn đã giao.
- Dữ liệu cũ chưa có mốc riêng dùng `created_at` làm thời điểm bắt đầu; UI phải hiển thị còn hạn, quá hạn hoặc đã hoàn thành bằng kết quả có cấu trúc từ backend.
- Backend trả `risk_status`, `risk_reason`, `expected_progress`; `at_risk` khi còn không quá 3 ngày mà chưa xong, hoặc sau 20% thời lượng mà tiến độ thực tế thấp hơn kỳ vọng từ 20 điểm phần trăm.
- Badge/tổng hợp rủi ro và tiến độ thành viên hiển thị cho tất cả thành viên trong dự án; quyền chỉnh sửa thành viên vẫn chỉ dành cho `TEAM_LEAD` và `PROJECT_LEAD` của dự án.

### Bộ cài App Catalog trong checklist
- `TEAM_LEAD` và user có role `PROJECT_LEAD` ở ít nhất một dự án được tải file bộ cài lên App Catalog; `MEMBER` bị chặn ở cả UI và API.
- Nút Cài đặt lấy plan qua `/api/v1/apps/{app_code}/install-plan`, backend ghép `Settings.installers_dir` với suffix `installer_path` và `install_args` đã lưu. Nếu tệp đó thiếu, báo lỗi, không tự chọn tệp khác.
- Frontend không tải/chmod/Popen bộ cài; hiển thị `confirm_install_dialog` và dùng token xác nhận một lần của `/install/execute`.
- Windows .exe/.msi chạy qua ShellExecuteExW với UAC, chờ handle tiến trình và đọc exit code; hủy quyền không coi là thành công. macOS .pkg mở Installer và chờ, Linux .deb dùng dpkg; không chạy tệp sai hệ điều hành. Sau tiến trình vẫn phải kiểm tra phiên bản trước khi đánh dấu đạt.

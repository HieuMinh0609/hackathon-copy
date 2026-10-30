# ==============================================================================
# AI BUDDY ONBOARDING & CHECKLIST TROUBLESHOOTING KNOWLEDGE BASE
# TÀI LIỆU HƯỚNG DẪN CHI TIẾT & KNOWLEDGE BASE HUẤN LUYỆN MODEL OLLAMA QWEN2.5:7B
# Phiên bản: 2.1 (Hướng dẫn phiên bản linh hoạt - Version Agnostic)
# Môi trường: Windows 10/11 - Dự án: AI Buddy Onboarding
# ==============================================================================

MỤC LỤC:
1. TỔNG QUAN HỆ THỐNG & NGUYÊN TẮC HOẠT ĐỘNG
2. HƯỚNG DẪN CÀI ĐẶT & SỬA LỖI CÁC CÔNG CỤ LẬP TRÌNH (SOFTWARE)
   - 2.0. Nguyên tắc kiểm tra & quản lý phiên bản chung (Version Agnostic Guidelines)
   - 2.1. Python (Python 3.x / Phiên bản theo yêu cầu dự án)
   - 2.2. Git (Quản lý mã nguồn)
   - 2.3. Node.js & Trình quản lý gói (NPM / Yarn / PNPM)
   - 2.4. Docker Desktop & Docker Compose
   - 2.5. Ollama & Các Mô Hình AI Local
   - 2.6. Java Development Kit (JDK) & Maven / Gradle
   - 2.7. Go / Golang
   - 2.8. .NET SDK
   - 2.9. Visual Studio Code & Tiện ích lập trình
   - 2.10. JetBrains IDE (IntelliJ IDEA, PyCharm)
   - 2.11. Quản lý Cơ Sở Dữ Liệu (DBeaver, PostgreSQL Client psql)
   - 2.12. Công cụ Kiểm Thử API (Postman, Insomnia, cURL)
   - 2.13. Windows Terminal & PowerShell 7
3. HƯỚNG DẪN KIỂM TRA MẠNG NỘI BỘ VÀ KẾT NỐI RA NGOÀI INTERNET (HOST_REACHABLE)
   - 3.1. Dịch vụ Ollama Local (127.0.0.1:11434)
   - 3.2. Git Server Nội Bộ (git.company.local:443)
   - 3.3. Database PostgreSQL Dev (db.company.local:5432)
   - 3.4. Kho mã nguồn công khai (GitHub.com, GitLab.com)
   - 3.5. Kho thư viện gói công khai (PyPI, NPM Registry, Docker Hub, Maven, Go Proxy)
   - 3.6. Dịch vụ Cloud & DNS ngoài (AWS, Google DNS 8.8.8.8, Cloudflare 1.1.1.1)
   - 3.7. Các lỗi kết nối mạng bên ngoài thường gặp và giải pháp chi tiết
4. HƯỚNG DẪN KIỂM TRA & GIẢI PHÓNG PORT XUNG ĐỘT (PORT_FREE)
   - 4.1. Cách tìm tiến trình đang chiếm Port trên Windows
   - 4.2. Cách tắt tiến trình chiếm Port an toàn
   - 4.3. Xử lý trường hợp Port bị Windows Hyper-V/WinNAT chiếm giữ
5. QUY TRÌNH XIN CẤP QUYỀN TRUY CẬP IP (IP ACCESS REQUEST PROCESS)
6. BẢNG TRA CỨU NHANH SỰ CỐ TOÀN DIỆN (TROUBLESHOOTING MATRIX CHO QWEN 2.5:7B)

==============================================================================
1. TỔNG QUAN HỆ THỐNG & NGUYÊN TẮC HOẠT ĐỘNG
==============================================================================
- Ứng dụng AI Buddy là trợ lý cá nhân chạy hoàn toàn OFFLINE trên máy tính của lập trình viên mới gia nhập dự án.
- Mô hình AI: Ollama chạy cục bộ mô hình Qwen-2.5 (`qwen2.5:7b`) và mô hình embedding `bge-m3`.
- Cơ sở dữ liệu: PostgreSQL local (chạy qua Docker) hoặc SQLite nội bộ, Vector DB ChromaDB lưu tại thư mục `data/chromadb/`.
- Nguyên tắc cốt lõi số 1 (BẮT BUỘC): "HỎI TRƯỚC KHI THỰC THI" (Ask before execute).
  + AI Buddy không bao giờ tự ý chạy các câu lệnh thay đổi hệ thống hoặc cài đặt phần mềm khi người dùng chưa xác nhận qua hộp thoại giao diện.
  + Mọi mã gói phần mềm đều phải nằm trong danh mục an toàn (whitelist).
- Nguyên tắc mạng:
  + Tuyệt đối KHÔNG sử dụng lệnh `telnet` (vì hệ điều hành Windows mặc định tắt tính năng này).
  + Luôn sử dụng lệnh PowerShell `Test-NetConnection`, kiểm tra socket TCP hoặc `curl`.
- Nguyên tắc an toàn dữ liệu:
  + Không gửi mã nguồn, tài liệu nội bộ hay thông tin cấu hình ra internet.

==============================================================================
2. HƯỚNG DẪN CÀI ĐẶT & SỬA LỖI CÁC CÔNG CỤ LẬP TRÌNH (SOFTWARE)
==============================================================================

------------------------------------------------------------------------------
2.0. HƯỚNG DẪN QUY CHUẨN CHUNG VỀ PHIÊN BẢN ỨNG DỤNG (VERSION AGNOSTIC GUIDELINES)
------------------------------------------------------------------------------
Mục này cung cấp quy chuẩn chung, triết lý vận hành và bộ công cụ xử lý phiên bản
cho TOÀN BỘ các ứng dụng lập trình, giúp mô hình Ollama Qwen 2.5:7b và lập trình viên
không bị đóng khung vào một phiên bản cố định, linh hoạt theo từng dự án.

--- 2.0.1. NGUYÊN TẮC CỐT LÕI: PHIÊN BẢN LINH HOẠT & TƯƠNG THÍCH NGƯỢC ---
1. Không cố định cứng (No Hardcoded Version):
   - Mọi dự án trong AI Buddy chỉ quy định:
     + Phiên bản tối thiểu (`min_version: "X.Y"`): Ngưỡng phiên bản thấp nhất đủ tính năng.
     + Hoặc Phiên bản khuyến nghị (Recommended Version): Bản đã được kiểm thử ổn định.
   - Các công cụ lập trình (Python, Node.js, Java, Docker, Git, Go, .NET...) liên tục
     phát hành các bản mới. Hướng dẫn này áp dụng được cho mọi phiên bản hiện tại và tương lai.

2. Quy chuẩn Semantic Versioning (SemVer):
   - Định dạng chuẩn: `MAJOR.MINOR.PATCH` (Ví dụ: `3.11.8`, `20.10.0`, `1.22.1`).
   - `MAJOR`: Thay đổi kiến trúc lớn, có khả năng phát sinh breaking change.
   - `MINOR`: Bổ sung tính năng mới, duy trì tương thích ngược (Backward Compatible).
   - `PATCH`: Sửa lỗi, vá bảo mật, hoàn toàn an toàn khi cập nhật.

3. Logic kiểm tra và đánh giá hợp lệ:
   - Công thức kiểm tra: `Phiên_bản_thực_tế_trên_máy >= Phiên_bản_tối_thiểu (min_version)`
   - NGUYÊN TẮC VÀNG CHO AI BUDDY / QWEN 2.5:7B:
     * Nếu máy người dùng ĐÃ CÀI ĐẶT phiên bản CAO HƠN hoặc TƯƠNG ĐƯƠNG (ví dụ: checklist
       yêu cầu Python >= 3.11, máy đang có 3.12 hoặc 3.13; checklist yêu cầu Node >= 18,
       máy đang có 20 hoặc 22; Docker >= 24, máy có 26...):
       => HỆ THỐNG GHI NHẬN ĐẠT (PASSED)!
       => TUYỆT ĐỐI KHÔNG bắt người dùng phải gỡ bỏ hay hạ cấp (downgrade) phiên bản!
     * Chỉ xem là KHÔNG ĐẠT (FAILED) khi:
       + Công cụ chưa được cài đặt trên máy (`Command not found` hoặc `where <app>` rỗng).
       + Phiên bản thực tế trên máy THẤP HƠN ngưỡng yêu cầu tối thiểu (`actual < min_version`).
       + Lỗi biến môi trường PATH khiến hệ điều hành không tìm thấy file thực thi.

--- 2.0.2. BỘ CÂU LỆNH TRA CỨU PHIÊN BẢN TỔNG QUÁT TRÊN WINDOWS ---
Khi cần kiểm tra phiên bản của bất kỳ ứng dụng nào, sử dụng các phương pháp chuẩn sau:

1. Kiểm tra qua Command Line Interface (CLI):
   <tên_lệnh> --version
   <tên_lệnh> -v
   <tên_lệnh> -V
   <tên_lệnh> version
   where <tên_lệnh>               (Xác định chính xác file thực thi đang chạy từ đâu)

2. Kiểm tra chính xác qua PowerShell (Trích xuất metadata file `.exe` trong PATH):
   # Lấy số phiên bản trực tiếp từ file nhị phân:
   (Get-Command <tên_lệnh> -ErrorAction SilentlyContinue).FileVersionInfo.ProductVersion
   
   # Hoặc:
   Get-Command <tên_lệnh> | Select-Object Name, Source, Version

3. Tra cứu danh sách phiên bản các phần mềm đã cài đặt trên Windows:
   # Qua Winget:
   winget list <tên_phần_mềm>
   
   # Qua Windows Registry (Kiểm tra phần mềm cài qua bộ cài .msi / .exe):
   Get-ItemProperty HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\* |
     Where-Object { $_.DisplayName -like "*<tên_phần_mềm>*" } |
     Select-Object DisplayName, DisplayVersion, InstallLocation

--- 2.0.3. BỘ CÚ PHÁP CÀI ĐẶT & NÂNG CẤP PHIÊN BẢN LINH HOẠT QUA PACKAGE MANAGERS ---
Không bao giờ tải file installer thủ công nếu có thể cài đặt tự động qua trình quản lý gói:

1. Trình quản lý gói chuẩn Windows (Winget):
   - Cài đặt phiên bản mới nhất / LTS ổn định:
     winget install -e --id <Mã_Gói>
   - Cài đặt một phiên bản cụ thể theo yêu cầu dự án:
     winget install -e --id <Mã_Gói> --version <Phiên_Bản_Mong_Muốn>
   - Tra cứu danh sách tất cả các phiên bản có sẵn trên kho để lựa chọn:
     winget show <Mã_Gói> --versions
   - Nâng cấp một công cụ lên bản mới nhất:
     winget upgrade -e --id <Mã_Gói>
   - Nâng cấp lên một phiên bản chỉ định:
     winget upgrade -e --id <Mã_Gói> --version <Phiên_Bản_Mới>
   - Nâng cấp toàn bộ phần mềm có trên máy:
     winget upgrade --all

2. Chocolatey (Dành cho máy sử dụng Choco):
   - Cài bản mới nhất:  choco install <tên_gói> -y
   - Cài bản cụ thể:   choco install <tên_gói> --version <x.y.z> -y
   - Nâng cấp:         choco upgrade <tên_gói> -y

3. Scoop (Dành cho lập trình viên thích cài không cần quyền Admin):
   - Cài bản mới nhất:  scoop install <tên_ứng_dụng>
   - Cài bản chỉ định:  scoop install <tên_ứng_dụng>@<phiên_bản>

--- 2.0.4. CẨM NANG QUẢN LÝ ĐA PHIÊN BẢN SONG SONG (VERSION MANAGERS & ISOLATION) ---
Trong môi trường doanh nghiệp, một lập trình viên thường phải tham gia nhiều dự án (dự án cũ
dùng bản LTS cũ, dự án mới dùng bản mới nhất). Giải pháp chuẩn mực là "CÁCH LY THEO THƯ MỤC
DỰ ÁN" (Project-Level Isolation), KHÔNG ghi đè PATH hệ thống bừa bãi:

1. Đối với Python:
   - Dùng Windows Python Launcher (`py.exe` - mặc định đi kèm khi cài Python trên Windows):
     py -0                              (Liệt kê mọi phiên bản Python đang có trên máy)
     py -3.10 -m venv .venv             (Tạo virtualenv với Python 3.10)
     py -3.11 -m venv .venv             (Tạo virtualenv với Python 3.11)
     py -3.12 -m venv .venv             (Tạo virtualenv với Python 3.12)
   - Kích hoạt môi trường ảo dự án:
     .\.venv\Scripts\Activate.ps1
   - Quản lý qua pyenv-win (chuyển đổi phiên bản tự động theo thư mục):
     winget install -e --id pyenv-win.pyenv-win
     pyenv install <version>            (Cài bất kỳ version nào, vd 3.10.11, 3.11.9, 3.12.3)
     pyenv local <version>              (Tạo file .python-version cố định cho thư mục này)

2. Đối với Node.js:
   - Dùng NVM for Windows (Node Version Manager):
     winget install -e --id CoreyButler.NVMforWindows
     nvm list available                 (Xem danh sách các bản Node có thể cài đặt)
     nvm install <version>              (Ví dụ: nvm install 18.20.0 hoặc nvm install 20.11.0)
     nvm list                           (Xem các bản đã tải về máy)
     nvm use <version>                  (Chuyển sang dùng phiên bản mong muốn)
   - Hoặc dùng FNM (Fast Node Manager - tốc độ cực nhanh):
     winget install -e --id Schniz.fnm
     fnm use <version> --install-if-missing

3. Đối với Java (JDK):
   - Cài đặt nhiều bản JDK (ví dụ JDK 11, 17, 21) vào các thư mục riêng biệt.
   - Chuyển đổi linh hoạt trong phiên làm việc PowerShell mà không ảnh hưởng toàn hệ thống:
     $env:JAVA_HOME = "C:\Program Files\Microsoft\jdk-17.0.10.7-hotspot"
     $env:Path = "$env:JAVA_HOME\bin;" + $env:Path
     java -version

4. Đối với .NET:
   - Tạo file `global.json` tại thư mục gốc dự án để khoá phiên bản SDK:
     dotnet new globaljson --sdk-version <version_yêu_cầu> --roll-forward latestFeature
   - Xem các phiên bản SDK đã cài đặt:
     dotnet --list-sdks

5. Đối với Golang:
   - Cài song song phiên bản phụ:
     go install golang.org/dl/go<version>@latest
     go<version> download
     go<version> version

--- 2.0.5. XỬ LÝ SỰ CỐ XUNG ĐỘT & BREAKING CHANGES GIỮA CÁC PHIÊN BẢN ---
- Tình huống 1: Thư viện dự án có module C-extension chưa biên dịch cho phiên bản runtime mới
  (Ví dụ: Dự án dùng thư viện chưa tương thích Python 3.13 hoặc Node 22).
  => Khắc phục: Không gỡ bản mới, mà cài thêm bản tương thích thấp hơn qua Version Manager
     (như `py -3.11 -m venv .venv` hoặc `nvm use 20.x`) để chạy riêng cho dự án đó.
- Tình huống 2: Phiên bản trên máy quá cũ (`actual_version < min_version`).
  => Khắc phục: Chạy `winget upgrade -e --id <Mã_Gói>` hoặc tải bản mới nhất. Các trình
     cài đặt hiện đại của Windows sẽ tự động cập nhật đè an toàn và giữ nguyên PATH.
- Tình huống 3: Windows gọi nhầm file thực thi của phiên bản cũ do thứ tự PATH.
  => Khắc phục: Chạy `where <tên_lệnh>` để xem thứ tự ưu tiên. Mở `sysdm.cpl` -> Environment
     Variables -> Đẩy đường dẫn thư mục phiên bản mong muốn lên trên đầu trong biến `Path`.

--- 2.0.6. KỊCH BẢN TƯ VẤN MẪU DÀNH CHO OLLAMA QWEN 2.5:7B KHI NGƯỜI DÙNG HỎI VỀ VERSION ---
Mô hình AI khi hỗ trợ người dùng cần áp dụng nghiêm ngặt các nguyên tắc sau:

* Kịch bản 1: Người dùng hỏi "Máy tôi đang cài Python 3.12 (hoặc Node 20 / Java 21), mà
  checklist yêu cầu Python >= 3.11 (hoặc Node >= 18 / Java >= 17), tôi có cần cài lại không?"
  -> Trả lời: "Bạn KHÔNG CẦN cài lại hay hạ cấp phiên bản! Phiên bản hiện tại trên máy bạn
     đã cao hơn yêu cầu tối thiểu (`>= min_version`) và hoàn toàn tương thích. Hệ thống
     AI Buddy sẽ tự động đánh giá mục này là ĐẠT (Passed). Bạn có thể tiếp tục tạo môi
     trường ảo hoặc chuyển sang mục tiếp theo."

* Kịch bản 2: Người dùng hỏi "Làm sao để cài phiên bản X.Y cụ thể mà dự án yêu cầu?"
  -> Trả lời: "Bạn có thể sử dụng Winget với cờ `--version` để cài chính xác bản bạn muốn:
     `winget install -e --id <Mã_Gói> --version <X.Y>`. Hoặc bạn có thể dùng Version Manager
     (như NVM cho Node, pyenv cho Python) để quản lý song song nhiều phiên bản."

* Kịch bản 3: Người dùng hỏi "Làm sao chạy được 2 phiên bản khác nhau cho 2 dự án trên cùng máy?"
  -> Trả lời: "Giải pháp tốt nhất là cô lập môi trường theo từng dự án:
     - Với Python: Dùng lệnh `py -<version> -m venv .venv` để tạo môi trường ảo riêng.
     - Với Node.js: Dùng `nvm use <version>` hoặc tạo file `.nvmrc` trong thư mục code.
     - Với .NET: Tạo file `global.json` bằng lệnh `dotnet new globaljson --sdk-version <version>`."


------------------------------------------------------------------------------
2.1. PYTHON (Python 3.x / Phiên bản theo yêu cầu dự án)
------------------------------------------------------------------------------
* Vai trò: Ngôn ngữ nền tảng xử lý hệ thống, API backend và AI LangChain.
* Câu lệnh kiểm tra:
  python --version
  py --version
  where python
  py -0  (Liệt kê tất cả các phiên bản Python đang có trên máy)

* Câu lệnh cài đặt linh hoạt trên Windows:
  - Cài bản mới nhất:
    winget install -e --id Python.Python.3
  - Cài bản chỉ định theo dự án (Ví dụ 3.11, 3.12...):
    winget install -e --id Python.Python.3.11
    (hoặc: winget install -e --id Python.Python.3 --version <version>)
  - Nâng cấp phiên bản:
    winget upgrade -e --id Python.Python.3
  - Cài qua Chocolatey:
    choco install python3 -y

* Quản lý nhiều phiên bản Python trên cùng một máy:
  - Sử dụng Python Launcher mặc định của Windows (`py.exe`):
    py -3.11 -m venv .venv        (Tạo virtual environment với Python 3.11)
    py -3.12 -m venv .venv        (Tạo virtual environment với Python 3.12)
  - Quản lý qua pyenv-win:
    winget install -e --id pyenv-win.pyenv-win
    pyenv install <version>
    pyenv local <version>

* Các lỗi thường gặp & Cách khắc phục:
  1. Lỗi: "'python' is not recognized as an internal or external command"
     - Nơi kiểm tra: `sysdm.cpl` -> Advanced -> Environment Variables -> `Path`.
     - Giải pháp: Thêm thư mục cài đặt Python và thư mục `Scripts` vào biến `Path`.
       (Ví dụ: `%LOCALAPPDATA%\Programs\Python\Python3xx\` và `%LOCALAPPDATA%\Programs\Python\Python3xx\Scripts\`).
  2. Lỗi: Gõ `python` tự động mở Microsoft Store:
     - Nơi kiểm tra: Windows Settings -> Apps -> Advanced app settings -> Execution aliases.
     - Giải pháp: Tắt (OFF) cả 2 mục "App Installer: python.exe" và "App Installer: python3.exe".

------------------------------------------------------------------------------
2.2. GIT (Quản lý mã nguồn)
------------------------------------------------------------------------------
* Vai trò: Quản lý mã nguồn, clone repository và làm việc với Git server nội bộ.
* Câu lệnh kiểm tra:
  git --version
  where git

* Câu lệnh cài đặt & nâng cấp:
  - Cài đặt mới nhất:
    winget install -e --id Git.Git
  - Nâng cấp Git lên bản mới nhất:
    git update-git-for-windows
    (hoặc: winget upgrade -e --id Git.Git)

* Các lỗi thường gặp & Cách khắc phục:
  1. Lỗi SSL Certificate (`SSL certificate problem: self signed certificate`):
     - Giải pháp tạm thời trong mạng nội bộ:
       git config --global http.sslVerify false
     - Giải pháp vĩnh viễn: Xuất file CA cert nội bộ và trỏ đường dẫn:
       git config --global http.sslCAInfo "C:/path/to/company-ca.crt"
  2. Lỗi Line Endings (CRLF vs LF):
     git config --global core.autocrlf true

------------------------------------------------------------------------------
2.3. NODE.JS & TRÌNH QUẢN LÝ GÓI (NPM / YARN / PNPM)
------------------------------------------------------------------------------
* Vai trò: Dành cho lập trình viên Frontend, chạy dev server, quản lý package UI.
* Câu lệnh kiểm tra:
  node -v
  npm -v
  where node

* Cài đặt linh hoạt:
  - Cài bản LTS mới nhất:
    winget install -e --id OpenJS.NodeJS.LTS
  - Quản lý đa phiên bản Node qua NVM Windows (Khuyên dùng):
    winget install -e --id CoreyButler.NVMforWindows
    nvm list available            (Xem các phiên bản có sẵn)
    nvm install <version_dự_án>   (Ví dụ: nvm install 18.20.0 hoặc nvm install 20.11.0)
    nvm use <version_dự_án>
  - Cài Yarn và PNPM:
    npm install -g yarn pnpm

* Lỗi thường gặp:
  1. Lỗi PowerShell chặn script `.ps1`:
     Mở PowerShell (Admin):
     Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned -Force
  2. Lỗi quyền ghi khi cài package global:
     npm config set prefix "%APPDATA%\npm-global"
     Thêm `%APPDATA%\npm-global` vào PATH.

------------------------------------------------------------------------------
2.4. DOCKER DESKTOP & DOCKER COMPOSE
------------------------------------------------------------------------------
* Vai trò: Chạy container microservices, database PostgreSQL cục bộ (`docker compose up -d db`).
* Câu lệnh kiểm tra:
  docker --version
  docker ps
  docker compose version

* Câu lệnh cài đặt & nâng cấp:
  - Cài đặt bản mới nhất:
    winget install -e --id Docker.DockerDesktop
  - Nâng cấp:
    winget upgrade -e --id Docker.DockerDesktop

* Lỗi thường gặp:
  1. `docker daemon is not running`: Khởi động ứng dụng Docker Desktop từ Start menu hoặc kiểm tra service `com.docker.service` trong `services.msc`.
  2. Lỗi ảo hóa phần cứng / WSL 2: Bật Virtualization trong BIOS/UEFI; chạy PowerShell (Admin): `wsl --install`, `wsl --update`, `wsl --set-default-version 2`.

------------------------------------------------------------------------------
2.5. OLLAMA & CÁC MÔ HÌNH AI LOCAL
------------------------------------------------------------------------------
* Vai trò: Chạy offline mô hình LLM Qwen-2.5 (`qwen2.5:7b`) và Embedding (`bge-m3`).
* Câu lệnh kiểm tra:
  ollama --version
  ollama list
  curl http://127.0.0.1:11434/api/tags

* Cài đặt & Tải mô hình:
  winget install -e --id Ollama.Ollama
  ollama pull qwen2.5:7b
  ollama pull bge-m3

* Lỗi thường gặp: Service chưa bật (chạy `ollama serve`); lỗi tràn VRAM GPU (xem log tại `%LOCALAPPDATA%\Ollama\server.log`, giảm kích thước batch).

------------------------------------------------------------------------------
2.6. JAVA DEVELOPMENT KIT (JDK) & MAVEN / GRADLE
------------------------------------------------------------------------------
* Vai trò: Xây dựng ứng dụng backend Java Spring Boot, microservices nền tảng.
* Câu lệnh kiểm tra:
  java -version
  javac -version
  mvn -v
  gradle -v

* Cài đặt linh hoạt qua Winget:
  - Cài bản mới nhất:
    winget install -e --id Microsoft.OpenJDK
    (hoặc Eclipse Temurin: `winget install -e --id EclipseAdoptium.Temurin.21.JDK`)
  - Cài phiên bản cụ thể (Ví dụ 17, 21...):
    winget install -e --id Microsoft.OpenJDK.<version>
  - Cài Maven:
    winget install -e --id Apache.Maven

* Lỗi thường gặp: `JAVA_HOME is not set`:
  Vào `sysdm.cpl` -> Environment Variables -> Tạo System variable `JAVA_HOME` trỏ tới thư mục JDK (ví dụ `C:\Program Files\Microsoft\jdk-21\`) và thêm `%JAVA_HOME%\bin` vào `Path`.

------------------------------------------------------------------------------
2.7. GO / GOLANG
------------------------------------------------------------------------------
* Vai trò: Xây dựng microservices hiệu năng cao, backend API, tooling.
* Câu lệnh kiểm tra:
  go version
  go env GOPATH
  go env GOROOT

* Cài đặt:
  winget install -e --id GoLang.Go
  (Hoặc nâng cấp: `winget upgrade -e --id GoLang.Go`)

* Cấu hình tối ưu:
  go env -w GOPROXY=https://proxy.golang.org,direct
  go env -w GO111MODULE=on
  Thêm `%USERPROFILE%\go\bin` vào biến PATH.

------------------------------------------------------------------------------
2.8. .NET SDK
------------------------------------------------------------------------------
* Vai trò: Phát triển backend C# / ASP.NET Core microservices.
* Câu lệnh kiểm tra:
  dotnet --version
  dotnet --list-sdks

* Cài đặt linh hoạt:
  - Cài bản mới nhất:
    winget install -e --id Microsoft.DotNet.SDK
  - Cài bản chỉ định theo dự án (ví dụ .NET 6, .NET 8, .NET 9...):
    winget install -e --id Microsoft.DotNet.SDK --version <version>
    (hoặc qua alias: winget install -e --id Microsoft.DotNet.SDK.8)

* Quản lý phiên bản SDK theo từng dự án:
  Đặt file `global.json` tại thư mục dự án:
    {
      "sdk": {
        "version": "<version_dự_án>",
        "rollForward": "latestFeature"
      }
    }
  Tin cậy chứng chỉ HTTPS dev: `dotnet dev-certs https --trust`.

------------------------------------------------------------------------------
2.9. VISUAL STUDIO CODE & TIỆN ÍCH LẬP TRÌNH
------------------------------------------------------------------------------
* Câu lệnh kiểm tra: `code --version`, `where code`
* Cài đặt: `winget install -e --id Microsoft.VisualStudioCode`
* Extension khuyên dùng:
  code --install-extension ms-python.python
  code --install-extension ms-azuretools.vscode-docker
  code --install-extension eamodio.gitlens
  code --install-extension dbaeumer.vscode-eslint
  code --install-extension esbenp.prettier-vscode
* Lỗi: `code .` không nhận lệnh -> Mở VS Code -> Ctrl+Shift+P -> `Shell Command: Install 'code' command in PATH`.

------------------------------------------------------------------------------
2.10. JETBRAINS IDE (INTELLIJ IDEA, PYCHARM)
------------------------------------------------------------------------------
* Cài đặt qua Winget:
  - IntelliJ IDEA: `winget install -e --id JetBrains.IntelliJIDEA.Community`
  - PyCharm: `winget install -e --id JetBrains.PyCharm.Community`
  - JetBrains Toolbox: `winget install -e --id JetBrains.Toolbox`
* Xử lý lỗi: File -> Project Structure -> Chọn đúng SDK mong muốn. Khi cache lỗi: File -> Invalidate Caches -> Invalidate and Restart.

------------------------------------------------------------------------------
2.11. QUẢN LÝ CƠ SỞ DỮ LIỆU (DBEAVER, POSTGRESQL CLIENT PSQL)
------------------------------------------------------------------------------
* Câu lệnh kiểm tra: `psql --version`
* Cài đặt:
  - DBeaver Community: `winget install -e --id dbeaver.dbeaver`
  - PostgreSQL CLI / Server:
    Cài bản mới nhất: `winget install -e --id PostgreSQL.PostgreSQL`
    Cài bản chỉ định (ví dụ 14, 15, 16): `winget install -e --id PostgreSQL.PostgreSQL --version <version>`
* Khắc phục: Khi chạy offline không tải được JDBC driver trong DBeaver, tải sẵn file `.jar` và nạp thủ công vào Local Driver Settings.

------------------------------------------------------------------------------
2.12. CÔNG CỤ KIỂM THỬ API (POSTMAN, INSOMNIA, CURL)
------------------------------------------------------------------------------
* Cài đặt:
  - Postman: `winget install -e --id Postman.Postman`
  - Insomnia: `winget install -e --id Insomnia.Insomnia`
* Xử lý: Tắt "SSL certificate verification" trong Settings khi test các API chạy HTTPS nội bộ có chứng chỉ tự ký.

------------------------------------------------------------------------------
2.13. WINDOWS TERMINAL & POWERSHELL 7
------------------------------------------------------------------------------
* Cài đặt:
  winget install -e --id Microsoft.WindowsTerminal
  winget install -e --id Microsoft.PowerShell
* Kiểm tra: `pwsh --version`

==============================================================================
3. HƯỚNG DẪN KIỂM TRA MẠNG NỘI BỘ VÀ KẾT NỐI RA NGOÀI INTERNET (HOST_REACHABLE)
==============================================================================

LƯU Ý ĐẶC BIỆT: Windows thường tắt sẵn Telnet, do đó AI Buddy KHÔNG DÙNG lệnh `telnet`.
Luôn sử dụng lệnh PowerShell `Test-NetConnection` hoặc socket TCP.

------------------------------------------------------------------------------
3.1. DỊCH VỤ OLLAMA LOCAL (127.0.0.1:11434)
------------------------------------------------------------------------------
* Câu lệnh kiểm tra:
  Test-NetConnection -ComputerName 127.0.0.1 -Port 11434
  curl -I http://127.0.0.1:11434
* Giải pháp khi thất bại: Khởi động Ollama bằng lệnh `ollama serve`.

------------------------------------------------------------------------------
3.2. GIT SERVER NỘI BỘ (git.company.local:443)
------------------------------------------------------------------------------
* Câu lệnh kiểm tra:
  Test-NetConnection -ComputerName git.company.local -Port 443
  nslookup git.company.local
* Giải pháp khi thất bại: Bật VPN nội bộ, kiểm tra DNS công ty hoặc làm thủ tục xin cấp quyền IP (Mục 5).

------------------------------------------------------------------------------
3.3. DATABASE POSTGRESQL DEV (db.company.local:5432)
------------------------------------------------------------------------------
* Câu lệnh kiểm tra:
  Test-NetConnection -ComputerName db.company.local -Port 5432
* Giải pháp khi thất bại: Kiểm tra VPN, kiểm tra Firewall chặn port 5432 hoặc xin cấp quyền IP.

------------------------------------------------------------------------------
3.4. KHO MÃ NGUỒN CÔNG KHAI NGOÀI INTERNET (GITHUB.COM, GITLAB.COM)
------------------------------------------------------------------------------
* Câu lệnh kiểm tra:
  PowerShell:
    Test-NetConnection -ComputerName github.com -Port 443
    Test-NetConnection -ComputerName api.github.com -Port 443
    Test-NetConnection -ComputerName gitlab.com -Port 443
  Kiểm tra cổng SSH (Port 22):
    Test-NetConnection -ComputerName github.com -Port 22
  CMD / cURL:
    curl -I https://github.com

* Các lỗi thường gặp & Cách khắc phục:
  1. Lỗi cổng SSH 22 bị tường lửa công ty chặn:
     - Biểu hiện: `ssh: connect to host github.com port 22: Connection timed out`.
     - Giải pháp: Chuyển sang dùng SSH qua cổng 443 của GitHub bằng cách cấu hình file `~/.ssh/config`:
       Host github.com
           Hostname ssh.github.com
           Port 443
           User git
     - Kiểm tra lại: `ssh -T -p 443 git@ssh.github.com`.
  2. Lỗi Clone qua HTTPS bị yêu cầu Personal Access Token (PAT):
     - Biểu hiện: `remote: Support for password authentication was removed on August 13, 2021`.
     - Giải pháp: Tạo Token tại GitHub Settings -> Developer settings -> Personal access tokens (classic), cấp quyền `repo` và dùng token này làm mật khẩu khi git hỏi.

------------------------------------------------------------------------------
3.5. KHO THƯ VIỆN GÓI CÔNG KHAI (PYPI, NPM, DOCKER HUB, MAVEN, GO PROXY)
------------------------------------------------------------------------------
* Danh sách Host & Port kiểm tra:
  1. Python PyPI:
     - Host: `pypi.org:443` và `files.pythonhosted.org:443`
     - Test: `Test-NetConnection -ComputerName pypi.org -Port 443`
     - Lệnh test thực tế: `pip install --dry-run requests`
  2. Node.js NPM Registry:
     - Host: `registry.npmjs.org:443`
     - Test: `Test-NetConnection -ComputerName registry.npmjs.org -Port 443`
     - Lệnh test thực tế: `npm ping`
  3. Docker Hub:
     - Host: `registry-1.docker.io:443` và `auth.docker.io:443`
     - Test: `Test-NetConnection -ComputerName registry-1.docker.io -Port 443`
     - Lệnh test thực tế: `docker pull hello-world`
  4. Maven Central:
     - Host: `repo1.maven.org:443`
     - Test: `Test-NetConnection -ComputerName repo1.maven.org -Port 443`
  5. Go Module Proxy:
     - Host: `proxy.golang.org:443`
     - Test: `Test-NetConnection -ComputerName proxy.golang.org -Port 443`

* Các lỗi thường gặp khi tải thư viện từ bên ngoài:
  1. Lỗi `pip install` báo `SSL: CERTIFICATE_VERIFY_FAILED`:
     - Nguyên nhân: Phần mềm diệt virus hoặc tường lửa mạng công ty thực hiện SSL Deep Packet Inspection (quét chứng chỉ HTTPS) bằng chứng chỉ tự ký.
     - Giải pháp tạm thời:
       pip install <tên_gói> --trusted-host pypi.org --trusted-host files.pythonhosted.org
     - Giải pháp vĩnh viễn: Cấu hình file `%APPDATA%\pip\pip.ini`:
       [global]
       trusted-host = pypi.org
                      files.pythonhosted.org
  2. Lỗi `npm install` báo `unable to get local issuer certificate`:
     - Giải pháp tạm thời:
       npm config set strict-ssl false
     - Giải pháp chuẩn: Thêm chứng chỉ công ty vào npm:
       npm config set cafile "C:/path/to/company-root-ca.crt"
  3. Lỗi Docker Hub: `toomanyrequests: You have reached your pull rate limit`:
     - Nguyên nhân: Docker Hub giới hạn số lần pull đối với người dùng ẩn danh (anonymous IP).
     - Giải pháp: Đăng nhập tài khoản Docker Hub miễn phí:
       docker login -u <username>

------------------------------------------------------------------------------
3.6. DỊCH VỤ HẠ TẦNG CLOUD & DNS CÔNG CỘNG
------------------------------------------------------------------------------
* Dịch vụ DNS ngoài:
  - Google DNS: `8.8.8.8:53`
  - Cloudflare DNS: `1.1.1.1:53`
  - Câu lệnh kiểm tra:
    Test-NetConnection -ComputerName 8.8.8.8 -Port 53
    nslookup google.com 8.8.8.8
* Dịch vụ AWS Cloud / S3:
  - Host: `s3.amazonaws.com:443`
  - Test: `Test-NetConnection -ComputerName s3.amazonaws.com -Port 443`

------------------------------------------------------------------------------
3.7. CÁC LỖI KẾT NỐI MẠNG BÊN NGOÀI THƯỜNG GẶP VÀ GIẢI PHÁP CHI TIẾT
------------------------------------------------------------------------------
1. Lỗi mạng công ty bắt buộc dùng Corporate Proxy (HTTP/HTTPS Proxy):
   - Biểu hiện: Vào web bằng trình duyệt bình thường nhưng chạy terminal (curl, git, pip, npm) đều báo Connection Refused hoặc Timeout.
   - Nơi kiểm tra:
     + Mở Run (`Win + R`) -> gõ `inetcpl.cpl` -> Chọn tab Connections -> Bấm LAN settings -> Xem mục Proxy server.
     + Hoặc xem biến môi trường: `echo %HTTP_PROXY%`, `echo %HTTPS_PROXY%`.
   - Giải pháp: Thiết lập Proxy cho các công cụ:
     + Trong PowerShell tạm thời:
       $env:HTTP_PROXY="http://proxy.company.com:8080"
       $env:HTTPS_PROXY="http://proxy.company.com:8080"
       $env:NO_PROXY="localhost,127.0.0.1,.company.local"
     + Cho Git:
       git config --global http.proxy http://proxy.company.com:8080
       git config --global https.proxy http://proxy.company.com:8080
     + Cho NPM:
       npm config set proxy http://proxy.company.com:8080
       npm config set https-proxy http://proxy.company.com:8080

2. Lỗi VPN Split Tunneling làm mất mạng ngoài:
   - Biểu hiện: Khi bật VPN kết nối vào công ty thì vào được Git nội bộ nhưng KHÔNG THỂ lướt web, không tải được pip/npm từ internet ngoài.
   - Nguyên nhân: VPN cấu hình Full-Tunnel chuyển toàn bộ default gateway về mạng công ty, trong khi gateway công ty chặn internet trực tiếp.
   - Nơi kiểm tra:
     Mở CMD gõ: `route print` -> Xem phần Default Gateway `0.0.0.0`.
   - Giải pháp: Liên hệ IT Network cấu hình lại Client VPN ở chế độ "Split-Tunneling" (chỉ điều hướng dải IP nội bộ qua VPN, còn lại giữ kết nối mạng gốc).

==============================================================================
4. HƯỚNG DẪN KIỂM TRA & GIẢI PHÓNG PORT XUNG ĐỘT (PORT_FREE)
==============================================================================

Dự án AI Buddy và ứng dụng microservices sử dụng các cổng mặc định:
- Port 8000: Backend API cục bộ của AI Buddy (FastAPI / Uvicorn).
- Port 3000: Frontend dev server (Vite / React).
- Port 8080: API Gateway của hệ thống.
- Port 5432: PostgreSQL local (Docker).

------------------------------------------------------------------------------
4.1. CÁCH TÌM TIẾN TRÌNH ĐANG CHIẾM PORT TRÊN WINDOWS
------------------------------------------------------------------------------
Cách 1: Sử dụng CMD:
  netstat -ano | findstr :8000
  (Cột cuối cùng hiển thị là mã PID - Process ID của tiến trình đang chiếm port).

  Sau đó kiểm tra tên tiến trình chiếm port bằng PID:
  tasklist /fi "pid eq <MÃ_PID>"

Cách 2: Sử dụng PowerShell (Khuyên dùng):
  Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select-Object LocalPort, State, OwningProcess

  Xem chi tiết tiến trình:
  Get-Process -Id <MÃ_PID> | Select-Object Id, ProcessName, Path

------------------------------------------------------------------------------
4.2. CÁCH TẮT TIẾN TRÌNH CHIẾM PORT AN TOÀN
------------------------------------------------------------------------------
- Tắt bằng lệnh CMD:
  taskkill /PID <MÃ_PID> /F

- Tắt bằng lệnh PowerShell:
  Stop-Process -Id <MÃ_PID> -Force

------------------------------------------------------------------------------
4.3. XỬ LÝ TRƯỜNG HỢP PORT BỊ WINDOWS HYPER-V / WINNAT CHIẾM GIỮ
------------------------------------------------------------------------------
* Biểu hiện: Khi chạy ứng dụng báo `OSError: [WinError 10013] An attempt was made to access a socket in a way forbidden by its access permissions`, nhưng khi kiểm tra `netstat` lại KHÔNG THẤY tiến trình nào đang chạy trên port đó!
* Nguyên nhân: Tính năng ảo hóa Hyper-V hoặc dịch vụ WinNAT của Windows đã tự động đặt dải cổng này vào "Excluded Port Range".
* Nơi kiểm tra:
  netsh interface ipv4 show excludedportrange protocol=tcp
* Giải pháp khắc phục:
  Restart lại service WinNAT của Windows bằng quyền Admin:
    PowerShell (Run as Administrator):
      net stop winnat
      net start winnat
    Sau đó khởi động lại ứng dụng.

==============================================================================
5. QUY TRÌNH XIN CẤP QUYỀN TRUY CẬP IP (IP ACCESS REQUEST PROCESS)
==============================================================================

Khi kiểm tra một checklist item thuộc loại `HOST_REACHABLE` mà bị Timeout hoặc Không kết nối được, người dùng cần làm theo quy trình 4 bước chuẩn của dự án:

Bước 1: Lấy địa chỉ IP chính xác của máy tính cá nhân:
  - Mở PowerShell gõ lệnh:
    ipconfig
  - Tìm card mạng bạn đang kết nối:
    + Nếu cắm dây mạng: Tìm mục "Ethernet adapter Ethernet" -> Xem dòng "IPv4 Address" (Ví dụ: 192.168.1.45 hoặc 10.x.x.x).
    + Nếu dùng Wifi: Tìm mục "Wireless LAN adapter Wi-Fi" -> Xem dòng "IPv4 Address".
    + Nếu đang bật VPN công ty: Tìm card mạng VPN (thường có tên công ty hoặc AnyConnect) -> Lấy IPv4 Address của card VPN.

Bước 2: Chuẩn bị thông tin tạo ticket IT:
  - Tiêu đề: "[Access Request] Xin mở quyền truy cập IP máy cá nhân"
  - IP nguồn (Source IP): Địa chỉ IPv4 lấy được ở Bước 1.
  - Host/IP đích (Destination Host/IP): Tên miền hoặc IP dịch vụ (Ví dụ: `db.company.local`, `git.company.local` hoặc external endpoint).
  - Port đích (Destination Port): Ví dụ Port 5432 (Postgres), Port 443 (Git), Port 8080.
  - Giao thức: TCP.
  - Dự án / Mục đích: Onboarding dự án AI Buddy / Phát triển tính năng.
  - Thời hạn yêu cầu: 3 tháng / 6 tháng hoặc Dài hạn theo dự án.

Bước 3: Gửi ticket và xin phê duyệt:
  - Tạo ticket trên hệ thống Helpdesk / Jira IT nội bộ (loại issue: Access Request).
  - Tag Tech Lead / Mentor phê duyệt. Thời gian phản hồi tiêu chuẩn (SLA): 1 ngày làm việc.

Bước 4: Xác nhận và kiểm tra lại:
  - Sau khi IT Network thông báo đã mở rule firewall thành công, quay trở lại ứng dụng AI Buddy.
  - Bấm nút icon "Kiểm tra lại" (Refresh) trên thẻ checklist tương ứng.
  - Hoặc gõ lệnh trong Chat AI Buddy: `kiểm tra <host>:<port>` để xác nhận kết nối xanh (Passed).

==============================================================================
6. BẢNG TRA CỨU NHANH SỰ CỐ TOÀN DIỆN (TROUBLESHOOTING MATRIX CHO QWEN 2.5:7B)
==============================================================================

+----------------------------+---------------------------------+----------------------------------------+------------------------------------------+
| Mục Checklist / Công cụ    | Lỗi Gặp Phải                   | Nguyên Nhân                            | Lệnh / Nơi Kiểm Tra & Giải Pháp          |
+----------------------------+---------------------------------+----------------------------------------+------------------------------------------+
| Python                     | 'python' is not recognized      | Chưa tick "Add to PATH" lúc cài đặt   | Win+R -> sysdm.cpl -> Environment Var   |
| (Chưa cài hoặc < min_ver)  | hoặc phiên bản thấp hơn yêu cầu | Cần thêm vào PATH hoặc nâng cấp bản mới| Thêm Python và Scripts vào PATH.         |
|                            |                                 |                                        | winget install Python.Python.3           |
|                            |                                 |                                        | Hoặc: winget upgrade Python.Python.3     |
+----------------------------+---------------------------------+----------------------------------------+------------------------------------------+
| Python                     | Gõ python mở Microsoft Store    | Windows App Execution Aliases đang bật | Settings -> Apps -> Execution Aliases    |
|                            |                                 |                                        | Tắt 2 mục App Installer python.exe.      |
+----------------------------+---------------------------------+----------------------------------------+------------------------------------------+
| Git                        | SSL certificate error           | Chưa tin cậy chứng chỉ CA nội bộ       | git config --global http.sslVerify false |
|                            |                                 |                                        | Hoặc trỏ http.sslCAInfo tới file CA.crt. |
+----------------------------+---------------------------------+----------------------------------------+------------------------------------------+
| Node.js                    | PSSecurityException /           | PowerShell chặn chạy script .ps1       | PowerShell (Admin):                      |
|                            | ExecutionPolicy disabled        |                                        | Set-ExecutionPolicy RemoteSigned -Scope  |
|                            | hoặc cần đổi phiên bản dự án   | Cần đổi version bằng NVM               | CurrentUser -Force                       |
|                            |                                 |                                        | nvm install <ver> && nvm use <ver>       |
+----------------------------+---------------------------------+----------------------------------------+------------------------------------------+
| Docker Desktop             | Docker daemon is not running    | Docker Desktop chưa bật                | Start-Process Docker Desktop.exe         |
|                            |                                 |                                        | Run: services.msc xem com.docker.service |
+----------------------------+---------------------------------+----------------------------------------+------------------------------------------+
| Docker Desktop             | WSL 2 kernel update needed      | Chưa cài gói Linux Kernel cho WSL 2    | PowerShell (Admin): wsl --update         |
|                            | Virtualization disabled         | Chưa bật ảo hóa trong BIOS/UEFI        | Task Manager -> Performance -> CPU       |
+----------------------------+---------------------------------+----------------------------------------+------------------------------------------+
| Ollama                     | Port 11434 không phản hồi       | Dịch vụ Ollama chưa chạy ngầm          | CMD: ollama serve                        |
|                            |                                 |                                        | Taskbar Tray: Mở biểu tượng Ollama       |
+----------------------------+---------------------------------+----------------------------------------+------------------------------------------+
| Ollama                     | Thiếu mô hình AI                | Chưa pull model qwen2.5 hoặc bge-m3    | ollama pull qwen2.5:7b                   |
|                            |                                 |                                        | ollama pull bge-m3                       |
+----------------------------+---------------------------------+----------------------------------------+------------------------------------------+
| Java JDK                   | JAVA_HOME is not set            | Chưa cấu hình biến môi trường JDK      | sysdm.cpl -> Đặt JAVA_HOME tới thư mục   |
|                            | hoặc cần chuyển đổi bản JDK     | Cần trỏ đúng phiên bản dự án           | JDK mong muốn; thêm %JAVA_HOME%\bin Path.|
+----------------------------+---------------------------------+----------------------------------------+------------------------------------------+
| Golang                     | go module download timeout      | Kết nối trực tiếp bị chặn hoặc chậm    | go env -w GOPROXY=https://proxy.golang.org|
+----------------------------+---------------------------------+----------------------------------------+------------------------------------------+
| .NET SDK                   | Untrusted dev cert              | Thiếu chứng chỉ SSL dev cục bộ         | dotnet dev-certs https --trust           |
+----------------------------+---------------------------------+----------------------------------------+------------------------------------------+
| VS Code                    | 'code' command not found        | Chưa thêm CLI code vào PATH            | VS Code: Ctrl+Shift+P -> Shell Command:  |
|                            |                                 |                                        | Install 'code' command in PATH           |
+----------------------------+---------------------------------+----------------------------------------+------------------------------------------+
| DBeaver / psql             | Connection refused              | Dịch vụ DB chưa bật                    | Kiểm tra Docker: docker ps               |
|                            |                                 |                                        | Kiểm tra kết nối Test-NetConnection      |
+----------------------------+---------------------------------+----------------------------------------+------------------------------------------+
| Port 8000/3000/8080        | Port đang bị chiếm              | Tiến trình khác đang listen port       | CMD: netstat -ano | findstr :<port>      |
|                            |                                 |                                        | taskkill /PID <PID> /F                   |
+----------------------------+---------------------------------+----------------------------------------+------------------------------------------+
| Port 8000/3000/8080        | WinError 10013 nhưng netstat    | Hyper-V / WinNAT giữ dải port riêng    | netsh interface ipv4 show excludedport   |
|                            | không thấy tiến trình chiếm     |                                        | PowerShell (Admin): net stop winnat &&   |
|                            |                                 |                                        | net start winnat                         |
+----------------------------+---------------------------------+----------------------------------------+------------------------------------------+
| Git server:443             | Không kết nối được              | Chưa bật VPN hoặc chưa whitelist IP    | Bật VPN nội bộ.                          |
| DB Dev:5432                | Connection timed out            | Chưa có quyền firewall                 | Lấy IP (ipconfig) -> Gửi ticket IT xin   |
|                            |                                 |                                        | cấp quyền truy cập theo quy trình mục 5. |
+----------------------------+---------------------------------+----------------------------------------+------------------------------------------+
| GitHub.com:22 (SSH)        | Port 22 Connection timed out    | Tường lửa công ty chặn cổng SSH 22     | Cấu hình ~/.ssh/config trỏ hostname về   |
|                            |                                 |                                        | ssh.github.com và Port 443.              |
+----------------------------+---------------------------------+----------------------------------------+------------------------------------------+
| PyPI / NPM ngoài           | CERTIFICATE_VERIFY_FAILED       | Tường lửa quét SSL / Proxy công ty     | pip install --trusted-host pypi.org      |
|                            |                                 |                                        | npm config set strict-ssl false          |
+----------------------------+---------------------------------+----------------------------------------+------------------------------------------+
| Docker Hub                 | Rate limit reached              | Giới hạn lượt pull ẩn danh             | docker login -u <username>               |
+----------------------------+---------------------------------+----------------------------------------+------------------------------------------+
| Mạng Internet ngoài        | Proxy Authentication Required   | Mạng công ty yêu cầu khai báo Proxy    | Thiết lập HTTP_PROXY và HTTPS_PROXY      |
|                            | (HTTP 407)                      |                                        | Kiểm tra trong inetcpl.cpl LAN Settings  |
+----------------------------+---------------------------------+----------------------------------------+------------------------------------------+

==============================================================================
LƯU Ý DÀNH CHO OLLAMA QWEN 2.5:7B KHI TƯ VẤN:
- Giữ câu trả lời bằng tiếng Việt, súc tích, trình bày rõ từng bước (1, 2, 3).
- ÁP DỤNG TRIỆT ĐỂ NGUYÊN TẮC PHIÊN BẢN LINH HOẠT (VERSION AGNOSTIC):
  + Nếu máy người dùng đã có phiên bản cao hơn hoặc tương đương yêu cầu tối thiểu (`actual >= min_version`), khẳng định ngay là ĐÃ ĐẠT TIÊU CHUẨN, KHÔNG BẮT HẠ CẤP (downgrade).
  + Không bao giờ áp đặt phiên bản cố định cứng; luôn cung cấp cú pháp linh hoạt:
    * Cài bản mới nhất: `winget install -e --id <ID>`
    * Cài bản chỉ định: `winget install -e --id <ID> --version <version>`
  + Khi người dùng cần dùng nhiều phiên bản song song, luôn tư vấn sử dụng Version Manager (`pyenv-win` / `venv`, `nvm-windows`, `global.json`, `JAVA_HOME`) theo thư mục dự án.
- Cung cấp sẵn câu lệnh CMD hoặc PowerShell cụ thể (có thể copy-paste chạy ngay).
- Nhắc nhở người dùng: Đối với thao tác cài đặt phần mềm, AI Buddy có thể hỗ trợ chạy tự động sau khi người dùng bấm xác nhận trên màn hình.
# ==============================================================================


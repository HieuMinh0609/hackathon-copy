# Kiến trúc hệ thống (Microservices)

- **API Gateway** (port 8080): cổng vào duy nhất, định tuyến request.
- **Auth Service**: đăng nhập, phân quyền (JWT).
- **User Service**: quản lý hồ sơ người dùng.
- **Backend API** (port 8000): nghiệp vụ chính.
- **Frontend** (port 3000 khi dev).
- **Database**: PostgreSQL dev tại `db.company.local:5432`.

Giao tiếp giữa các service qua REST; sự kiện bất đồng bộ qua message queue.

(Dữ liệu mẫu.)

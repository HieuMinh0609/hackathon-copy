# Luồng phân quyền user theo từng dự án

## Mục tiêu

Quyền `PROJECT_LEAD` không phải thuộc tính toàn cục của user. Một user có thể là `PROJECT_LEAD` trong dự án A và `MEMBER` trong dự án B.

## Mô hình dữ liệu

| Cột | Ý nghĩa |
|---|---|
| `roles.key_role` | Khóa quyền ổn định: `TEAM_LEAD`, `PROJECT_LEAD`, `MEMBER` |
| `users.role_id` | Quyền hệ thống của user |
| `users.job_title` | Chức danh/cấp bậc chuyên môn, không dùng để phân quyền |
| `user_checklists.role_id` | Cột tương thích dữ liệu cũ; quyền dự án không đọc từ cột này |
| `user_checklists.project_role_id` | Quyền của user trong riêng dự án đó: `PROJECT_LEAD` hoặc `MEMBER` |

Chức danh và quyền phải được chọn độc lập. Việc nâng user thành Project Lead không được làm mất `job_title` QA/Backend/BA của user.

## Luồng xác thực và phân quyền

1. Session key xác định user; header email không được ghi đè danh tính session.
2. Backend join `users.role_id -> roles.key_role`.
3. Nếu key là `TEAM_LEAD`, cho phép thao tác toàn hệ thống.
4. Với thao tác có `project_code`, backend join `user_checklists.project_role_id -> roles.key_role` của đúng user và đúng project.
5. Chỉ cho phép quản lý project khi assignment có key `PROJECT_LEAD`.
6. Không có `project_code` thì Project Lead không nhận quyền toàn hệ thống.
7. `TEAM_LEAD` là admin toàn cục; Project Lead không được thêm hoặc xóa Team Lead khỏi dự án.

## Luồng gán thành viên

Request thêm member chỉ gửi quyền của user trong dự án:

```json
{
  "user_email": "qa@example.com",
  "project_role_key": "PROJECT_LEAD"
}
```

- `project_role_key` chỉ nhận `PROJECT_LEAD` hoặc `MEMBER`.
- Chức danh được lấy từ `users.job_title`; luồng gán dự án không hiển thị hoặc cập nhật trường này.
- Thêm lại user đã có trong project sẽ cập nhật quyền nhưng giữ nguyên `started_at` và `due_at`.

## Luồng giao diện

Dialog quản lý thành viên chỉ có dropdown **Quyền trong dự án**: Member hoặc Project Lead. Chức danh không xuất hiện trong luồng thêm thành viên.

## Ma trận bắt buộc

| User | Project A | Project B | Kết quả |
|---|---|---|---|
| U1 | `PROJECT_LEAD` | `MEMBER` | Quản lý A, chỉ thực thi B |
| U2 | `MEMBER` | Không tham gia | Chỉ thực thi A, không xem B |
| Team Lead | Bất kỳ | Bất kỳ | Quản lý toàn bộ |

Test phải kiểm tra cả service và API để tránh frontend disabled nút nhưng backend vẫn cho phép truy cập chéo dự án.

# Luồng theo dõi tiến độ và rủi ro onboarding

Tài liệu này mô tả luồng leader theo dõi thành viên có nguy cơ chậm onboarding trên Dashboard.

## 1. Phân quyền

| Quyền | Phạm vi xem rủi ro | Tạo dự án | Quản lý thành viên |
|---|---|---|---|
| `TEAM_LEAD` | Tất cả dự án | Có | Có |
| `PROJECT_LEAD` | Chỉ dự án được giao | Không | Có, trong dự án được giao |
| `MEMBER` | Chỉ xem deadline của chính mình | Không | Không |

Role chuyên môn trong bảng `roles` không được dùng để suy ra quyền xem rủi ro.

## 2. Dữ liệu đầu vào

Backend tính trạng thái từ bảng `user_checklists`:

- `started_at`: thời điểm member được thêm vào dự án.
- `due_at`: hạn onboarding đã chốt cho member.
- `progress`: tiến độ thực tế, từ 0 đến 100.
- `status`: trạng thái checklist, trong đó `COMPLETED` là đã hoàn thành.
- `onboarding_template.duration_days`: thời lượng mặc định khi giao onboarding.

Dữ liệu cũ thiếu `started_at` dùng `created_at`. Hạn đã giao không bị thay đổi khi project đổi `duration_days`.

## 3. Quy tắc tính trạng thái

Backend là nguồn sự thật duy nhất. Frontend không tự suy diễn trạng thái.

1. `completed`: checklist có status `COMPLETED`.
2. `overdue`: chưa hoàn thành và thời điểm hiện tại đã qua `due_at`.
3. `at_risk`: chưa hoàn thành và thỏa một trong hai điều kiện:
   - Còn không quá 3 ngày; hoặc
   - Đã trôi qua ít nhất 20% thời hạn và tiến độ thực tế thấp hơn tiến độ kỳ vọng từ 20 điểm phần trăm.
4. `on_track`: đang còn hạn và không thuộc nhóm nguy cơ.
5. `not_started`: chưa có đủ mốc thời gian để đánh giá.

Tiến độ kỳ vọng được tính tuyến tính:

```text
expected_progress = elapsed_time / (due_at - started_at) * 100
```

## 4. Luồng API JSON

### Danh sách dự án

1. Dashboard gọi `GET /api/v1/projects` bằng session đã xác thực.
2. Backend giới hạn dự án theo quyền và assignment.
3. Với leader, mỗi dự án trả thêm:

```json
{
  "member_count": 8,
  "risk_count": 2,
  "overdue_count": 1
}
```

Member nhận các giá trị tổng hợp bằng 0 để không lộ tiến độ của người khác.

### Danh sách thành viên

1. Leader bấm **Thành viên** trên thẻ dự án.
2. Frontend gọi `GET /api/v1/projects/{project_code}/members`.
3. Mỗi member nhận metadata có cấu trúc:

```json
{
  "progress": 20,
  "days_remaining": 2,
  "deadline_status": "active",
  "risk_status": "at_risk",
  "risk_reason": "Chỉ còn 2 ngày, tiến độ 20%",
  "expected_progress": 80
}
```

## 5. Luồng hiển thị

- Thẻ dự án hiển thị badge màu vàng cho `risk_count` và màu đỏ cho `overdue_count`.
- Dialog quản lý thành viên hiển thị badge trạng thái trên từng dòng.
- Tooltip của badge hiển thị `risk_reason`.
- Leader có thể lọc theo: tất cả, có nguy cơ, quá hạn, đúng tiến độ, hoàn thành.
- Badge không hiển thị trên thẻ dự án của `MEMBER`.

## 6. Luồng cập nhật

- Khi member hoàn thành checklist, backend cập nhật `progress/status`.
- Lần tải lại danh sách dự án hoặc mở lại dialog thành viên sẽ tính trạng thái mới theo thời gian thực.
- Không lưu cứng `risk_status` vào database vì trạng thái thay đổi theo thời gian; backend tính lại khi đọc.

## 7. Kiểm thử bắt buộc

- Member mới được giao việc phải là `on_track`, không cảnh báo sai ngay ngày đầu.
- Member chậm tiến độ phải trả `at_risk` và có `risk_reason`.
- Member quá hạn phải trả `overdue`.
- Member hoàn thành phải ưu tiên `completed`, kể cả khi ngày hiện tại đã qua hạn.
- Tổng `risk_count` và `overdue_count` phải khớp danh sách chi tiết.

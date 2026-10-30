"""Chạy các phép kiểm tra thực tế cho từng mục checklist."""
from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import TYPE_CHECKING, Callable

from backend.core.utils import network_utils, system_utils
from backend.core.utils.system_utils import InstallPlan
from backend.services.notification_service import NotificationService

if TYPE_CHECKING:
    from backend.services.checklist_service import ChecklistItem, ChecklistService


@dataclass
class VerificationResult:
    key: str
    status: str  # passed | failed | warning | pending
    message: str
    suggestion: str = ""


class VerificationService:
    def __init__(self, checklist: ChecklistService, notifier: NotificationService | None = None) -> None:
        self.checklist = checklist
        self.notifier = notifier
        self._install_lock = threading.Lock()

    # ---------- từng loại kiểm tra ----------
    def _check_software(self, item: ChecklistItem) -> tuple[bool, str, str]:
        p = item.params
        name = p.get("name") or item.title
        command = p.get("command", "").strip()
        version_args = p.get("version_args", ["--version"])
        # Tương thích CSV cũ chứa cả lệnh; không bao giờ chuyển qua shell/cmd /c.
        for flag in ("--version", "-version", "-V", "version"):
            if command.endswith(" " + flag) and "version_args" not in p:
                command = command[:-(len(flag) + 1)].strip().strip('"')
                version_args = [flag]
                break
        st = system_utils.check_software(
            name, command, version_args, p.get("min_version")
        )
        suggestion = ""
        if not st.meets_min:
            suggestion = p.get("hint", "")
            if system_utils.build_install_plan(name, p.get("install")):
                suggestion = (suggestion + " Có thể nhờ AI Buddy cài tự động (sẽ hỏi xác nhận).").strip()
        return st.meets_min, st.message, suggestion

    def _check_port_free(self, item: ChecklistItem) -> tuple[bool, str, str]:
        port = int(item.params["port"])
        if network_utils.is_port_in_use(port):
            return False, f"Port {port} đang bị chiếm.", item.params.get("hint", "Đổi port hoặc tắt tiến trình đang dùng.")
        return True, f"Port {port} còn trống.", ""

    def _check_host(self, item: ChecklistItem) -> tuple[bool, str, str]:
        host, port = item.params["host"], int(item.params["port"])
        res = network_utils.tcp_connect(host, port)
        if res.ok:
            return True, f"Kết nối {host}:{port} OK ({res.latency_ms:.0f} ms).", ""
        hint = item.params.get("hint", "Kiểm tra VPN hoặc xin cấp quyền IP.")
        return False, f"Không kết nối được {host}:{port} - {res.error}.", hint

    # ---------- API ----------
    def _check_wifi(self, item: ChecklistItem) -> tuple[bool, str, str]:
        ok, message = network_utils.check_wifi()
        return ok, message, "" if ok else item.params.get("hint", "Kiểm tra Wi-Fi trong cài đặt mạng của máy.")

    def verify_item(self, item: ChecklistItem) -> VerificationResult:
        check_type = (item.check_type or "MANUAL").upper()
        if check_type == "MANUAL":
            return VerificationResult(item.key, item.status, item.message)

        checkers = {
            "SOFTWARE": self._check_software,
            "PORT_FREE": self._check_port_free,
            "HOST_REACHABLE": self._check_host,
            "WIFI": self._check_wifi,
        }
        checker = checkers.get(check_type)
        if checker is None:
            return VerificationResult(
                item.key,
                "failed",
                f"Loại kiểm tra không hỗ trợ: {item.check_type}",
            )
        try:
            ok, message, suggestion = checker(item)
        except Exception as exc:  # không để 1 mục lỗi làm hỏng cả checklist
            ok, message, suggestion = False, f"Lỗi khi kiểm tra: {exc}", ""

        status = "passed" if ok else ("failed" if item.required else "warning")
        full_message = f"{message} 💡 {suggestion}" if suggestion else message
        self.checklist.update_status(item.key, status, full_message)
        return VerificationResult(item.key, status, message, suggestion)

    def verify_key(self, key: str, user_email: str | None = None) -> VerificationResult:
        item = self.checklist.get_item(key)
        if item is None:
            raise KeyError(key)
        blocker = (
            self.checklist.step_blocker(key, user_email=user_email)
            if user_email
            else self.checklist.step_blocker(key)
        )
        if blocker:
            return VerificationResult(item.key, "pending", blocker)
        return self.verify_item(item)

    def verify_all(
        self,
        on_progress: Callable[[int, int, VerificationResult], None] | None = None,
        template_code: str | None = None,
        user_email: str | None = None,
    ) -> list[VerificationResult]:
        items = self.checklist.list_items(template_code=template_code, user_email=user_email)
        results: list[VerificationResult] = []
        for idx, item in enumerate(items, start=1):
            if item.status.lower() in {"passed", "completed"}:
                continue
            if (item.check_type or "MANUAL").upper() == "MANUAL":
                break  # Không tự xác nhận thay người dùng hoặc bỏ qua bước thủ công.
            res = (
                self.verify_key(item.key, user_email=user_email)
                if user_email
                else self.verify_key(item.key)
            )
            results.append(res)
            if on_progress:
                on_progress(idx, len(items), res)
            if res.status != "passed":
                break
        if self.notifier:
            failed = sum(1 for r in results if r.status == "failed")
            if failed:
                self.notifier.warning(f"Còn {failed} mục bắt buộc chưa đạt.")
            else:
                self.notifier.info("Đã kiểm tra các bước có thể chạy. Hoàn thành bước hiện tại để tiếp tục.")
        return results

    # ---------- cài đặt (luôn hỏi trước) ----------
    def install_plan(self, item: ChecklistItem) -> InstallPlan | None:
        if (item.check_type or "").upper() != "SOFTWARE":
            return None
        return system_utils.build_install_plan(item.params.get("name") or item.title, item.params.get("install"))

    def run_install(self, plan: InstallPlan, key: str | None = None) -> tuple[bool, str]:
        """Chỉ gọi sau khi người dùng xác nhận. Kiểm tra lại sau khi cài."""
        if not self._install_lock.acquire(blocking=False):
            return False, "Đang cài một phần mềm khác. Hãy chờ rồi tạo lại yêu cầu cài đặt."
        try:
            ok, output = system_utils.run_install_plan(plan)
            if key:
                try:
                    result = self.verify_key(key)
                    if result.status != "passed":
                        ok = False
                        output += f"\nKiểm tra lại chưa đạt: {result.message}. Có thể cần mở lại ứng dụng để cập nhật PATH."
                except Exception:
                    ok = False
                    output += "\nChưa kiểm tra lại được môi trường. Hãy chạy kiểm tra lại trước khi tiếp tục."
            if self.notifier:
                (self.notifier.success if ok else self.notifier.error)(
                    f"Cài {plan.software}: {'thành công' if ok else 'chưa hoàn tất'}"
                )
            return ok, output
        finally:
            self._install_lock.release()

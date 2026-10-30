"""Agent kiểm tra môi trường / checklist và cài đặt phần mềm kết hợp ChromaDB (RAG) & Qwen 2.5:7b."""
from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from config.settings import Settings, get_prompt, get_settings
from backend.core.agents.base import AgentReply
from backend.core.llm import LLMClient, LLMUnavailable
from backend.core.utils.system_utils import InstallPlan
from backend.services.checklist_service import ChecklistService
from backend.services.verification_service import VerificationResult, VerificationService

if TYPE_CHECKING:
    from backend.services.knowledge_service import KnowledgeService

_ICON = {"passed": "✅", "failed": "❌", "warning": "⚠️", "pending": "⏳"}

# Từ khóa thể hiện người dùng muốn hỏi đáp / xin hướng dẫn thay vì ra lệnh cài đặt ngay
_QUESTION_WORDS = (
    "sao", "thế nào", "the nao", "không", "khong", "được không", "duoc khong",
    "có cần", "co can", "hướng dẫn", "huong dan", "lỗi", "loi", "tại sao", "tai sao",
    "viết code", "viet code", "script", "làm cách nào", "lam cach nao",
)


def _extract_core_rules(guide_path: Path) -> str:
    """Trích xuất nguyên tắc cốt lõi (Mục 1 & Mục 2.0) để đảm bảo mô hình không bao giờ vi phạm."""
    if not guide_path.exists():
        return (
            "Nguyên tắc cốt lõi: Áp dụng Semantic Versioning (SemVer), actual >= min_version là ĐẠT, "
            "không ép hạ cấp (downgrade). Luôn dùng Test-NetConnection/socket, tuyệt đối không dùng telnet. "
            "Hỏi trước khi thực thi lệnh cài đặt."
        )
    try:
        content = guide_path.read_text(encoding="utf-8")
        m = re.search(r"(2\.0\..*?)(?=\n\s*2\.1\.|\Z)", content, re.DOTALL)
        return m.group(1).strip() if m else ""
    except Exception:
        return ""


def _extract_guide_context(guide_path: Path, query: str) -> str:
    """Trích xuất ngữ cảnh liên quan trực tiếp từ file cẩm nang khi ChromaDB chưa sẵn sàng (Fallback)."""
    if not guide_path.exists():
        return _extract_core_rules(guide_path)
    try:
        content = guide_path.read_text(encoding="utf-8")
    except Exception:
        return "Không thể nạp nội dung cẩm nang hướng dẫn."

    q_low = query.lower()
    sections: list[str] = []

    # Mục 2.0 (Nguyên tắc phiên bản chung) luôn được ưu tiên đưa vào ngữ cảnh
    m20 = re.search(r"(2\.0\..*?)(?=\n\s*2\.1\.|\Z)", content, re.DOTALL)
    if m20:
        sections.append(m20.group(1).strip())

    # Map các nhóm chủ đề công cụ lập trình, IP, port và sự cố
    app_patterns = [
        (["python", "pip", "venv", "pyenv", "py -0"], r"(2\.1\. PYTHON.*?)(?=\n\s*2\.2\.|\Z)"),
        (["git", "clone", "sslverify", "crlf", "github"], r"(2\.2\. GIT.*?)(?=\n\s*2\.3\.|\Z)"),
        (["node", "npm", "yarn", "pnpm", "nvm", "fnm"], r"(2\.3\. NODE\.JS.*?)(?=\n\s*2\.4\.|\Z)"),
        (["docker", "compose", "wsl", "container"], r"(2\.4\. DOCKER.*?)(?=\n\s*2\.5\.|\Z)"),
        (["ollama", "qwen", "bge", "vram", "model"], r"(2\.5\. OLLAMA.*?)(?=\n\s*2\.6\.|\Z)"),
        (["java", "jdk", "maven", "mvn", "gradle", "java_home"], r"(2\.6\. JAVA.*?)(?=\n\s*2\.7\.|\Z)"),
        (["go", "golang", "gopath"], r"(2\.7\. GO.*?)(?=\n\s*2\.8\.|\Z)"),
        ([".net", "dotnet", "c#", "global.json"], r"(2\.8\. \.NET.*?)(?=\n\s*2\.9\.|\Z)"),
        (["vscode", "code", "extension"], r"(2\.9\. VISUAL STUDIO.*?)(?=\n\s*2\.10\.|\Z)"),
        (["jetbrains", "intellij", "pycharm"], r"(2\.10\. JETBRAINS.*?)(?=\n\s*2\.11\.|\Z)"),
        (["dbeaver", "psql", "postgres", "postgresql", "database", "db"], r"(2\.11\. QUẢN LÝ CƠ SỞ DỮ LIỆU.*?)(?=\n\s*2\.12\.|\Z)"),
        (["postman", "insomnia", "curl", "api"], r"(2\.12\. CÔNG CỤ KIỂM THỬ API.*?)(?=\n\s*2\.13\.|\Z)"),
        (["terminal", "powershell", "pwsh", "cmd"], r"(2\.13\. WINDOWS TERMINAL.*?)(?=\n\s*3\.|\Z)"),
        (["ip", "mạng", "mang", "network", "host", "proxy", "vpn", "ssl"], r"(3\. HƯỚNG DẪN KIỂM TRA MẠNG.*?)(?=\n\s*4\.|\Z)"),
        (["port", "cổng", "cong", "chiếm", "chiem", "xung đột", "xung dot", "netstat", "winnat"], r"(4\. HƯỚNG DẪN KIỂM TRA & GIẢI PHÓNG PORT.*?)(?=\n\s*5\.|\Z)"),
        (["xin quyền", "xin quyen", "ticket", "ipconfig", "quy trình ip", "quy trinh ip"], r"(5\. QUY TRÌNH XIN CẤP QUYỀN TRUY CẬP IP.*?)(?=\n\s*6\.|\Z)"),
        (["lỗi", "loi", "error", "sự cố", "su co", "khắc phục", "khac phuc", "troubleshoot", "tra cứu", "tra cuu"], r"(6\. BẢNG TRA CỨU NHANH SỰ CỐ.*?)(?=\n\s*={5,}|\Z)"),
    ]

    matched_count = 0
    for keywords, pattern in app_patterns:
        if any(k in q_low for k in keywords):
            m = re.search(pattern, content, re.DOTALL)
            if m:
                # Chỉ lấy tối đa 1 section sát nhất (giới hạn 1000 ký tự) để tăng tốc LLM
                sections.append(m.group(1).strip()[:1000])
                matched_count += 1
                break

    # Nếu câu hỏi chung chung, chỉ lấy tóm tắt ngắn gọn
    if matched_count == 0:
        sections.append(
            "Cẩm nang nhanh: Dùng Test-NetConnection kiểm tra IP/port (không dùng telnet). "
            "Dùng netstat -ano | findstr :<port> giải phóng port. Mọi công cụ đạt chuẩn khi actual >= min_version."
        )

    return "\n\n--------------------\n\n".join(sections)


class ChecklistAgent:
    name = "checklist"

    def __init__(
        self,
        checklist: ChecklistService,
        verification: VerificationService,
        llm: LLMClient,
        settings: Settings | None = None,
        knowledge: KnowledgeService | None = None,
    ) -> None:
        self.checklist = checklist
        self.verification = verification
        self.llm = llm
        self.settings = settings or getattr(checklist, "settings", None) or get_settings()
        self.knowledge = knowledge
        self._cached_target_model: str | None = None
        self._qa_cache: dict[tuple[str, str], tuple[str, list[str]]] = {}

    @property
    def guide_path(self) -> Path:
        return self.settings.config_dir / "checklist_troubleshooting_guide.txt"

    # ---------- intent: cài đặt trực tiếp ----------
    def _match_software(self, message: str):
        low = message.lower()
        for item in self.checklist.list_items():
            if (item.check_type or "").upper() != "SOFTWARE":
                continue
            names = {item.key.removeprefix("sw_"), item.params.get("name", "").lower(), item.params.get("command", "")}
            if any(n and n in low for n in names):
                return item
        return None

    def _propose_install(self, message: str) -> AgentReply | None:
        item = self._match_software(message)
        if item is None:
            return None
        plan = self.verification.install_plan(item)
        if plan is None:
            return AgentReply(
                f"Mình chưa có cách cài **{item.params.get('name') or item.title}** tự động trên hệ điều hành này. "
                f"{item.params.get('hint', 'Hãy cài thủ công theo tài liệu dự án.')}",
                agent=self.name,
            )
        return AgentReply(
            f"Mình sẽ cài **{plan.software}** bằng lệnh:\n\n```\n{plan.display}\n```\n"
            "Bạn có đồng ý chạy lệnh này không?",
            pending_install=plan, pending_key=item.key, agent=self.name,
        )

    # ---------- intent: kiểm tra toàn diện ----------
    def run_full_check(self) -> tuple[list[VerificationResult], str]:
        results = self.verification.verify_all()
        return results, self.format_report()

    def format_report(self) -> str:
        lines: list[str] = []
        for cat in self.checklist.categories():
            lines.append(f"**{cat}**")
            for it in self.checklist.list_items(cat):
                lines.append(f"- {_ICON.get(it.status, '⏳')} {it.title}" + (f" - {it.message}" if it.message else ""))
            lines.append("")
        prog = self.checklist.progress()
        lines.append(f"Tiến độ: **{prog['passed']}/{prog['total']} ({prog['percent']}%)**")
        return "\n".join(lines)

    def _summary_report(self) -> str:
        """Tóm tắt ngắn gọn trạng thái checklist để đưa vào prompt LLM."""
        try:
            prog = self.checklist.progress()
            failed = [it.title for it in self.checklist.list_items() if it.status in ("failed", "warning")]
            failed_str = ", ".join(failed) if failed else "Tất cả đã đạt yêu cầu"
            return f"Tiến độ: {prog['passed']}/{prog['total']} ({prog['percent']}%). Mục chưa đạt: {failed_str}."
        except Exception:
            return "Chưa có thông tin tiến độ checklist."

    def _get_target_model(self) -> str:
        """Kiểm tra và cache mô hình tối ưu (aibuddy-checklist hoặc default) để tránh gọi HTTP lặp lại."""
        if self._cached_target_model is not None:
            return self._cached_target_model
        try:
            from backend.core.llm import list_local_models
            local_models = list_local_models(self.settings)
            for m in local_models:
                if m.startswith("aibuddy-checklist"):
                    self._cached_target_model = m
                    return m
        except Exception:
            pass
        self._cached_target_model = self.settings.llm_model
        return self._cached_target_model

    def ask_specialist(self, message: str, project_code: str | None = None) -> tuple[str, list[str]]:
        """Truy xuất tri thức từ ChromaDB (RAG) kết hợp cẩm nang và mô hình Ollama (Qwen 2.5:7b)."""
        cache_key = (message.strip().lower(), project_code or "")
        if cache_key in self._qa_cache:
            return self._qa_cache[cache_key]

        sources: list[str] = []
        retrieved_context = ""

        # 1. Ưu tiên tìm kiếm ngữ nghĩa từ ChromaDB qua KnowledgeService
        if self.knowledge:
            try:
                if project_code:
                    docs = self.knowledge.search_project(project_code, message, k=2)
                else:
                    docs = self.knowledge.search(message, k=2)

                if docs:
                    sources = self.knowledge.sources(docs)
                    retrieved_context = self.knowledge.format_context(docs)[:1200]
            except Exception:
                # Nếu ChromaDB chưa nạp hoặc tạm thời chưa sẵn sàng, tiếp tục fallback
                pass

        # 2. Nếu ChromaDB chưa có tài liệu tương ứng, tự động fallback đọc từ file cẩm nang
        if not retrieved_context:
            retrieved_context = _extract_guide_context(self.guide_path, message)
            if self.guide_path.exists():
                sources.append(self.guide_path.name)
        else:
            # Khi ChromaDB đã trả về kết quả, vẫn đính kèm nguyên tắc Version Agnostic để AI luôn tuân thủ
            rules = _extract_core_rules(self.guide_path)
            if rules and rules not in retrieved_context:
                retrieved_context = f"{rules}\n\n=== TÀI LIỆU TRA CỨU ===\n{retrieved_context}"

        report_summary = self._summary_report()
        target_model = self._get_target_model()

        # 3. Gửi prompt vào mô hình Ollama
        try:
            prompt = get_prompt(
                "checklist_specialist",
                guide_context=retrieved_context,
                checklist_report=report_summary,
            )
            answer = self.llm.ask(message, system=prompt, model=target_model)
            if len(self._qa_cache) >= 50:
                self._qa_cache.clear()
            self._qa_cache[cache_key] = (answer, sources)
            return answer, sources
        except LLMUnavailable:
            snippet = retrieved_context[:1000]
            answer = (
                "⚠️ *Dịch vụ Ollama hiện chưa chạy (bạn có thể mở Ollama hoặc chạy lệnh `ollama serve`)*.\n\n"
                "Dưới đây là thông tin trích xuất từ kho tri thức / cẩm nang hướng dẫn:\n\n"
                f"{snippet}\n\n"
                "---\n💡 *Gợi ý: Hãy kiểm tra các câu lệnh mẫu phía trên hoặc bật Ollama để nhận tư vấn đầy đủ hơn.*"
            )
            return answer, sources

    def handle(self, message: str, project_code: str | None = None, checklist_mode: bool = False) -> AgentReply:
        low = message.lower()

        # Kiểm tra xem có phải lệnh cài đặt trực tiếp không (không chứa từ hỏi đáp)
        is_direct_install = any(low.startswith(p) for p in ("cài ", "cai ", "install ", "hãy cài ", "chạy cài "))
        is_question = any(qw in low for qw in _QUESTION_WORDS)

        if is_direct_install and not is_question:
            proposal = self._propose_install(message)
            if proposal:
                return proposal

        # Nếu người dùng đang ở chế độ Checklist Switch (checklist_mode=True)
        # hoặc đang đặt câu hỏi về cài đặt, version, kiểm tra IP, port, viết code:
        if checklist_mode or is_question or any(k in low for k in ("ip", "port", "version", "phiên bản", "lỗi", "code", "script")):
            answer, sources = self.ask_specialist(message, project_code=project_code)
            return AgentReply(answer, sources=sources, agent=self.name)

        # Mặc định: chạy kiểm tra môi trường và báo cáo
        _, report = self.run_full_check()
        text = report
        sources: list[str] = []
        if any(r.status in ("failed", "warning") for r in self.checklist.list_items()):
            try:
                advice, src = self.ask_specialist(
                    f"Dưới đây là báo cáo checklist. Hãy gợi ý cách khắc phục ngắn gọn:\n{report}",
                    project_code=project_code,
                )
                if advice:
                    text += f"\n\n---\n💡 **Gợi ý từ AI Buddy (Qwen 2.5:7b + ChromaDB)**\n{advice}"
                    sources = src
            except Exception:
                pass
            text += "\n\nNếu thiếu phần mềm, hãy nhắn *“cài git”*, *“cài python”*… mình sẽ hỏi bạn trước khi cài."
        return AgentReply(text, sources=sources, agent=self.name)

    # ---------- thực thi sau khi đã xác nhận ----------
    def execute_install(self, plan: InstallPlan, key: str | None = None) -> AgentReply:
        ok, output = self.verification.run_install(plan, key)
        status = "✅ Cài đặt thành công." if ok else "❌ Cài đặt thất bại."
        tail = f"\n\n```\n{output[-600:]}\n```" if output else ""
        return AgentReply(f"{status}{tail}", agent=self.name, install_ok=ok)

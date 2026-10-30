"""Trang cài đặt: model Ollama, role, nạp tài liệu RAG."""
from __future__ import annotations

import flet as ft

from frontend.context import FrontendContext
from frontend import theme


class SettingsPage(ft.Column):
    def __init__(self, ctx: FrontendContext) -> None:
        self.ctx = ctx
        s = ctx.settings
        field = dict(border_radius=12, border_color=theme.BORDER, focused_border_color=theme.ACCENT, bgcolor=theme.SURFACE)

        self.role = ft.Dropdown(
            label="Vai trò của bạn",
            value=s.user_role,
            options=[ft.dropdown.Option(k, v) for k, v in s.roles.items()],
            **field,
        )
        self.base_url = ft.TextField(label="Ollama URL", value=s.ollama_base_url, **field)
        self.llm_model = ft.TextField(label="LLM model", value=s.llm_model, **field)
        self.embed_model = ft.TextField(label="Embedding model", value=s.embedding_model, **field)

        self.ollama_status = ft.Text("", size=12)
        self.ingest_status = ft.Text("", size=12, color=theme.MUTED)
        self.ingest_bar = ft.ProgressBar(visible=False, color=theme.ACCENT_2, bgcolor=theme.SURFACE_ALT)
        self.reset_switch = ft.Switch(label="Xoá và nạp lại toàn bộ", value=False)
        self.db_status = ft.Text("", size=12, selectable=True)

        def section(title: str, *controls: ft.Control) -> ft.Container:
            return ft.Container(
                content=ft.Column([ft.Text(title, size=15, weight=ft.FontWeight.W_600, color=theme.TEXT), *controls], spacing=12),
                **theme.card_decoration(),
            )

        super().__init__(
            expand=True,
            spacing=14,
            scroll=ft.ScrollMode.AUTO,
            controls=[
                ft.Text("Cài đặt", size=24, weight=ft.FontWeight.BOLD, color=theme.TEXT),
                section(
                    "Mô hình AI (Ollama, offline)",
                    self.base_url, self.llm_model, self.embed_model, self.role,
                    ft.Row(
                        [
                            ft.FilledButton("Lưu", icon=ft.Icons.SAVE_OUTLINED, on_click=self._save),
                            ft.OutlinedButton("Kiểm tra Ollama", icon=ft.Icons.NETWORK_CHECK, on_click=self._test_ollama),
                            self.ollama_status,
                        ],
                        wrap=True,
                    ),
                ),
                section(
                    "Kho tri thức (ChromaDB)",
                    ft.Text(f"Thư mục tài liệu: {s.documents_dir}", size=12, color=theme.MUTED, selectable=True),
                    ft.Row(
                        [
                            ft.FilledButton("Nạp tài liệu", icon=ft.Icons.UPLOAD_FILE, on_click=self._ingest),
                            self.reset_switch,
                        ],
                        wrap=True,
                    ),
                    self.ingest_bar,
                    self.ingest_status,
                ),
                section(
                    "Database (PostgreSQL)",
                    ft.Text(s.database_description, size=12, color=theme.MUTED, selectable=True),
                    ft.Text("Đổi database bằng POSTGRES_* hoặc DATABASE_URL trong file .env rồi khởi động lại app.", size=12, color=theme.MUTED),
                    ft.Row(
                        [ft.OutlinedButton("Kiểm tra kết nối DB", icon=ft.Icons.STORAGE, on_click=self._test_db), self.db_status],
                        wrap=True,
                    ),
                ),
            ],
        )

    def _test_db(self, _=None) -> None:
        def work() -> None:
            status = self.ctx.database_status()
            ok, message = status["ok"], status["message"]
            self.db_status.value = ("✅ " if ok else "❌ ") + message
            self.db_status.color = theme.OK if ok else theme.ERR
            self.db_status.update()

        self.db_status.value = "Đang kiểm tra…"
        self.db_status.color = theme.MUTED
        self.db_status.update()
        self.page.run_thread(work)

    # ---------- handlers ----------
    def _save(self, _=None) -> None:
        s = self.ctx.settings
        s.ollama_base_url = self.base_url.value.strip()
        s.llm_model = self.llm_model.value.strip()
        s.embedding_model = self.embed_model.value.strip()
        s.user_role = self.role.value
        s.save_user_overrides()
        self.ctx.notifier.success("Đã lưu cài đặt.")

    def _test_ollama(self, _=None) -> None:
        self._save()

        def work() -> None:
            s = self.ctx.settings
            status = self.ctx.ollama_status()
            if status["running"]:
                models = status["models"]
                missing = [m for m in (s.llm_model, s.embedding_model) if not any(x.split(":")[0] == m.split(":")[0] for x in models)]
                if missing:
                    self.ollama_status.value = f"⚠️ Ollama chạy, thiếu model: {', '.join(missing)} (ollama pull ...)"
                    self.ollama_status.color = theme.WARN
                else:
                    self.ollama_status.value = f"✅ Ollama sẵn sàng ({len(models)} model)"
                    self.ollama_status.color = theme.OK
            else:
                self.ollama_status.value = "❌ Không kết nối được Ollama (chạy 'ollama serve')"
                self.ollama_status.color = theme.ERR
            self.ollama_status.update()

        self.page.run_thread(work)

    def _ingest(self, _=None) -> None:
        self._save()

        def work() -> None:
            self.ingest_bar.visible = True
            self.ingest_status.value = "Đang nạp…"
            self.update()

            def progress(i: int, n: int, name: str) -> None:
                self.ingest_bar.value = i / n
                self.ingest_status.value = f"({i}/{n}) {name}"
                self.update()

            try:
                report = self.ctx.knowledge.ingest_all(reset=self.reset_switch.value, progress=progress)
                self.ingest_status.value = report.summary()
                self.ctx.notifier.success(report.summary())
            except Exception as exc:
                self.ingest_status.value = f"❌ Lỗi: {exc}"
                self.ctx.notifier.error("Nạp tài liệu thất bại - kiểm tra Ollama & embedding model.")
            self.ingest_bar.visible = False
            self.update()

        self.page.run_thread(work)

"""LLM client dùng LangChain + Ollama (Qwen-2.5 chạy local)."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Iterator

from config.settings import Settings, get_prompt


class LLMUnavailable(RuntimeError):
    """Ollama chưa chạy hoặc model chưa được pull."""


def is_ollama_running(settings: Settings, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(f"{settings.ollama_base_url}/api/tags", timeout=timeout):
            return True
    except (urllib.error.URLError, OSError, ValueError):
        return False


def list_local_models(settings: Settings, timeout: float = 2.0) -> list[str]:
    try:
        with urllib.request.urlopen(f"{settings.ollama_base_url}/api/tags", timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return [m["name"] for m in data.get("models", [])]
    except (urllib.error.URLError, OSError, ValueError, KeyError):
        return []


class LLMClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _model(self, model: str | None = None, num_predict: int | None = None):
        from langchain_ollama import ChatOllama

        target_model = model or self.settings.llm_model
        predict = num_predict or getattr(self.settings, "num_predict", 512)
        threads = getattr(self.settings, "num_thread", 8)

        return ChatOllama(
            model=target_model,
            base_url=self.settings.ollama_base_url,
            temperature=self.settings.temperature,
            num_ctx=self.settings.num_ctx,
            num_predict=predict,
            num_thread=threads,
            client_kwargs={"timeout": self.settings.request_timeout},
        )

    @staticmethod
    def _messages(system: str, user: str):
        from langchain_core.messages import HumanMessage, SystemMessage

        return [SystemMessage(content=system), HumanMessage(content=user)]

    def ask(self, user: str, system: str | None = None, model: str | None = None) -> str:
        system = system or get_prompt("system")
        target_model = model or self.settings.llm_model
        try:
            return str(self._model(target_model).invoke(self._messages(system, user)).content).strip()
        except Exception as exc:
            raise LLMUnavailable(
                f"Không gọi được model '{target_model}' tại {self.settings.ollama_base_url}: {exc}"
            ) from exc

    def stream(self, user: str, system: str | None = None) -> Iterator[str]:
        system = system or get_prompt("system")
        try:
            for chunk in self._model().stream(self._messages(system, user)):
                yield str(chunk.content)
        except Exception as exc:
            raise LLMUnavailable(str(exc)) from exc

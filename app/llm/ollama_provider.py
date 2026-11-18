"""Local Ollama provider. Screen images stay on this machine."""

from __future__ import annotations

import base64
from pathlib import Path

from app.config.settings import AppSettings
from app.llm.provider import message_payload
from app.storage.models import ChatMessage


class OllamaProvider:
    name = "ollama"

    def __init__(self, settings: AppSettings, transport=None) -> None:
        self.settings = settings
        self._transport = transport or _http_json

    @property
    def supports_vision(self) -> bool:
        return bool(self.settings.ollama_vision)

    def complete(self, messages: list[ChatMessage], *, timeout: float, json_mode: bool = False) -> str:
        payload_messages = []
        for message in messages:
            item = message_payload(message, include_images=self.supports_vision)
            if message.image_paths:
                if not self.supports_vision:
                    raise PermissionError("当前本地模型没有开启视觉能力，已取消发送截屏")
                item["images"] = [_encode(path) for path in message.image_paths]
                item.pop("image_paths", None)
            payload_messages.append(item)
        options: dict = {"temperature": 0.1}
        if any(item.get("images") for item in payload_messages):
            options["num_ctx"] = 8192
        body: dict = {
            "model": self.settings.ollama_model,
            "messages": payload_messages,
            "stream": False,
            "options": options,
        }
        if json_mode:
            body["format"] = "json"
        url = self.settings.ollama_base_url.rstrip("/") + "/api/chat"
        data = self._transport("POST", url, body, timeout, None)
        return str(data.get("message", {}).get("content", ""))

    def health(self) -> tuple[bool, str]:
        try:
            url = self.settings.ollama_base_url.rstrip("/") + "/api/tags"
            data = self._transport("GET", url, None, 2, None)
        except Exception as exc:
            return False, f"Ollama 不可用: {exc}"
        models = [item.get("name", "") for item in data.get("models", []) if isinstance(item, dict)]
        if self.settings.ollama_model and models and not any(self.settings.ollama_model in name for name in models):
            return True, "已连接 Ollama，但列表中没有所选模型"
        return True, "已连接 Ollama"


def _encode(path: str) -> str:
    return base64.b64encode(Path(path).read_bytes()).decode("ascii")


def _http_json(method: str, url: str, payload: dict | None, timeout: float, headers: dict | None):
    import httpx

    with httpx.Client(timeout=timeout) as client:
        if method == "GET":
            response = client.get(url, headers=headers)
        else:
            response = client.post(url, json=payload, headers=headers)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = response.text.replace("\n", " ")[:300]
            raise RuntimeError(f"本地模型拒绝了这次请求：{detail}") from exc
        return response.json()

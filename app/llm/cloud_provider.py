"""Opt-in OpenAI-compatible cloud provider."""

from __future__ import annotations

import base64
from pathlib import Path

from app.config.settings import AppSettings
from app.llm.provider import message_payload
from app.storage.models import ChatMessage


class CloudProvider:
    name = "cloud"

    def __init__(self, settings: AppSettings, api_key: str = "", transport=None) -> None:
        self.settings = settings
        self.api_key = api_key
        self._transport = transport or _http_json

    @property
    def supports_vision(self) -> bool:
        return bool(self.settings.cloud_enabled and self.settings.cloud_vision and self.settings.cloud_allow_screenshots)

    def complete(self, messages: list[ChatMessage], *, timeout: float, json_mode: bool = False) -> str:
        if not self.settings.cloud_enabled:
            raise PermissionError("Cloud inference is not enabled")
        if not self.api_key:
            raise PermissionError("No cloud API key is configured")
        payload_messages = []
        for message in messages:
            self._reject_private_payload(message)
            if message.image_paths:
                content = [
                    {"type": "text", "text": message.content},
                    *[
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{_encode(path)}"}}
                        for path in message.image_paths
                    ],
                ]
                payload_messages.append({"role": message.role, "content": content})
            else:
                item = message_payload(message, include_images=False)
                payload_messages.append(item)
        body = {
            "model": self.settings.cloud_model,
            "messages": payload_messages,
            "temperature": 0.1,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {self.api_key}"}
        url = self.settings.cloud_base_url.rstrip("/") + "/chat/completions"
        data = self._transport("POST", url, body, timeout, headers)
        return str(data["choices"][0]["message"]["content"])

    def health(self) -> tuple[bool, str]:
        if not self.settings.cloud_enabled:
            return False, "Cloud inference is not enabled"
        if not self.api_key:
            return False, "No cloud API key is configured"
        try:
            url = self.settings.cloud_base_url.rstrip("/") + "/models"
            self._transport("GET", url, None, 3, {"Authorization": f"Bearer {self.api_key}"})
        except Exception as exc:
            return False, f"The cloud service is unavailable: {exc}"
        return True, "Connected to the cloud service"

    def _reject_private_payload(self, message: ChatMessage) -> None:
        if message.image_paths and not (self.settings.cloud_allow_screenshots and self.settings.cloud_vision):
            raise PermissionError("Sending a screenshot to the cloud was blocked")
        lowered = message.content.lower()
        if "data:image" in lowered and not self.settings.cloud_allow_screenshots:
            raise PermissionError("Sending a screenshot to the cloud was blocked")
        if "file_content" in lowered and not self.settings.cloud_allow_file_contents:
            raise PermissionError("Sending file contents to the cloud was blocked")


def _encode(path: str) -> str:
    return base64.b64encode(Path(path).read_bytes()).decode("ascii")


def _http_json(method: str, url: str, payload: dict | None, timeout: float, headers: dict | None):
    import httpx

    with httpx.Client(timeout=timeout) as client:
        if method == "GET":
            response = client.get(url, headers=headers)
        else:
            response = client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()

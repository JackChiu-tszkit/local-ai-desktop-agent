"""Provider interface. LangChain message objects stay inside this boundary."""

from __future__ import annotations

from typing import Protocol

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.storage.models import ChatMessage


class LLMProvider(Protocol):
    name: str
    supports_vision: bool

    def complete(self, messages: list[ChatMessage], *, timeout: float, json_mode: bool = False) -> str: ...

    def health(self) -> tuple[bool, str]: ...


def to_langchain(message: ChatMessage):
    mapping = {"system": SystemMessage, "user": HumanMessage, "assistant": AIMessage}
    return mapping[message.role](content=message.content)


def message_payload(message: ChatMessage, *, include_images: bool) -> dict:
    langchain_message = to_langchain(message)
    payload: dict = {"role": message.role, "content": str(langchain_message.content)}
    if include_images and message.image_paths:
        payload["image_paths"] = list(message.image_paths)
    return payload

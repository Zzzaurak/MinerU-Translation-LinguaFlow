from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

from mineru_batch_cli.http_client import HttpClient, HttpClientError


class TranslationClientError(ValueError):
    pass


class TranslationProvider(Protocol):
    def translate_markdown(self, markdown: str, *, target_language: str) -> str:
        ...


@dataclass(frozen=True)
class OpenAICompatibleTranslationAdapter:
    http_client: HttpClient
    api_base_url: str
    api_key: str
    model: str

    def translate_markdown(self, markdown: str, *, target_language: str) -> str:
        if not markdown.strip():
            return markdown

        endpoint = f"{self.api_base_url.rstrip('/')}/chat/completions"
        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a Markdown translator. Translate natural-language prose into the target "
                        "language while preserving Markdown structure, code blocks, inline code, URLs, and "
                        "image references exactly. Output only translated Markdown."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Target language: {target_language}\n\n"
                        "Translate the following Markdown:\n\n"
                        f"{markdown}"
                    ),
                },
            ],
        }

        try:
            response = self.http_client.request(
                "POST",
                endpoint,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json_body=payload,
            )
        except HttpClientError as exc:
            raise TranslationClientError(f"Translation request failed: {exc}") from exc

        if response.status_code != 200:
            raise TranslationClientError(
                f"Translation request returned status {response.status_code}"
            )

        translated = _extract_text(response.body)
        if not translated.strip():
            raise TranslationClientError("Translation response content is empty")
        return translated


def _extract_text(body: bytes) -> str:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TranslationClientError("Invalid translation JSON response") from exc

    if not isinstance(payload, dict):
        raise TranslationClientError("Invalid translation response shape")

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise TranslationClientError("Translation response missing choices")

    first = choices[0]
    if not isinstance(first, dict):
        raise TranslationClientError("Translation response has invalid choice type")

    message = first.get("message")
    if not isinstance(message, dict):
        raise TranslationClientError("Translation response missing message")

    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
                continue
            if not isinstance(part, dict):
                continue
            text = part.get("text")
            if isinstance(text, str):
                parts.append(text)
        merged = "".join(parts)
        if merged:
            return merged

    raise TranslationClientError("Translation response missing text content")

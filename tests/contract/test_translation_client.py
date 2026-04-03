from __future__ import annotations

import json

import pytest

from mineru_batch_cli.http_client import HttpClient, HttpClientError, HttpResponse
from mineru_batch_cli.translation_client import (
    OpenAICompatibleTranslationAdapter,
    TranslationClientError,
)


def _build_adapter(*, request_func, retry_max: int = 3) -> OpenAICompatibleTranslationAdapter:
    http = HttpClient(request_func=request_func, retry_max=retry_max)
    return OpenAICompatibleTranslationAdapter(
        http_client=http,
        api_base_url="https://llm.example/v1",
        api_key="secret-key",
        model="gpt-4.1-mini",
    )


def test_translation_client_success() -> None:
    def fake_request(
        _method: str,
        _url: str,
        _headers: dict[str, str],
        _data: bytes | None,
        _timeout: float,
    ) -> HttpResponse:
        body = json.dumps(
            {
                "choices": [
                    {
                        "message": {
                            "content": "# 标题\n\n这是中文。",
                        }
                    }
                ]
            }
        ).encode("utf-8")
        return HttpResponse(status_code=200, body=body, headers={})

    adapter = _build_adapter(request_func=fake_request)
    translated = adapter.translate_markdown("# Title\n\nThis is English.", target_language="zh-CN")
    assert "中文" in translated


def test_translation_client_empty_input_returns_input_without_request() -> None:
    calls: list[int] = []

    def fake_request(
        _method: str,
        _url: str,
        _headers: dict[str, str],
        _data: bytes | None,
        _timeout: float,
    ) -> HttpResponse:
        calls.append(1)
        return HttpResponse(status_code=500, body=b"", headers={})

    adapter = _build_adapter(request_func=fake_request)
    assert adapter.translate_markdown("   ", target_language="zh-CN") == "   "
    assert calls == []


def test_translation_client_retries_transient_then_success() -> None:
    calls: list[int] = []

    def fake_request(
        _method: str,
        _url: str,
        _headers: dict[str, str],
        _data: bytes | None,
        _timeout: float,
    ) -> HttpResponse:
        calls.append(1)
        if len(calls) == 1:
            return HttpResponse(status_code=429, body=b"busy", headers={})
        body = json.dumps({"choices": [{"message": {"content": "好的"}}]}).encode("utf-8")
        return HttpResponse(status_code=200, body=body, headers={})

    adapter = _build_adapter(request_func=fake_request, retry_max=2)
    translated = adapter.translate_markdown("hello", target_language="zh-CN")
    assert translated == "好的"
    assert len(calls) == 2


def test_translation_client_non_429_4xx_fails_fast() -> None:
    calls: list[int] = []

    def fake_request(
        _method: str,
        _url: str,
        _headers: dict[str, str],
        _data: bytes | None,
        _timeout: float,
    ) -> HttpResponse:
        calls.append(1)
        return HttpResponse(status_code=401, body=b"unauthorized", headers={})

    adapter = _build_adapter(request_func=fake_request)
    with pytest.raises(TranslationClientError, match="status 401"):
        adapter.translate_markdown("hello", target_language="zh-CN")
    assert len(calls) == 1


def test_translation_client_invalid_response_shape_raises() -> None:
    def fake_request(
        _method: str,
        _url: str,
        _headers: dict[str, str],
        _data: bytes | None,
        _timeout: float,
    ) -> HttpResponse:
        body = json.dumps({"choices": []}).encode("utf-8")
        return HttpResponse(status_code=200, body=body, headers={})

    adapter = _build_adapter(request_func=fake_request)
    with pytest.raises(TranslationClientError, match="missing choices"):
        adapter.translate_markdown("hello", target_language="zh-CN")


def test_translation_client_accepts_array_content_parts() -> None:
    def fake_request(
        _method: str,
        _url: str,
        _headers: dict[str, str],
        _data: bytes | None,
        _timeout: float,
    ) -> HttpResponse:
        body = json.dumps(
            {
                "choices": [
                    {
                        "message": {
                            "content": [
                                {"type": "output_text", "text": "第一段。"},
                                {"type": "output_text", "text": "第二段。"},
                            ]
                        }
                    }
                ]
            }
        ).encode("utf-8")
        return HttpResponse(status_code=200, body=body, headers={})

    adapter = _build_adapter(request_func=fake_request)
    translated = adapter.translate_markdown("hello", target_language="zh-CN")
    assert translated == "第一段。第二段。"


def test_translation_client_provider_swap_via_protocol() -> None:
    class FakeProvider:
        def translate_markdown(self, markdown: str, *, target_language: str) -> str:
            assert target_language == "zh-CN"
            return f"[{target_language}] {markdown}"

    provider = FakeProvider()
    assert provider.translate_markdown("hello", target_language="zh-CN") == "[zh-CN] hello"


def test_translation_client_network_error_maps_to_translation_error() -> None:
    def fake_request(
        _method: str,
        _url: str,
        _headers: dict[str, str],
        _data: bytes | None,
        _timeout: float,
    ) -> HttpResponse:
        raise HttpClientError("Network error: timeout", retriable=True)

    adapter = _build_adapter(request_func=fake_request)
    with pytest.raises(TranslationClientError, match="Translation request failed"):
        adapter.translate_markdown("hello", target_language="zh-CN")

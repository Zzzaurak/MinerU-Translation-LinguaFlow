from __future__ import annotations

import json
from pathlib import Path


class VerifyError(ValueError):
    pass


REQUIRED_KEYS = {
    "schema_version",
    "run_id",
    "started_at",
    "finished_at",
    "input_root",
    "output_root",
    "total",
    "succeeded",
    "failed",
    "items",
}

REQUIRED_ITEM_KEYS = {
    "input_path",
    "item_slug",
    "status",
    "error_code",
    "error_message",
    "document_path",
    "images_count",
    "warnings",
}

def verify_manifest(path: Path) -> None:
    if not path.exists() or not path.is_file():
        raise VerifyError("manifest file not found")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise VerifyError("manifest is not valid JSON") from exc

    if not isinstance(payload, dict):
        raise VerifyError("manifest root must be an object")

    missing = sorted(REQUIRED_KEYS - payload.keys())
    if missing:
        raise VerifyError(f"manifest missing required keys: {', '.join(missing)}")

    items = payload.get("items")
    if not isinstance(items, list):
        raise VerifyError("manifest items must be a list")

    if not isinstance(payload.get("total"), int):
        raise VerifyError("manifest total must be an integer")
    if not isinstance(payload.get("succeeded"), int):
        raise VerifyError("manifest succeeded must be an integer")
    if not isinstance(payload.get("failed"), int):
        raise VerifyError("manifest failed must be an integer")

    total = payload["total"]
    succeeded = payload["succeeded"]
    failed = payload["failed"]
    if total != len(items):
        raise VerifyError("manifest total does not match items length")
    if succeeded + failed != total:
        raise VerifyError("manifest succeeded + failed must equal total")

    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise VerifyError(f"manifest items[{index}] must be an object")
        missing_item = sorted(REQUIRED_ITEM_KEYS - item.keys())
        if missing_item:
            raise VerifyError(
                f"manifest items[{index}] missing keys: {', '.join(missing_item)}"
            )
        if not isinstance(item.get("warnings"), list):
            raise VerifyError(f"manifest items[{index}] warnings must be a list")
        if not isinstance(item.get("input_path"), str):
            raise VerifyError(f"manifest items[{index}] input_path must be a string")
        if not isinstance(item.get("item_slug"), str):
            raise VerifyError(f"manifest items[{index}] item_slug must be a string")
        if item.get("status") not in {"succeeded", "failed"}:
            raise VerifyError(f"manifest items[{index}] status must be succeeded or failed")
        document_path = item.get("document_path")
        if document_path is not None and not isinstance(document_path, str):
            raise VerifyError(f"manifest items[{index}] document_path must be string or null")
        translated_document_path = item.get("translated_document_path")
        if translated_document_path is not None and not isinstance(translated_document_path, str):
            raise VerifyError(
                f"manifest items[{index}] translated_document_path must be string or null"
            )
        translation_status = item.get("translation_status")
        if translation_status is not None and translation_status not in {"succeeded", "failed"}:
            raise VerifyError(
                f"manifest items[{index}] translation_status must be succeeded, failed, or null"
            )
        translation_error = item.get("translation_error")
        if translation_error is not None and not isinstance(translation_error, str):
            raise VerifyError(
                f"manifest items[{index}] translation_error must be string or null"
            )
        source_file_path = item.get("source_file_path")
        if source_file_path is not None and not isinstance(source_file_path, str):
            raise VerifyError(
                f"manifest items[{index}] source_file_path must be string or null"
            )
        source_move_status = item.get("source_move_status")
        if source_move_status is not None and source_move_status not in {
            "moved",
            "copied_then_deleted",
            "failed",
        }:
            raise VerifyError(
                f"manifest items[{index}] source_move_status must be moved, copied_then_deleted, failed, or null"
            )
        source_move_error = item.get("source_move_error")
        if source_move_error is not None and not isinstance(source_move_error, str):
            raise VerifyError(
                f"manifest items[{index}] source_move_error must be string or null"
            )
        error_code = item.get("error_code")
        if error_code is not None and not isinstance(error_code, str):
            raise VerifyError(f"manifest items[{index}] error_code must be string or null")
        error_message = item.get("error_message")
        if error_message is not None and not isinstance(error_message, str):
            raise VerifyError(f"manifest items[{index}] error_message must be string or null")
        if not isinstance(item.get("images_count"), int):
            raise VerifyError(f"manifest items[{index}] images_count must be an integer")

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Sequence
from uuid import uuid4
from hashlib import sha256

from mineru_batch_cli.config import ConfigError, load_run_config, load_translate_config
from mineru_batch_cli.http_client import HttpClient
from mineru_batch_cli.discovery import DiscoveryError, discover_inputs, DiscoveredInput
from mineru_batch_cli.mineru_client import MineruClient, MineruClientError, UploadItem
from mineru_batch_cli.polling import PollingError, poll_batch_until_terminal
from mineru_batch_cli.artifacts import fetch_and_extract_artifacts
from mineru_batch_cli.normalize_markdown import normalize_primary_markdown
from mineru_batch_cli.image_filter import filter_referenced_images
from mineru_batch_cli.output_writer import (
    build_item_slug,
    build_translated_markdown_name,
    write_item_output,
)
from mineru_batch_cli.manifest import ManifestItem, build_manifest, write_manifest
from mineru_batch_cli.translation_client import (
    OpenAICompatibleTranslationAdapter,
    TranslationProvider,
)
from mineru_batch_cli.verify import VerifyError, verify_manifest


MODEL_VERSIONS = ("pipeline", "vlm", "MinerU-HTML")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mineru_batch_cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run batch processing")
    run_parser.add_argument("--input", required=True, help="Input directory")
    run_parser.add_argument("--output", required=True, help="Output directory")
    run_parser.add_argument(
        "--model-version",
        required=True,
        choices=MODEL_VERSIONS,
        help="MinerU model version",
    )
    run_parser.add_argument(
        "--continue-on-error",
        choices=("true", "false"),
        default="false",
        help="Continue processing after a file error",
    )
    run_parser.add_argument(
        "--config",
        help="Path to a JSON config file",
    )
    run_parser.add_argument(
        "--translation-enabled",
        choices=("true", "false"),
        default=None,
        help="Enable markdown translation step",
    )
    run_parser.add_argument(
        "--translation-api-base-url", default=None, help="Translation API base URL"
    )
    run_parser.add_argument(
        "--translation-api-key", default=None, help="Translation API key"
    )
    run_parser.add_argument(
        "--translation-model", default=None, help="Translation model name"
    )
    run_parser.add_argument(
        "--translation-target-language",
        default=None,
        help="Translation target language, e.g. zh-CN",
    )
    run_parser.add_argument(
        "--translation-timeout-sec",
        default=None,
        help="Translation HTTP timeout in seconds",
    )
    run_parser.add_argument(
        "--translation-retry-max",
        default=None,
        help="Translation HTTP max retry count",
    )
    run_parser.set_defaults(handler=_handle_run)

    translate_parser = subparsers.add_parser(
        "translate", help="Translate markdown files only"
    )
    translate_parser.add_argument("--input", required=True, help="Input directory")
    translate_parser.add_argument("--output", required=True, help="Output directory")
    translate_parser.add_argument(
        "--continue-on-error",
        choices=("true", "false"),
        default="true",
        help="Continue processing after a file error",
    )
    translate_parser.add_argument("--config", help="Path to a JSON config file")
    translate_parser.add_argument(
        "--translation-api-base-url", default=None, help="Translation API base URL"
    )
    translate_parser.add_argument(
        "--translation-api-key", default=None, help="Translation API key"
    )
    translate_parser.add_argument(
        "--translation-model", default=None, help="Translation model name"
    )
    translate_parser.add_argument(
        "--translation-target-language",
        default=None,
        help="Translation target language, e.g. zh-CN",
    )
    translate_parser.add_argument(
        "--translation-timeout-sec",
        default=None,
        help="Translation HTTP timeout in seconds",
    )
    translate_parser.add_argument(
        "--translation-retry-max",
        default=None,
        help="Translation HTTP max retry count",
    )
    translate_parser.set_defaults(handler=_handle_translate)

    verify_parser = subparsers.add_parser("verify", help="Verify a manifest")
    verify_parser.add_argument("--manifest", required=True, help="Manifest file")
    verify_parser.set_defaults(handler=_handle_verify)

    return parser


def _handle_run(_args: argparse.Namespace) -> int:
    try:
        config = load_run_config(_args, config_path=_args.config)
        discovered = discover_inputs(Path(_args.input))
    except ConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except DiscoveryError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    continue_on_error = _args.continue_on_error == "true"
    try:
        items = _run_pipeline(config, discovered, Path(_args.output), continue_on_error)
    except (MineruClientError, PollingError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    manifest = build_manifest(
        run_id=f"run-{uuid4().hex[:12]}",
        started_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        finished_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        input_root=str(Path(_args.input)),
        output_root=str(Path(_args.output)),
        items=items,
    )
    manifest_path = Path(_args.output) / "manifest.json"
    write_manifest(manifest_path, manifest)

    failed_obj = manifest.get("failed")
    succeeded_obj = manifest.get("succeeded")
    failed = failed_obj if isinstance(failed_obj, int) else 0
    succeeded = succeeded_obj if isinstance(succeeded_obj, int) else 0
    if failed == 0:
        return 0
    if succeeded > 0:
        return 2
    return 1


def _handle_translate(_args: argparse.Namespace) -> int:
    try:
        config = load_translate_config(_args, config_path=_args.config)
        discovered = discover_markdown_inputs(Path(_args.input))
    except ConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except DiscoveryError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    continue_on_error = _args.continue_on_error == "true"
    items = _run_translate_pipeline(
        config, discovered, Path(_args.output), continue_on_error
    )

    manifest = build_manifest(
        run_id=f"run-{uuid4().hex[:12]}",
        started_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        finished_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        input_root=str(Path(_args.input)),
        output_root=str(Path(_args.output)),
        items=items,
    )
    manifest_path = Path(_args.output) / "manifest.json"
    write_manifest(manifest_path, manifest)

    failed_obj = manifest.get("failed")
    succeeded_obj = manifest.get("succeeded")
    failed = failed_obj if isinstance(failed_obj, int) else 0
    succeeded = succeeded_obj if isinstance(succeeded_obj, int) else 0
    if failed == 0:
        return 0
    if succeeded > 0:
        return 2
    return 1


def discover_markdown_inputs(input_dir: Path) -> list[DiscoveredInput]:
    root = input_dir.resolve()
    if not root.exists() or not root.is_dir():
        raise DiscoveryError(f"Input directory does not exist: {input_dir}")

    collected: list[DiscoveredInput] = []
    for candidate in root.rglob("*"):
        if candidate.is_dir() or candidate.is_symlink():
            continue
        if candidate.suffix.lower() != ".md":
            continue
        relative = candidate.relative_to(root).as_posix()
        stats = candidate.stat()
        material = f"{relative}|{stats.st_size}|{stats.st_mtime_ns}"
        input_id = sha256(material.encode("utf-8")).hexdigest()[:16]
        collected.append(
            DiscoveredInput(path=candidate, relative_path=relative, input_id=input_id)
        )

    return sorted(
        collected,
        key=lambda item: (item.relative_path.casefold(), item.relative_path),
    )


def _run_translate_pipeline(
    config, discovered, output_root: Path, continue_on_error: bool
) -> list[ManifestItem]:
    output_root.mkdir(parents=True, exist_ok=True)
    if not discovered:
        return []

    translation_http_client = HttpClient(
        timeout_sec=config.translation_timeout_sec,
        retry_max=config.translation_retry_max,
    )
    translator = OpenAICompatibleTranslationAdapter(
        http_client=translation_http_client,
        api_base_url=config.translation_api_base_url,
        api_key=config.translation_api_key,
        model=config.translation_model,
    )

    ordered_items: list[ManifestItem] = []
    slug_set: set[str] = set()

    for index, source in enumerate(discovered):
        slug = build_item_slug(source.relative_path, existing=slug_set)
        slug_set.add(slug)

        translation_status: str | None = None
        translation_error: str | None = None
        warnings: list[str] = []
        translated_document_path: Path | None = None

        translation_status, translation_error, translated_document_path = (
            _translate_document(
                translator,
                document_path=source.path,
                target_language=config.translation_target_language,
                output_dir=output_root / "_translate_tmp" / source.input_id,
            )
        )
        if translation_error is not None:
            translation_error = _sanitize_error_message(translation_error)
            warnings.append(f"translation_failed: {translation_error}")

        metadata = {
            "data_id": source.input_id,
            "input_path": source.relative_path,
            "warnings": warnings,
            "translation_status": translation_status,
            "translation_error": translation_error,
        }

        try:
            out = write_item_output(
                output_root=output_root,
                item_slug=slug,
                document_source=source.path,
                translated_document_source=translated_document_path,
                translated_target_language=config.translation_target_language,
                source_input_file=source.path,
                images_source_dir=output_root / "_translate_tmp" / "images-empty",
                item_metadata_json=json.dumps(metadata, ensure_ascii=False),
            )
        except OSError as exc:
            ordered_items.append(
                ManifestItem(
                    input_path=source.relative_path,
                    item_slug=slug,
                    status="failed",
                    error_code="output_write_failed",
                    error_message=_sanitize_error_message(str(exc)),
                    document_path=None,
                    translated_document_path=None,
                    translation_status=translation_status,
                    translation_error=translation_error,
                    source_file_path=None,
                    source_move_status=None,
                    source_move_error=None,
                    images_count=0,
                    warnings=warnings,
                )
            )
            if not continue_on_error:
                for pending in discovered[index + 1 :]:
                    pending_slug = build_item_slug(
                        pending.relative_path, existing=slug_set
                    )
                    slug_set.add(pending_slug)
                    ordered_items.append(
                        ManifestItem(
                            input_path=pending.relative_path,
                            item_slug=pending_slug,
                            status="failed",
                            error_code="skipped_after_failure",
                            error_message="stopped after previous failure",
                            document_path=None,
                            translated_document_path=None,
                            translation_status=None,
                            translation_error=None,
                            source_file_path=None,
                            source_move_status=None,
                            source_move_error=None,
                            images_count=0,
                            warnings=[],
                        )
                    )
                break
            continue

        status = "succeeded" if translation_status == "succeeded" else "failed"
        error_code = None if status == "succeeded" else "translation_failed"
        error_message = None if status == "succeeded" else translation_error

        if out.source_move_status == "failed" and out.source_move_error is not None:
            warnings.append(_sanitize_error_message(out.source_move_error))

        ordered_items.append(
            ManifestItem(
                input_path=source.relative_path,
                item_slug=slug,
                status=status,
                error_code=error_code,
                error_message=error_message,
                document_path=str(out.document_path),
                translated_document_path=(
                    str(out.translated_document_path)
                    if out.translated_document_path is not None
                    else None
                ),
                translation_status=translation_status,
                translation_error=translation_error,
                source_file_path=(
                    str(out.source_document_path)
                    if out.source_document_path is not None
                    else None
                ),
                source_move_status=out.source_move_status,
                source_move_error=out.source_move_error,
                images_count=0,
                warnings=warnings,
            )
        )

        if status == "failed" and not continue_on_error:
            for pending in discovered[index + 1 :]:
                pending_slug = build_item_slug(pending.relative_path, existing=slug_set)
                slug_set.add(pending_slug)
                ordered_items.append(
                    ManifestItem(
                        input_path=pending.relative_path,
                        item_slug=pending_slug,
                        status="failed",
                        error_code="skipped_after_failure",
                        error_message="stopped after previous failure",
                        document_path=None,
                        translated_document_path=None,
                        translation_status=None,
                        translation_error=None,
                        source_file_path=None,
                        source_move_status=None,
                        source_move_error=None,
                        images_count=0,
                        warnings=[],
                    )
                )
            break

    return ordered_items


def _run_pipeline(
    config, discovered, output_root: Path, continue_on_error: bool
) -> list[ManifestItem]:
    output_root.mkdir(parents=True, exist_ok=True)
    if not discovered:
        return []

    http_client = HttpClient(timeout_sec=30.0, retry_max=config.retry_max)
    mineru = MineruClient(
        http_client,
        api_base_url=config.api_base_url,
        api_token=config.api_token,
    )

    translator: TranslationProvider | None = None
    if config.translation_enabled:
        translation_http_client = HttpClient(
            timeout_sec=config.translation_timeout_sec,
            retry_max=config.translation_retry_max,
        )
        translator = OpenAICompatibleTranslationAdapter(
            http_client=translation_http_client,
            api_base_url=config.translation_api_base_url,
            api_key=config.translation_api_key,
            model=config.translation_model,
        )

    uploads = [UploadItem(path=item.path, data_id=item.input_id) for item in discovered]
    upload_result = mineru.upload_local_files_batch(uploads)

    discovered_by_id = {item.input_id: item for item in discovered}
    index_by_id = {item.input_id: index for index, item in enumerate(discovered)}
    manifest_by_id: dict[str, ManifestItem] = {}
    slug_by_id: dict[str, str] = {}
    slug_set: set[str] = set()

    def mark_skipped_after(failed_data_id: str) -> None:
        failed_index = index_by_id.get(failed_data_id)
        if failed_index is None:
            return
        for entry in discovered[failed_index + 1 :]:
            if entry.input_id in manifest_by_id:
                continue
            manifest_by_id[entry.input_id] = ManifestItem(
                input_path=entry.relative_path,
                item_slug=_get_or_create_slug(
                    entry.input_id, entry.relative_path, slug_by_id, slug_set
                ),
                status="failed",
                error_code="skipped_after_failure",
                error_message="stopped after previous failure",
                document_path=None,
                translated_document_path=None,
                translation_status=None,
                translation_error=None,
                source_file_path=None,
                source_move_status=None,
                source_move_error=None,
                images_count=0,
                warnings=[],
            )

    uploaded_ids: list[str] = []
    for result in upload_result.results:
        source = discovered_by_id.get(result.data_id)
        if source is None:
            continue
        slug = _get_or_create_slug(
            result.data_id, source.relative_path, slug_by_id, slug_set
        )
        if result.status == "uploaded":
            uploaded_ids.append(result.data_id)
            continue
        manifest_by_id[result.data_id] = ManifestItem(
            input_path=source.relative_path,
            item_slug=slug,
            status="failed",
            error_code="upload_failed",
            error_message=result.error,
            document_path=None,
            translated_document_path=None,
            translation_status=None,
            translation_error=None,
            source_file_path=None,
            source_move_status=None,
            source_move_error=None,
            images_count=0,
            warnings=[],
        )
        if not continue_on_error:
            mark_skipped_after(result.data_id)
            break

    if uploaded_ids:
        polled = poll_batch_until_terminal(
            http_client,
            api_base_url=config.api_base_url,
            api_token=config.api_token,
            batch_id=upload_result.batch_id,
            poll_interval_sec=config.poll_interval_sec,
            max_poll_min=config.max_poll_min,
        )

        polled_map = {
            item.data_id: item for item in polled if item.data_id in uploaded_ids
        }

        artifact_inputs: list[dict[str, str]] = []
        for data_id in uploaded_ids:
            if (
                data_id in manifest_by_id
                and manifest_by_id[data_id].status != "succeeded"
            ):
                if not continue_on_error:
                    break
                continue
            source = discovered_by_id[data_id]
            slug = _get_or_create_slug(
                data_id, source.relative_path, slug_by_id, slug_set
            )
            polled_item = polled_map.get(data_id)
            if polled_item is None:
                manifest_by_id[data_id] = ManifestItem(
                    input_path=source.relative_path,
                    item_slug=slug,
                    status="failed",
                    error_code="poll_missing",
                    error_message="missing poll result",
                    document_path=None,
                    translated_document_path=None,
                    translation_status=None,
                    translation_error=None,
                    source_file_path=None,
                    source_move_status=None,
                    source_move_error=None,
                    images_count=0,
                    warnings=[],
                )
                if not continue_on_error:
                    mark_skipped_after(data_id)
                    break
                continue
            if polled_item.state != "done":
                manifest_by_id[data_id] = ManifestItem(
                    input_path=source.relative_path,
                    item_slug=slug,
                    status="failed",
                    error_code=f"poll_{polled_item.state}",
                    error_message=polled_item.err_msg,
                    document_path=None,
                    translated_document_path=None,
                    translation_status=None,
                    translation_error=None,
                    source_file_path=None,
                    source_move_status=None,
                    source_move_error=None,
                    images_count=0,
                    warnings=[],
                )
                if not continue_on_error:
                    mark_skipped_after(data_id)
                    break
                continue
            if polled_item.full_zip_url is None:
                manifest_by_id[data_id] = ManifestItem(
                    input_path=source.relative_path,
                    item_slug=slug,
                    status="failed",
                    error_code="poll_missing_zip_url",
                    error_message="done state without full_zip_url",
                    document_path=None,
                    translated_document_path=None,
                    translation_status=None,
                    translation_error=None,
                    source_file_path=None,
                    source_move_status=None,
                    source_move_error=None,
                    images_count=0,
                    warnings=[],
                )
                if not continue_on_error:
                    mark_skipped_after(data_id)
                    break
                continue
            artifact_inputs.append(
                {
                    "data_id": data_id,
                    "state": "done",
                    "full_zip_url": polled_item.full_zip_url,
                }
            )

        with tempfile.TemporaryDirectory(prefix="mineru-artifacts-") as temp_dir:
            artifact_results = fetch_and_extract_artifacts(
                http_client,
                items=artifact_inputs,
                output_root=Path(temp_dir),
            )
            for artifact in artifact_results:
                source = discovered_by_id[artifact.data_id]
                slug = _get_or_create_slug(
                    artifact.data_id, source.relative_path, slug_by_id, slug_set
                )

                if (
                    artifact.status != "artifact_ready"
                    or artifact.extracted_dir is None
                ):
                    manifest_by_id[artifact.data_id] = ManifestItem(
                        input_path=source.relative_path,
                        item_slug=slug,
                        status="failed",
                        error_code=artifact.status,
                        error_message=artifact.error,
                        document_path=None,
                        translated_document_path=None,
                        translation_status=None,
                        translation_error=None,
                        source_file_path=None,
                        source_move_status=None,
                        source_move_error=None,
                        images_count=0,
                        warnings=[],
                    )
                    if not continue_on_error:
                        mark_skipped_after(artifact.data_id)
                        break
                    continue

                normalized = normalize_primary_markdown(
                    artifact.extracted_dir,
                    Path(temp_dir) / "normalized" / artifact.data_id,
                )
                if (
                    normalized.status != "markdown_ready"
                    or normalized.document_path is None
                ):
                    manifest_by_id[artifact.data_id] = ManifestItem(
                        input_path=source.relative_path,
                        item_slug=slug,
                        status="failed",
                        error_code="markdown_missing",
                        error_message="markdown not found",
                        document_path=None,
                        translated_document_path=None,
                        translation_status=None,
                        translation_error=None,
                        source_file_path=None,
                        source_move_status=None,
                        source_move_error=None,
                        images_count=0,
                        warnings=[],
                    )
                    if not continue_on_error:
                        mark_skipped_after(artifact.data_id)
                        break
                    continue

                translated_document_path: Path | None = None
                translation_status: str | None = None
                translation_error: str | None = None
                warnings: list[str] = []
                if translator is not None:
                    translation_status, translation_error, translated_document_path = (
                        _translate_document(
                            translator,
                            document_path=normalized.document_path,
                            target_language=config.translation_target_language,
                            output_dir=Path(temp_dir) / "translated" / artifact.data_id,
                        )
                    )
                    if translation_error is not None:
                        safe_error = _sanitize_error_message(translation_error)
                        translation_error = safe_error
                        warnings.append(f"translation_failed: {safe_error}")

                filtered_dir = Path(temp_dir) / "filtered" / artifact.data_id
                try:
                    image_result = filter_referenced_images(
                        normalized.document_path,
                        artifact.extracted_dir,
                        filtered_dir,
                    )
                    missing_images = image_result.missing_images
                    kept_images_count = len(image_result.kept_images)
                except OSError as exc:
                    filtered_dir.mkdir(parents=True, exist_ok=True)
                    missing_images = []
                    kept_images_count = 0
                    warnings.append(
                        _sanitize_error_message(f"image_filter_failed: {exc}")
                    )

                metadata = {
                    "data_id": artifact.data_id,
                    "input_path": source.relative_path,
                    "warnings": missing_images + warnings,
                    "translation_status": translation_status,
                    "translation_error": translation_error,
                }
                try:
                    out = write_item_output(
                        output_root=output_root,
                        item_slug=slug,
                        document_source=normalized.document_path,
                        translated_document_source=translated_document_path,
                        translated_target_language=config.translation_target_language,
                        source_input_file=source.path,
                        images_source_dir=filtered_dir,
                        item_metadata_json=json.dumps(metadata, ensure_ascii=False),
                    )
                except OSError as exc:
                    manifest_by_id[artifact.data_id] = ManifestItem(
                        input_path=source.relative_path,
                        item_slug=slug,
                        status="failed",
                        error_code="output_write_failed",
                        error_message=_sanitize_error_message(str(exc)),
                        document_path=None,
                        translated_document_path=None,
                        translation_status=translation_status,
                        translation_error=translation_error,
                        source_file_path=None,
                        source_move_status=None,
                        source_move_error=None,
                        images_count=0,
                        warnings=missing_images + warnings,
                    )
                    if not continue_on_error:
                        mark_skipped_after(artifact.data_id)
                        break
                    continue

                if (
                    out.source_move_status == "failed"
                    and out.source_move_error is not None
                ):
                    warnings.append(_sanitize_error_message(out.source_move_error))

                manifest_by_id[artifact.data_id] = ManifestItem(
                    input_path=source.relative_path,
                    item_slug=slug,
                    status="succeeded",
                    error_code=None,
                    error_message=None,
                    document_path=str(out.document_path),
                    translated_document_path=(
                        str(out.translated_document_path)
                        if out.translated_document_path is not None
                        else None
                    ),
                    translation_status=translation_status,
                    translation_error=translation_error,
                    source_file_path=(
                        str(out.source_document_path)
                        if out.source_document_path is not None
                        else None
                    ),
                    source_move_status=out.source_move_status,
                    source_move_error=out.source_move_error,
                    images_count=kept_images_count,
                    warnings=missing_images + warnings,
                )

    ordered_items: list[ManifestItem] = []
    for entry in discovered:
        item = manifest_by_id.get(entry.input_id)
        if item is None:
            item = ManifestItem(
                input_path=entry.relative_path,
                item_slug=_get_or_create_slug(
                    entry.input_id, entry.relative_path, slug_by_id, slug_set
                ),
                status="failed",
                error_code="unprocessed",
                error_message="item not processed",
                document_path=None,
                translated_document_path=None,
                translation_status=None,
                translation_error=None,
                source_file_path=None,
                source_move_status=None,
                source_move_error=None,
                images_count=0,
                warnings=[],
            )
        ordered_items.append(item)

    return ordered_items


def _translate_document(
    translator: TranslationProvider,
    *,
    document_path: Path,
    target_language: str,
    output_dir: Path,
) -> tuple[str | None, str | None, Path | None]:
    try:
        markdown = document_path.read_text(encoding="utf-8")
    except OSError as exc:
        return ("failed", f"read markdown failed: {exc}", None)

    try:
        translated = translator.translate_markdown(
            markdown, target_language=target_language
        )
    except Exception as exc:
        return ("failed", _sanitize_error_message(str(exc)), None)

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        translated_name = build_translated_markdown_name(
            document_path.name, target_language
        )
        translated_path = output_dir / translated_name
        translated_path.write_text(translated, encoding="utf-8")
    except OSError as exc:
        return (
            "failed",
            _sanitize_error_message(f"write translated markdown failed: {exc}"),
            None,
        )

    return ("succeeded", None, translated_path)


def _sanitize_error_message(message: str, max_chars: int = 300) -> str:
    collapsed = " ".join(message.splitlines()).strip()
    if len(collapsed) <= max_chars:
        return collapsed
    return f"{collapsed[:max_chars]}..."


def _get_or_create_slug(
    data_id: str,
    relative_path: str,
    slug_by_id: dict[str, str],
    slug_set: set[str],
) -> str:
    existing = slug_by_id.get(data_id)
    if existing is not None:
        return existing
    slug = build_item_slug(relative_path, existing=slug_set)
    slug_set.add(slug)
    slug_by_id[data_id] = slug
    return slug


def _handle_verify(_args: argparse.Namespace) -> int:
    try:
        verify_manifest(Path(_args.manifest))
    except VerifyError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print("MANIFEST_OK")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        return 0
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())

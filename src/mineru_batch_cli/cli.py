from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Sequence
from uuid import uuid4

from mineru_batch_cli.config import ConfigError, load_run_config
from mineru_batch_cli.http_client import HttpClient
from mineru_batch_cli.discovery import DiscoveryError, discover_inputs
from mineru_batch_cli.mineru_client import MineruClient, MineruClientError, UploadItem
from mineru_batch_cli.polling import PolledItem, PollingError, poll_batch_until_terminal
from mineru_batch_cli.artifacts import ArtifactFetchResult, fetch_and_extract_artifacts
from mineru_batch_cli.normalize_markdown import normalize_primary_markdown
from mineru_batch_cli.image_filter import filter_referenced_images
from mineru_batch_cli.output_writer import build_item_slug, write_item_output
from mineru_batch_cli.manifest import ManifestItem, build_manifest, write_manifest
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
    run_parser.set_defaults(handler=_handle_run)

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
    except (MineruClientError, PollingError) as exc:
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


def _run_pipeline(config, discovered, output_root: Path, continue_on_error: bool) -> list[ManifestItem]:
    output_root.mkdir(parents=True, exist_ok=True)
    if not discovered:
        return []

    http_client = HttpClient(timeout_sec=30.0, retry_max=config.retry_max)
    mineru = MineruClient(
        http_client,
        api_base_url=config.api_base_url,
        api_token=config.api_token,
    )

    uploads = [UploadItem(path=item.path, data_id=item.input_id) for item in discovered]
    upload_result = mineru.upload_local_files_batch(uploads)

    discovered_by_id = {item.input_id: item for item in discovered}
    manifest_by_id: dict[str, ManifestItem] = {}
    uploaded_ids: list[str] = []
    for result in upload_result.results:
        source = discovered_by_id.get(result.data_id)
        if source is None:
            continue
        slug = source.relative_path.replace("/", "-").lower()
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
            images_count=0,
            warnings=[],
        )

    if uploaded_ids:
        polled = poll_batch_until_terminal(
            http_client,
            api_base_url=config.api_base_url,
            api_token=config.api_token,
            batch_id=upload_result.batch_id,
            poll_interval_sec=config.poll_interval_sec,
            max_poll_min=config.max_poll_min,
        )

        polled_map = {item.data_id: item for item in polled if item.data_id in uploaded_ids}

        artifact_inputs: list[dict[str, str]] = []
        for data_id in uploaded_ids:
            source = discovered_by_id[data_id]
            slug = source.relative_path.replace("/", "-").lower()
            polled_item = polled_map.get(data_id)
            if polled_item is None:
                manifest_by_id[data_id] = ManifestItem(
                    input_path=source.relative_path,
                    item_slug=slug,
                    status="failed",
                    error_code="poll_missing",
                    error_message="missing poll result",
                    document_path=None,
                    images_count=0,
                    warnings=[],
                )
                continue
            if polled_item.state != "done":
                manifest_by_id[data_id] = ManifestItem(
                    input_path=source.relative_path,
                    item_slug=slug,
                    status="failed",
                    error_code=f"poll_{polled_item.state}",
                    error_message=polled_item.err_msg,
                    document_path=None,
                    images_count=0,
                    warnings=[],
                )
                continue
            if polled_item.full_zip_url is None:
                manifest_by_id[data_id] = ManifestItem(
                    input_path=source.relative_path,
                    item_slug=slug,
                    status="failed",
                    error_code="poll_missing_zip_url",
                    error_message="done state without full_zip_url",
                    document_path=None,
                    images_count=0,
                    warnings=[],
                )
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
            slug_set: set[str] = set()
            for artifact in artifact_results:
                source = discovered_by_id[artifact.data_id]
                slug = build_item_slug(source.relative_path, existing=slug_set)
                slug_set.add(slug)

                if artifact.status != "artifact_ready" or artifact.extracted_dir is None:
                    manifest_by_id[artifact.data_id] = ManifestItem(
                        input_path=source.relative_path,
                        item_slug=slug,
                        status="failed",
                        error_code=artifact.status,
                        error_message=artifact.error,
                        document_path=None,
                        images_count=0,
                        warnings=[],
                    )
                    continue

                normalized = normalize_primary_markdown(
                    artifact.extracted_dir,
                    Path(temp_dir) / "normalized" / artifact.data_id,
                )
                if normalized.status != "markdown_ready" or normalized.document_path is None:
                    manifest_by_id[artifact.data_id] = ManifestItem(
                        input_path=source.relative_path,
                        item_slug=slug,
                        status="failed",
                        error_code="markdown_missing",
                        error_message="markdown not found",
                        document_path=None,
                        images_count=0,
                        warnings=[],
                    )
                    continue

                filtered_dir = Path(temp_dir) / "filtered" / artifact.data_id
                image_result = filter_referenced_images(
                    normalized.document_path,
                    artifact.extracted_dir,
                    filtered_dir,
                )

                metadata = {
                    "data_id": artifact.data_id,
                    "input_path": source.relative_path,
                    "warnings": image_result.missing_images,
                }
                out = write_item_output(
                    output_root=output_root,
                    item_slug=slug,
                    document_source=normalized.document_path,
                    images_source_dir=filtered_dir,
                    item_metadata_json=json.dumps(metadata, ensure_ascii=False),
                )

                manifest_by_id[artifact.data_id] = ManifestItem(
                    input_path=source.relative_path,
                    item_slug=slug,
                    status="succeeded",
                    error_code=None,
                    error_message=None,
                    document_path=str(out.document_path),
                    images_count=len(image_result.kept_images),
                    warnings=image_result.missing_images,
                )

    ordered_items: list[ManifestItem] = []
    for entry in discovered:
        item = manifest_by_id.get(entry.input_id)
        if item is None:
            item = ManifestItem(
                input_path=entry.relative_path,
                item_slug=entry.relative_path.replace("/", "-").lower(),
                status="failed",
                error_code="unprocessed",
                error_message="item not processed",
                document_path=None,
                images_count=0,
                warnings=[],
            )
        ordered_items.append(item)

    if not continue_on_error:
        first_fail_index = next((i for i, item in enumerate(ordered_items) if item.status != "succeeded"), None)
        if first_fail_index is not None:
            for idx in range(first_fail_index + 1, len(ordered_items)):
                current = ordered_items[idx]
                if current.status == "succeeded":
                    ordered_items[idx] = ManifestItem(
                        input_path=current.input_path,
                        item_slug=current.item_slug,
                        status="failed",
                        error_code="skipped_after_failure",
                        error_message="stopped after previous failure",
                        document_path=None,
                        images_count=0,
                        warnings=[],
                    )

    return ordered_items


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

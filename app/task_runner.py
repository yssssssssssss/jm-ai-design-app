from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from openai import OpenAI

from app.config import Settings
from app.db import connect
from app.evidence_tools import (
    build_issues_json,
    filter_font_related_audit,
    run_annotations,
    run_color_analysis,
    run_measurements,
    write_json,
    write_regions_json,
)
from app.models import TASK_FAILED, TASK_RUNNING, TASK_SUCCEEDED
from app.openai_audit import (
    AUDIT_IMAGE_MAX_SIDE,
    DEGRADED_AUDIT_IMAGE_MAX_SIDE,
    audit_image,
    audit_image_with_chat,
    compact_audit_spec,
)
from app.report_renderer import render_report_html
from app.repositories import (
    get_task_by_id,
    list_task_images,
    update_task_image_status,
    update_task_status,
)
from app.storage import ensure_task_dirs, relative_to_data, resolve_data_path


Auditor = Callable[[Path], dict[str, Any]]
SPEC_PATH = Path(__file__).resolve().parent.parent / "references" / "jm-ai-design-spec.md"
PRIMARY_AUDIT_TIMEOUT_SECONDS = 120
MIN_FALLBACK_AUDIT_TIMEOUT_SECONDS = 30


def _openai_client(settings: Settings, timeout: int) -> OpenAI:
    return OpenAI(
        api_key=settings.audit_api_key,
        base_url=settings.audit_base_url,
        timeout=timeout,
        max_retries=0,
    )


def _fallback_timeout(settings: Settings, primary_timeout: int) -> int:
    if settings.audit_timeout_seconds <= primary_timeout:
        return settings.audit_timeout_seconds
    return max(
        MIN_FALLBACK_AUDIT_TIMEOUT_SECONDS,
        settings.audit_timeout_seconds - primary_timeout,
    )


def _is_timeout_error(exc: Exception) -> bool:
    text = f"{exc.__class__.__name__}: {exc}".lower()
    return "timeout" in text or "timed out" in text


def _degraded_reasoning_effort(reasoning_effort: str | None) -> str | None:
    if reasoning_effort in {"medium", "high", "xhigh"}:
        return "low"
    return reasoning_effort


def _default_auditor(
    settings: Settings,
    declared_screen_size: tuple[int, int] | None = None,
) -> Auditor:
    spec_text = compact_audit_spec(SPEC_PATH.read_text(encoding="utf-8"))
    primary_timeout = min(settings.audit_timeout_seconds, PRIMARY_AUDIT_TIMEOUT_SECONDS)
    client = _openai_client(settings, primary_timeout)
    audit = (
        audit_image_with_chat
        if settings.audit_model_provider == "jdcloud"
        else audit_image
    )

    def run_audit(image_path: Path) -> dict[str, Any]:
        try:
            return audit(
                client,
                settings.audit_model,
                image_path,
                spec_text,
                reasoning_effort=settings.audit_reasoning_effort,
                declared_screen_size=declared_screen_size,
                max_image_side=AUDIT_IMAGE_MAX_SIDE,
                image_detail="high",
            )
        except Exception as exc:
            if not _is_timeout_error(exc):
                raise

            fallback_client = _openai_client(
                settings,
                _fallback_timeout(settings, primary_timeout),
            )
            return audit(
                fallback_client,
                settings.audit_model,
                image_path,
                spec_text,
                reasoning_effort=_degraded_reasoning_effort(
                    settings.audit_reasoning_effort
                ),
                declared_screen_size=declared_screen_size,
                max_image_side=DEGRADED_AUDIT_IMAGE_MAX_SIDE,
                image_detail="low",
            )

    return run_audit


def _stem(filename: str) -> str:
    return filename.rsplit(".", 1)[0]


def _short_error(exc: Exception) -> str:
    return str(exc)[:500] or exc.__class__.__name__


def run_task(
    settings: Settings,
    task_id: int,
    auditor: Auditor | None = None,
) -> None:
    conn = connect(settings.db_path)
    try:
        task = get_task_by_id(conn, task_id)
        if task is None:
            return

        update_task_status(conn, task_id, TASK_RUNNING, error_message=None)
        dirs = ensure_task_dirs(settings, task_id)
        declared_screen_size = (
            (task.screen_width_px, task.screen_height_px)
            if task.screen_width_px and task.screen_height_px
            else None
        )
        auditor = auditor or _default_auditor(settings, declared_screen_size)

        image_results: list[dict[str, Any]] = []
        success_count = 0
        failure_count = 0

        for image in list_task_images(conn, task_id):
            update_task_image_status(conn, image.id, TASK_RUNNING, error_message=None)
            image_path = resolve_data_path(settings, image.original_path)
            image_artifacts = dirs.artifacts / _stem(image.filename)
            image_artifacts.mkdir(parents=True, exist_ok=True)

            try:
                audit = filter_font_related_audit(auditor(image_path))
                audit_path = image_artifacts / "audit.json"
                tokens_path = image_artifacts / "tokens.json"
                regions_path = image_artifacts / "regions.json"
                measurements_path = image_artifacts / "measurements.json"
                issues_path = image_artifacts / "issues.json"
                crop_dir = image_artifacts / "region-crops"

                write_json(audit_path, audit)
                run_color_analysis(image_path, tokens_path, audit.get("sample_points", []))
                write_regions_json(
                    regions_path,
                    audit.get("regions", []),
                    audit.get("distances", []),
                )
                run_measurements(image_path, regions_path, measurements_path, crop_dir)

                issues_for_screenshots = build_issues_json(audit.get("issues", []))
                write_json(issues_path, issues_for_screenshots)
                annotated_path = None
                issue_crop_paths: list[str] = []
                if issues_for_screenshots:
                    run_annotations(image_path, issues_path, image_artifacts)
                    annotated_path = image_artifacts / "annotated.png"
                    issue_crop_paths = [
                        relative_to_data(settings, path)
                        for path in sorted(image_artifacts.glob("issue-*.png"))
                    ]

                annotated_rel = (
                    relative_to_data(settings, annotated_path) if annotated_path else None
                )
                tokens_rel = relative_to_data(settings, tokens_path)
                measurements_rel = relative_to_data(settings, measurements_path)
                issues_rel = relative_to_data(settings, issues_path)
                audit_rel = relative_to_data(settings, audit_path)

                update_task_image_status(
                    conn,
                    image.id,
                    TASK_SUCCEEDED,
                    annotated_path=annotated_rel,
                    tokens_path=tokens_rel,
                    measurements_path=measurements_rel,
                    issues_path=issues_rel,
                    audit_json_path=audit_rel,
                    error_message=None,
                )
                image_results.append(
                    {
                        "filename": image.filename,
                        "audit": audit,
                        "artifacts": {
                            "annotated": annotated_rel,
                            "issue_crops": issue_crop_paths,
                            "tokens": tokens_rel,
                            "measurements": measurements_rel,
                            "issues": issues_rel,
                            "audit_json": audit_rel,
                        },
                    }
                )
                success_count += 1
            except Exception as exc:  # noqa: BLE001 - image-level isolation is intentional.
                failure_count += 1
                update_task_image_status(
                    conn,
                    image.id,
                    TASK_FAILED,
                    error_message=_short_error(exc),
                )

        if success_count:
            if failure_count:
                summary = f"部分图片审核失败：成功 {success_count} 张，失败 {failure_count} 张"
            else:
                summary = "审核完成"
            html = render_report_html(
                {
                    "title": task.title,
                    "summary": summary,
                    "screen_width_px": task.screen_width_px,
                    "screen_height_px": task.screen_height_px,
                },
                image_results,
                task_id=task_id,
            )
            dirs.report.write_text(html, encoding="utf-8")
            update_task_status(
                conn,
                task_id,
                TASK_SUCCEEDED,
                summary=summary,
                report_path=relative_to_data(settings, dirs.report),
                error_message=None,
            )
            return

        update_task_status(
            conn,
            task_id,
            TASK_FAILED,
            summary=None,
            report_path=None,
            error_message="全部图片审核失败",
        )
    finally:
        conn.close()

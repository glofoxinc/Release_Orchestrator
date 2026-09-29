"""Shared release deployment execute / preview / undo / mark-released.

Used by Streamlit (``ui/step5_execute.py``) and MCP/headless callers.
Progress reporting is injectable via callbacks — no Streamlit dependency here.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Iterable

import config
import deployment_history
import jira_client
import team_scope

# (completed_count, total, ticket_key_or_message)
ProgressCallback = Callable[[int, int, str], None]


def _browse_link(key: str) -> str:
    return f"[{key}]({config.JIRA_BASE_URL}/browse/{key})"


def _emit_progress(
    on_progress: ProgressCallback | None,
    completed: int,
    total: int,
    message: str,
) -> None:
    if on_progress is None:
        return
    on_progress(completed, total, message)


def _guard_scoped_write_keys(
    project_key: str,
    release: dict,
    ticket_keys: Iterable[str],
) -> dict[str, Any] | None:
    version_id = str((release or {}).get("id") or "")
    if not version_id:
        return None
    try:
        team_scope.assert_keys_in_scoped_version(project_key, version_id, ticket_keys)
    except team_scope.TeamScopeError as exc:
        return {
            "status": "error",
            "error": str(exc),
            "out_of_scope_keys": team_scope.keys_outside_scoped_version(
                project_key,
                version_id,
                ticket_keys,
            ),
        }
    return None


def _normalize_selected_keys(selected_keys: Iterable[str] | None) -> set[str]:
    if not selected_keys:
        return set()
    return {str(k) for k in selected_keys}


def _first_filled_entry(filled: dict[str, dict]) -> dict | None:
    if not filled:
        return None
    return next(iter(filled.values()))


def _resolve_grouped_client(client_label: str, grouped: dict[str, list]) -> str | None:
    if client_label in grouped:
        return client_label
    return jira_client.fuzzy_match_client(client_label, list(grouped.keys()))


def _issues_for_filled_client(client_label: str, grouped: dict[str, list]) -> list[dict]:
    key = _resolve_grouped_client(client_label, grouped)
    if not key:
        return []
    return grouped.get(key, [])


def build_tickets_to_process(
    *,
    filled: dict,
    selected_keys: Iterable[str] | None,
    project_key: str,
    issues: list[dict] | None = None,
    grouped: dict[str, list] | None = None,
    multi_client: bool = False,
) -> list[tuple[str, dict, dict]]:
    """Build ``(label, deploy_info, issue)`` rows matching the UI deploy loop."""
    keys = _normalize_selected_keys(selected_keys)
    issues = issues or []
    if multi_client:
        grp = grouped or {}
        return [
            (client, info, iss)
            for client, info in filled.items()
            for iss in _issues_for_filled_client(client, grp)
            if iss["key"] in keys
        ]
    info_single = _first_filled_entry(filled)
    if not info_single or not keys:
        return []
    return [(project_key, info_single, iss) for iss in issues if iss["key"] in keys]


def _history_clients(
    *,
    filled: dict,
    selected_keys: set[str],
    project_key: str,
    multi_client: bool,
    grouped: dict[str, list] | None,
    issues: list[dict] | None,
) -> dict:
    history_clients: dict = {}
    if multi_client:
        grp = grouped or {}
        for cname, cinfo in filled.items():
            history_clients[cname] = {
                **cinfo,
                "tickets": [iss["key"] for iss in _issues_for_filled_client(cname, grp) if iss["key"] in selected_keys],
            }
    else:
        single_info = _first_filled_entry(filled) or {}
        history_clients[project_key] = {
            **single_info,
            "tickets": [iss["key"] for iss in (issues or []) if iss["key"] in selected_keys] if selected_keys else [],
        }
    return history_clients


def _deployment_comment_text(
    deployment_date: str,
    deployment_time: str,
    deployment_id: str,
) -> str:
    """Plain-text body matching the Jira deployment comment template."""
    env = config.DEPLOY_ENVIRONMENT
    try:
        import template_engine

        return template_engine.render_template(
            "deployment_comment.j2",
            environment=env,
            deployment_date=deployment_date,
            deployment_time=deployment_time,
            deployment_id=deployment_id,
        ).strip()
    except Exception:
        return (
            f"The change has been deployed to {env} on {deployment_date} "
            f"at {deployment_time}.\n\n"
            f"and changes are reflecting the {env} and verified\n\n"
            f"Deployment ID: {deployment_id}"
        )


def preview_deploy(
    tickets_to_process: list[tuple[str, dict, dict]] | None = None,
    *,
    filled: dict | None = None,
    release: dict | None = None,
    project_key: str = "",
    selected_keys: Iterable[str] | None = None,
    issues: list[dict] | None = None,
    grouped: dict[str, list] | None = None,
    multi_client: bool = False,
    force_deploy: bool = False,
) -> dict[str, Any]:
    """Dry-run preview: duplicate-comment checks only; no writes."""
    if tickets_to_process is None:
        tickets_to_process = build_tickets_to_process(
            filled=filled or {},
            selected_keys=selected_keys,
            project_key=project_key,
            issues=issues,
            grouped=grouped,
            multi_client=multi_client,
        )

    write_keys = [row[2]["key"] for row in tickets_to_process]
    scope_block = _guard_scoped_write_keys(project_key, release or {}, write_keys)
    if scope_block:
        return scope_block

    would_update: list[str] = []
    would_skip: list[str] = []
    errors: list[str] = []
    log: list[str] = []
    comment_previews: dict[str, str] = {}

    if not tickets_to_process:
        return {
            "status": "dry_run",
            "would_update": [],
            "would_skip": [],
            "errors": 1 if _normalize_selected_keys(selected_keys) else 0,
            "log": [
                "No tickets matched deployment selection."
                if _normalize_selected_keys(selected_keys)
                else "No tickets selected for deployment."
            ],
            "release": (release or {}).get("name"),
            "project": project_key,
            "force_deploy": force_deploy,
            "comment_preview": None,
            "comment_previews": {},
            "message": "Preview only — no Jira writes.",
        }

    for _label, t_info, iss in tickets_to_process:
        key = iss["key"]
        comment_previews[key] = _deployment_comment_text(
            str(t_info.get("deployment_date") or ""),
            str(t_info.get("deployment_time") or ""),
            str(t_info.get("deployment_id") or ""),
        )

    # Read-only duplicate checks may use bounded concurrency; result order is preserved.
    keys_in_order = [iss["key"] for _label, _info, iss in tickets_to_process]
    if force_deploy:
        already_by_key = {k: False for k in keys_in_order}
        check_errors: dict[str, Exception] = {}
    else:
        already_by_key, check_errors = jira_client.check_deployment_comments(
            keys_in_order,
        )

    for _label, _t_info, iss in tickets_to_process:
        key = iss["key"]
        link = _browse_link(key)
        if force_deploy:
            would_update.append(key)
            log.append(f"Would update {link} (force_deploy)")
            continue
        if key in check_errors:
            errors.append(key)
            log.append(f"Cannot verify comments for {link}: {check_errors[key]}")
            continue
        if already_by_key.get(key):
            would_skip.append(key)
            log.append(f"Would skip {link} — verified deployment comment exists")
        else:
            would_update.append(key)
            log.append(f"Would update {link}")

    sample_comment = None
    if tickets_to_process:
        sample_key = would_update[0] if would_update else tickets_to_process[0][2]["key"]
        sample_comment = comment_previews.get(sample_key)

    return {
        "status": "dry_run",
        "would_update": would_update,
        "would_skip": would_skip,
        "errors": len(errors),
        "error_keys": errors,
        "log": log,
        "ticket_count": len(tickets_to_process),
        "release": (release or {}).get("name"),
        "project": project_key,
        "force_deploy": force_deploy,
        "comment_preview": sample_comment,
        "comment_previews": comment_previews,
        "message": "Preview only — no Jira writes.",
    }


def execute_deploy(
    tickets_to_process: list[tuple[str, dict, dict]] | None = None,
    *,
    filled: dict,
    release: dict,
    project_key: str,
    selected_keys: Iterable[str] | None = None,
    issues: list[dict] | None = None,
    grouped: dict[str, list] | None = None,
    multi_client: bool = False,
    force_deploy: bool = False,
    dry_run: bool = False,
    save_to_history: bool = True,
    sharepoint_url: str | None = None,
    tckt_key: str | None = None,
    tckt_url: str | None = None,
    slack_results: Any = None,
    project_results: list[dict] | None = None,
    on_progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Execute deployment (or preview when ``dry_run=True``).

    Accepts an explicit ``tickets_to_process`` list, or builds one from
    ``filled`` / ``selected_keys`` / ``issues`` / ``grouped``.

    All Jira **writes** (comments, transitions) remain sequential and ordered.
    ``on_progress(completed, total, message)`` is invoked after each ticket
    attempt so Streamlit / MCP can surface progress without owning the loop.
    """
    if dry_run:
        return preview_deploy(
            tickets_to_process,
            filled=filled,
            release=release,
            project_key=project_key,
            selected_keys=selected_keys,
            issues=issues,
            grouped=grouped,
            multi_client=multi_client,
            force_deploy=force_deploy,
        )

    keys = _normalize_selected_keys(selected_keys)
    if tickets_to_process is None:
        tickets_to_process = build_tickets_to_process(
            filled=filled,
            selected_keys=keys,
            project_key=project_key,
            issues=issues,
            grouped=grouped,
            multi_client=multi_client,
        )

    if not tickets_to_process:
        msg = (
            "No tickets matched the deployment client(s) you filled in."
            if keys
            else "No tickets selected for deployment."
        )
        return {
            "status": "empty",
            "success": 0,
            "skipped": 0,
            "errors": 0,
            "log": [msg],
            "undo_data": [],
            "history_timestamp": None,
        }

    write_keys = [row[2]["key"] for row in tickets_to_process]
    scope_block = _guard_scoped_write_keys(project_key, release or {}, write_keys)
    if scope_block:
        return {
            **scope_block,
            "success": 0,
            "skipped": 0,
            "errors": len(write_keys),
            "log": [scope_block.get("error", "Out-of-scope tickets blocked.")],
            "undo_data": [],
            "history_timestamp": None,
        }

    success = skip = errors = 0
    log_lines: list[str] = []
    undo_data: list[dict] = []
    total = len(tickets_to_process)
    keys_in_order = [row[2]["key"] for row in tickets_to_process]
    already_by_key: dict[str, bool] = {}
    check_errors: dict[str, Exception] = {}
    if not force_deploy:
        already_by_key, check_errors = jira_client.check_deployment_comments(keys_in_order)

    for idx, (_label, t_info, iss) in enumerate(tickets_to_process):
        key = iss["key"]
        link = _browse_link(key)
        _emit_progress(on_progress, idx + 1, total, key)

        if not force_deploy:
            if key in check_errors:
                log_lines.append(f"\u274c {link} \u2014 SKIPPED (cannot verify existing comments: {check_errors[key]})")
                errors += 1
                continue
            already_deployed = already_by_key.get(key, False)
            if already_deployed:
                log_lines.append(f"\u23ed\ufe0f  {link} \u2014 verified deployment comment already exists, skipped")
                skip += 1
                continue

        prev_status = iss["fields"]["status"]["name"]

        try:
            result = jira_client.add_deployment_comment(
                key,
                t_info["deployment_date"],
                t_info["deployment_time"],
                t_info["deployment_id"],
            )
            comment_id = result.get("id", "") if result else ""
            log_lines.append(f"\u2705 {link} \u2014 comment posted")
        except Exception as exc:  # noqa: BLE001 — per-ticket isolation
            log_lines.append(f"\u274c {link} \u2014 FAILED to post comment: {exc}")
            errors += 1
            continue

        transitioned = False
        status_cat = iss["fields"]["status"].get("statusCategory", {}).get("key", "")
        if status_cat == "done":
            log_lines.append("   \u21b3 already Done")
        else:
            try:
                if jira_client.transition_to_done(key):
                    log_lines.append("   \u21b3 transitioned to Done")
                    transitioned = True
                else:
                    log_lines.append("   \u26a0\ufe0f  no Done transition found")
            except Exception as exc:  # noqa: BLE001 — continue after transition failure
                log_lines.append(f"   \u26a0\ufe0f  transition failed: {exc}")

        undo_data.append(
            {
                "key": key,
                "comment_id": comment_id,
                "prev_status": prev_status,
                "transitioned": transitioned,
            }
        )
        success += 1

    _emit_progress(on_progress, total, total, "Complete!")

    history_timestamp = None
    if success > 0 and save_to_history:
        history_timestamp = datetime.now(timezone.utc).isoformat()
        per_project = list(project_results or [])
        per_project.append(
            {
                "project": project_key,
                "success": success,
                "skipped": skip,
                "errors": errors,
                "undo_data": undo_data,
            }
        )
        deployment_history.save_history(
            deployment_history.build_history_entry(
                timestamp=history_timestamp,
                project=project_key,
                version=release.get("name", "?"),
                clients=_history_clients(
                    filled=filled,
                    selected_keys=keys,
                    project_key=project_key,
                    multi_client=multi_client,
                    grouped=grouped,
                    issues=issues,
                ),
                success=success,
                skipped=skip,
                errors=errors,
                undo_data=undo_data,
                sharepoint_url=sharepoint_url,
                tckt_key=tckt_key,
                tckt_url=tckt_url,
                slack_results=slack_results,
                project_results=per_project,
                event="deploy",
            )
        )

    status = "ok"
    if errors and success:
        status = "partial"
    elif errors and not success:
        status = "failed"
    elif skip and not success:
        status = "skipped"

    return {
        "status": status,
        "success": success,
        "skipped": skip,
        "errors": errors,
        "log": log_lines,
        "undo_data": undo_data,
        "history_timestamp": history_timestamp,
        "release": release.get("name"),
        "project": project_key,
    }


def undo_deploy(
    undo_data: list[dict],
    *,
    history_timestamp: str | None = None,
    on_progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Delete deployment comments and revert statuses from ``undo_data``.

    Writes remain sequential. ``on_progress`` mirrors :func:`execute_deploy`.
    """
    undo_ok = undo_fail = 0
    undo_log: list[str] = []
    total = len(undo_data)

    for idx, ud in enumerate(undo_data):
        k = ud["key"]
        link = _browse_link(k)
        _emit_progress(on_progress, idx + 1, total, k)
        comment_deleted = False
        cid = ud.get("comment_id", "")

        if cid:
            try:
                jira_client.delete_comment(k, cid)
                undo_log.append(f"\u2705 {link} \u2014 comment deleted")
                comment_deleted = True
            except Exception as exc:  # noqa: BLE001 — try fallback
                fallback = jira_client.get_latest_deployment_comment_id(k)
                if fallback:
                    jira_client.delete_comment(k, fallback)
                    undo_log.append(f"\u2705 {link} \u2014 comment deleted (fallback)")
                    comment_deleted = True
                else:
                    undo_log.append(f"\u274c {link} \u2014 failed to delete comment: {exc}")
                    undo_fail += 1
                    continue
        else:
            fallback = jira_client.get_latest_deployment_comment_id(k)
            if fallback:
                jira_client.delete_comment(k, fallback)
                undo_log.append(f"\u2705 {link} \u2014 comment deleted (fallback)")
                comment_deleted = True
            else:
                undo_log.append(f"\u26a0\ufe0f  {link} \u2014 no deployment comment found to delete")

        if ud.get("transitioned"):
            prev = ud.get("prev_status", "")
            tid = jira_client.find_transition_by_name(k, prev) if prev else None
            if tid:
                try:
                    jira_client.transition_issue(k, tid)
                    undo_log.append(f"   \u21b3 reverted to {prev}")
                except Exception as exc:  # noqa: BLE001 — log and continue
                    undo_log.append(f"   \u26a0\ufe0f  could not revert status: {exc}")
            else:
                undo_log.append(f"   \u26a0\ufe0f  no transition back to '{prev}' available")

        if comment_deleted:
            undo_ok += 1
        else:
            undo_fail += 1

    if total:
        _emit_progress(on_progress, total, total, "Complete!")

    if history_timestamp and undo_ok > 0:
        deployment_history.mark_history_entry_reverted(history_timestamp)

    return {
        "status": "ok" if undo_fail == 0 else "partial",
        "ok": undo_ok,
        "fail": undo_fail,
        "log": undo_log,
    }


def mark_release(
    version_id: str,
    *,
    project_key: str = "",
    history_timestamp: str | None = None,
    version_name: str = "",
) -> dict[str, Any]:
    """Mark a Jira version as Released."""
    if not version_id:
        return {"status": "error", "error": "version_id is required"}
    pk = (project_key or "").strip().upper()
    if pk:
        try:
            team_scope.assert_can_mark_version_released(pk)
        except team_scope.TeamScopeError as exc:
            return {"status": "blocked", "error": str(exc), "project": pk}
    try:
        ok = jira_client.release_version(version_id)
    except Exception as exc:  # noqa: BLE001 — surface to caller
        return {"status": "error", "error": str(exc)}
    if ok:
        if history_timestamp:
            deployment_history.record_mark_released(
                history_timestamp,
                version_id=version_id,
                version_name=version_name,
                status="released",
            )
        return {"status": "released", "version_id": version_id}
    return {
        "status": "error",
        "error": "Jira returned an unexpected response. The version may not have been updated.",
        "version_id": version_id,
    }

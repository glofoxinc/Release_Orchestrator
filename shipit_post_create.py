"""Post-create SHIPIT workflow — SHIPIT-17036 parity (Review Ready, owner, links)."""

from __future__ import annotations

import os
from typing import Any

import config
import jira_client


def merge_post_create_options(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Merge workspace defaults with MCP / wizard overrides."""
    base = dict(config.SHIPIT_POST_CREATE or {})
    if overrides:
        for key, value in overrides.items():
            if value is not None:
                base[key] = value
    return base


def release_ticket_keys_from_extracted(extracted: list[dict[str, Any]]) -> list[str]:
    """Unique PIC/AN keys from extracted release rows."""
    keys: list[str] = []
    seen: set[str] = set()
    for row in extracted or []:
        key = str(row.get("ticket") or row.get("key") or "").strip().upper()
        if not key or key in seen:
            continue
        seen.add(key)
        keys.append(key)
    return keys


def resolve_owner_account_id(override: str | None = None) -> tuple[str, str]:
    """Return (accountId, displayName) for SHIPIT reporter/assignee parity."""
    explicit = (
        (override or "").strip()
        or os.getenv("SHIPIT_OWNER_ACCOUNT_ID", "").strip()
        or os.getenv("JIRA_SHIPIT_OWNER_ACCOUNT_ID", "").strip()
    )
    if explicit:
        return explicit, explicit
    user = jira_client.get_current_user()
    return (
        str(user.get("accountId") or ""),
        str(user.get("displayName") or "Current user"),
    )


def _linked_release_keys(shipit_key: str) -> set[str]:
    try:
        issue = jira_client.get_issue(shipit_key)
    except Exception:  # noqa: BLE001
        return set()
    links = (issue.get("fields") or {}).get("issuelinks") or []
    linked: set[str] = set()
    for link in links:
        for side in ("inwardIssue", "outwardIssue"):
            other = link.get(side) or {}
            other_key = str(other.get("key") or "").strip().upper()
            if other_key and other_key != shipit_key.upper():
                linked.add(other_key)
    return linked


def build_post_create_plan(
    extracted: list[dict[str, Any]],
    *,
    is_test: bool = False,
    options: dict[str, Any] | None = None,
    owner_account_id: str | None = None,
) -> dict[str, Any]:
    """Describe post-create steps without calling Jira (dry-run preview)."""
    opts = merge_post_create_options(options)
    release_keys = release_ticket_keys_from_extracted(extracted)
    owner_id, owner_name = resolve_owner_account_id(owner_account_id)

    if not opts.get("enabled", True):
        return {
            "enabled": False,
            "skipped_reason": "disabled_in_config",
            "release_ticket_keys": release_keys,
        }

    if is_test and opts.get("skip_if_test_mode", True):
        return {
            "enabled": False,
            "skipped_reason": "test_mode",
            "release_ticket_keys": release_keys,
        }

    steps: list[dict[str, Any]] = []
    if opts.get("assign_to_creator", True) and owner_id:
        steps.append({
            "action": "assign_to_creator",
            "account_id": owner_id,
            "display_name": owner_name,
            "note": "Reporter is set at create time via API user; assignee updated post-create.",
        })

    transition_status = str(opts.get("transition_status") or "").strip()
    if transition_status and opts.get("transition_to_status", True):
        steps.append({
            "action": "transition",
            "target_status": transition_status,
        })

    if opts.get("link_release_tickets", True) and release_keys:
        steps.append({
            "action": "link_release_tickets",
            "link_type": str(opts.get("link_type") or "Discovery - Connected"),
            "ticket_keys": release_keys,
            "direction": "shipit_outward_connects_to_release_inward",
        })

    return {
        "enabled": True,
        "request_type": config.TCKT_REQUEST_TYPE_NAME or "Manual Change",
        "approver_groups": list(config.TCKT_DEFAULTS.get("approver_groups") or []),
        "owner_account_id": owner_id or None,
        "owner_display_name": owner_name,
        "release_ticket_keys": release_keys,
        "steps": steps,
    }


def apply_post_create(
    shipit_key: str,
    extracted: list[dict[str, Any]],
    *,
    is_test: bool = False,
    options: dict[str, Any] | None = None,
    owner_account_id: str | None = None,
) -> dict[str, Any]:
    """Run SHIPIT-17036-style post-create: assign owner, Review Ready, link PIC/AN tickets."""
    plan = build_post_create_plan(
        extracted,
        is_test=is_test,
        options=options,
        owner_account_id=owner_account_id,
    )
    result: dict[str, Any] = {
        "plan": plan,
        "shipit_key": shipit_key,
        "applied": [],
        "warnings": [],
        "skipped": [],
    }

    if not plan.get("enabled"):
        result["skipped"].append(plan.get("skipped_reason") or "not_enabled")
        return result

    opts = merge_post_create_options(options)
    owner_id, owner_name = resolve_owner_account_id(owner_account_id)

    if opts.get("assign_to_creator", True) and owner_id:
        try:
            jira_client.set_assignee(shipit_key, owner_id)
            result["applied"].append({
                "action": "assign_to_creator",
                "account_id": owner_id,
                "display_name": owner_name,
            })
        except Exception as exc:  # noqa: BLE001
            result["warnings"].append(f"Assignee not set: {exc}")

    transition_status = str(opts.get("transition_status") or "").strip()
    if transition_status and opts.get("transition_to_status", True):
        try:
            current = jira_client.get_issue_status_name(shipit_key)
            if current and current.strip().lower() == transition_status.strip().lower():
                result["skipped"].append(f"already_{transition_status}")
            else:
                ok, err = jira_client.transition_to_status(shipit_key, transition_status)
                if ok:
                    result["applied"].append({
                        "action": "transition",
                        "target_status": transition_status,
                    })
                else:
                    result["warnings"].append(err or f"Could not transition to {transition_status}")
        except Exception as exc:  # noqa: BLE001
            result["warnings"].append(f"Transition failed: {exc}")

    if opts.get("link_release_tickets", True):
        release_keys = plan.get("release_ticket_keys") or []
        link_type = str(opts.get("link_type") or "Discovery - Connected")
        already = _linked_release_keys(shipit_key)
        linked_now: list[str] = []
        link_errors: list[str] = []
        for key in release_keys:
            if key in already:
                result["skipped"].append(f"link_exists:{key}")
                continue
            try:
                jira_client.create_issue_link(shipit_key, key, link_type)
                linked_now.append(key)
            except Exception as exc:  # noqa: BLE001
                link_errors.append(f"{key}: {exc}")
        if linked_now:
            result["applied"].append({
                "action": "link_release_tickets",
                "link_type": link_type,
                "ticket_keys": linked_now,
            })
        result["warnings"].extend(link_errors)

    result["status"] = "warning" if result["warnings"] else "ok"
    return result

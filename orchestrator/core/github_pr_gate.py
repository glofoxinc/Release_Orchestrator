"""GitHub open-PR gate for release-ready tickets + Jira assignee comments."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

import config
import github_host_repo
import jira_client

COMMENT_MARKER = "Release Orchestrator — GitHub PR check"


class GitHubPRError(Exception):
    pass


def gate_enabled() -> bool:
    root = getattr(config, "RELEASE_GATES", {}) or {}
    if not isinstance(root, dict) or not root.get("enabled", True):
        return False
    section = root.get("github_pr") or {}
    if not isinstance(section, dict):
        return False
    return bool(section.get("enabled", True))


def auto_comment_enabled() -> bool:
    section = (getattr(config, "RELEASE_GATES", {}) or {}).get("github_pr") or {}
    if not isinstance(section, dict):
        return True
    return bool(section.get("auto_comment", True))


def comment_on_fetch_enabled() -> bool:
    """Post Jira assignee comments when release-notes tickets are fetched."""
    section = (getattr(config, "RELEASE_GATES", {}) or {}).get("github_pr") or {}
    if not isinstance(section, dict):
        return True
    if not auto_comment_enabled():
        return False
    return bool(section.get("comment_on_fetch", True))


def github_configured() -> dict[str, Any]:
    token = (
        os.getenv("GITHUB_TOKEN", "").strip()
        or os.getenv("GH_TOKEN", "").strip()
    )
    return {
        "configured": bool(token),
        "token_present": bool(token),
    }


def _auth_header() -> str:
    cfg = github_configured()
    if not cfg["configured"]:
        raise GitHubPRError(
            "GitHub token not configured — set GITHUB_TOKEN or GH_TOKEN in .env"
        )
    token = os.getenv("GITHUB_TOKEN", "").strip() or os.getenv("GH_TOKEN", "").strip()
    return f"Bearer {token}"


def _request_json(url: str) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": _auth_header(),
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise GitHubPRError(f"GitHub API {exc.code}: {body[:240]}") from exc
    except urllib.error.URLError as exc:
        raise GitHubPRError(f"Could not reach GitHub: {exc.reason}") from exc


def _pr_review_summary(owner: str, repo: str, number: int) -> dict[str, Any]:
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}/reviews"
    reviews = _request_json(url)
    approved = 0
    changes_requested = 0
    pending = 0
    for review in reviews if isinstance(reviews, list) else []:
        state = str(review.get("state") or "").upper()
        if state == "APPROVED":
            approved += 1
        elif state == "CHANGES_REQUESTED":
            changes_requested += 1
        elif state in ("PENDING", ""):
            pending += 1
    return {
        "approved_count": approved,
        "changes_requested_count": changes_requested,
        "pending_count": pending,
    }


def _pr_needs_attention(pr: dict[str, Any], review_summary: dict[str, Any]) -> tuple[bool, str]:
    state = str(pr.get("state") or "").lower()
    if state != "open":
        return False, "merged_or_closed"
    if pr.get("draft"):
        return True, "draft_pr"
    if pr.get("merged"):
        return False, "merged"
    if review_summary.get("changes_requested_count", 0) > 0:
        return True, "changes_requested"
    if review_summary.get("approved_count", 0) == 0:
        return True, "not_approved"
    mergeable = pr.get("mergeable")
    if mergeable is False:
        return True, "not_mergeable"
    return True, "not_merged"


def find_open_prs_for_ticket(
    ticket_key: str,
    *,
    owner: str,
    repo: str,
) -> list[dict[str, Any]]:
    """Return open PRs in repo that reference the Jira ticket key."""
    key = str(ticket_key or "").strip().upper()
    if not key or not owner or not repo:
        return []
    query = f"repo:{owner}/{repo} is:pr is:open {key}"
    url = "https://api.github.com/search/issues?" + urllib.parse.urlencode(
        {"q": query, "per_page": 10}
    )
    data = _request_json(url)
    items = data.get("items") or []
    out: list[dict[str, Any]] = []
    for item in items:
        number = item.get("number")
        if not number:
            continue
        pr_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}"
        pr = _request_json(pr_url)
        reviews = _pr_review_summary(owner, repo, int(number))
        needs, reason = _pr_needs_attention(pr, reviews)
        out.append(
            {
                "number": number,
                "title": pr.get("title") or item.get("title"),
                "html_url": pr.get("html_url") or item.get("html_url"),
                "state": pr.get("state"),
                "draft": bool(pr.get("draft")),
                "head_ref": (pr.get("head") or {}).get("ref"),
                "mergeable": pr.get("mergeable"),
                "needs_attention": needs,
                "attention_reason": reason,
                "reviews": reviews,
            }
        )
    return out


def check_ticket_github_prs(
    ticket: dict[str, Any],
    *,
    description: str = "",
) -> dict[str, Any]:
    """Resolve repo + list open PRs needing merge/approval for one ticket row."""
    key = str(ticket.get("ticket") or "").strip().upper()
    summary = str(ticket.get("summary") or ticket.get("report") or "")
    desc = str(description or ticket.get("description") or "")
    host = github_host_repo.resolve_report_host_repo(
        jira_key=key,
        summary=summary,
        description=desc,
    )
    owner = host.get("owner")
    repo = host.get("repo")
    row: dict[str, Any] = {
        "ticket": key,
        "summary": summary,
        "assignee": str(ticket.get("assignee") or "Unassigned"),
        "status": str(ticket.get("status") or ""),
        "host_repo": host,
        "open_prs": [],
        "blocking_prs": [],
        "error": None,
    }
    if not host.get("ok") or not owner or not repo:
        row["error"] = host.get("reason") or "Could not resolve GitHub repo for ticket."
        return row
    if not github_configured()["configured"]:
        row["error"] = "GITHUB_TOKEN not configured"
        return row
    try:
        prs = find_open_prs_for_ticket(key, owner=owner, repo=repo)
        row["open_prs"] = prs
        row["blocking_prs"] = [p for p in prs if p.get("needs_attention")]
    except GitHubPRError as exc:
        row["error"] = str(exc)
    return row


def run_pr_gate(
    extracted: list[dict],
    *,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Check release-ready tickets for open / unapproved GitHub PRs."""
    if not gate_enabled():
        return {"status": "disabled", "tickets_checked": 0, "tickets_with_blocking_prs": []}

    cfg = github_configured()
    if not cfg["configured"]:
        return {
            "status": "skipped",
            "reason": "GITHUB_TOKEN not set — PR check skipped.",
            "tickets_checked": 0,
            "tickets_with_blocking_prs": [],
        }

    checked: list[dict[str, Any]] = []
    blocking: list[dict[str, Any]] = []
    for item in extracted:
        row = check_ticket_github_prs(item)
        checked.append(row)
        if row.get("blocking_prs"):
            blocking.append(row)

    return {
        "status": "ok",
        "dry_run": dry_run,
        "auto_comment": auto_comment_enabled(),
        "tickets_checked": len(checked),
        "tickets_with_open_prs": [r for r in checked if r.get("open_prs")],
        "tickets_with_blocking_prs": blocking,
        "blocking_count": len(blocking),
        "details": checked,
    }


def _recent_pr_comment_exists(issue_key: str) -> bool:
    try:
        for comment in jira_client.get_issue_comments(issue_key)[-15:]:
            body = comment.get("body")
            if isinstance(body, dict):
                from adf_builder import adf_to_plain_text

                text = adf_to_plain_text(body)
            else:
                text = str(body or "")
            if COMMENT_MARKER in text:
                return True
    except Exception:  # noqa: BLE001
        return False
    return False


def _assignee_account_id(issue_key: str) -> tuple[str, str]:
    issue = jira_client.get_issue(issue_key)
    assignee = (issue.get("fields") or {}).get("assignee") or {}
    return (
        str(assignee.get("accountId") or ""),
        str(assignee.get("displayName") or "Assignee"),
    )


def build_pr_comment_adf(
    *,
    ticket_key: str,
    blocking_prs: list[dict[str, Any]],
    host_repo: str,
    assignee_account_id: str,
    assignee_display_name: str,
) -> dict[str, Any]:
    from adf_builder import bullet_item, doc, hard_break, link, mention, paragraph, text

    if assignee_account_id:
        opener = paragraph(
            mention(assignee_display_name, assignee_account_id),
            text(
                " — this ticket is release-ready but the linked GitHub pull request still needs action:"
            ),
        )
    else:
        opener = paragraph(
            text(
                "This ticket is release-ready but the linked GitHub pull request still needs action:"
            )
        )

    content: list[dict[str, Any]] = [opener, paragraph(text(" "))]
    for pr in blocking_prs:
        reason = str(pr.get("attention_reason") or "open").replace("_", " ")
        label = f"PR #{pr.get('number')}: {pr.get('title') or 'Pull request'}"
        url = str(pr.get("html_url") or "")
        if url:
            content.append(bullet_item(link(label, url), text(f" — {reason}")))
        else:
            content.append(bullet_item(text(f"{label} — {reason}")))
    content.append(paragraph(text(" ")))
    content.append(
        paragraph(
            text("Repo: "),
            text(host_repo or "unknown", bold=True),
            hard_break(),
            text("Please merge and obtain approval before deployment."),
        )
    )
    content.append(
        paragraph(text(COMMENT_MARKER, bold=True))
    )
    return doc(*content)


def post_pr_comments(
    gate_result: dict[str, Any],
    *,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Post Jira comments tagging assignees for tickets with blocking PRs."""
    blocking = list(gate_result.get("tickets_with_blocking_prs") or [])
    if not blocking:
        return {"status": "ok", "posted": [], "skipped": [], "dry_run": dry_run}

    posted: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for row in blocking:
        key = str(row.get("ticket") or "").strip().upper()
        prs = list(row.get("blocking_prs") or [])
        host_repo = str((row.get("host_repo") or {}).get("report_host_repo") or "")
        if not key or not prs:
            continue
        if _recent_pr_comment_exists(key):
            skipped.append({"ticket": key, "reason": "recent_pr_comment_exists"})
            continue
        account_id, display_name = _assignee_account_id(key)
        body = build_pr_comment_adf(
            ticket_key=key,
            blocking_prs=prs,
            host_repo=host_repo,
            assignee_account_id=account_id,
            assignee_display_name=display_name or str(row.get("assignee") or "Assignee"),
        )
        if dry_run:
            posted.append(
                {
                    "ticket": key,
                    "assignee": display_name,
                    "pr_count": len(prs),
                    "dry_run": True,
                }
            )
            continue
        try:
            result = jira_client.add_adf_comment(key, body)
            posted.append(
                {
                    "ticket": key,
                    "assignee": display_name,
                    "comment_id": result.get("id"),
                    "pr_count": len(prs),
                }
            )
        except Exception as exc:  # noqa: BLE001
            errors.append({"ticket": key, "error": str(exc)})

    status = "error" if errors and not posted else "ok"
    return {
        "status": status,
        "dry_run": dry_run,
        "posted": posted,
        "skipped": skipped,
        "errors": errors,
    }


def format_gate_summary(gate_result: dict[str, Any]) -> str:
    """Chat-friendly summary for MCP guided flow."""
    status = gate_result.get("status")
    if status == "disabled":
        return ""
    if status == "skipped":
        return str(gate_result.get("reason") or "GitHub PR check skipped.")
    blocking = gate_result.get("tickets_with_blocking_prs") or []
    if not blocking:
        return "GitHub PR check: all linked PRs are merged (or no open PRs found)."
    lines = [
        f"**GitHub PR check** — {len(blocking)} ticket(s) have open PRs not merged:",
    ]
    for row in blocking:
        key = row.get("ticket")
        assignee = row.get("assignee") or "Unassigned"
        repo = (row.get("host_repo") or {}).get("report_host_repo") or "?"
        pr_bits = []
        for pr in row.get("blocking_prs") or []:
            pr_bits.append(f"#{pr.get('number')} ({pr.get('attention_reason', 'open')})")
        lines.append(f"- **{key}** ({assignee}) — `{repo}` — {', '.join(pr_bits)}")
    if gate_result.get("auto_comment"):
        lines.append(
            "Jira comments tagging assignees will be posted (or were posted) on these tickets."
        )
    return "\n".join(lines)

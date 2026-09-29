"""Deployment Slack announcements for Customize BI releases.

Builds the standard two-channel messages used after a TCKT is created
(#insights-customize-squad and #customize-bi-buddies), with preview text and
optional send via Slack Bot API (``SLACK_BOT_TOKEN``).

This is the canonical announce path. The older incoming-webhook helper in
``notifier.py`` (``SLACK_DEPLOY_WEBHOOK``) is legacy/deprecated and must not be
confused with this Bot API flow.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any
from urllib.parse import unquote, urlparse

import requests

logger = logging.getLogger(__name__)

_VERSION_RE = re.compile(r"\bv?\d{4}\.\d{1,2}\.\d{2}\.\d{2}\b", re.IGNORECASE)
# Trailing CC line(s); editable body is everything before this suffix.
_CC_LINE_RE = re.compile(r"(?:\r?\n)+CC:\s*.*$", re.IGNORECASE | re.DOTALL)


# Exact Customize BI destinations and required CC keys (workspace / defaults).
def never_post_unless_asked(ws: dict[str, Any] | None = None) -> bool:
    """Post to Slack only when the operator explicitly says send slack."""
    if ws is not None:
        section = ws.get("slack_announce") or {}
    else:
        import config

        section = getattr(config, "SLACK_ANNOUNCE", {}) or {}
    if not isinstance(section, dict):
        return False
    return bool(section.get("never_post_unless_asked", False))


CANONICAL_CHANNEL_REQUIREMENTS: tuple[dict[str, Any], ...] = (
    {
        "key": "squad",
        "name": "insights-customize-squad",
        "cc_keys": ("sushma", "sai_anirudh", "zeke", "eoin"),
    },
    {
        "key": "buddies",
        "name": "customize-bi-buddies",
        "cc_keys": ("sushma",),
    },
)


@dataclass(frozen=True)
class SlackCcPerson:
    """A person tagged in the CC line."""

    name: str
    user_id: str = ""
    email: str = ""

    def mention(self) -> str:
        if self.user_id:
            return f"<@{self.user_id}>"
        return f"@{self.name}"

    def display(self) -> str:
        return f"@{self.name}"


@dataclass(frozen=True)
class SlackChannelTarget:
    """One destination channel and its CC list."""

    key: str
    name: str
    channel_id: str = ""
    cc: tuple[SlackCcPerson, ...] = ()


@dataclass
class SlackAnnounceDraft:
    """Editable inputs for the deployment announcement."""

    ticket_key: str
    ticket_summary: str
    ticket_url: str
    version: str
    deploy_date: date
    sharepoint_url: str
    sharepoint_label: str
    sharepoint_download_url: str = ""
    sharepoint_folder_url: str = ""
    sharepoint_folder_label: str = ""
    environments: str = "Analyze & Custom environments"
    ticket_count: int = 0


@dataclass
class SlackChannelMessage:
    channel: SlackChannelTarget
    text: str
    preview: str


@dataclass
class SlackSendResult:
    channel_name: str
    ok: bool
    error: str = ""
    permalink: str = ""
    ts: str = ""


@dataclass
class SlackAnnounceConfig:
    """Workspace + env configuration for Slack announce."""

    enabled: bool = True
    bot_token: str = ""
    channels: list[SlackChannelTarget] = field(default_factory=list)

    def any_channel(self) -> bool:
        return bool(self.channels)

    def can_send(self) -> bool:
        return bool(self.bot_token and self.channels)


@dataclass(frozen=True)
class ConfigValidationIssue:
    """One config validation finding for Slack announce destinations / CCs."""

    level: str  # "error" | "warning"
    code: str
    message: str


def deployer_slack_gate_open(
    *,
    enabled: bool,
    sent: bool = False,
    skipped: bool = False,
    can_send: bool | None = None,
) -> bool:
    """Return True when Release Deployer may proceed past the Slack step.

    ``slack_announce.enabled=false`` must never block the UI deployer gate.
    When ``can_send=False`` (missing bot token / channels), the gate is also
    open — live send is unavailable but workflow must not stall.
    """
    if not enabled:
        return True
    if can_send is False:
        return True
    return bool(sent or skipped)


def slack_gate_applies(cfg: SlackAnnounceConfig) -> bool:
    """True when Slack announce should block deploy until send or skip.

    Config may say ``enabled=true`` while credentials are missing; those
    cases are treated as non-blocking (preview/copy only).
    """
    return bool(cfg.enabled and cfg.can_send())


def format_cc_line(channel: SlackChannelTarget, *, for_preview: bool = False) -> str:
    bits = " ".join((p.display() if for_preview else p.mention()) for p in channel.cc)
    return f"CC: {bits}"


def strip_cc_suffix(text: str) -> str:
    """Remove a trailing ``CC: …`` suffix so the editable body is preserved."""
    raw = text or ""
    cleaned = _CC_LINE_RE.sub("", raw).rstrip()
    # Also drop a lone final CC line without a leading blank when DOTALL missed.
    lines = cleaned.splitlines()
    while lines and lines[-1].strip().upper().startswith("CC:"):
        lines.pop()
    return "\n".join(lines).rstrip()


def ensure_canonical_cc(
    text: str,
    channel: SlackChannelTarget,
    *,
    for_preview: bool = False,
) -> str:
    """Preserve the editable body and reappend required channel CC mentions."""
    body = strip_cc_suffix(text)
    cc_line = format_cc_line(channel, for_preview=for_preview)
    if not body:
        return cc_line
    return f"{body}\n{cc_line}"


def missing_required_cc_tokens(
    text: str,
    channel: SlackChannelTarget,
    *,
    for_preview: bool = False,
) -> list[str]:
    """Return required CC tokens that are absent from ``text``."""
    missing: list[str] = []
    blob = text or ""
    for person in channel.cc:
        token = person.display() if for_preview else person.mention()
        if token and token not in blob:
            # Accept either mention form when validating send text.
            if not for_preview and person.user_id and f"<@{person.user_id}>" in blob:
                continue
            if for_preview and person.display() in blob:
                continue
            missing.append(token)
    return missing


def validate_announce_config(
    cfg: SlackAnnounceConfig,
    *,
    require_canonical: bool = True,
) -> list[ConfigValidationIssue]:
    """Validate configured channel names and CC mappings (offline)."""
    issues: list[ConfigValidationIssue] = []
    if not cfg.enabled:
        return issues

    by_key = {c.key: c for c in cfg.channels}
    by_name = {c.name.lstrip("#"): c for c in cfg.channels}
    if require_canonical:
        for spec in CANONICAL_CHANNEL_REQUIREMENTS:
            channel = by_key.get(spec["key"]) or by_name.get(spec["name"])
            if channel is None:
                issues.append(
                    ConfigValidationIssue(
                        level="error",
                        code="missing_channel",
                        message=(f"Missing required Slack channel #{spec['name']} (key={spec['key']})."),
                    )
                )
                continue
            if channel.name.lstrip("#") != spec["name"]:
                issues.append(
                    ConfigValidationIssue(
                        level="error",
                        code="channel_name_mismatch",
                        message=(f"Channel key={spec['key']} must be named #{spec['name']}, got #{channel.name}."),
                    )
                )
            expected_ids = [default_cc_people()[k].user_id for k in spec["cc_keys"] if k in default_cc_people()]
            actual_ids = [p.user_id for p in channel.cc if p.user_id]
            if expected_ids and actual_ids != expected_ids:
                # Allow name-key order match via emails/ids subset check.
                if set(actual_ids) != set(expected_ids) or len(actual_ids) != len(expected_ids):
                    issues.append(
                        ConfigValidationIssue(
                            level="error",
                            code="cc_mismatch",
                            message=(
                                f"#{channel.name} CC mapping must be "
                                f"{list(spec['cc_keys'])} "
                                f"(ids={expected_ids}); got ids={actual_ids}."
                            ),
                        )
                    )
            elif not channel.cc:
                issues.append(
                    ConfigValidationIssue(
                        level="error",
                        code="cc_empty",
                        message=f"#{channel.name} has an empty CC list.",
                    )
                )

    if cfg.can_send():
        missing_ids = [c.name for c in cfg.channels if not c.channel_id]
        if missing_ids:
            issues.append(
                ConfigValidationIssue(
                    level="warning",
                    code="channel_id_unresolved",
                    message=(
                        "channel_id blank for: "
                        + ", ".join(f"#{n}" for n in missing_ids)
                        + " (will resolve by name at send time)."
                    ),
                )
            )
    elif cfg.enabled and cfg.any_channel() and not cfg.bot_token:
        issues.append(
            ConfigValidationIssue(
                level="warning",
                code="missing_bot_token",
                message="SLACK_BOT_TOKEN is not configured; send is unavailable.",
            )
        )
    return issues


def pending_channel_messages(
    messages: list[SlackChannelMessage],
    prior_results: list[SlackSendResult] | None = None,
) -> list[SlackChannelMessage]:
    """Return only channels that still need a send (failed or not yet tried)."""
    if not prior_results:
        return list(messages)
    ok_names = {r.channel_name.lstrip("#") for r in prior_results if r.ok}
    return [m for m in messages if m.channel.name.lstrip("#") not in ok_names]


def merge_send_results(
    prior: list[SlackSendResult] | None,
    new_results: list[SlackSendResult],
) -> list[SlackSendResult]:
    """Merge prior successes with new attempt results by channel name."""
    merged: dict[str, SlackSendResult] = {}
    order: list[str] = []
    for result in list(prior or []) + list(new_results):
        key = result.channel_name.lstrip("#")
        if key not in merged:
            order.append(key)
        merged[key] = result
    return [merged[key] for key in order]


def default_cc_people() -> dict[str, SlackCcPerson]:
    """Known CC people for Customize BI deployment announces."""
    return {
        "sushma": SlackCcPerson(
            name="Sushma Bhamidipati",
            user_id="U08LDAQ7SDV",
            email="VenkataSuryaNagaSushma.Bhamidipati@abcfitness.com",
        ),
        "sai_anirudh": SlackCcPerson(
            name="Sai Anirudh Karre",
            user_id="U0BSG4ABZC0",
            email="SaiAnirudh.Karre@abcfitness.com",
        ),
        "zeke": SlackCcPerson(
            name="Zeke Brustkern",
            user_id="U083R8TP1J9",
            email="Ezekiel.Brustkern@abcfitness.com",
        ),
        "eoin": SlackCcPerson(
            name="Eoin George",
            user_id="U01H0UL5JGP",
            email="eoin.george@abcfitness.com",
        ),
        "soumyakant": SlackCcPerson(
            name="Soumyakant Mishra",
            user_id="U062RM3T87Q",
            email="Soumyakant.Mishra@abcfitness.com",
        ),
        "trent": SlackCcPerson(
            name="Trent Vanest",
            user_id="U0ASR2XGRPZ",
            email="Trent.Vanest@abcfitness.com",
        ),
    }


def default_channels(people: dict[str, SlackCcPerson] | None = None) -> list[SlackChannelTarget]:
    p = people or default_cc_people()
    return [
        SlackChannelTarget(
            key="squad",
            name="insights-customize-squad",
            channel_id="",
            cc=(p["sushma"], p["sai_anirudh"], p["zeke"], p["eoin"]),
        ),
        SlackChannelTarget(
            key="buddies",
            name="customize-bi-buddies",
            channel_id="",
            cc=(p["sushma"],),
        ),
    ]


def extract_version_label(summary: str, fallback: str = "") -> str:
    """Pull ``vYYYY.M.MM.DD`` from a TCKT summary or fall back."""
    match = _VERSION_RE.search(summary or "")
    if match:
        raw = match.group(0)
        return raw if raw.lower().startswith("v") else f"v{raw}"
    fb = (fallback or "").strip()
    if not fb:
        return ""
    return fb if fb.lower().startswith("v") else f"v{fb}"


def version_without_prefix(version: str) -> str:
    v = (version or "").strip()
    return v[1:] if v.lower().startswith("v") else v


def sharepoint_label_from_url(url: str, version: str) -> str:
    """Prefer the filename from the SharePoint URL; else Release Notes <ver>.docx."""
    raw = (url or "").strip()
    if raw:
        path = unquote(urlparse(raw).path)
        name = path.rsplit("/", 1)[-1] if path else ""
        if name.lower().endswith(".docx"):
            return name
        # SharePoint often puts the name in ?file=
        from urllib.parse import parse_qs

        qs = parse_qs(urlparse(raw).query)
        for key in ("file", "File"):
            vals = qs.get(key) or []
            if vals and str(vals[0]).lower().endswith(".docx"):
                return unquote(str(vals[0]))
    ver = version_without_prefix(version)
    return f"Release Notes {ver}.docx" if ver else "Release Notes.docx"


def format_deploy_day(d: date) -> str:
    """``Wednesday, August 05, 2026`` — zero-padded day to match existing posts."""
    return d.strftime("%A, %B %d, %Y")


def _sharepoint_doc_label(draft: SlackAnnounceDraft) -> str:
    version = draft.version if draft.version.lower().startswith("v") else f"v{draft.version}"
    return draft.sharepoint_label or sharepoint_label_from_url(
        draft.sharepoint_url,
        version,
    )


def format_sharepoint_display(
    draft: SlackAnnounceDraft,
    *,
    for_preview: bool = False,
) -> str:
    """SharePoint download line — linked doc name (legacy alias)."""
    return format_sharepoint_download_display(draft, for_preview=for_preview)


def format_sharepoint_download_display(
    draft: SlackAnnounceDraft,
    *,
    for_preview: bool = False,
) -> str:
    """Direct download link for the Release Notes .docx."""
    sp_label = _sharepoint_doc_label(draft)
    url = (draft.sharepoint_download_url or draft.sharepoint_url or "").strip()
    if not url:
        from sharepoint_url import sharepoint_direct_download_url

        url = sharepoint_direct_download_url(draft.sharepoint_url)
    if for_preview or not url:
        return sp_label
    return f"<{url}|{sp_label}>"


def format_sharepoint_folder_display(
    draft: SlackAnnounceDraft,
    *,
    for_preview: bool = False,
) -> str:
    """SharePoint quarter folder browse link."""
    label = (draft.sharepoint_folder_label or "Release Notes folder").strip()
    url = (draft.sharepoint_folder_url or "").strip()
    if for_preview or not url:
        return label
    return f"<{url}|{label}>"


def format_service_desk_display(
    draft: SlackAnnounceDraft,
    *,
    for_preview: bool = False,
) -> str:
    """Service Desk line — full ticket title as link text (not key-only)."""
    label = (draft.ticket_summary or "").strip() or draft.ticket_key
    if for_preview or not draft.ticket_url:
        return label
    return f"<{draft.ticket_url}|{label}>"


def build_announce_text(
    draft: SlackAnnounceDraft,
    channel: SlackChannelTarget,
    *,
    for_preview: bool = False,
) -> str:
    """Build the exact announcement body used in both channels."""
    try:
        from slack_message_content import build_announce_body_from_template, template_enabled

        if template_enabled():
            rendered = build_announce_body_from_template(draft, channel, for_preview=for_preview)
            if rendered:
                return rendered
    except Exception:  # noqa: BLE001
        pass

    day = format_deploy_day(draft.deploy_date)
    sharepoint_download = format_sharepoint_download_display(draft, for_preview=for_preview)
    sharepoint_folder = format_sharepoint_folder_display(draft, for_preview=for_preview)
    service_desk_display = format_service_desk_display(draft, for_preview=for_preview)
    cc_line = format_cc_line(channel, for_preview=for_preview)
    body = (
        "Hello Team,\n"
        f"Our upcoming deployment is scheduled for {day}.\n"
        "Deployment notes and the deployment ticket are below for reference:\n\n"
        f"SharePoint — Download: {sharepoint_download}\n"
        f"SharePoint — Folder: {sharepoint_folder}\n"
        f"Service Desk: {service_desk_display}\n"
        f"{cc_line}"
    )
    return body


def build_channel_messages(
    draft: SlackAnnounceDraft,
    channels: list[SlackChannelTarget] | None = None,
    *,
    body_overrides: dict[str, str] | None = None,
) -> list[SlackChannelMessage]:
    targets = channels or default_channels()
    overrides = body_overrides or {}
    out: list[SlackChannelMessage] = []
    for ch in targets:
        custom = (overrides.get(ch.key) or overrides.get(ch.name.lstrip("#")) or "").strip()
        if custom:
            text = ensure_canonical_cc(custom, ch, for_preview=False)
            preview = ensure_canonical_cc(custom, ch, for_preview=True)
        else:
            text = build_announce_text(draft, ch, for_preview=False)
            preview = build_announce_text(draft, ch, for_preview=True)
        out.append(
            SlackChannelMessage(
                channel=ch,
                text=text,
                preview=preview,
            )
        )
    return out


def draft_from_session(
    *,
    ticket_key: str,
    summary: str,
    ticket_url: str,
    planned_start: date | datetime | None,
    sharepoint_url: str,
    version_hint: str = "",
    environments: str = "Analyze & Custom environments",
) -> SlackAnnounceDraft:
    """Build a draft from Service Ticket session values."""
    if isinstance(planned_start, datetime):
        deploy_date = planned_start.date()
    elif isinstance(planned_start, date):
        deploy_date = planned_start
    else:
        deploy_date = date.today()

    version = extract_version_label(summary, version_hint)
    sp_url = (sharepoint_url or "").strip()
    from sharepoint_url import resolve_sharepoint_folder_link, sharepoint_direct_download_url

    folder_url, folder_label = resolve_sharepoint_folder_link(version_name=version)
    return SlackAnnounceDraft(
        ticket_key=ticket_key,
        ticket_summary=summary,
        ticket_url=ticket_url,
        version=version,
        deploy_date=deploy_date,
        sharepoint_url=sp_url,
        sharepoint_label=sharepoint_label_from_url(sp_url, version),
        sharepoint_download_url=sharepoint_direct_download_url(sp_url),
        sharepoint_folder_url=folder_url,
        sharepoint_folder_label=folder_label,
        environments=environments,
    )


def load_announce_config(ws: dict[str, Any] | None = None) -> SlackAnnounceConfig:
    """Load Slack announce settings from workspace.yaml + env."""
    data = ws if ws is not None else {}
    section = data.get("slack_announce") or {}
    people = default_cc_people()

    # Allow workspace overrides for user ids / names.
    for key, person in list(people.items()):
        override = (section.get("cc") or {}).get(key) or {}
        if isinstance(override, dict):
            people[key] = SlackCcPerson(
                name=str(override.get("name") or person.name),
                user_id=str(override.get("user_id") or person.user_id),
                email=str(override.get("email") or person.email),
            )

    channels: list[SlackChannelTarget] = []
    raw_channels = section.get("channels") or []
    if raw_channels:
        defaults_by_key = {c.key: c for c in default_channels(people)}
        for raw in raw_channels:
            if not isinstance(raw, dict):
                continue
            key = str(raw.get("key") or raw.get("name") or "").strip()
            base = defaults_by_key.get(key)
            name = str(raw.get("name") or (base.name if base else key)).lstrip("#")
            channel_id = str(raw.get("channel_id") or "").strip()
            cc_people: list[SlackCcPerson] = []
            if "cc" in raw:
                for ck in raw.get("cc") or []:
                    if isinstance(ck, str) and ck in people:
                        cc_people.append(people[ck])
                    elif isinstance(ck, dict):
                        cc_people.append(
                            SlackCcPerson(
                                name=str(ck.get("name") or ""),
                                user_id=str(ck.get("user_id") or ""),
                                email=str(ck.get("email") or ""),
                            )
                        )
            elif base:
                cc_people = list(base.cc)
            else:
                for ck in (
                    ["sushma", "sai_anirudh", "zeke", "eoin"]
                    if key in ("squad", "insights-customize-squad")
                    else ["sushma"]
                ):
                    if ck in people:
                        cc_people.append(people[ck])
            if not cc_people and base:
                cc_people = list(base.cc)
            channels.append(
                SlackChannelTarget(
                    key=key or name,
                    name=name,
                    channel_id=channel_id,
                    cc=tuple(cc_people),
                )
            )
    else:
        channels = default_channels(people)

    id_map = section.get("channel_ids") or {}
    if isinstance(id_map, dict) and id_map:
        channels = [
            SlackChannelTarget(
                key=c.key,
                name=c.name,
                channel_id=str(
                    c.channel_id or id_map.get(c.name) or id_map.get(f"#{c.name}") or id_map.get(c.key) or ""
                ).strip(),
                cc=c.cc,
            )
            for c in channels
        ]

    token = os.environ.get("SLACK_BOT_TOKEN", "").strip() or os.environ.get("SLACK_TOKEN", "").strip()
    enabled = bool(section.get("enabled", True))
    return SlackAnnounceConfig(enabled=enabled, bot_token=token, channels=channels)


def _slack_api(
    method: str,
    token: str,
    payload: dict[str, Any] | None = None,
    *,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    url = f"https://slack.com/api/{method}"
    headers = {"Authorization": f"Bearer {token}"}
    # conversations.list / chat.getPermalink / conversations.info expect query params (GET).
    get_methods = {
        "conversations.list",
        "conversations.info",
        "chat.getPermalink",
        "users.lookupByEmail",
    }
    if method in get_methods:
        resp = requests.get(url, headers=headers, params=params or {}, timeout=20)
    else:
        headers["Content-Type"] = "application/json; charset=utf-8"
        resp = requests.post(
            url,
            headers=headers,
            json=payload or {},
            params=params or {},
            timeout=20,
        )
    data = resp.json() if resp.content else {}
    if not resp.ok:
        raise RuntimeError(f"Slack HTTP {resp.status_code}: {(resp.text or '')[:200]}")
    if not data.get("ok"):
        raise RuntimeError(data.get("error") or f"Slack {method} failed")
    return data


def resolve_channel_id(token: str, channel_name: str, known_id: str = "") -> str:
    """Resolve a public/private channel id by name when not configured."""
    if known_id:
        return known_id
    name = channel_name.lstrip("#").strip().lower()
    cursor = None
    while True:
        params: dict[str, Any] = {
            "types": "public_channel,private_channel",
            "limit": 200,
            "exclude_archived": True,
        }
        if cursor:
            params["cursor"] = cursor
        data = _slack_api("conversations.list", token, params=params)
        for ch in data.get("channels") or []:
            if str(ch.get("name", "")).lower() == name:
                return str(ch.get("id") or "")
        cursor = ((data.get("response_metadata") or {}).get("next_cursor") or "").strip()
        if not cursor:
            break
    raise RuntimeError(
        f"Slack channel #{channel_name} not found. Invite the bot to the channel and set channel_id in workspace.yaml."
    )


def send_channel_message(
    token: str,
    channel: SlackChannelTarget,
    text: str,
) -> SlackSendResult:
    """Post one announcement to a Slack channel."""
    try:
        # Always reappend/validate required CC mentions before posting.
        safe_text = ensure_canonical_cc(text, channel, for_preview=False)
        missing = missing_required_cc_tokens(
            safe_text,
            channel,
            for_preview=False,
        )
        if missing:
            return SlackSendResult(
                channel_name=channel.name,
                ok=False,
                error=f"Missing required CC mentions: {', '.join(missing)}",
            )
        channel_id = resolve_channel_id(token, channel.name, channel.channel_id)
        data = _slack_api(
            "chat.postMessage",
            token,
            {
                "channel": channel_id,
                "text": safe_text,
                "unfurl_links": False,
                "unfurl_media": False,
            },
        )
        ts = str(data.get("ts") or "")
        permalink = ""
        try:
            link_data = _slack_api(
                "chat.getPermalink",
                token,
                params={"channel": channel_id, "message_ts": ts},
            )
            permalink = str(link_data.get("permalink") or "")
        except Exception:
            permalink = ""
        return SlackSendResult(
            channel_name=channel.name,
            ok=True,
            ts=ts,
            permalink=permalink,
        )
    except Exception as exc:
        logger.warning("Slack send to #%s failed: %s", channel.name, exc)
        return SlackSendResult(channel_name=channel.name, ok=False, error=str(exc))


def send_announce_messages(
    cfg: SlackAnnounceConfig,
    messages: list[SlackChannelMessage],
) -> list[SlackSendResult]:
    if not cfg.bot_token:
        return [
            SlackSendResult(
                channel_name=m.channel.name,
                ok=False,
                error="SLACK_BOT_TOKEN is not configured in .env",
            )
            for m in messages
        ]
    return [send_channel_message(cfg.bot_token, m.channel, m.text) for m in messages]


@dataclass(frozen=True)
class SlackPreflightResult:
    """Read-only Slack diagnostic outcome for one check."""

    name: str
    ok: bool
    message: str
    channel_name: str = ""
    channel_id: str = ""
    is_member: bool | None = None


def preflight_slack_readonly(cfg: SlackAnnounceConfig | None = None) -> list[SlackPreflightResult]:
    """Validate bot token and channel resolution/membership without posting.

    Uses only ``auth.test``, ``conversations.list`` / ``conversations.info``.
    Never calls ``chat.postMessage``.
    """
    announce = cfg or load_announce_config({"slack_announce": {}})
    results: list[SlackPreflightResult] = []

    if not announce.enabled:
        results.append(
            SlackPreflightResult(
                name="slack_enabled",
                ok=True,
                message="slack_announce.enabled is false — Slack checks skipped",
            )
        )
        return results

    if not announce.bot_token:
        results.append(
            SlackPreflightResult(
                name="slack_auth",
                ok=False,
                message="SLACK_BOT_TOKEN is not configured",
            )
        )
        return results

    try:
        auth = _slack_api("auth.test", announce.bot_token, {})
        team = str(auth.get("team") or auth.get("url") or "?")
        user = str(auth.get("user") or auth.get("bot_id") or "?")
        results.append(
            SlackPreflightResult(
                name="slack_auth",
                ok=True,
                message=f"auth.test ok as {user} on {team}",
            )
        )
    except Exception as exc:  # noqa: BLE001 — surface as diagnostic
        results.append(
            SlackPreflightResult(
                name="slack_auth",
                ok=False,
                message=f"auth.test failed: {exc}",
            )
        )
        return results

    for channel in announce.channels:
        try:
            channel_id = resolve_channel_id(
                announce.bot_token,
                channel.name,
                channel.channel_id,
            )
            info = _slack_api(
                "conversations.info",
                announce.bot_token,
                params={"channel": channel_id},
            )
            ch = info.get("channel") or {}
            is_member = ch.get("is_member")
            if is_member is False:
                results.append(
                    SlackPreflightResult(
                        name="slack_channel",
                        ok=False,
                        message=(
                            f"#{channel.name} resolved ({channel_id}) but bot is not a member. "
                            "Invite the bot before sending."
                        ),
                        channel_name=channel.name,
                        channel_id=channel_id,
                        is_member=False,
                    )
                )
            else:
                results.append(
                    SlackPreflightResult(
                        name="slack_channel",
                        ok=True,
                        message=f"#{channel.name} resolved ({channel_id}); membership ok/unknown",
                        channel_name=channel.name,
                        channel_id=channel_id,
                        is_member=bool(is_member) if is_member is not None else None,
                    )
                )
        except Exception as exc:  # noqa: BLE001 — per-channel diagnostic
            results.append(
                SlackPreflightResult(
                    name="slack_channel",
                    ok=False,
                    message=f"#{channel.name}: {exc}",
                    channel_name=channel.name,
                    channel_id=channel.channel_id,
                )
            )
    return results


__all__ = [
    "CANONICAL_CHANNEL_REQUIREMENTS",
    "ConfigValidationIssue",
    "SlackAnnounceConfig",
    "SlackAnnounceDraft",
    "SlackCcPerson",
    "SlackChannelMessage",
    "SlackChannelTarget",
    "SlackPreflightResult",
    "SlackSendResult",
    "build_announce_text",
    "build_channel_messages",
    "default_cc_people",
    "default_channels",
    "deployer_slack_gate_open",
    "draft_from_session",
    "ensure_canonical_cc",
    "extract_version_label",
    "format_cc_line",
    "format_deploy_day",
    "format_service_desk_display",
    "format_sharepoint_display",
    "format_sharepoint_download_display",
    "format_sharepoint_folder_display",
    "load_announce_config",
    "merge_send_results",
    "missing_required_cc_tokens",
    "never_post_unless_asked",
    "pending_channel_messages",
    "preflight_slack_readonly",
    "send_announce_messages",
    "send_channel_message",
    "sharepoint_label_from_url",
    "strip_cc_suffix",
    "validate_announce_config",
    "version_without_prefix",
]

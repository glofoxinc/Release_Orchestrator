"""Playwright MCP playbooks for SharePoint upload and Slack announce.

The Release Orchestrator MCP does not drive a browser directly. It returns
structured handoffs for the Cursor agent to execute via **Playwright MCP**
(``user-playwright``) and/or **Slack MCP** (``plugin-slack-slack``).

Operators sign in once in the Playwright browser profile (M365 + Slack).
No Graph app or Slack bot token is required for this path.
"""

from __future__ import annotations

import json
import os
from datetime import date
from typing import Any
from urllib.parse import quote

import config
import sharepoint_upload as sp
from shipit_test_mode import parse_release_version_date


def _section() -> dict[str, Any]:
    return dict(config.BROWSER_AUTOMATION or {})


def enabled() -> bool:
    return bool(_section().get("enabled", True))


def sharepoint_section() -> dict[str, Any]:
    base = dict(_section().get("sharepoint") or {})
    try:
        from release_mcp import onboarding_store

        override = onboarding_store.load_state().get("sharepoint_override")
        if isinstance(override, dict) and override:
            merged = dict(base)
            merged.update(override)
            return merged
    except Exception:  # noqa: BLE001
        pass
    return base


def slack_section() -> dict[str, Any]:
    return dict(_section().get("slack") or {})


def playwright_mcp() -> str:
    """Cursor mcp.json server name (often ``playwright``; plugin folder may be user-playwright)."""
    section = _section()
    return str(section.get("mcp_server") or section.get("mcp") or "playwright").strip()


def playwright_mcp_readiness() -> dict[str, Any]:
    """Readiness for Cursor Playwright MCP — config presence + optional manual confirm."""
    mcp = playwright_mcp()
    in_config = False
    try:
        from release_mcp import mcp_installer

        servers = mcp_installer.load_mcp_config(prefer_project=True).get("servers") or {}
        in_config = mcp in servers or "playwright" in servers or any(
            "playwright" in str(k).lower() for k in servers
        )
    except Exception:  # noqa: BLE001
        in_config = False

    confirmed = False
    try:
        from release_mcp import onboarding_store

        confirmed = bool(
            onboarding_store.manual_confirmed("playwright_plugin")
            or onboarding_store.manual_confirmed("playwright_mcp_fallback")
            or onboarding_store.manual_confirmed("cursor_plugins")
        )
    except Exception:  # noqa: BLE001
        pass

    can_schedule = in_config and confirmed
    blockers: list[str] = []
    if not in_config:
        blockers.append(
            f"Add Playwright MCP (`{mcp}`) to `.cursor/mcp.json` — say **continue** after onboarding merge"
        )
    elif not confirmed:
        blockers.append(
            "Sign in to M365 + Slack once in the Playwright browser, then say **playwright confirmed**"
        )

    return {
        "enabled": True,
        "mcp_server": mcp,
        "in_mcp_config": in_config,
        "can_schedule": can_schedule,
        "blockers": blockers,
        "trigger_phrases": [
            "schedule review call",
            "daily review calendar playwright",
            "upload sharepoint",
        ],
        "completion_phrases": ["calendar done", "meeting scheduled", "sharepoint done"],
    }


def prefer_slack_mcp() -> bool:
    section = slack_section()
    if "prefer_slack_mcp" in section:
        return bool(section.get("prefer_slack_mcp"))
    if "prefer_playwright" in section:
        return not bool(section.get("prefer_playwright"))
    return True


def prefer_playwright_slack() -> bool:
    """True when Step 6 should default to Playwright browser (private Glofox channels)."""
    section = slack_section()
    if "prefer_playwright" in section:
        return bool(section.get("prefer_playwright"))
    return not bool(section.get("prefer_slack_mcp", True))


def sharepoint_browser_upload_enabled() -> bool:
    """True when Release Notes Step 3 should auto-chain to Playwright SharePoint upload."""
    if not enabled():
        return False
    sp = sharepoint_section()
    if sp.get("enabled") is False:
        return False
    if sp.get("auto_upload_after_docx") is False:
        return False
    return bool(sp.get("folder_path") or sp.get("folder_browse_url") or sp.get("hostname"))


def slack_auto_handoff_after_shipit() -> bool:
    """True when SHIPIT create should auto-start Slack announce (Playwright for Glofox)."""
    if not enabled():
        return False
    from slack_announce import never_post_unless_asked

    if never_post_unless_asked():
        return False
    slack = slack_section()
    if slack.get("enabled") is False:
        return False
    if slack.get("auto_send_after_shipit") is False:
        return False
    return (
        prefer_playwright_slack()
        or prefer_slack_mcp()
        or bool(slack.get("auto_send_after_shipit"))
    )


def resolve_sharepoint_folder_relative(
    sp_cfg: dict[str, Any] | None = None,
    *,
    version_name: str = "",
    reference_date: date | None = None,
) -> str:
    """Folder path under the site root, including quarter subfolder when configured."""
    cfg = sp_cfg or sharepoint_section()
    folder_path = str(cfg.get("folder_path") or "Shared Documents/Release Notes").strip()
    ref = reference_date or parse_release_version_date(version_name) or date.today()
    if "{{quarter}}" in folder_path:
        return folder_path.replace("{{quarter}}", sp.quarter_label(ref))
    if bool(cfg.get("auto_quarter_subfolder", False)):
        base = folder_path.rstrip("/\\")
        return f"{base}/{sp.quarter_label(ref)}"
    return folder_path


def resolve_sharepoint_id_path(
    *,
    version_name: str = "",
    reference_date: date | None = None,
    sp_cfg: dict[str, Any] | None = None,
) -> str:
    """Server-relative SharePoint path used in AllItems.aspx ``id=``."""
    cfg = sp_cfg or sharepoint_section()
    site_path = str(cfg.get("site_path") or "").strip()
    if not site_path.startswith("/"):
        site_path = f"/{site_path}"
    folder = resolve_sharepoint_folder_relative(
        cfg,
        version_name=version_name,
        reference_date=reference_date,
    )
    return f"{site_path}/{folder}".replace("//", "/")


def resolve_sharepoint_folder_url(
    *,
    version_name: str = "",
    reference_date: date | None = None,
) -> str:
    """Build the SharePoint quarter folder URL operators open before upload."""
    sp_cfg = sharepoint_section()
    explicit = str(sp_cfg.get("folder_browse_url") or "").strip()
    ref = reference_date or parse_release_version_date(version_name) or date.today()
    quarter = sp.quarter_label(ref)
    if explicit:
        if "{{quarter}}" in explicit:
            return explicit.replace("{{quarter}}", quarter)
        return explicit

    hostname = str(sp_cfg.get("hostname") or "").strip()
    site_path = str(sp_cfg.get("site_path") or "").strip()
    if not hostname or not site_path:
        return ""

    if not site_path.startswith("/"):
        site_path = f"/{site_path}"

    id_path = resolve_sharepoint_id_path(
        version_name=version_name,
        reference_date=reference_date,
        sp_cfg=sp_cfg,
    )
    encoded_id = quote(id_path, safe="")
    site_segment = site_path.lstrip("/")

    url = (
        f"https://{hostname}/{site_segment}/Shared%20Documents/Forms/AllItems.aspx"
        f"?id={encoded_id}"
    )
    viewid = str(sp_cfg.get("viewid") or "").strip()
    if viewid:
        url += f"&viewid={quote(viewid, safe='')}"
    return url


def resolve_sharepoint_quarter_label(
    *,
    version_name: str = "",
    reference_date: date | None = None,
) -> str:
    ref = reference_date or parse_release_version_date(version_name) or date.today()
    return sp.quarter_label(ref)


def resolve_remote_name(version_name: str) -> str:
    sp_cfg = sharepoint_section()
    template = str(
        sp_cfg.get("remote_name_template")
        or config.SHAREPOINT_UPLOAD.get("remote_name_template")
        or "Release Notes {{version}}.docx"
    )
    return sp.default_remote_name(version_name.lstrip("v"), template)


def status() -> dict[str, Any]:
    """Configuration readiness for browser automation handoffs."""
    sp_cfg = sharepoint_section()
    sl_cfg = slack_section()
    folder_url = resolve_sharepoint_folder_url()
    quarter_example = resolve_sharepoint_quarter_label()
    folder_relative = resolve_sharepoint_folder_relative()
    issues: list[dict[str, str]] = []

    if not enabled():
        issues.append({
            "level": "info",
            "code": "disabled",
            "message": "browser_automation.enabled=false in workspace.yaml",
        })

    if not sp_cfg.get("enabled", True):
        issues.append({
            "level": "warn",
            "code": "sharepoint_disabled",
            "message": "SharePoint browser upload disabled in config.",
        })
    elif not folder_url and not sp_cfg.get("folder_browse_url"):
        issues.append({
            "level": "error",
            "code": "sharepoint_folder_url",
            "message": "Set browser_automation.sharepoint.folder_browse_url or hostname+site_path.",
        })

    if not sl_cfg.get("enabled", True):
        issues.append({
            "level": "warn",
            "code": "slack_disabled",
            "message": "Slack browser fallback disabled in config.",
        })

    return {
        "enabled": enabled(),
        "playwright_mcp": playwright_mcp(),
        "prefer_slack_mcp": prefer_slack_mcp(),
        "sharepoint": {
            "enabled": bool(sp_cfg.get("enabled", True)),
            "folder_browse_url": folder_url or sp_cfg.get("folder_browse_url"),
            "folder_path": folder_relative,
            "quarter_folder_example": quarter_example,
            "auto_quarter_subfolder": bool(sp_cfg.get("auto_quarter_subfolder", False)),
            "hostname": sp_cfg.get("hostname"),
            "site_path": sp_cfg.get("site_path"),
        },
        "slack": {
            "enabled": bool(sl_cfg.get("enabled", True)),
            "workspace_url": sl_cfg.get("workspace_url"),
            "team_id": sl_cfg.get("team_id") or os.getenv("SLACK_TEAM_ID", ""),
        },
        "setup": [
            "Enable Playwright MCP (playwright) in Cursor Settings > MCP.",
            "Step 6 Slack: Playwright web (one-time abcfitness.com sign-in per machine).",
            "Slack MCP optional — private Glofox channels use Playwright instead.",
            "No MS_GRAPH_* or SLACK_BOT_TOKEN required for browser handoff paths.",
        ],
        "config_issues": issues,
        "ready": enabled() and not any(i["level"] == "error" for i in issues),
    }


def _step(
    order: int,
    title: str,
    *,
    mcp_tool: str,
    arguments: dict[str, Any] | None = None,
    note: str = "",
    optional: bool = False,
) -> dict[str, Any]:
    return {
        "order": order,
        "title": title,
        "mcp": playwright_mcp(),
        "mcp_tool": mcp_tool,
        "arguments": arguments or {},
        "operator_note": note,
        "optional": optional,
    }


def build_sharepoint_upload_handoff(
    local_path: str,
    *,
    version_name: str = "",
    remote_name: str | None = None,
) -> dict[str, Any]:
    """Playwright MCP playbook to upload Release Notes .docx to SharePoint."""
    st = status()
    folder_url = resolve_sharepoint_folder_url(version_name=version_name).strip()
    quarter_folder = resolve_sharepoint_quarter_label(version_name=version_name)
    folder_relative = resolve_sharepoint_folder_relative(version_name=version_name)
    file_name = remote_name or resolve_remote_name(version_name)
    abs_path = os.path.abspath(local_path)

    if not os.path.isfile(abs_path):
        return {
            "ok": False,
            "error": f"Local file not found: {abs_path}",
            "delivery": "cursor_playwright_mcp",
        }

    steps = [
        _step(
            1,
            f"Open Release Notes folder ({quarter_folder})",
            mcp_tool="browser_navigate",
            arguments={"url": folder_url},
            note="Sign in with your ABC M365 account if prompted.",
        ),
        _step(
            2,
            "Snapshot the page",
            mcp_tool="browser_snapshot",
            arguments={},
            note=f"Confirm you are in **{folder_relative}** before uploading.",
        ),
        _step(
            3,
            f"Create quarter folder '{quarter_folder}' if missing",
            mcp_tool="browser_run_code_unsafe",
            arguments={
                "code": (
                    "async (page) => {"
                    f"  const name = {quarter_folder!r};"
                    "  const exists = await page.getByText(name, { exact: true }).count();"
                    "  if (exists) return 'Folder already exists: ' + name;"
                    "  const newBtn = page.getByRole('button', { name: /^new$/i }).first();"
                    "  if (!(await newBtn.count())) {"
                    "    return 'Click New → Folder manually and name it: ' + name;"
                    "  }"
                    "  await newBtn.click();"
                    "  const folderItem = page.getByRole('menuitem', { name: /folder/i }).first();"
                    "  if (await folderItem.count()) await folderItem.click();"
                    "  const input = page.getByRole('textbox').first();"
                    "  if (await input.count()) {"
                    "    await input.fill(name);"
                    "    await input.press('Enter');"
                    "    return 'Created folder: ' + name;"
                    "  }"
                    "  return 'Create folder manually: ' + name;"
                    "}"
                ),
            },
            note=(
                f"SharePoint path uses a quarter subfolder per release (e.g. **{quarter_folder}**). "
                "Create it if the folder list does not show it yet."
            ),
            optional=True,
        ),
        _step(
            4,
            "Open Upload menu",
            mcp_tool="browser_run_code_unsafe",
            arguments={
                "code": (
                    "async (page) => {"
                    "  const upload = page.getByRole('button', { name: /upload/i }).first();"
                    "  if (await upload.count()) { await upload.click(); return 'clicked Upload'; }"
                    "  const menu = page.locator('[data-automationid=\"uploadCommand\"]').first();"
                    "  if (await menu.count()) { await menu.click(); return 'clicked uploadCommand'; }"
                    "  return 'Upload control not found — use snapshot and click Upload manually';"
                    "}"
                ),
            },
            note="If this fails, click **Upload → Files** manually from the snapshot.",
            optional=True,
        ),
        _step(
            5,
            "Choose Files upload",
            mcp_tool="browser_run_code_unsafe",
            arguments={
                "code": (
                    "async (page) => {"
                    "  const files = page.getByRole('menuitem', { name: /files/i }).first();"
                    "  if (await files.count()) { await files.click(); return 'Files menu'; }"
                    "  return 'Files menu not found';"
                    "}"
                ),
            },
            optional=True,
        ),
        _step(
            6,
            f"Upload {file_name}",
            mcp_tool="browser_file_upload",
            arguments={"paths": [abs_path]},
            note=f"Select the generated DOCX: {abs_path}",
        ),
        _step(
            7,
            "Wait for upload to finish",
            mcp_tool="browser_wait_for",
            arguments={"text": file_name.replace(".docx", ""), "time": 120},
            note="SharePoint may take a minute for large files.",
        ),
        _step(
            8,
            "Copy document link",
            mcp_tool="browser_run_code_unsafe",
            arguments={
                "code": (
                    "async (page) => {"
                    f"  const row = page.getByText('{file_name}', {{ exact: false }}).first();"
                    "  if (!(await row.count())) return 'File row not visible yet';"
                    "  await row.click({ button: 'right' });"
                    "  return 'Right-click the file → Copy link, or open file and copy browser URL';"
                    "}"
                ),
            },
            note=(
                "Copy the SharePoint document URL (must contain abcfinancial.sharepoint.com). "
                "Paste it in chat or say **sharepoint done <url>**."
            ),
        ),
    ]

    return {
        "ok": bool(folder_url),
        "delivery": "cursor_playwright_mcp",
        "mcp": playwright_mcp(),
        "instruction": (
            "Execute each step below using **Playwright MCP**. The upload target is the "
            f"**{quarter_folder}** quarter folder under your team's Release Notes library. "
            "When upload completes, paste the SharePoint document URL in chat "
            "(or say **sharepoint done**)."
        ),
        "local_path": abs_path,
        "remote_name": file_name,
        "quarter_folder": quarter_folder,
        "folder_relative_path": folder_relative,
        "folder_browse_url": folder_url,
        "completion": {
            "user_phrases": ["sharepoint done", "uploaded sharepoint"],
            "session_input": "sharepoint_url",
            "validate": "URL must be *.sharepoint.com document link",
        },
        "steps": steps,
        "config_status": st,
        "error": "" if folder_url else "SharePoint folder URL not configured.",
    }


def build_playwright_slack_compose(
    draft: Any,
    channel: Any,
) -> dict[str, Any]:
    """Structured Slack web compose payload — hyperlinks + @mentions for Playwright."""
    from slack_announce import (
        format_deploy_day,
        format_service_desk_display,
        format_sharepoint_download_display,
        format_sharepoint_folder_display,
        sharepoint_label_from_url,
    )

    day = format_deploy_day(draft.deploy_date)
    version = draft.version if draft.version.lower().startswith("v") else f"v{draft.version}"
    sp_label = draft.sharepoint_label or sharepoint_label_from_url(
        draft.sharepoint_url,
        version,
    )
    from sharepoint_url import resolve_sharepoint_folder_link, sharepoint_document_open_url

    sp_download_url = sharepoint_document_open_url((draft.sharepoint_url or "").strip())
    if not sp_download_url:
        sp_download_url = sharepoint_document_open_url(
            (getattr(draft, "sharepoint_download_url", "") or "").strip()
        )
    sp_folder_url = (getattr(draft, "sharepoint_folder_url", "") or "").strip()
    sp_folder_label = (
        getattr(draft, "sharepoint_folder_label", "") or "Release Notes folder"
    )
    if not sp_folder_url:
        sp_folder_url, sp_folder_label = resolve_sharepoint_folder_link(
            version_name=version,
            reference_date=getattr(draft, "deploy_date", None),
        )
    ticket_url = (draft.ticket_url or "").strip()
    ticket_label = format_service_desk_display(draft, for_preview=True)
    cc_people = list(getattr(channel, "cc", ()) or ())

    def _link(url: str, label: str) -> dict[str, str]:
        return {"type": "link", "url": url, "label": label}

    def _text(value: str) -> dict[str, str]:
        return {"type": "text", "text": value}

    def _mention(person: Any) -> dict[str, str]:
        return {
            "type": "mention",
            "user_id": str(getattr(person, "user_id", "") or ""),
            "name": str(getattr(person, "name", "") or ""),
        }

    sharepoint_download_part = (
        _link(sp_download_url, sp_label) if sp_download_url else _text(sp_label)
    )
    sharepoint_folder_part = (
        _link(sp_folder_url, sp_folder_label) if sp_folder_url else _text(sp_folder_label)
    )
    service_desk_part = _link(ticket_url, ticket_label) if ticket_url else _text(ticket_label)
    cc_parts: list[dict[str, str]] = [_text("CC: ")]
    for index, person in enumerate(cc_people):
        if index:
            cc_parts.append(_text(" "))
        cc_parts.append(_mention(person))

    blocks: list[dict[str, Any]] = [
        {"type": "line", "parts": [_text("Hello Team,")]},
        {"type": "line", "parts": [_text(f"Our upcoming deployment is scheduled for {day}.")]},
        {
            "type": "line",
            "parts": [_text("Deployment notes and the deployment ticket are below for reference:")],
        },
        {"type": "blank"},
        {
            "type": "line",
            "parts": [_text("SharePoint — Release Notes: "), sharepoint_download_part],
        },
        {
            "type": "line",
            "parts": [_text("SharePoint — Folder: "), sharepoint_folder_part],
        },
        {"type": "line", "parts": [_text("Service Desk: "), service_desk_part]},
        {"type": "line", "parts": cc_parts},
    ]
    plain_lines = [
        "Hello Team,",
        f"Our upcoming deployment is scheduled for {day}.",
        "Deployment notes and the deployment ticket are below for reference:",
        "",
        f"SharePoint — Release Notes: {sp_label}",
        f"SharePoint — Folder: {sp_folder_label}",
        f"Service Desk: {ticket_label}",
        "CC: " + " ".join(f"@{p.name}" for p in cc_people),
    ]
    return {"blocks": blocks, "plain_fallback": "\n".join(plain_lines)}


def playwright_slack_send_code(compose: dict[str, Any] | str) -> str:
    """Playwright JS to post one Slack message with hyperlinks and @mentions.

    Accepts a structured ``playwright_compose`` dict (preferred) or legacy plain text.
    """
    if isinstance(compose, str):
        msg_literal = json.dumps(compose)
        return (
            "async (page) => {"
            f"  const text = {msg_literal};"
            "  const box = page.locator('[data-qa=\"message_input\"]').first();"
            "  if (!(await box.count())) return 'composer not found';"
            "  await box.click();"
            "  const lines = text.split('\\n');"
            "  for (let i = 0; i < lines.length; i++) {"
            "    if (lines[i]) await page.keyboard.type(lines[i], { delay: 2 });"
            "    if (i < lines.length - 1) {"
            "      await page.keyboard.down('Shift');"
            "      await page.keyboard.press('Enter');"
            "      await page.keyboard.up('Shift');"
            "    }"
            "  }"
            "  await page.keyboard.press('Enter');"
            "  return 'sent plain text';"
            "}"
        )

    compose_literal = json.dumps(compose)
    return (
        "async (page) => {"
        f"  const compose = {compose_literal};"
        "  const escapeHtml = (s) => String(s || '')"
        "    .replace(/&/g, '&amp;')"
        "    .replace(/</g, '&lt;')"
        "    .replace(/>/g, '&gt;')"
        "    .replace(/\"/g, '&quot;');"
        "  const partHtml = (part) => {"
        "    if (part.type === 'text') return escapeHtml(part.text);"
        "    if (part.type === 'link') {"
        "      const href = escapeHtml(part.url);"
        "      const label = escapeHtml(part.label);"
        "      return `<a href=\"${href}\">${label}</a>`;"
        "    }"
        "    if (part.type === 'mention') {"
        "      const uid = escapeHtml(part.user_id || '');"
        "      const name = escapeHtml(part.name || '');"
        "      return `<span data-stringify-type=\"mention\" data-stringify-id=\"${uid}\">@${name}</span>`;"
        "    }"
        "    return '';"
        "  };"
        "  const html = (compose.blocks || []).map((block) => {"
        "    if (block.type === 'blank') return '<p><br></p>';"
        "    const inner = (block.parts || []).map(partHtml).join('');"
        "    return `<p>${inner || '<br>'}</p>`;"
        "  }).join('');"
        "  const plain = compose.plain_fallback || '';"
        "  const box = page.locator('[data-qa=\"message_input\"]').first();"
        "  if (!(await box.count())) return 'composer not found';"
        "  await box.click();"
        "  let mode = 'clipboard';"
        "  try {"
        "    await page.evaluate(async ({ htmlBody, plainBody }) => {"
        "      const htmlBlob = new Blob([htmlBody], { type: 'text/html' });"
        "      const textBlob = new Blob([plainBody], { type: 'text/plain' });"
        "      const item = new ClipboardItem({ 'text/html': htmlBlob, 'text/plain': textBlob });"
        "      await navigator.clipboard.write([item]);"
        "    }, { htmlBody: html, plainBody: plain });"
        "    await page.keyboard.press('Control+v');"
        "  } catch (err) {"
        "    mode = 'quill';"
        "    await page.evaluate(({ blocks }) => {"
        "      const root = document.querySelector('[data-qa=\"message_input\"] .ql-editor');"
        "      if (!root) throw new Error('quill editor not found');"
        "      root.innerHTML = '';"
        "      for (const block of blocks || []) {"
        "        const p = document.createElement('p');"
        "        if (block.type === 'blank') {"
        "          root.appendChild(p);"
        "          continue;"
        "        }"
        "        for (const part of block.parts || []) {"
        "          if (part.type === 'text') p.appendChild(document.createTextNode(part.text || ''));"
        "          else if (part.type === 'link') {"
        "            const a = document.createElement('a');"
        "            a.href = part.url || '';"
        "            a.textContent = part.label || part.url || '';"
        "            p.appendChild(a);"
        "          } else if (part.type === 'mention') {"
        "            const span = document.createElement('span');"
        "            span.setAttribute('data-stringify-type', 'mention');"
        "            if (part.user_id) span.setAttribute('data-stringify-id', part.user_id);"
        "            span.textContent = '@' + (part.name || '');"
        "            p.appendChild(span);"
        "          }"
        "        }"
        "        root.appendChild(p);"
        "      }"
        "      root.dispatchEvent(new InputEvent('input', { bubbles: true }));"
        "    }, { blocks: compose.blocks || [] });"
        "  }"
        "  await page.waitForTimeout(800);"
        "  const sendBtn = page.locator('[data-qa=\"texty_send_button\"], button[aria-label=\"Send now\"]').first();"
        "  if (await sendBtn.count()) {"
        "    await sendBtn.click();"
        "  } else {"
        "    await page.keyboard.press('Enter');"
        "  }"
        "  await page.waitForTimeout(500);"
        "  return `sent via ${mode}`;"
        "}"
    )


def build_slack_channel_url(channel_id: str, *, team_id: str = "") -> str:
    """Deep link to a Slack channel in the browser client."""
    tid = (team_id or slack_section().get("team_id") or os.getenv("SLACK_TEAM_ID") or "").strip()
    base = str(slack_section().get("workspace_url") or "https://app.slack.com/client").rstrip("/")
    cid = (channel_id or "").strip()
    if tid and cid:
        return f"{base}/{tid}/{cid}?skip_today=1"
    if cid:
        return f"{base}/?channel={cid}"
    return base


def build_slack_post_handoff(
    *,
    channel_id: str,
    channel_name: str,
    message: str = "",
    compose: dict[str, Any] | None = None,
    team_id: str = "",
) -> dict[str, Any]:
    """Playwright MCP playbook to post one Slack message (fallback when Slack MCP unavailable)."""
    channel_url = build_slack_channel_url(channel_id, team_id=team_id)
    payload = compose if compose else message
    send_code = playwright_slack_send_code(payload)

    steps = [
        _step(
            1,
            f"Open #{channel_name.lstrip('#')}",
            mcp_tool="browser_navigate",
            arguments={"url": channel_url},
            note="Sign in to Slack if prompted.",
        ),
        _step(
            2,
            "Focus message composer",
            mcp_tool="browser_run_code_unsafe",
            arguments={
                "code": (
                    "async (page) => {"
                    "  const box = page.locator('[data-qa=\"message_input\"]').first();"
                    "  if (await box.count()) { await box.click(); return 'composer focused'; }"
                    "  const alt = page.getByRole('textbox').last();"
                    "  if (await alt.count()) { await alt.click(); return 'textbox focused'; }"
                    "  return 'Message box not found — use snapshot';"
                    "}"
                ),
            },
        ),
        _step(
            3,
            "Paste linked deployment message and send",
            mcp_tool="browser_run_code_unsafe",
            arguments={"code": send_code},
            note="Inserts SharePoint + Service Desk hyperlinks and @mentions, then sends.",
        ),
    ]

    preview_source = (compose or {}).get("plain_fallback") or message
    return {
        "delivery": "cursor_playwright_mcp",
        "mcp": playwright_mcp(),
        "channel_id": channel_id,
        "channel_name": channel_name,
        "channel_url": channel_url,
        "playwright_compose": compose,
        "message_preview": preview_source[:200] + ("…" if len(preview_source) > 200 else ""),
        "steps": steps,
    }


def build_slack_announce_handoff(preview: dict[str, Any]) -> dict[str, Any]:
    """Playwright handoff for all channels in a Slack preview."""
    posts: list[dict[str, Any]] = []
    for item in preview.get("channels") or []:
        channel_id = str(item.get("channel_id") or "").strip()
        message = str(item.get("text") or "").strip()
        compose = item.get("playwright_compose")
        name = str(item.get("name") or "").strip()
        if not channel_id or (not message and not compose):
            continue
        posts.append(build_slack_post_handoff(
            channel_id=channel_id,
            channel_name=name,
            message=message,
            compose=compose if isinstance(compose, dict) else None,
        ))

    return {
        "delivery": "cursor_playwright_mcp",
        "mcp": playwright_mcp(),
        "prefer_slack_mcp": prefer_slack_mcp(),
        "instruction": (
            "Post to each channel below using **Playwright MCP** (one-time Slack web login per machine). "
            "(fallback when Slack MCP is unavailable). "
            "Recommended: use **Slack MCP** `slack_send_message` when enabled. "
            "When both channels are posted, say **slack done**."
        ),
        "slack_mcp_alternative": {
            "mcp": "plugin-slack-slack",
            "mcp_tool": "slack_send_message",
            "note": "Preferred — no browser login required when Slack MCP is connected.",
        },
        "channels": posts,
        "completion": {
            "user_phrases": ["slack done", "posted slack"],
        },
    }

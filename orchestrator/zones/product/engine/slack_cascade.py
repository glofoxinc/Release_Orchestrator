"""Slack send cascade: Playwright → Slack MCP → bot token (must succeed on both channels)."""

from __future__ import annotations

from typing import Any

CANONICAL_CHANNEL_KEYS: tuple[str, ...] = ("squad", "buddies")


def cascade_order() -> list[str]:
    """Preferred send paths when operator says **send slack**."""
    import browser_automation

    order: list[str] = []
    if browser_automation.prefer_playwright_slack() and browser_automation.enabled():
        order.append("playwright")
    if browser_automation.prefer_slack_mcp():
        order.append("slack_mcp")
    order.append("bot_token")
    seen: set[str] = set()
    out: list[str] = []
    for item in order:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def required_channel_keys(preview: dict[str, Any] | None) -> list[str]:
    keys = [
        str(item.get("key") or "").strip()
        for item in (preview or {}).get("channels") or []
        if str(item.get("key") or "").strip()
    ]
    return keys or list(CANONICAL_CHANNEL_KEYS)


def receipts_from_send_result(result: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Build slack_receipts map from bot-token send result."""
    out: dict[str, dict[str, Any]] = {}
    for item in (result or {}).get("results") or []:
        key = str(item.get("key") or "").strip()
        if not key or not item.get("ok"):
            continue
        out[key] = {
            "permalink": item.get("permalink"),
            "ts": item.get("ts"),
            "channel_name": item.get("channel_name"),
            "source": "bot_token",
        }
    return out


def merge_receipts(
    existing: dict[str, Any] | None,
    incoming: dict[str, dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {
        str(k): dict(v) for k, v in (existing or {}).items() if isinstance(v, dict)
    }
    for key, value in (incoming or {}).items():
        if not isinstance(value, dict):
            continue
        if value.get("permalink") or value.get("ts"):
            merged[str(key)] = {**merged.get(str(key), {}), **value}
    return merged


def receipt_complete(receipt: dict[str, Any] | None) -> bool:
    if not isinstance(receipt, dict):
        return False
    return bool(str(receipt.get("permalink") or "").strip() or str(receipt.get("ts") or "").strip())


def missing_receipt_keys(
    preview: dict[str, Any] | None,
    receipts: dict[str, Any] | None,
) -> list[str]:
    required = required_channel_keys(preview)
    store = receipts or {}
    return [key for key in required if not receipt_complete(store.get(key))]


def receipts_complete(preview: dict[str, Any] | None, receipts: dict[str, Any] | None) -> bool:
    return not missing_receipt_keys(preview, receipts)


def parse_receipt_inputs(raw: Any) -> dict[str, dict[str, Any]]:
    """Normalize wizard inputs slack_receipts / slack_receipt_* fields."""
    out: dict[str, dict[str, Any]] = {}
    if isinstance(raw, dict):
        for key, value in raw.items():
            k = str(key).strip()
            if not k:
                continue
            if isinstance(value, dict):
                out[k] = dict(value)
            else:
                url = str(value or "").strip()
                if url:
                    out[k] = {"permalink": url, "source": "manual"}
    return out

"""Open Teams scheduling dialog pre-filled for Daily Review Agent demo."""

from __future__ import annotations

import subprocess
import sys
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

_APP_ROOT = Path(__file__).resolve().parents[2]
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

from daily_review_agent.config_loader import load_agent_config
from daily_review_agent.schedule import demo_window


def build_teams_deep_link(*, minutes_from_now: int = 30) -> tuple[str, datetime, datetime]:
    cfg = load_agent_config()
    start, end = demo_window(cfg, minutes_from_now=minutes_from_now)
    emails = ",".join(a.email for a in cfg.demo_attendees if a.email)
    subject = cfg.demo_subject
    content = "Daily Review Agent demo call (smoke test). Safe to delete."
    url = (
        "https://teams.microsoft.com/l/meeting/new?"
        f"subject={quote(subject)}"
        f"&startTime={quote(start.isoformat(), safe='')}"
        f"&endTime={quote(end.isoformat(), safe='')}"
        f"&content={quote(content)}"
        f"&attendees={quote(emails, safe='@.,')}"
    )
    return url, start, end


def main() -> int:
    url, start, end = build_teams_deep_link()
    out = _APP_ROOT / "orchestrator" / "agents" / "review" / ".state" / "demo_teams_deep_link.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(url, encoding="utf-8")
    print(f"Meeting start: {start.isoformat()}")
    print(f"Meeting end:   {end.isoformat()}")
    print(f"Deep link saved: {out}")
    print(f"\n{url}\n")
    try:
        webbrowser.open(url)
    except Exception:
        subprocess.run(["cmd", "/c", "start", "", url], check=False)
    print("Opened Teams scheduling dialog — click Send to create the invite and Teams link.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

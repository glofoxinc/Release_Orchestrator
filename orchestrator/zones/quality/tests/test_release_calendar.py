"""Safe deploy vs Friday-OK review dates."""

from __future__ import annotations

from datetime import date

import release_calendar as cal


def test_thursday_deploys_monday():
    thu = date(2026, 10, 15)  # Thursday
    assert cal.next_safe_deploy_day(thu, set()) == date(2026, 10, 19)
    assert cal.next_workday(thu, set()) == date(2026, 10, 16)  # Friday review OK


def test_wednesday_friday_holiday_skips_thursday_deploy():
    wed = date(2026, 10, 14)
    holidays = {date(2026, 10, 16)}  # Friday holiday
    assert cal.next_safe_deploy_day(wed, holidays) == date(2026, 10, 19)
    assert cal.next_workday(wed, holidays) == date(2026, 10, 15)  # Thursday review OK


def test_monday_deploys_tuesday():
    mon = date(2026, 10, 12)
    assert cal.next_safe_deploy_day(mon, set()) == date(2026, 10, 13)
    assert cal.next_workday(mon, set()) == date(2026, 10, 13)


def test_propose_does_not_call_outlook(tmp_path, monkeypatch):
    cache = tmp_path / "company_holidays.json"
    monkeypatch.setattr(cal, "CACHE_FILE", cache)
    out = cal.propose_release_dates(today=date(2026, 10, 15), holidays=set())
    assert out["review_day"] == "2026-10-16"
    assert out["deploy_day"] == "2026-10-19"
    assert out["playwright_handoff"]["mcp"] == "playwright"
    assert "background" in out["playwright_handoff"]["note"].lower()

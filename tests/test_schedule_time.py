"""Tests for TCKT planned start/end timezone handling."""

from __future__ import annotations

from datetime import date, time

import schedule_time as stz


def test_iso_uses_selected_zone_not_machine_local():
    iso = stz.format_jira_iso(date(2026, 8, 5), time(10, 0), "Asia/Kolkata")
    assert iso == "2026-08-05T10:00:00.000+0530"


def test_iso_handles_us_central_dst():
    # August is CDT (-0500), January is CST (-0600).
    summer = stz.format_jira_iso(date(2026, 8, 5), time(10, 0), "America/Chicago")
    winter = stz.format_jira_iso(date(2026, 1, 14), time(10, 0), "America/Chicago")
    assert summer.endswith("-0500")
    assert winter.endswith("-0600")


def test_unknown_zone_falls_back_to_default():
    iso = stz.format_jira_iso(date(2026, 8, 5), time(10, 0), "Not/AZone")
    assert iso.endswith("-0500")


def test_ist_morning_renders_as_previous_night_in_central():
    info = stz.describe_window(
        date(2026, 8, 5), time(10, 0),
        date(2026, 8, 5), time(13, 0),
        tz_name="Asia/Kolkata",
        display_tz="America/Chicago",
    )
    # This is exactly what the created ticket showed for reviewers.
    assert info["display_start"].startswith("Aug 04, 2026, 11:30 PM")
    assert info["display_end"].startswith("Aug 05, 2026, 2:30 AM")
    assert info["display_crosses_day"] is True
    assert info["duration_minutes"] == 180
    assert info["valid"] is True
    assert info["same_zone"] is False


def test_entered_window_keeps_local_reading():
    info = stz.describe_window(
        date(2026, 8, 5), time(10, 30),
        date(2026, 8, 5), time(13, 0),
        tz_name="Asia/Kolkata",
        display_tz="America/Chicago",
    )
    assert info["entered_start"].startswith("Aug 05, 2026, 10:30 AM")
    assert info["entered_end"].startswith("Aug 05, 2026, 1:00 PM")
    assert info["start_iso"] == "2026-08-05T10:30:00.000+0530"
    assert info["duration_minutes"] == 150


def test_same_zone_window_does_not_cross_day():
    info = stz.describe_window(
        date(2026, 8, 5), time(10, 0),
        date(2026, 8, 5), time(13, 0),
        tz_name="America/Chicago",
        display_tz="America/Chicago",
    )
    assert info["same_zone"] is True
    assert info["display_crosses_day"] is False
    assert info["start_iso"] == "2026-08-05T10:00:00.000-0500"


def test_invalid_window_flagged():
    info = stz.describe_window(
        date(2026, 8, 5), time(13, 0),
        date(2026, 8, 5), time(10, 0),
        tz_name="Asia/Kolkata",
    )
    assert info["valid"] is False
    assert info["duration_minutes"] < 0


def test_duration_label():
    assert stz.duration_label(180) == "3 hours"
    assert stz.duration_label(150) == "2 hours 30 minutes"
    assert stz.duration_label(60) == "1 hour"
    assert stz.duration_label(0) == "invalid window"


def test_zone_label_includes_friendly_name():
    assert "India" in stz.zone_label("Asia/Kolkata")
    assert "Asia/Kolkata" in stz.zone_label("Asia/Kolkata")
    assert stz.zone_label("Mars/Base") == "Mars/Base"


def test_window_statement_states_both_clocks():
    w = stz.window_statement(
        date(2026, 8, 5), time(10, 0),
        date(2026, 8, 5), time(13, 0),
        tz_name="Asia/Kolkata",
        display_tz="America/Chicago",
    )
    assert w["primary"] == "Aug 05, 2026, 10:00 AM \u2013 1:00 PM IST"
    assert w["secondary"] == (
        "Aug 04, 2026, 11:30 PM \u2013 Aug 05, 2026, 2:30 AM CDT"
    )
    assert w["primary"] in w["sentence"]
    assert w["secondary"] in w["sentence"]
    # The guard that stops another team closing the change early.
    assert "Do not close" in w["note"]
    assert "Agreed deployment window" in w["comment_body"]
    assert "10:00 AM" in w["comment_body"]
    assert "IST" in w["comment_body"]
    assert "CDT" in w["comment_body"]
    assert "timezone clarification" in w["comment_title"]


def test_window_statement_skips_conversion_when_same_zone():
    w = stz.window_statement(
        date(2026, 8, 5), time(10, 30),
        date(2026, 8, 5), time(11, 30),
        tz_name="America/Chicago",
        display_tz="America/Chicago",
    )
    assert w["secondary"] == ""
    assert w["note"] == ""
    assert w["sentence"] == (
        "Deployment window: Aug 05, 2026, 10:30 AM \u2013 11:30 AM CDT."
    )
    assert "Agreed deployment window" in w["comment_body"]
    assert "match that window" in w["comment_body"]


def test_window_statement_spells_out_multi_day_window():
    w = stz.window_statement(
        date(2026, 8, 5), time(22, 0),
        date(2026, 8, 6), time(1, 0),
        tz_name="Asia/Kolkata",
        display_tz="America/Chicago",
    )
    assert "Aug 05, 2026, 10:00 PM" in w["primary"]
    assert "Aug 06, 2026, 1:00 AM" in w["primary"]


def test_defaults_cover_this_team():
    assert stz.DEFAULT_SCHEDULE_TZ == "America/Chicago"
    assert stz.DEFAULT_DISPLAY_TZ == "America/Chicago"
    assert "Asia/Kolkata" in stz.COMMON_TIMEZONES
    assert "America/Chicago" in stz.COMMON_TIMEZONES


def test_normal_deployment_profile_is_ist_1030_1130():
    import release_defaults as rd

    sched = rd.default_deployment_schedule()
    assert sched["start_time"] == time(10, 30)
    assert sched["end_time"] == time(11, 30)
    assert sched["source_timezone"] == "Asia/Kolkata"
    assert sched["store_timezone"] == "America/Chicago"
    assert sched["timezone_name"] == "Asia/Kolkata"


def test_resolve_jira_schedule_converts_ist_to_central():
    jira = stz.resolve_jira_schedule(
        date(2026, 9, 11), time(10, 30),
        date(2026, 9, 11), time(11, 30),
    )
    assert jira["agreed_range"] == "Sep 11, 2026, 10:30 AM \u2013 11:30 AM IST"
    assert jira["reviewer_range"].startswith("Sep 11, 2026, 12:00 AM")
    assert "CDT" in str(jira["reviewer_range"])
    assert str(jira["start_iso"]).endswith("-0500")
    assert str(jira["end_iso"]).endswith("-0500")

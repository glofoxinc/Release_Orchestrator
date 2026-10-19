"""Glofox Jira → GitHub repo slug parsing."""

from __future__ import annotations

from glofox_jira_routing import detect_explicit_github_repo


def test_explicit_repo_keeps_names_ending_in_t_or_g():
    assert (
        detect_explicit_github_repo(
            "https://github.com/glofoxinc/abc-customize-insights-lift"
        )
        == "glofoxinc/abc-customize-insights-lift"
    )
    assert (
        detect_explicit_github_repo("https://github.com/glofoxinc/reporting")
        == "glofoxinc/reporting"
    )


def test_explicit_repo_strips_git_suffix_only():
    assert (
        detect_explicit_github_repo(
            "https://github.com/glofoxinc/abc-customize-insights-lift.git"
        )
        == "glofoxinc/abc-customize-insights-lift"
    )

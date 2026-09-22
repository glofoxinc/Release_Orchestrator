"""CSS dark-mode contrast guards and theme-aware component classes."""

from release_platform.ui.css import get_design_css


def test_dark_mode_expander_header_uses_dark_text_on_light_bar():
    css = get_design_css()
    assert 'html[data-theme="dark"] div[data-testid="stExpander"] summary' in css
    assert "color: #0f172a !important" in css


def test_dark_mode_checkbox_labels_use_theme_text():
    css = get_design_css()
    assert 'html[data-theme="dark"] .main .block-container [data-testid="stCheckbox"] label' in css
    assert "color: var(--jt-text) !important" in css


def test_light_mode_tokens_unchanged():
    css = get_design_css()
    assert 'html[data-theme="light"]' in css
    assert "--jt-text: #0f172a" in css


def test_dark_mode_tokens_defined():
    css = get_design_css()
    assert 'html[data-theme="dark"]' in css
    assert "--jt-text: #f1f5f9" in css
    assert "--jt-link:" in css


def test_theme_aware_banner_classes():
    css = get_design_css()
    assert ".success-banner h2" in css
    assert "color: var(--jt-success)" in css
    assert ".stk-created-banner" in css
    assert ".stk-error-panel" in css
    assert ".error-banner--warn" in css


def test_theme_aware_link_and_diff_classes():
    css = get_design_css()
    assert "a.jt-link" in css
    assert "color: var(--jt-link)" in css
    assert ".jt-diff-added" in css
    assert ".jt-diff-removed" in css


def test_missing_component_classes_restored():
    css = get_design_css()
    assert ".paste-hint" in css
    assert ".hist-client-card" in css
    assert ".review-card" in css
    assert ".jt-table" in css


def test_dark_mode_alert_and_code_blocks():
    css = get_design_css()
    assert 'html[data-theme="dark"] div[data-testid="stAlert"]' in css
    assert 'html[data-theme="dark"] [data-testid="stCodeBlock"]' in css

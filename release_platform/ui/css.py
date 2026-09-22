"""CSS design system — theme-aware tokens and component styles."""

from __future__ import annotations

import streamlit as st

_STATUS_COLORS = {
    "done": ("#22c55e", "#052e16"),
    "indeterminate": ("#3b82f6", "#0c1a3d"),
    "new": ("#a3a3a3", "#262626"),
}

_STEP_LABELS = ["Select Release", "Tickets", "Exclude Tickets", "Deployment Info", "Review", "Deploy"]

# ── Design tokens (light + dark via data-theme on html) ───────────────

_DESIGN_TOKENS = """
<style>
html[data-theme="light"], html:not([data-theme]) {
  --jt-bg: #f4f6fb;
  --jt-bg-elevated: #ffffff;
  --jt-bg-subtle: #eef2ff;
  --jt-bg-hover: #f8fafc;
  --jt-border: rgba(15, 23, 42, 0.08);
  --jt-border-strong: rgba(15, 23, 42, 0.14);
  --jt-text: #0f172a;
  --jt-text-muted: #64748b;
  --jt-text-faint: #94a3b8;
  --jt-accent: #6366f1;
  --jt-accent-2: #a855f7;
  --jt-accent-soft: rgba(99, 102, 241, 0.1);
  --jt-success: #16a34a;
  --jt-success-soft: rgba(22, 163, 74, 0.1);
  --jt-warning: #d97706;
  --jt-danger: #dc2626;
  --jt-link: #6366f1;
  --jt-shadow: 0 10px 40px rgba(15, 23, 42, 0.08);
  --jt-shadow-lg: 0 20px 50px rgba(99, 102, 241, 0.12);
  --jt-sidebar: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
  --jt-gradient: linear-gradient(135deg, #6366f1 0%, #a855f7 50%, #ec4899 100%);
  --jt-promo: linear-gradient(135deg, rgba(99,102,241,.12), rgba(168,85,247,.08));
  --jt-input-bg: #ffffff;
  --jt-st-header: rgba(255,255,255,.85);
}

html[data-theme="dark"] {
  --jt-bg: #0b1020;
  --jt-bg-elevated: #121829;
  --jt-bg-subtle: #171f35;
  --jt-bg-hover: #1a2238;
  --jt-border: rgba(148, 163, 184, 0.12);
  --jt-border-strong: rgba(148, 163, 184, 0.2);
  --jt-text: #f1f5f9;
  --jt-text-muted: #94a3b8;
  --jt-text-faint: #64748b;
  --jt-accent: #818cf8;
  --jt-accent-2: #c084fc;
  --jt-accent-soft: rgba(129, 140, 248, 0.14);
  --jt-success: #4ade80;
  --jt-success-soft: rgba(74, 222, 128, 0.12);
  --jt-warning: #fbbf24;
  --jt-danger: #f87171;
  --jt-link: #818cf8;
  --jt-shadow: 0 10px 40px rgba(0, 0, 0, 0.35);
  --jt-shadow-lg: 0 20px 50px rgba(99, 102, 241, 0.18);
  --jt-sidebar: linear-gradient(180deg, #0f1528 0%, #0b1020 100%);
  --jt-gradient: linear-gradient(135deg, #818cf8 0%, #c084fc 50%, #f472b6 100%);
  --jt-promo: linear-gradient(135deg, rgba(99,102,241,.18), rgba(168,85,247,.12));
  --jt-input-bg: #171f35;
  --jt-st-header: rgba(18, 24, 41, 0.9);
}
</style>
"""

_COMPONENT_CSS = """
<style>
/* ── Base layout ─────────────────────────────────────── */
html, body, [class*="css"] {
  font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, Roboto, "Helvetica Neue", sans-serif;
  color: var(--jt-text);
}

.stApp {
  background: var(--jt-bg) !important;
  color: var(--jt-text) !important;
}

.main .block-container {
  padding-top: 1.5rem !important;
  max-width: 1180px !important;
  animation: jtFadeIn 0.4s ease-out;
}

@keyframes jtFadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

/* ── Sidebar ─────────────────────────────────────────── */
section[data-testid="stSidebar"] {
  background: var(--jt-sidebar) !important;
  border-right: 1px solid var(--jt-border) !important;
}

section[data-testid="stSidebar"] > div {
  background: transparent !important;
}

section[data-testid="stSidebar"] .stMarkdown,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span {
  color: var(--jt-text) !important;
}

section[data-testid="stSidebar"] hr {
  border-color: var(--jt-border) !important;
  margin: 1rem 0 !important;
}

/* ── Brand + promo ───────────────────────────────────── */
.jt-brand {
  display: flex; align-items: center; gap: 12px;
  padding: 4px 0 12px;
}
.jt-brand__mark {
  width: 42px; height: 42px; border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
  font-weight: 800; font-size: .85rem; color: #fff;
  background: var(--jt-gradient);
  box-shadow: 0 8px 20px rgba(99, 102, 241, 0.35);
}
.jt-brand__title {
  font-size: 1.05rem; font-weight: 800; letter-spacing: -.02em;
  color: var(--jt-text);
}
.jt-brand__sub {
  font-size: .72rem; color: var(--jt-text-muted); font-weight: 600;
}
.jt-sidebar-context {
  display: inline-block; margin-bottom: 8px;
  padding: 4px 10px; border-radius: 999px;
  font-size: .72rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: .06em; color: var(--jt-accent);
  background: var(--jt-accent-soft); border: 1px solid var(--jt-border);
}

.jt-promo {
  border-radius: 16px; padding: 16px;
  background: var(--jt-promo);
  border: 1px solid var(--jt-border);
  margin-top: 8px;
}
.jt-promo__title {
  font-size: .82rem; font-weight: 800; margin-bottom: 6px;
  background: var(--jt-gradient);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  background-clip: text;
}
.jt-promo__body {
  font-size: .75rem; line-height: 1.45; color: var(--jt-text-muted);
}
.jt-promo__meta {
  margin-top: 8px; font-size: .65rem; color: var(--jt-text-faint);
  font-weight: 600;
}

/* ── Top bar ─────────────────────────────────────────── */
.jt-topbar { margin-bottom: 0; }
.jt-breadcrumb {
  font-size: .78rem; font-weight: 600; color: var(--jt-text-muted);
  margin-bottom: 4px;
}
.jt-page-title {
  font-size: 2rem !important; font-weight: 800 !important;
  letter-spacing: -.03em !important; margin: 0 !important;
  color: var(--jt-text) !important;
}
.jt-page-sub {
  margin: 6px 0 0; font-size: .95rem; color: var(--jt-text-muted);
}
.jt-topbar__label {
  font-size: .68rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: .08em; color: var(--jt-text-faint); margin-bottom: 6px;
}
.jt-topbar-spacer { height: 12px; }

.jt-status {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 12px; border-radius: 12px;
  font-size: .78rem; font-weight: 700;
  border: 1px solid var(--jt-border);
  background: var(--jt-bg-elevated);
}
.jt-status__dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: currentColor; box-shadow: 0 0 0 4px rgba(74, 222, 128, 0.15);
}
.jt-status--ok { color: var(--jt-success); }
.jt-status--warn { color: var(--jt-warning); }

/* ── Hero + sections ─────────────────────────────────── */
.home-hero {
  text-align: center; padding: 28px 20px 8px; margin-bottom: 8px;
}
.home-hero h1 {
  font-size: 2.6rem !important; font-weight: 800 !important;
  letter-spacing: -.04em; margin: 0 0 8px !important;
  background: var(--jt-gradient);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  background-clip: text;
}
.home-hero p {
  color: var(--jt-text-muted); font-size: 1.05rem; margin: 0;
}

.jt-section-label {
  font-size: .75rem; font-weight: 800; text-transform: uppercase;
  letter-spacing: .08em; color: var(--jt-text-faint); margin-bottom: 10px;
}

/* ── Main content readability (checkbox labels, markdown) ─ */
.main .block-container label,
.main .block-container label p,
.main .block-container label span,
.main .block-container [data-testid="stMarkdownContainer"] p,
.main .block-container [data-testid="stMarkdownContainer"] li {
  color: var(--jt-text) !important;
}

.main .block-container label span[data-testid="stMarkdownContainer"] p em,
.main .block-container label span[data-testid="stMarkdownContainer"] p {
  color: var(--jt-text-muted) !important;
}

.main [data-testid="stCheckbox"] label {
  color: var(--jt-text) !important;
}

/* ── Team cards ──────────────────────────────────────── */
.jt-team-card {
  border: 1px solid var(--jt-border); border-radius: 16px;
  padding: 18px; min-height: 96px; background: var(--jt-bg-elevated);
  transition: all .25s ease; box-shadow: var(--jt-shadow);
}
.jt-team-card:hover {
  transform: translateY(-2px); box-shadow: var(--jt-shadow-lg);
}
.jt-team-card--active {
  border-color: var(--jt-success);
  background: var(--jt-success-soft);
  box-shadow: 0 0 0 3px rgba(74, 222, 128, 0.12);
}
.jt-team-card__name {
  font-size: 1rem; font-weight: 800; color: var(--jt-text); margin-bottom: 4px;
}
.jt-team-card__meta {
  font-size: .78rem; color: var(--jt-text-muted); font-weight: 600;
}
.jt-badge-active {
  display: inline-block; margin-left: 6px;
  font-size: .62rem; font-weight: 800; color: var(--jt-success);
  background: var(--jt-success-soft); padding: 2px 8px; border-radius: 999px;
}

/* ── App launcher cards ──────────────────────────────── */
.jt-app-card {
  border: 1px solid var(--jt-border); border-radius: 20px;
  padding: 24px; margin-bottom: 8px;
  background: var(--jt-bg-elevated);
  box-shadow: var(--jt-shadow);
  transition: all .28s cubic-bezier(.4,0,.2,1);
  position: relative; overflow: hidden;
}
.jt-app-card::before {
  content: ""; position: absolute; top: 0; left: 0; right: 0; height: 4px;
  background: var(--card-accent, var(--jt-gradient)); opacity: .85;
}
.jt-app-card:hover {
  transform: translateY(-4px);
  box-shadow: var(--jt-shadow-lg);
  border-color: var(--jt-border-strong);
}
.jt-app-card__icon {
  width: 52px; height: 52px; border-radius: 14px;
  display: flex; align-items: center; justify-content: center;
  font-size: 1.5rem; margin-bottom: 14px;
  background: var(--jt-accent-soft);
  border: 1px solid var(--jt-border);
}
.jt-app-card__title {
  font-size: 1.12rem; font-weight: 800; letter-spacing: -.02em;
  color: var(--jt-text); margin-bottom: 4px;
}
.jt-app-card__subtitle {
  font-size: .72rem; font-weight: 800; text-transform: uppercase;
  letter-spacing: .06em; margin-bottom: 10px;
  color: var(--card-accent, var(--jt-accent));
}
.jt-app-card__desc {
  font-size: .88rem; line-height: 1.5; color: var(--jt-text-muted);
  margin-bottom: 12px; min-height: 42px;
}
.jt-app-card__meta {
  font-size: .72rem; font-weight: 700; color: var(--jt-text-faint);
}

/* ── Banners ─────────────────────────────────────────── */
.jt-banner {
  padding: 14px 18px; border-radius: 14px; margin-bottom: 18px;
  font-size: .88rem; border: 1px solid var(--jt-border);
  background: var(--jt-bg-elevated);
}
.jt-banner--info {
  border-color: rgba(99, 102, 241, 0.25);
  background: var(--jt-accent-soft);
}
.jt-banner--success {
  border-color: rgba(74, 222, 128, 0.25);
  background: var(--jt-success-soft);
}

/* ── Stepper ─────────────────────────────────────────── */
.stepper{display:flex;justify-content:center;align-items:center;gap:0;margin:0 auto 2rem;max-width:820px}
.stepper .step{display:flex;align-items:center;gap:0}
.stepper .circle{width:38px;height:38px;border-radius:50%;display:flex;align-items:center;
  justify-content:center;font-weight:700;font-size:.85rem;flex-shrink:0;transition:all .3s ease}
.stepper .circle.done{background:linear-gradient(135deg,#22c55e,#16a34a);color:#fff;
  box-shadow:0 4px 14px rgba(34,197,94,.35)}
.stepper .circle.active{background:var(--jt-gradient);color:#fff;
  box-shadow:0 0 0 4px var(--jt-accent-soft),0 4px 16px rgba(99,102,241,.35)}
.stepper .circle.pending{background:var(--jt-bg-subtle);color:var(--jt-text-faint);border:1px solid var(--jt-border)}
.stepper .label{font-size:.76rem;margin-left:8px;white-space:nowrap;font-weight:700;letter-spacing:-.01em}
.stepper .label.done{color:var(--jt-success)}
.stepper .label.active{color:var(--jt-accent)}
.stepper .label.pending{color:var(--jt-text-faint)}
.stepper .line{width:40px;height:2px;margin:0 8px;flex-shrink:0;border-radius:1px}
.stepper .line.done{background:linear-gradient(90deg,#22c55e,#16a34a)}
.stepper .line.pending{background:var(--jt-border)}

/* ── Streamlit widgets ───────────────────────────────── */
h2 { font-weight: 800 !important; letter-spacing: -.03em !important; color: var(--jt-text) !important; }
h3 { font-weight: 700 !important; color: var(--jt-text) !important; }

div[data-testid="stMetric"]{
  border: 1px solid var(--jt-border); border-radius: 16px;
  padding: 18px 20px; background: var(--jt-bg-elevated);
  box-shadow: var(--jt-shadow); transition: all .2s;
}
div[data-testid="stMetric"]:hover{
  border-color: var(--jt-border-strong); box-shadow: var(--jt-shadow-lg);
}

div[data-testid="stExpander"] {
  border-radius: 14px !important;
  border: 1px solid var(--jt-border) !important;
  background: var(--jt-bg-elevated) !important;
  overflow: hidden;
}

/*
 * Dark mode uses html[data-theme="dark"] while Streamlit widgets keep
 * config.toml base=light (white expander headers, dark label defaults).
 * Scope fixes to dark only — light mode rules above stay unchanged.
 */
html[data-theme="dark"] div[data-testid="stExpander"] summary,
html[data-theme="dark"] div[data-testid="stExpander"] details > summary,
html[data-theme="dark"] div[data-testid="stExpander"] > div > div:first-child {
  background: #f1f5f9 !important;
  color: #0f172a !important;
}

html[data-theme="dark"] div[data-testid="stExpander"] summary [data-testid="stMarkdownContainer"],
html[data-theme="dark"] div[data-testid="stExpander"] summary [data-testid="stMarkdownContainer"] p,
html[data-theme="dark"] div[data-testid="stExpander"] summary [data-testid="stMarkdownContainer"] strong,
html[data-theme="dark"] div[data-testid="stExpander"] > div > div:first-child [data-testid="stMarkdownContainer"],
html[data-theme="dark"] div[data-testid="stExpander"] > div > div:first-child [data-testid="stMarkdownContainer"] p,
html[data-theme="dark"] div[data-testid="stExpander"] > div > div:first-child
  [data-testid="stMarkdownContainer"] strong {
  color: #0f172a !important;
}

html[data-theme="dark"] div[data-testid="stExpander"] details[open] > div,
html[data-theme="dark"] div[data-testid="stExpander"] [data-testid="stExpanderDetails"],
html[data-theme="dark"] div[data-testid="stExpander"] > div > div:nth-child(2) {
  background: var(--jt-bg-elevated) !important;
  border-top: 1px solid var(--jt-border) !important;
}

html[data-theme="dark"] div[data-testid="stExpander"] [data-testid="stCheckbox"] label,
html[data-theme="dark"] div[data-testid="stExpander"] [data-testid="stCheckbox"] label p,
html[data-theme="dark"] div[data-testid="stExpander"] [data-testid="stCheckbox"] label span,
html[data-theme="dark"] div[data-testid="stExpander"] [data-testid="stCheckbox"] [data-testid="stMarkdownContainer"] p,
html[data-theme="dark"] div[data-testid="stExpander"] [data-testid="stCheckbox"]
  [data-testid="stMarkdownContainer"] strong {
  color: var(--jt-text) !important;
}

html[data-theme="dark"] div[data-testid="stExpander"] [data-testid="stCheckbox"]
  [data-testid="stMarkdownContainer"] p em {
  color: var(--jt-text-muted) !important;
}

html[data-theme="dark"] .main .block-container [data-testid="stCheckbox"] label,
html[data-theme="dark"] .main .block-container [data-testid="stCheckbox"] label p,
html[data-theme="dark"] .main .block-container [data-testid="stCheckbox"] label span,
html[data-theme="dark"] .main .block-container [data-testid="stCheckbox"] [data-testid="stMarkdownContainer"] p,
html[data-theme="dark"] .main .block-container [data-testid="stCheckbox"] [data-testid="stMarkdownContainer"] strong {
  color: var(--jt-text) !important;
}

html[data-theme="dark"] .main .block-container [data-testid="stCheckbox"] [data-testid="stMarkdownContainer"] p em {
  color: var(--jt-text-muted) !important;
}

button[data-testid="stBaseButton-primary"]{
  border-radius: 12px !important; font-weight: 700 !important;
  background: var(--jt-gradient) !important; border: none !important;
  transition: transform .15s, box-shadow .15s !important;
}
button[data-testid="stBaseButton-primary"]:hover{
  transform: translateY(-1px);
  box-shadow: 0 8px 24px rgba(99, 102, 241, 0.35) !important;
}
button[data-testid="stBaseButton-secondary"]{
  border-radius: 12px !important; font-weight: 600 !important;
  border: 1px solid var(--jt-border) !important;
  background: var(--jt-bg-elevated) !important;
  color: var(--jt-text) !important;
}

div[data-baseweb="select"] > div,
input[data-testid="stTextInputRootElement"] input,
div[data-testid="stTextArea"] textarea {
  border-radius: 12px !important;
  background: var(--jt-input-bg) !important;
  border-color: var(--jt-border) !important;
  color: var(--jt-text) !important;
}

.stAlert {
  border-radius: 14px !important;
  border: 1px solid var(--jt-border) !important;
}

.avatar{
  width: 38px; height: 38px; border-radius: 50%;
  display: inline-flex; align-items: center; justify-content: center;
  font-weight: 800; font-size: .82rem; color: #fff;
  background: var(--jt-gradient); flex-shrink: 0; margin-right: 10px;
}

.release-card{
  border: 1px solid var(--jt-border); border-radius: 16px; padding: 18px 20px;
  margin-bottom: 10px; background: var(--jt-bg-elevated);
  transition: all .2s;
}
.release-card.selected{
  border-color: var(--jt-accent);
  background: var(--jt-accent-soft);
  box-shadow: 0 0 0 3px var(--jt-accent-soft);
}

.success-banner, .error-banner, .review-card, .hist-item, .hist-detail-header {
  border-radius: 16px; border: 1px solid var(--jt-border);
  background: var(--jt-bg-elevated);
}

.review-card {
  padding: 18px 22px; margin-bottom: 10px;
  border-left: 4px solid var(--jt-accent);
  background: var(--jt-bg-subtle);
}
.review-card--added { border-left-color: var(--jt-success); }
.review-card--removed { border-left-color: var(--jt-danger); }
.review-card--changed { border-left-color: var(--jt-warning); }
.review-card--same { border-left-color: var(--jt-text-faint); }

.success-banner {
  padding: 28px 32px; text-align: center; margin: 10px 0 20px;
  background: linear-gradient(135deg, var(--jt-success-soft), transparent);
  border-color: rgba(74, 222, 128, 0.35);
}
.success-banner h2, .success-banner h3 {
  color: var(--jt-success) !important;
  margin: 0 0 8px !important;
}
.success-banner p { color: var(--jt-text-muted); margin: 0; font-size: .95rem; }
.success-banner a { color: var(--jt-success); font-weight: 700; text-decoration: none; }
.success-banner a:hover { text-decoration: underline; }

.stk-created-banner {
  padding: 28px 32px; border-radius: 18px; margin: 16px 0;
  text-align: center;
  background: linear-gradient(135deg, var(--jt-success-soft), transparent);
  border: 2px solid rgba(74, 222, 128, 0.4);
  box-shadow: var(--jt-shadow);
}
.stk-created-banner__icon {
  font-size: 2.5rem; line-height: 1; margin-bottom: 12px;
}
.stk-created-banner h2 {
  margin: 0 0 8px 0 !important; color: var(--jt-success) !important;
}
.stk-created-banner p { color: var(--jt-text-muted); margin: 0; }
.stk-created-banner a {
  color: var(--jt-success); font-weight: 700; text-decoration: none;
}
.stk-created-banner a:hover { text-decoration: underline; }

.error-banner {
  padding: 28px 32px; text-align: center; margin: 10px 0 20px;
  background: linear-gradient(135deg, rgba(248, 113, 113, 0.12), transparent);
  border-color: rgba(248, 113, 113, 0.35);
}
.error-banner h2, .error-banner h3 {
  color: var(--jt-danger) !important;
  margin: 0 0 8px !important;
}
.error-banner p { color: var(--jt-text-muted); margin: 0; font-size: .95rem; }
.error-banner--warn h3 { color: var(--jt-warning) !important; }
.error-banner--warn {
  background: linear-gradient(135deg, rgba(251, 191, 36, 0.12), transparent);
  border-color: rgba(251, 191, 36, 0.35);
}

.stk-error-panel {
  padding: 14px 18px; border-radius: 12px; margin: 8px 0;
  background: rgba(248, 113, 113, 0.15);
  border: 1px solid rgba(248, 113, 113, 0.45);
  color: var(--jt-text);
}
.stk-error-panel strong { color: var(--jt-danger); }

.paste-hint {
  border: 2px dashed var(--jt-border-strong);
  border-radius: 14px; padding: 18px 22px; text-align: center;
  margin-bottom: 16px; color: var(--jt-text-muted);
  font-size: .9rem; background: var(--jt-bg-subtle);
}

.hist-item {
  padding: 10px 14px; margin-bottom: 8px;
  transition: all .2s; cursor: pointer;
}
.hist-item:hover {
  border-color: var(--jt-accent) !important;
  background: var(--jt-accent-soft) !important;
  transform: translateX(2px);
}
.hist-item .hi-title { font-weight: 600; font-size: .88rem; margin: 0; color: var(--jt-text); }
.hist-item .hi-meta { font-size: .72rem; color: var(--jt-text-faint); margin: 2px 0 0; }
.hist-item .hi-stats { font-size: .75rem; margin: 4px 0 0; color: var(--jt-text-muted); }

.hist-detail-header { padding: 28px 32px; margin-bottom: 20px; }

.hist-client-card {
  padding: 18px 22px; margin-bottom: 10px;
  border-left: 4px solid var(--jt-accent);
  background: var(--jt-bg-subtle);
}

a.jt-link, .jt-link {
  color: var(--jt-link) !important;
  text-decoration: none;
  font-weight: 600;
}
a.jt-link:hover { text-decoration: underline; opacity: .92; }

.jt-diff-added { color: var(--jt-success) !important; font-weight: 600; }
.jt-diff-removed { color: var(--jt-danger) !important; font-weight: 600; }
.jt-diff-changed { color: var(--jt-warning) !important; font-weight: 600; }
.jt-diff-same { color: var(--jt-text-muted) !important; }

.jt-table {
  width: 100%; border-collapse: collapse; font-size: .85rem; margin: 8px 0;
}
.jt-table th {
  text-align: left; padding: 8px 10px;
  border-bottom: 2px solid var(--jt-border-strong);
  font-weight: 700; color: var(--jt-text);
}
.jt-table td {
  padding: 6px 10px; color: var(--jt-text);
  border-bottom: 1px solid var(--jt-border);
}
.jt-table tr.jt-table__group-start td {
  border-top: 2px solid var(--jt-border-strong);
}

html[data-theme="dark"] div[data-testid="stAlert"] {
  background: var(--jt-bg-elevated) !important;
  color: var(--jt-text) !important;
}
html[data-theme="dark"] div[data-testid="stAlert"] p,
html[data-theme="dark"] div[data-testid="stAlert"] span {
  color: var(--jt-text) !important;
}

html[data-theme="dark"] [data-testid="stCodeBlock"],
html[data-theme="dark"] pre {
  background: var(--jt-bg-subtle) !important;
  color: var(--jt-text) !important;
  border: 1px solid var(--jt-border) !important;
}

html[data-theme="dark"] [data-baseweb="tab-list"] button {
  color: var(--jt-text-muted) !important;
}
html[data-theme="dark"] [data-baseweb="tab-list"] button[aria-selected="true"] {
  color: var(--jt-text) !important;
  border-bottom-color: var(--jt-accent) !important;
}

html[data-theme="dark"] .stDataFrame, html[data-theme="dark"] [data-testid="stDataFrame"] {
  color: var(--jt-text) !important;
}

#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
header[data-testid="stHeader"] {
  background: var(--jt-st-header) !important;
  backdrop-filter: blur(10px);
  border-bottom: 1px solid var(--jt-border);
}
</style>
"""


def get_design_css() -> str:
    return _DESIGN_TOKENS + _COMPONENT_CSS


CUSTOM_CSS = get_design_css()


@st.cache_resource
def _get_cached_css() -> str:
    return get_design_css()


def inject_design_system() -> None:
    """Inject CSS + theme bootstrap (once per session)."""
    if not st.session_state.get("_design_injected"):
        st.markdown(_get_cached_css(), unsafe_allow_html=True)
        st.session_state["_design_injected"] = True


def status_badge(status_name: str, category_key: str) -> str:
    bg, _ = _STATUS_COLORS.get(category_key, _STATUS_COLORS["new"])
    return (
        f'<span style="display:inline-block;padding:3px 10px;border-radius:999px;'
        f'font-size:.72rem;font-weight:700;background:{bg}22;color:{bg};'
        f'border:1px solid {bg}44;">{status_name}</span>'
    )


def render_stepper(current: int, labels: list[str] | None = None) -> None:
    step_labels = labels if labels is not None else _STEP_LABELS
    parts: list[str] = []
    for i, label in enumerate(step_labels):
        step_num = i + 1
        if step_num < current:
            cls = "done"
            icon = "\u2713"
        elif step_num == current:
            cls = "active"
            icon = str(step_num)
        else:
            cls = "pending"
            icon = str(step_num)
        parts.append(
            f'<div class="step"><div class="circle {cls}">{icon}</div>'
            f'<span class="label {cls}">{label}</span></div>'
        )
        if step_num < len(step_labels):
            line_cls = "done" if step_num < current else "pending"
            parts.append(f'<div class="line {line_cls}"></div>')
    st.markdown(
        f'<nav aria-label="Wizard progress"><div class="stepper">{"".join(parts)}</div></nav>',
        unsafe_allow_html=True,
    )

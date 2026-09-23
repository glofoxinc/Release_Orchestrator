# Contributing to Release Orchestrator

Thank you for your interest in improving Release Orchestrator! This guide covers everything you need to get started.

## Prerequisites

- **Python 3.10+**
- **Git**
- A Jira Cloud instance with an [API token](https://id.atlassian.com/manage-profile/security/api-tokens)
- (Optional) **Docker** for containerised development

## Setup

### 1. Clone and create a virtual environment

```bash
git clone <repo-url> jira-toolkit
cd jira-toolkit
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure credentials

Copy the example environment file and fill in your Jira details:

```bash
cp .env.example .env
```

| Variable | Description |
|----------|-------------|
| `JIRA_BASE_URL` | Your Jira Cloud URL, e.g. `https://yourorg.atlassian.net` |
| `JIRA_EMAIL` | Email address linked to your Atlassian account |
| `JIRA_API_TOKEN` | Personal API token (never commit this) |

### 3. Verify the installation

```bash
streamlit run app.py
```

Open `http://localhost:8501` — you should see the Home page.

## Testing

All tests live in the `tests/` directory and use **pytest**.

```bash
# Run the full suite
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ --cov --cov-report=term-missing
```

Every pull request must keep the existing tests green. Add new tests for any new functionality.

## Linting — Ruff

The project uses [Ruff](https://docs.astral.sh/ruff/) for linting and import sorting.

```bash
# Check for issues
ruff check .

# Auto-fix what's possible
ruff check . --fix
```

Ruff configuration lives in `pyproject.toml` under `[tool.ruff]`. CI runs `ruff check .` on every push.

## Docker Workflow

Build and run the toolkit in a container:

```bash
docker-compose up -d          # build + start
docker-compose logs -f        # tail logs
docker-compose down           # stop
```

The container mounts `.env`, `workspace.yaml`, `workspaces/`, and `templates/` from the host so you can iterate without rebuilding.

## Multi-Workspace Support

The toolkit supports multiple team configurations from a single installation:

```
workspaces/
  team-a/workspace.yaml
  team-b/workspace.yaml
```

- The root `workspace.yaml` is the default workspace.
- Sub-workspaces live under `workspaces/<folder>/workspace.yaml`.
- Switch workspaces via the sidebar dropdown or the `JIRA_TOOLKIT_WORKSPACE` environment variable.
- Use `config.list_workspaces()` and `config.switch_workspace(name)` in code.

When adding a feature, make sure it respects the active workspace returned by `config.get_active_workspace_path()`.

## Template Customization

Generated text (deployment comments, plans, etc.) is driven by Jinja2 templates:

```
templates/
  default/           # built-in templates (don't edit directly)
  deployment_comment.j2
  review_format.j2
  ...
```

The engine checks `templates/` first, then falls back to `templates/default/`. To customise output, copy a default template to the top-level `templates/` directory and modify it there.

When adding new generated text, create a default template and register it in `template_engine.py`.

## Pull Request Checklist

- [ ] All existing tests pass (`python -m pytest tests/ -v`)
- [ ] New functionality has corresponding tests
- [ ] `ruff check .` reports no errors
- [ ] `workspace.yaml` schema changes are documented
- [ ] Commit messages are concise and describe *why*, not just *what*

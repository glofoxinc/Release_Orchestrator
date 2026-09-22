# Observability — jira-release-tool

## Log format

- Default: human-readable `%(asctime)s [%(levelname)s] %(name)s: %(message)s`.
- JSON: set `LOG_FORMAT=json` to emit one JSON record per line. Useful when
  deploying the Streamlit app inside a container where stdout is parsed by a
  log collector.

The shared `common/logger.py` provides `setup_logging()` and a
`JsonFormatter` compatible with the rest of the Cursor workspace's Python
tools. Streamlit (`app.py`) and the MCP server (`mcp_server/server.py`) both
call `setup_logging` at startup.

### Redaction and correlation

- A `RedactingFilter` masks Slack bot tokens (`xox*`), Bearer/Basic auth, and
  known `*_TOKEN` / `*_API_KEY` assignments in message text.
- `set_log_context(workflow_id=..., release_id=..., **extra)` attaches safe
  correlation fields; keys containing `token` / `password` / `secret` are
  dropped so credentials never land in context.

## Log levels

`DEBUG`, `INFO` (default), `WARNING`, `ERROR`, `CRITICAL`.

```powershell
$env:LOG_LEVEL = "DEBUG"
$env:LOG_FORMAT = "json"
streamlit run app.py
```

## Health check endpoint

Not applicable — Streamlit app. Streamlit itself exposes `/_stcore/health`
when you need a liveness probe for the container platform.

## Metrics endpoint

Not exposed. The tool is internal and writes its own
`.deployment_history.json` for auditability; extend it with Prometheus only
if we start hosting the app for multiple users.

## Where logs go

- `streamlit run`: stdout.
- `launcher.pyw` / `launch.vbs`: the wrapper redirects to a log file —
  check `%USERPROFILE%\Cursor\projects\jira-release-tool\*.log`.
- Docker: stdout, collected by Docker.

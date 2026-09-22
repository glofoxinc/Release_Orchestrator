# Versioning

This project follows [Semantic Versioning 2.0.0](https://semver.org/).

## Version format

```
MAJOR.MINOR.PATCH
```

| Segment | When to bump | Example |
|---|---|---|
| **MAJOR** | Incompatible API / behaviour change that breaks existing callers, configs, or integrations | `1.4.2 -> 2.0.0` |
| **MINOR** | New functionality added in a backward-compatible way | `1.4.2 -> 1.5.0` |
| **PATCH** | Backward-compatible bug fixes, docs, or internal cleanup | `1.4.2 -> 1.4.3` |

Pre-release and build metadata are permitted (`1.5.0-rc.1`, `1.5.0+build.42`) but reserved for release candidates and internal builds only.

## Git tags

Every release is tagged in git as `vMAJOR.MINOR.PATCH`:

```bash
git tag -a v1.2.3 -m "Release v1.2.3"
git push origin v1.2.3
```

Pushing a tag matching `v*` triggers the `Release` GitHub Actions workflow (`.github/workflows/release.yml`) which builds artifacts and creates a GitHub Release with auto-generated notes. The `Docker` workflow (`.github/workflows/docker.yml`) builds container images tagged `{{version}}`, `{{major}}.{{minor}}`, and `sha-<commit>` on the same trigger.

## Release process

1. **Update `CHANGELOG.md`** - move items from `## [Unreleased]` into a new `## [X.Y.Z] - YYYY-MM-DD` section. Keep the Keep-a-Changelog format: `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`.
2. **Bump the version**
   - Python: `pyproject.toml` -> `[project] version = "X.Y.Z"`
   - Node: `package.json` -> `"version": "X.Y.Z"` (or `npm version patch|minor|major`)
3. **Commit** with message `Release vX.Y.Z` on `main`.
4. **Tag** locally: `git tag -a vX.Y.Z -m "Release vX.Y.Z"`.
5. **Push** the commit and tag: `git push && git push origin vX.Y.Z`.
6. **CI** (`release.yml`) builds distributions, publishes a GitHub Release, and (when tokens are configured) publishes to PyPI / npm / Docker Hub.
7. **Verify** the GitHub Release page, installer smoke-test (`pip install` / `npm install`), and Docker image pull.

## Breaking change checklist

Before bumping MAJOR:

- [ ] Public API change is documented in `CHANGELOG.md` under `Changed` or `Removed`
- [ ] Migration guide for downstream consumers is published (README or `docs/MIGRATION.md`)
- [ ] Deprecated APIs were announced at least one MINOR release earlier, where feasible
- [ ] Existing integrations (Jira release tickets, TCKT deployment tickets, internal Power BI dashboards consuming this package) have been notified

## Hotfixes

For urgent production fixes from an older MAJOR line:

1. Branch from the tag: `git checkout -b hotfix/vX.Y.Z+1 vX.Y.Z`
2. Apply the fix, bump PATCH, update `CHANGELOG.md`.
3. Tag `vX.Y.(Z+1)` and push.
4. Merge fix back into `main` to prevent regression.

## See also

- [`CHANGELOG.md`](../CHANGELOG.md) - historical changes
- [`.github/workflows/release.yml`](../.github/workflows/release.yml) - release pipeline
- [`.github/workflows/docker.yml`](../.github/workflows/docker.yml) - container pipeline (if present)
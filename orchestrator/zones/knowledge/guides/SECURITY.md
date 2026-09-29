# Security Policy

## Supported Versions
The latest minor release is supported.

## Reporting a Vulnerability
Please report security vulnerabilities privately to the maintainers.
Do not open public issues for security bugs.

Expected response time: 48 hours.

## Security Practices
- No secrets committed to git (scanned via gitleaks)
- Dependencies scanned weekly (GitHub Actions)
- All API endpoints require authentication (where applicable)
- Rate limiting enabled on public endpoints
- Input validation on all user-supplied data

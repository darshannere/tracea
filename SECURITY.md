# Security Policy

## Reporting a Vulnerability

If you discover a security issue, please **do not open a public issue**.

Instead, email **darshan.nere2@gmail.com** with:
- A description of the vulnerability
- Steps to reproduce
- Potential impact
- Any suggested fixes

We aim to respond within 48 hours and will work with you to validate and fix the issue before any public disclosure.

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | ✅         |

## Security Best Practices

- Rotate your `TRACEA_API_KEY` regularly
- Use `TRACEA_RCA_REDACT_CONTENT=true` to prevent sensitive data from being sent to third-party LLM APIs
- Run tracea behind a reverse proxy (e.g., nginx, Caddy) with TLS in production
- Keep your SQLite database file (`TRACEA_DB_PATH`) on a secure volume with appropriate file permissions

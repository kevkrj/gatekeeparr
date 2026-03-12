# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | Yes                |

## Reporting a Vulnerability

If you discover a security vulnerability in Gatekeeparr, please report it responsibly.

**Do not open a public GitHub issue for security vulnerabilities.**

Instead, please email **kevin@jonesfamily.club** with:

- A description of the vulnerability
- Steps to reproduce the issue
- Potential impact
- Suggested fix (if any)

You should receive a response within 48 hours. We will work with you to understand the issue and coordinate a fix before any public disclosure.

## Security Considerations

Gatekeeparr handles API keys and authentication tokens for several services. When deploying:

- **Never commit `.env` files** or API keys to version control
- Use the `docker-compose.override.yml` pattern (gitignored) for local configuration
- Enable the `WEBHOOK_SECRET` option to authenticate incoming webhooks
- Run the container on a trusted network; the admin panel should not be exposed to the public internet without additional authentication (e.g., reverse proxy with SSO)
- API keys are stored in environment variables, not in the database
- Session cookies are configured with `HttpOnly` and `SameSite=Lax` flags

## Scope

The following are in scope for security reports:

- Authentication bypass
- Unauthorized access to API endpoints
- Injection vulnerabilities (SQL, XSS, command injection)
- Exposure of API keys or credentials
- Webhook spoofing

The following are out of scope:

- Denial of service on a local-only deployment
- Issues requiring physical access to the host
- Vulnerabilities in upstream dependencies (report those to the respective projects)

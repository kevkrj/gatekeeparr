# Contributing to Gatekeeparr

All help is welcome and greatly appreciated! If you would like to contribute to the project, the following instructions should get you started.

## AI Assistance Notice

> **Important:** If you are using any kind of AI assistance while contributing to Gatekeeparr, this must be disclosed in the pull request, along with the extent to which AI assistance was used (e.g., docs only vs. code generation).

We welcome AI-assisted contributions, but we expect contributors to understand the code that is produced and be able to answer questions about it. Unreviewed AI-generated submissions will be rejected.

## Development

### Tools Required

- [Python](https://www.python.org/) 3.11+
- [Docker](https://www.docker.com/) and Docker Compose
- [Git](https://git-scm.com/downloads)

### Getting Started

1. [Fork](https://help.github.com/articles/fork-a-repo/) the repository to your own GitHub account and [clone](https://help.github.com/articles/cloning-a-repository/) it to your local device:

   ```bash
   git clone https://github.com/YOUR_USERNAME/gatekeeparr.git
   cd gatekeeparr/
   ```

2. Add the remote `upstream`:

   ```bash
   git remote add upstream https://github.com/kevkrj/gatekeeparr.git
   ```

3. Create a new branch:

   ```bash
   git switch -c BRANCH_NAME main
   ```

   Give your branch a meaningful name relevant to the feature or fix:
   - Good: `fix-seerr-sync`, `feature-plex-auth`, `docs-setup-guide`
   - Bad: `fix`, `update`, `patch`

4. Copy the example environment file and configure it:

   ```bash
   cp .env.example .env
   # Edit .env with your service URLs and API keys
   ```

5. Run the development environment:

   ```bash
   docker compose up -d --build
   ```

   Or run locally without Docker:

   ```bash
   pip install -r requirements.txt
   python -m gatekeeper.app
   ```

6. Create your patch and test your changes.

   To update your fork from upstream:

   ```bash
   git fetch upstream
   git rebase upstream/main
   git push origin BRANCH_NAME -f
   ```

### Contributing Code

- If you are taking on an existing bug or feature ticket, please comment on the [issue](../../issues) to avoid duplicate work.
- Please make meaningful commits with clear messages.
- Rebase your branch on the latest `main` before opening a pull request.
- Your code should not introduce security vulnerabilities (see [SECURITY.md](SECURITY.md)).
- Test your changes with the services you have available (Jellyseerr/Seerr, Radarr, Sonarr).
- Only open pull requests to `main`.

### Project Structure

```
gatekeeparr/
├── gatekeeper/
│   ├── admin/           # Admin panel (templates, static assets)
│   ├── api/             # REST API endpoints
│   ├── models/          # SQLAlchemy models
│   ├── services/        # External service clients (Seerr, Radarr, Sonarr, AI)
│   └── webhooks/        # Webhook handlers
├── scripts/             # Utility scripts
├── docker-compose.yml
└── requirements.txt
```

### Adding a New AI Provider

Gatekeeparr supports multiple AI backends. To add a new provider:

1. Create a new class in `gatekeeper/services/` implementing the analyzer interface.
2. Register it in the analyzer factory (`gatekeeper/services/analyzer.py`).
3. Add configuration fields to `gatekeeper/config.py`.
4. Update the setup wizard and `.env.example`.

### Adding a New Notification Provider

1. Add the notification logic in `gatekeeper/services/notifications.py`.
2. Add configuration fields to `gatekeeper/config.py`.
3. Update the setup wizard step 4 and `.env.example`.

## Reporting Bugs

Please use [GitHub Issues](../../issues) to report bugs. Include:

- Steps to reproduce the issue
- Expected vs. actual behavior
- Relevant logs (`docker logs gatekeeper`)
- Your environment (Docker version, OS, Seerr/Jellyseerr version)

## Feature Requests

Feature requests are welcome! Please open a [GitHub Issue](../../issues) describing:

- The problem you're trying to solve
- Your proposed solution
- Any alternatives you've considered

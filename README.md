# Gatekeeparr

**Parental content gating for the *arr stack**

Gatekeeparr is an open-source content filtering and approval system for home media servers. It integrates with **Jellyseerr/Seerr, Radarr, and Sonarr** to automatically analyze content and route requests based on user type and content ratings.

Works with **Jellyfin, Plex, and Emby** — any media server supported by Jellyseerr or Seerr.

## Why Gatekeeparr?

Nothing else in the *arr ecosystem handles parental content filtering with nuance. Jellyseerr lets you block ratings globally, but that's all-or-nothing. Gatekeeparr gives you:

- **Context, not just ratings** — A PG-13 superhero movie is different from a PG-13 war film
- **AI-powered analysis** — Explains *why* content might be concerning, not just *that* it's rated PG-13
- **Common Sense Media integration** — Real age recommendations and detailed content breakdowns
- **Per-user routing** — Kids get reviewed, adults auto-approve
- **Three-tier rating control** — Configure auto-approve, needs-approval, and auto-deny ceilings per user
- **Interactive approvals** — Approve/deny from your phone via Mattermost or Discord

## Features

- **AI-Powered Content Analysis**: Uses LLMs to analyze content for parental concerns
  - Supports Claude (Anthropic), Ollama (local), OpenAI, and Grok
- **Three-Tier Rating System**: Per-user configurable thresholds
  - Auto-approve up to a rating (e.g., PG)
  - Hold for approval up to a rating (e.g., R)
  - Auto-deny above the approval ceiling
- **User-Aware Routing**: Different rules for kids, teens, and adults
- **Pluggable Notifications**: Mattermost, Discord, or any webhook
- **Interactive Approvals**: Approve/Deny buttons in notifications
- **Admin Panel**: Web UI for managing users, requests, and approvals
- **Request Sync**: Automatically cleans up stale requests when content is removed from Seerr
- **Jellyfin Authentication**: Log in with your Jellyfin account (via Seerr)
- **Setup Wizard**: First-run configuration through the browser

## Architecture

```
┌─────────────────┐      ┌─────────────────┐
│ Jellyseerr/Seerr│────> │   Gatekeeparr   │
│  (User Request) │      │   (Analysis)    │
└─────────────────┘      └────────┬────────┘
                                  │
          ┌───────────────────────┼───────────────────────┐
          │                       │                       │
     ┌────▼────┐            ┌─────▼─────┐           ┌─────▼─────┐
     │  Admin  │            │   Adult   │           │   Kid     │
     │  Auto   │            │   Auto    │           │  Analyze  │
     └─────────┘            └───────────┘           └─────┬─────┘
                                                          │
                                                ┌────────┴────────┐
                                                │                 │
                                          ┌─────▼──────┐    ┌─────▼──────┐
                                          │ ≤ Max Auto │    │ > Max Auto │
                                          │  Approve   │    │            │
                                          └────────────┘    └─────┬──────┘
                                                                  │
                                                         ┌────────┴────────┐
                                                         │                 │
                                                   ┌─────▼──────┐    ┌─────▼──────┐
                                                   │ ≤ Approval │    │ > Approval │
                                                   │  Ceiling   │    │  Ceiling   │
                                                   │   HOLD     │    │ AUTO-DENY  │
                                                   └────────────┘    └────────────┘
```

### Request Flow

1. **User requests** content in Jellyseerr/Seerr
2. **Webhook fires** to Gatekeeparr with request details
3. **Gatekeeparr identifies** the user and looks up their rating thresholds
4. **TMDB rating** is fetched for the content
5. **Routing decision**:
   - Rating at or below **auto-approve ceiling** → approved in Seerr
   - Rating above auto-approve but at or below **approval ceiling** → held, AI analysis runs, parent notified
   - Rating above **approval ceiling** → auto-denied in Seerr
6. **Parent approves/denies** via Mattermost, Discord, or the admin panel
7. **Seerr forwards** approved requests to Radarr/Sonarr for download

### Approval Notifications

When content is held for review, the parent receives a notification:

```
┌─────────────────────────────────────────────┐
│    Content Request Held                     │
│                                             │
│ [Movie Name] [(RATING)]                     │
│ [Age Reccomendation] [One line content]     │
│ Requested by: [User]                        │
│                                             │
│ AI Analysis:                                │
│ • Strong violence and gore                  │
│ • Pervasive language                        │
│ • Adult humor throughout                    │
│                                             │
│ [  Approve  ]  [  Deny  ]                   │
└─────────────────────────────────────────────┘
```

## Quick Start

### 1. Clone and Configure

```bash
git clone https://github.com/kevkrj/gatekeeparr.git && cd gatekeeparr
cp .env.example .env
# Edit .env with your API keys and URLs
```

### 2. Deploy with Docker

```bash
docker compose up -d
```

### 3. Configure Webhooks

**Jellyseerr or Seerr** (required):
Settings → Notifications → Webhook
- Webhook URL: `http://<gatekeeparr-ip>:5023/webhook/jellyseerr` (or `/webhook/seerr`)
- Notification Types: Enable **Media Requested** (MEDIA_PENDING)
- JSON Payload: Use default template

> **Note:** Seerr is the successor to Jellyseerr and Overseerr, supporting Jellyfin, Plex, and Emby. Gatekeeparr works with both — just point `JELLYSEERR_URL` at whichever you run.

**Radarr** (optional — for kids library symlinks):
Settings → Connect → Add → Webhook
- URL: `http://<gatekeeparr-ip>:5023/webhook/radarr`
- Events: On Import (Download)

**Sonarr** (optional — for kids library symlinks):
Settings → Connect → Add → Webhook
- URL: `http://<gatekeeparr-ip>:5023/webhook/sonarr`
- Events: On Import (Download)

### 4. Set Up Users

Visit the admin panel at `http://<gatekeeparr-ip>:5023/admin` and log in with your Jellyfin or Seerr credentials.

Users can be managed through the admin panel UI, or via CLI:

```bash
# Add admin user
docker exec gatekeeper python /app/scripts/add_user.py parent admin - admin

# Add kid (auto-approve up to PG)
docker exec gatekeeper python /app/scripts/add_user.py child1 kid PG child1

# Add teen (auto-approve up to PG-13)
docker exec gatekeeper python /app/scripts/add_user.py teen1 teen PG-13 teen1

# Add adult
docker exec gatekeeper python /app/scripts/add_user.py adult1 adult - adult1
```

**Important:** The username must match what Jellyseerr/Seerr sends in webhooks (case-insensitive).

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GATEKEEPER_SECRET_KEY` | Session secret (change in production!) | `change-me-in-production` |
| `GATEKEEPER_URL` | External URL for notification callbacks | `http://localhost:5000` |
| `AI_PROVIDER` | AI backend: `claude`, `ollama`, `openai`, `grok` | `claude` |
| `AI_API_KEY` | API key for AI provider | required |
| `AI_MODEL` | Override default model | provider default |
| `AI_BASE_URL` | Custom API URL (for Ollama) | provider default |
| `JELLYSEERR_URL` | Jellyseerr/Seerr base URL | `http://localhost:5055` |
| `JELLYSEERR_API_KEY` | Jellyseerr/Seerr API key | required |
| `RADARR_URL` | Radarr base URL | `http://localhost:7878` |
| `RADARR_API_KEY` | Radarr API key | required |
| `SONARR_URL` | Sonarr base URL | `http://localhost:8989` |
| `SONARR_API_KEY` | Sonarr API key | required |
| `TMDB_API_KEY` | TMDB API key (for rating lookups) | optional |
| `WEBHOOK_SECRET` | Shared secret for webhook authentication | optional |
| `MATTERMOST_WEBHOOK` | Mattermost incoming webhook URL | optional |
| `DISCORD_WEBHOOK` | Discord webhook URL | optional |

### AI Providers

**Claude (Recommended)**
```env
AI_PROVIDER=claude
AI_API_KEY=sk-ant-xxx
AI_MODEL=claude-sonnet-4-20250514
```

**Ollama (Local/Free)**
```env
AI_PROVIDER=ollama
AI_BASE_URL=http://localhost:11434
AI_MODEL=llama3.2
```

**OpenAI**
```env
AI_PROVIDER=openai
AI_API_KEY=sk-xxx
AI_MODEL=gpt-4o-mini
```

**Grok**
```env
AI_PROVIDER=grok
AI_API_KEY=xxx
AI_MODEL=grok-2-latest
```

## User Types & Rating Tiers

Each user has three configurable rating thresholds:

| Setting | Description |
|---------|-------------|
| **Auto-Approve** | Requests at or below this rating are approved automatically |
| **Approval Ceiling** | Requests above auto-approve but at or below this are held for parent review |
| **Auto-Deny** | Anything above the approval ceiling is automatically denied |

### Default Thresholds

| Type | Auto-Approve | Approval Ceiling | Auto-Deny |
|------|--------------|------------------|-----------|
| `admin` | No limit | — | — |
| `adult` | No limit | — | NC-17/X |
| `teen` | PG-13 / TV-14 | R / TV-MA | NC-17/X |
| `kid` | PG / TV-PG | PG-13 / TV-14 | R+ |

All thresholds are configurable per-user through the admin panel.

## API Endpoints

### Webhooks

| Endpoint | Description |
|----------|-------------|
| `POST /webhook/jellyseerr` | Jellyseerr/Seerr webhook handler |
| `POST /webhook/seerr` | Alias for above |
| `POST /webhook/radarr` | Radarr download webhook (kids library symlinks) |
| `POST /webhook/sonarr` | Sonarr download webhook (kids library symlinks) |
| `POST /action` | Notification button callback |

### Admin API (requires authentication)

| Endpoint | Description |
|----------|-------------|
| `GET /api/requests` | List all requests (filterable) |
| `GET /api/requests/:id` | Get request details |
| `POST /api/requests/:id/approve` | Approve a held request |
| `POST /api/requests/:id/deny` | Deny a held request |
| `POST /api/requests/sync` | Sync requests with Seerr |
| `GET /api/users` | List users |
| `PUT /api/users/:id` | Update user settings |
| `POST /api/users/sync` | Sync users from Seerr |
| `GET /api/stats` | Dashboard statistics |
| `GET /api/approvals` | Approval history |

### Utility

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Health check |
| `GET /test` | Test AI integration |
| `GET /test/connections` | Test all service connections |

## Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run development server
python -m gatekeeper.app
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for full development setup and guidelines.

## Roadmap

- [x] Core webhook handlers (Jellyseerr/Seerr, Radarr, Sonarr)
- [x] AI content analysis (Claude, Ollama, OpenAI, Grok)
- [x] User-based routing with configurable thresholds
- [x] Three-tier rating system (auto-approve / needs-approval / auto-deny)
- [x] Mattermost & Discord notifications with approve/deny buttons
- [x] Request tracking and audit trail
- [x] Kids libraries (symlink-based)
- [x] Admin panel UI with dashboard
- [x] Jellyfin / Seerr authentication
- [x] First-run setup wizard
- [x] Request sync with Seerr (cleanup stale requests)
- [ ] ntfy.sh mobile push notifications

## Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT License — see [LICENSE](LICENSE).

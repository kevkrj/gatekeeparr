# Gatekeeparr

**Parental content gating for the *arr stack**

Gatekeeparr is an open-source content filtering and approval system for home media servers. It integrates with Jellyseerr, Radarr, and Sonarr to automatically analyze content and route requests based on user type and content ratings.

## Why Gatekeeparr?

Nothing else in the *arr ecosystem handles parental content filtering with nuance. Jellyseerr lets you block ratings globally, but that's all-or-nothing. Gatekeeparr gives you:

- **Context, not just ratings** - A PG-13 superhero movie is different from a PG-13 war film
- **AI-powered analysis** - Explains *why* content might be concerning, not just *that* it's rated PG-13
- **Common Sense Media integration** - Real age recommendations (12+, 15+) and detailed content breakdowns
- **Per-user routing** - Kids get reviewed, adults auto-approve
- **Interactive approvals** - Approve/deny from your phone via Mattermost or Discord

## Features

- **AI-Powered Content Analysis**: Uses LLMs to analyze content for parental concerns
  - Supports Claude (Anthropic), Ollama (local), OpenAI, and Grok
- **User-Aware Routing**: Different rules for kids, teens, and adults
  - Kids: Auto-approve G/PG/TV-PG, hold PG-13/TV-14, block R/TV-MA
  - Teens: Auto-approve up to PG-13/TV-14, hold R/TV-MA
  - Adults: Auto-approve everything
- **Pluggable Notifications**: Mattermost, Discord, or any webhook
- **Interactive Approvals**: Approve/Deny buttons in notifications
- **Request Tracking**: Full audit trail of all requests and decisions
- **Blocked Content**: Automatically block NC-17/X-rated content

## Architecture

```
┌─────────────────┐     ┌─────────────────┐
│   Jellyseerr    │────▶│   Gatekeeparr    │
│  (User Request) │     │   (Analysis)    │
└─────────────────┘     └────────┬────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         │                       │                       │
    ┌────▼────┐            ┌─────▼─────┐           ┌─────▼─────┐
    │  Admin  │            │   Adult   │           │   Kid     │
    │ Auto ✓  │            │  Auto ✓   │           │  Analyze  │
    └────┬────┘            └─────┬─────┘           └─────┬─────┘
         │                       │                       │
         │                       │              ┌────────┴────────┐
         │                       │              │                 │
         │                       │         ┌────▼────┐      ┌─────▼─────┐
         │                       │         │  G/PG   │      │  PG-13+   │
         │                       │         │ Auto ✓  │      │   HOLD    │
         │                       │         └────┬────┘      └─────┬─────┘
         │                       │              │                 │
         ▼                       ▼              ▼                 ▼
    ┌─────────────────────────────────────────────────────────────────┐
    │                       Jellyseerr                                │
    │               (approve / decline API)                           │
    └─────────────────────────────────────────────────────────────────┘
                                                              │
                                                     ┌────────▼────────┐
                                                     │   Mattermost    │
                                                     │  Approve / Deny │
                                                     └─────────────────┘
```

## Complete Pipeline Flow

This section documents the end-to-end flow of a media request through the entire stack.

### Infrastructure Overview

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                           MEDIA REQUEST PIPELINE                              │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌──────────────┐  │
│  │ Jellyseerr  │───▶│   Radarr/   │───▶│  Prowlarr   │───▶│ Transmission │  │
│  │   :5055     │    │   Sonarr    │    │   :9696     │    │    :9091     │  │
│  │             │    │ :7878/:8989 │    │  (Indexers) │    │  (VPN: PIA)  │  │
│  └──────┬──────┘    └──────┬──────┘    └─────────────┘    └──────┬───────┘  │
│         │                  │                                      │          │
│         │ webhook          │ webhook                              │          │
│         ▼                  ▼                                      │          │
│  ┌─────────────────────────────────────┐                         │          │
│  │           GATEKEEPER :5023          │                         │          │
│  │      (AI Content Analysis)          │                         │          │
│  │                                     │                         │          │
│  │  • Analyzes content via Claude API  │                         │          │
│  │  • Routes based on user type        │                         │          │
│  │  • Sends Mattermost notifications   │                         │          │
│  └──────────────┬──────────────────────┘                         │          │
│                 │                                                 │          │
│                 │ approve/deny                                    │          │
│                 ▼                                                 ▼          │
│  ┌─────────────────────────────┐              ┌─────────────────────────┐   │
│  │       Mattermost :8065      │              │     Jellyfin :8096      │   │
│  │  (Approve/Deny Buttons)     │              │    (Media Playback)     │   │
│  │                             │              │                         │   │
│  │  Parent receives alert ────────────────────▶ Content available      │   │
│  │  clicks Approve/Deny        │              │                         │   │
│  └─────────────────────────────┘              └─────────────────────────┘   │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Step-by-Step Flow

#### 1. User Makes Request (Jellyseerr)
```
User visits Jellyseerr (e.g., requests.example.com)
  └─▶ Browses/searches for movie or TV show
  └─▶ Clicks "Request"
  └─▶ Jellyseerr sends webhook to Gatekeeparr
  └─▶ Jellyseerr forwards request to Radarr/Sonarr
```

#### 2. Content Analysis (Gatekeeparr)
```
Gatekeeparr receives Jellyseerr webhook
  └─▶ Identifies requesting user
  └─▶ Looks up user type (admin/adult/teen/kid)
  └─▶ Fetches content metadata from TMDB
  └─▶ Sends to AI for parental content analysis
  └─▶ AI returns: rating, concerns, recommendation
```

#### 3. Routing Decision (Gatekeeparr)
```
Based on user type + content rating:

ADMIN or ADULT user:
  └─▶ Auto-approve → Radarr/Sonarr monitors & downloads

KID user + G/PG/TV-PG content:
  └─▶ Auto-approve in Jellyseerr → flows to Radarr/Sonarr → downloads

KID user + PG-13/TV-14 content:
  └─▶ HOLD → Leave pending in Jellyseerr (kid sees "Pending")
  └─▶ Run AI analysis with Common Sense Media data
  └─▶ Send Mattermost alert with Approve/Deny buttons

KID user + R/TV-MA content:
  └─▶ AUTO-DECLINE → Declined in Jellyseerr (kid sees "Declined")

ANY user + NC-17/X content:
  └─▶ AUTO-BLOCK → Declined in Jellyseerr
```

#### 4. Download & Availability
```
If approved/auto-approved:
  └─▶ Radarr/Sonarr searches via Prowlarr
  └─▶ Prowlarr queries indexers (TPB, YTS, etc.)
  └─▶ Best match sent to Transmission (VPN-protected)
  └─▶ Download completes
  └─▶ Radarr/Sonarr imports to media library
  └─▶ Jellyfin scans and makes available
```

#### 5. Parent Approval Flow (Mattermost)
```
When content is held for review:
  └─▶ Parent receives Mattermost notification:
      ┌─────────────────────────────────────────────┐
      │ 🎬 Content Request Held                     │
      │                                             │
      │ Movie: Deadpool & Wolverine (2024)          │
      │ Rating: R                                   │
      │ Requested by: child1                         │
      │                                             │
      │ AI Analysis:                                │
      │ • Strong violence and gore                  │
      │ • Pervasive language                        │
      │ • Adult humor throughout                    │
      │                                             │
      │ [  Approve  ]  [  Deny  ]                   │
      └─────────────────────────────────────────────┘

  └─▶ Parent clicks Approve:
      └─▶ Gatekeeparr calls Jellyseerr approve API
      └─▶ Request flows to Radarr/Sonarr → download begins
      └─▶ Mattermost updated: "Approved by @parent"

  └─▶ Parent clicks Deny:
      └─▶ Gatekeeparr calls Jellyseerr decline API
      └─▶ Request marked declined (kid sees "Declined")
      └─▶ Mattermost updated: "Denied by @parent"
```

### Quality Controls (Radarr/Sonarr/Prowlarr)

The pipeline includes automatic quality controls configured outside Gatekeeparr:

| Setting | Value | Effect |
|---------|-------|--------|
| Minimum Seeders | 5 | Only grab well-seeded torrents |
| Max Size (1080p WEB) | ~8 GB/hr | ~16GB max for 2hr movie |
| Max Size (1080p Bluray) | ~12 GB/hr | ~24GB max for 2hr movie |
| Remux/4K | Disabled | Prevents 30-80GB downloads |

### Content Pre-Filtering (Jellyseerr)

Jellyseerr blacklist tags prevent inappropriate content from appearing in browse/discover:

**Recommended Blacklisted Tags:** `erotic`, `sexploitation`, `porn`, `pornographic`, `softcore`, `hardcore`, `adult film`, `sex`

> **Note:** Search results are not filtered (TMDB API limitation). Gatekeeparr catches any inappropriate requests.

### Services & Ports

| Service | Port | Purpose |
|---------|------|---------|
| Jellyseerr | 5055 | Media request UI |
| Gatekeeparr | 5023 | Content analysis & routing |
| Radarr | 7878 | Movie management |
| Sonarr | 8989 | TV show management |
| Prowlarr | 9696 | Indexer aggregation |
| Transmission | 9091 | Torrent downloads (VPN) |
| Jellyfin | 8096 | Media playback |
| Mattermost | 8065 | Notifications & approvals |

## Quick Start

### 1. Clone and Configure

```bash
git clone https://github.com/kevkrj/gatekeeparr.git && cd gatekeeparr
cp .env.example .env
# Edit .env with your API keys and URLs
```

### 2. Deploy with Docker

```bash
docker-compose up -d
```

### 3. Configure Webhooks

**Jellyseerr** (required - primary decision point):
Settings → Notifications → Webhook
- Webhook URL: `http://<gatekeeper-ip>:5023/webhook/jellyseerr`
- Notification Types: Enable **Media Requested** (MEDIA_PENDING)
- JSON Payload: Use default template

**Radarr** (for symlink creation after download):
Settings → Connect → Add → Webhook
- URL: `http://<gatekeeper-ip>:5023/webhook/radarr`
- Events: On Import (Download)

**Sonarr** (for symlink creation after download):
Settings → Connect → Add → Webhook
- URL: `http://<gatekeeper-ip>:5023/webhook/sonarr`
- Events: On Import (Download)

### 4. Set Up Users

Users must be configured in Gatekeeparr to enable proper routing. The `jellyseerr_username` field maps Jellyseerr usernames to local Gatekeeparr users.

**Via Docker CLI:**
```bash
# Add admin user (maps to Jellyseerr username "admin")
docker exec gatekeeper python /app/scripts/add_user.py parent admin - admin

# Add kid (maps to Jellyseerr username "child1")
docker exec gatekeeper python /app/scripts/add_user.py child1 kid PG child1

# Add teen
docker exec gatekeeper python /app/scripts/add_user.py teen1 teen PG-13 teen1_jellyseerr

# Add adult
docker exec gatekeeper python /app/scripts/add_user.py adult1 adult - adult1
```

**Via API:**
```bash
curl -X POST http://localhost:5000/api/users \
  -H "Content-Type: application/json" \
  -d '{"username": "parent", "user_type": "admin", "jellyseerr_username": "admin"}'
```

**Important:** The `jellyseerr_username` must match exactly what Jellyseerr sends in webhooks (case-insensitive). Check your Jellyseerr user list to find the correct usernames.

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `AI_PROVIDER` | AI backend: claude, ollama, openai, grok | `claude` |
| `AI_API_KEY` | API key for AI provider | required |
| `AI_MODEL` | Override default model | provider default |
| `AI_BASE_URL` | Custom API URL (for Ollama) | provider default |
| `JELLYSEERR_URL` | Jellyseerr base URL | `http://localhost:5055` |
| `JELLYSEERR_API_KEY` | Jellyseerr API key | required |
| `RADARR_URL` | Radarr base URL | `http://localhost:7878` |
| `RADARR_API_KEY` | Radarr API key | required |
| `SONARR_URL` | Sonarr base URL | `http://localhost:8989` |
| `SONARR_API_KEY` | Sonarr API key | required |
| `MATTERMOST_WEBHOOK` | Mattermost incoming webhook | optional |
| `DISCORD_WEBHOOK` | Discord webhook URL | optional |
| `GATEKEEPER_URL` | External URL for callbacks | `http://localhost:5000` |

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

## API Endpoints

### Webhooks

| Endpoint | Description |
|----------|-------------|
| `POST /webhook/radarr` | Radarr webhook handler |
| `POST /webhook/sonarr` | Sonarr webhook handler |
| `POST /webhook/jellyseerr` | Jellyseerr webhook handler |
| `POST /action` | Notification button callback |

### Utility

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Health check |
| `GET /test` | Test AI integration |
| `GET /test/connections` | Test all service connections |

### API

| Endpoint | Description |
|----------|-------------|
| `GET /api/requests` | List all requests |
| `GET /api/requests/:id` | Get request details |
| `POST /api/requests/:id/approve` | Approve request |
| `POST /api/requests/:id/deny` | Deny request |
| `GET /api/users` | List users |
| `PUT /api/users/:id` | Update user settings |
| `GET /api/stats` | Dashboard statistics |

## User Types

| Type | Auto-Approve | Hold For Review | Block |
|------|--------------|-----------------|-------|
| `admin` | Everything | Nothing | Nothing |
| `adult` | Everything | Nothing* | NC-17/X |
| `teen` | G, PG, PG-13, TV-14 | R, TV-MA | NC-17/X |
| `kid` | G, PG, TV-PG | PG-13, TV-14 | R, TV-MA, NC-17/X |

*Adults with `requires_approval: true` follow the same rules as kids

## Rating Mappings

### Movies (for kids)
- G, PG → Auto-approve
- PG-13 → Hold for review (AI analysis)
- R → Auto-block
- NC-17, X → Always blocked

### TV (for kids)
- TV-Y, TV-Y7, TV-G, TV-PG → Auto-approve
- TV-14 → Hold for review (AI analysis)
- TV-MA → Auto-block

## Development

### Local Setup

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run development server
python -m gatekeeper.app
```

## Roadmap

- [x] Core webhook handlers
- [x] AI content analysis
- [x] User-based routing
- [x] Mattermost notifications
- [x] Request tracking
- [x] Kids libraries (symlink-based Kids Movies + Kids TV)
- [ ] ntfy.sh mobile notifications
- [x] Admin panel UI
- [x] Jellyseerr SSO (login via Jellyseerr credentials)
- [x] First-run setup wizard

## Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Submit a pull request

## License

MIT License - feel free to use in your own projects.

## Credits

Built for families who want smarter parental controls.

Inspired by:
- [Pulsarr](https://github.com/jamcalli/Pulsarr) - Approval workflow patterns
- [rarrnomore](https://github.com/Schaka/rarrnomore) - Webhook interception patterns

# Gatekeeparr External Dependencies

This document describes the required configurations in external applications that Gatekeeparr depends on.

## Jellyseerr (Required)

Jellyseerr is the **primary decision point** - all parental filtering happens when requests are made.

### Webhook Configuration

**Location**: Settings → Notifications → Webhook

| Setting | Value |
|---------|-------|
| Enabled | Yes |
| Webhook URL | `http://<gatekeeper-ip>:5023/webhook/jellyseerr` |
| Authorization Header | (leave empty) |
| JSON Payload | Use default template |

**Notification Types** (enable these):
- [x] Media Requested (sends `MEDIA_PENDING`)
- [x] Media Auto-Approved (optional, for logging)

### How to Verify

```bash
# Test webhook endpoint
curl -s http://<gatekeeper-ip>:5023/webhook/jellyseerr/test
# Should return: {"status": "ok", "message": "Jellyseerr webhook endpoint ready"}
```

### What Happens

When a user makes a request in Jellyseerr:
1. Jellyseerr sends `MEDIA_PENDING` webhook to Gatekeeparr
2. Gatekeeparr looks up user type and fetches TMDB rating
3. Decision is made:
   - **Auto-approve**: Gatekeeparr calls Jellyseerr approve API → flows to Radarr/Sonarr
   - **Hold**: Request stays pending in Jellyseerr, parent notified via Mattermost
   - **Block**: Gatekeeparr calls Jellyseerr decline API → user sees "Declined"

---

## Radarr (Required for Movies)

Radarr webhook creates symlinks in `/media/kids-approved/` after downloads complete.

### Webhook Configuration

**Location**: Settings → Connect → Add → Webhook

| Setting | Value |
|---------|-------|
| Name | Gatekeeparr |
| URL | `http://<gatekeeper-ip>:5023/webhook/radarr` |
| Method | POST |

**Triggers** (enable these):
- [x] On Import

### Path Translation

Radarr container uses `/movies` internally. Gatekeeparr translates this:
- `/movies/Movie Name (2024)` → `/media/movies/Movie Name (2024)`

This is handled automatically by `_translate_path()` in the webhook handler.

---

## Sonarr (Required for TV)

Sonarr webhook creates symlinks in `/media/kids-approved/` after downloads complete.

### Webhook Configuration

**Location**: Settings → Connect → Add → Webhook

| Setting | Value |
|---------|-------|
| Name | Gatekeeparr |
| URL | `http://<gatekeeper-ip>:5023/webhook/sonarr` |
| Method | POST |

**Triggers** (enable these):
- [x] On Import

### Path Translation

Sonarr container uses `/tv` internally. Gatekeeparr translates this:
- `/tv/Show Name (2024)` → `/media/tv/Show Name (2024)`

---

## Ollama (Required for AI Analysis)

Ollama provides local AI analysis for held content.

### Configuration

| Setting | Value |
|---------|-------|
| API URL | `http://<ollama-host>:11434` |
| Model | `phi3:3.8b` (recommended) or `llama3.2:3b` |
| Keep-alive | 5 minutes (auto-unloads from GPU) |

### Environment Variables

```env
AI_PROVIDER=ollama
AI_BASE_URL=http://<ollama-host>:11434
AI_MODEL=phi3:3.8b
```

### Verify Ollama is Running

```bash
# Check Ollama status
systemctl status ollama

# Test API
curl http://<ollama-host>:11434/api/tags | jq '.models[].name'
```

---

## Mattermost (Optional - Notifications)

Mattermost receives notifications for held content with approve/deny buttons.

### Incoming Webhook Configuration

**Location**: Integrations → Incoming Webhooks → Add

| Setting | Value |
|---------|-------|
| Title | Gatekeeparr |
| Channel | #media-requests (or your choice) |

Copy the webhook URL and set in Gatekeeparr:

```env
MATTERMOST_WEBHOOK=https://chat.example.com/hooks/xxx
```

### Outgoing Webhook (for approve/deny buttons)

**Location**: Integrations → Outgoing Webhooks → Add

| Setting | Value |
|---------|-------|
| Title | Gatekeeparr Actions |
| Content Type | application/json |
| URLs | `http://<gatekeeper-ip>:5023/action` |
| Trigger Words | (leave empty - uses callback URLs) |

---

## TMDB (Required - Rating Lookup)

TMDB provides official content ratings (PG-13, R, TV-MA, etc.).

### Get API Key

1. Create account at https://www.themoviedb.org/
2. Go to Settings → API → Request API Key
3. Copy the API Key (v3 auth)

```env
TMDB_API_KEY=your_api_key_here
```

---

## Docker Volume Mounts

Gatekeeparr needs access to media paths for symlink creation:

```yaml
volumes:
  - ./data:/app/data
  - /media/movies:/media/movies:ro
  - /media/tv:/media/tv:ro
  - /media/kids-approved/movies:/media/kids-approved/movies:rw
  - /media/kids-approved/tv:/media/kids-approved/tv:rw
```

| Mount | Access | Purpose |
|-------|--------|---------|
| `/media/movies` | Read-only | Source for movie symlinks |
| `/media/tv` | Read-only | Source for TV symlinks |
| `/media/kids-approved/movies` | Read-write | Destination for movie symlinks |
| `/media/kids-approved/tv` | Read-write | Destination for TV symlinks |

## Jellyfin Library Configuration

For proper display of movies and TV shows, configure **two separate libraries** in Jellyfin:

1. **Kids Movies** (Content type: Movies)
   - Path: `/media/kids-approved/movies`

2. **Kids TV** (Content type: Shows)
   - Path: `/media/kids-approved/tv`

This ensures TV shows are grouped properly with seasons, rather than showing individual episodes.

### Recommended Library Settings

| Setting | Value | Reason |
|---------|-------|--------|
| Enable realtime monitoring | Yes | Auto-detect new symlinks |
| Enable internet providers | Yes | Fetch metadata from TMDB |

### User Access Configuration

Kids should ONLY have access to the Kids Movies and Kids TV libraries. Remove access to the main Movies/Shows libraries.

**Important User Policy Settings:**
- `EnableAllFolders`: `false`
- `EnabledFolders`: Only include Kids Movies and Kids TV library IDs
- `BlockUnratedItems`: `[]` (empty - Gatekeeparr handles filtering at request time)

### Pre-populating Kids Libraries

Gatekeeparr only creates symlinks for content requested through Jellyseerr. For existing G/PG content already in your library, manually create symlinks:

```bash
# Example: Add existing G/PG movie
sudo ln -s "/media/movies/Finding Nemo (2003)" "/media/kids-approved/movies/Finding Nemo (2003)"

# Example: Add existing TV-Y/TV-G show
sudo ln -s "/media/tv/Bluey (2018)" "/media/kids-approved/tv/Bluey (2018)"

# Trigger Jellyfin library scan
curl -X POST "http://localhost:8096/Library/Refresh" -H "X-Emby-Token: YOUR_API_KEY"
```

---

## Network Requirements

Gatekeeparr needs to reach:

| Service | Port | Purpose |
|---------|------|---------|
| Jellyseerr | 5055 | Approve/decline requests |
| Radarr | 7878 | (legacy - not currently used) |
| Sonarr | 8989 | (legacy - not currently used) |
| Ollama | 11434 | AI analysis |
| Mattermost | 8065 | Notifications |
| TMDB API | 443 | Rating lookup |
| Common Sense Media | 443 | Content data (web scraping) |

---

## Quick Verification Checklist

```bash
# 1. Test Gatekeeparr health
curl http://<gatekeeper-ip>:5023/health

# 2. Test all service connections
curl http://<gatekeeper-ip>:5023/test/connections | jq .

# 3. Test AI integration
curl http://<gatekeeper-ip>:5023/test | jq .

# 4. Test Jellyseerr webhook endpoint
curl http://<gatekeeper-ip>:5023/webhook/jellyseerr/test
```

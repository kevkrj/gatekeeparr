# Gatekeeper Production Roadmap

## Completed (2025-12-12)

- [x] Jellyseerr-first pipeline (webhook intercept at request time)
- [x] TMDB rating lookup
- [x] Common Sense Media data fetching
- [x] Ollama AI summaries (phi3:3.8b)
- [x] Mattermost notifications with approve/deny buttons
- [x] Jellyseerr approve/decline API integration
- [x] Code cleanup (~955 lines removed)
- [x] Kids libraries via symlinks (Kids Movies + Kids TV)

## Phase 2: Mobile Notifications (ntfy.sh)

**Goal**: Approve/deny requests from iPhone via push notifications

### Tasks
1. Set up ntfy.sh (self-hosted or public server)
2. Add NtfyChannel to notifier.py
3. Include action URLs in notification for approve/deny
4. Install ntfy iOS app and subscribe to topic
5. Test end-to-end flow

### Technical Notes
- ntfy supports action buttons via `Actions` header
- Actions can be `http` type with POST to gatekeeper approve/deny endpoints
- Format: `action=http, label=Approve, url=http://<gatekeeper-ip>:5023/action/approve/123`
- Consider: May need external URL (Cloudflare tunnel) for approve actions from outside network

### Config Changes
```env
NTFY_URL=https://ntfy.sh  # or self-hosted
NTFY_TOPIC=gatekeeper-approvals
```

## Phase 3: Kids Libraries - COMPLETED

**Goal**: Kids only see age-appropriate content

**Implementation**: Symlink-based separate Jellyfin libraries (simpler than collections)

### How It Works
1. Two separate Jellyfin libraries for kids:
   - **Kids Movies** → `/media/kids-approved/movies`
   - **Kids TV** → `/media/kids-approved/tv`
2. Kid accounts only have access to these two libraries
3. When content is approved or auto-approved for kids:
   - Radarr/Sonarr webhook fires on import
   - Gatekeeparr creates symlink from `/media/movies/` → `/media/kids-approved/movies/`
   - Jellyfin detects new content via realtime monitoring
4. G/PG content auto-approved → symlink created automatically
5. PG-13 content held → parent approves → symlink created after download

### Jellyfin Configuration
- Kids Movies library: CollectionType = movies, EnableRealtimeMonitor = true
- Kids TV library: CollectionType = tvshows, EnableRealtimeMonitor = true
- Kid user policies: EnableAllFolders = false, EnabledFolders = [Kids Movies ID, Kids TV ID]

## Phase 4: Future Ideas

- [ ] Admin panel UI
- [ ] Jellyseerr SSO
- [ ] First-run setup scripts (for open source release)
- [ ] Discord notifications (already have channel, just not configured)
- [ ] Automatic re-notification if no response in X hours

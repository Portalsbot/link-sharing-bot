# Link Sharing Bot — private project foundation

This ZIP is the independently deployable foundation for the Link Sharing Bot master repository. It includes a Telegram app shell, PostgreSQL persistence, channel registration and permission checks, normal and join-request invite generation, tracked invite expiry, bulk generation/revocation, approval-delay controls, join-request approval handler, FSub records, generic HTTPS shortener API integration, usage/history analytics, and the branded message editor. It is **not yet the complete production feature set** from the product blueprint.

## Branding image

All bot-authored text replies are sent as branded photo captions using `https://raw.githubusercontent.com/Portalsbot/image/main/photo_2026-11-01_20-42-48.jpg`. Original user link: `https://github.com/Portalsbot/image/blob/main/photo_2026-11-01_20-42-48.jpg`. The image binary is not included because external binary downloads are unavailable in this build environment. Verify public accessibility and Telegram fetch. Optionally set `BRANDING_IMAGE_PATH` to a local image.

Telegram caption limit is 1024 characters after parsing; long texts are split into branded photo captions. This bot primarily sends invitation links as photo captions with URLs and buttons, so the branding image accompanies those responses.

## Run locally

```bash
python -m venv .venv
pip install -e .[dev]
cp .env.example .env
# configure BOT_TOKEN, OWNER_ID and DATABASE_URL
python -m link_sharing_bot.main
```

## Commands included

| Command | Use |
|---|---|
| `/start`, `/help`, `/about`, `/ping` | Basic interface |
| `/addch CHANNEL_ID` | Register target channel; bot needs admin invite permission |
| `/delch CHANNEL_ID` | Remove registered channel |
| `/channels`, `/channelpanel` | List registered channels |
| `/genlink CHANNEL_ID [request] [TTL_SECONDS]` | Generate invite link |
| `/bulklink ID1 ID2 ...` | Generate up to 20 links |
| `/links` | List recent tracked invitation links |
| `/revoke_links CHANNEL_ID` | Revoke tracked active links in a channel |
| `/bulkexpire CHANNEL_ID TTL_SECONDS` | Change default TTL for future links |
| `/setapproval CHANNEL_ID auto|manual DELAY_SECONDS` | Set channel approval policy |
| `/reqmode on|off` | Global auto-approval mode |
| `/reqtime SECONDS` | Set global approval delay |
| `/add_fsub CHANNEL_ID normal|request` | Add FSub record |
| `/del_fsub CHANNEL_ID`, `/fsub` | Remove/list FSub records |
| `/shorten URL` | Use configured shortener |
| `/set_api HTTPS_ENDPOINT API_KEY` | Configure generic GET shortener API (admin) |
| `/shortnerstatus`, `/shortnerstats`, `/linkhistory` | Shortener status and statistics |
| `/channelstats CHANNEL_ID` | Join-request analytics |
| `/schedulelink CHANNEL_ID ISO_TIMESTAMP [request]` | Schedule an invite (current in-memory job queue) |
| `/texts`, `/edittext`, `/previewtext`, `/resettext` | Edit messages |
| `/buttons`, `/addbutton`, `/delbutton` | Edit inline URL buttons |

## Permissions and limitations

- The bot must be an administrator in each target channel with `can_invite_users` permission to create/revoke invite links. Join-request workflows require the appropriate channel permissions.
- FSub records are stored here; the full subscription-gating middleware and interactive channel wizard remain to be implemented.
- `/bulkexpire` changes the default expiry policy for future links; it does not modify Telegram's expiry on already-created invite links. Use `/revoke_links` to invalidate tracked current links.
- `/schedulelink` currently uses the process job queue; jobs are lost after a process restart. Durable DB-backed scheduling is a production task.
- The generic shortener expects a JSON response with `shortenedUrl`, `short_url` or `url`. Providers with different APIs need a dedicated adapter. Custom aliases are not guaranteed unless the provider API supports them.
- API endpoints are owner-configured and must be trusted HTTPS endpoints. A production SSRF allowlist is still required before enabling arbitrary provider endpoints.

## Formatting

Use `(B)`, `(I)`, `(U)`, `(S)`, `(CODE)`, `(PRE)`, `(Q)`, `(SPOILER)` and `(LINK url="https://...")` markup in editable templates.

## Not yet implemented

Full paginated channel UI, durable scheduling, full FSub membership gate, approval welcome templates, built-in adapters for each named shortener, alias support, DNS/IP SSRF guard, broadcast engine, advanced per-channel request queue, and full analytics dashboard.

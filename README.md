# Link Sharing Bot — private project foundation

This ZIP is the independently deployable foundation for the Link Sharing Bot master repository. It includes a Telegram app shell, PostgreSQL persistence, channel registration and permission checks, normal and join-request invite generation, tracked invite expiry, bulk generation/revocation, approval-delay controls, join-request approval handler, FSub records, generic HTTPS shortener API integration, usage/history analytics, and the branded message editor. It is **not yet the complete production feature set** from the product blueprint.

## Branding image

All bot-authored text replies are sent as branded photo captions using `https://i.ibb.co/PGpMYwYY/Gemini-Generated-Image-a7tjlia7tjlia7tj.png`. Original user link: `https://github.com/Portalsbot/image/blob/main/photo_2026-11-01_20-42-48.jpg`. The configured `BRANDING_IMAGE_URL` is used by default. Set `BRANDING_IMAGE_PATH` only when you intentionally want to use a local image instead.

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
| `/addch CHANNEL_ID` | Register channel and return a permanent public bot deep link |
| `/newlink URL [LABEL]` | Save an external URL behind a permanent public bot deep link |
| `/publiclinks` | List saved public bot-link entries |
| `/deletelink ENTRY_ID` | Disable one saved public bot-link entry |
| `/setttl CHANNEL_ID SECONDS` | Set expiry for future temporary channel invites |
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
| `/set_api HTTPS_ENDPOINT API_KEY` | Configure generic GET shortener API (Owner only; encrypted storage and allowlisted HTTPS host required) |
| `/shortnerstatus`, `/shortnerstats`, `/linkhistory` | Shortener status and statistics |
| `/channelstats CHANNEL_ID` | Join-request analytics |
| `/publiclinks`, `/editlink ENTRY_ID URL [LABEL]`, `/checkduplicate URL` | Manage permanent public bot links |
| `/scheduledlinks`, `/cancelschedule JOB_ID` | Inspect or cancel durable scheduled invitations |
| `/joinrequests`, `/approve USER_ID CHANNEL_ID`, `/decline USER_ID CHANNEL_ID` | Manual join-request queue and decisions |
| `/requeststats`, `/requesthistory`, `/linkstats` | Request and link dashboards |
| `/users`, `/userinfo USER_ID`, `/blockuser USER_ID`, `/unblockuser USER_ID` | User management |
| `/security`, `/database`, `/diagnostics` | Security, database and runtime diagnostics |
| `/broadcast`, `/broadcasts`, `/cancelbroadcast ID` | Immediate and scheduled text/media broadcasts with URL buttons |
| `/setbackupchannel CHANNEL_ID`, `/backup`, `/backups` | Configure and create Telegram-channel backups |
| `/restore ID CONFIRM`, `/exportdata`, `/importdata` | Restore or transfer a validated JSON backup |
| `/schedulelink CHANNEL_ID ISO_TIMESTAMP [request]` | Schedule an invite in the persistent PostgreSQL queue |
| `/texts`, `/edittext`, `/previewtext`, `/resettext` | Edit messages |
| `/buttons`, `/addbutton`, `/delbutton` | Edit inline URL buttons |

## Permissions and limitations

- The bot must be an administrator in each target channel with `can_invite_users` permission to create/revoke invite links. Join-request workflows require the appropriate channel permissions.
- FSub membership is checked before public channel and external-link delivery. The bot must be admin in each configured FSub channel; private FSub channels also need invite permission.
- `/bulkexpire` changes the default expiry policy for future links; it does not modify Telegram's expiry on already-created invite links. Use `/revoke_links` to invalidate tracked current links.
- `/schedulelink` currently uses the process job queue; jobs are lost after a process restart. Durable DB-backed scheduling is a production task.
- The generic shortener expects a JSON response with `shortenedUrl`, `short_url` or `url`. Providers with different APIs need a dedicated adapter. Custom aliases are not guaranteed unless the provider API supports them.
- API endpoints are owner-configured and must be trusted HTTPS endpoints. A production SSRF allowlist is still required before enabling arbitrary provider endpoints.

## Formatting

Use `(B)`, `(I)`, `(U)`, `(S)`, `(CODE)`, `(PRE)`, `(Q)`, `(SPOILER)` and `(LINK url="https://...")` markup in editable templates.

## Current implementation status

- Public bot deep links and temporary Telegram invitations have separate lifecycles. The public link remains permanent; each Start creates a fresh invitation using the channel TTL.
- External URLs saved with `/newlink` remain unchanged until their public bot entry is disabled or edited.
- FSub is checked before both channel and external public entries. The bot must be an administrator in every FSub channel; private channels also require invite-link permission.
- Pending join requests are persisted and can be reviewed with `/joinrequests`, `/approve` and `/decline`. Automatic approval uses the channel policy and global delay.
- Scheduled invitation jobs persist in PostgreSQL and can be listed/cancelled. Interrupted in-flight jobs are marked for review rather than replayed blindly.
- Shortener credentials are Fernet-encrypted at rest. The provider hostname must match `SHORTENER_ALLOWED_HOSTS`, resolve only to public IPs, and use HTTPS. Set `SHORTENER_ENCRYPTION_KEY` before using `/set_api`.
- Text/media broadcasts support URL buttons, immediate delivery, durable scheduled delivery, reports and cancellation.
- Telegram-channel backups, JSON export/import and Owner-confirmed restore are implemented. Configure `/setbackupchannel` before relying on remote backups.
- User management, link/request analytics, database/security diagnostics, and automatic Telegram admin command menus are implemented.
- The HTTP health endpoint is `/health` when a `PORT` environment variable is supplied.

## Remaining constraints

Provider-specific shortener response formats may require an adapter. The generic adapter expects a JSON response with `shortenedUrl`, `short_url` or `url`. Set the shortener encryption key and exact allowed hostname in the deployment environment; the repository intentionally contains no production key. PostgreSQL-native backups are still recommended for databases too large for Telegram document limits.
\n## Public links versus temporary channel invitations\n\n- `/addch CHANNEL_ID` registers the channel and returns a permanent public bot deep link. Share that bot link publicly.\n- When someone opens that public link and presses Start, the bot creates a fresh Telegram channel invite using the channel's configured TTL and sends it as an inline button. The public bot link never expires because of this TTL.\n- `/setttl CHANNEL_ID SECONDS` changes the TTL for future generated invites (60–604800 seconds). Existing Telegram invites retain their own expiry.\n- `/newlink HTTPS_URL [LABEL]` stores an external destination URL unchanged behind a permanent public bot deep link. It is not auto-expired by the bot. Use `/publiclinks` to view entries and `/deletelink ENTRY_ID` to disable one. Disabling the bot entry does not revoke or modify the external destination itself.\n- New channel registrations default to manual join-request handling; explicitly enable automatic approval with the channel approval command if desired.\n

## Channel links, force-subscription and scheduling

- `/addch CHANNEL_ID` creates a permanent public bot deep link. The bot generates a new Telegram invite each time a user starts through that link.
- `/setttl CHANNEL_ID SECONDS` applies only to future invites. It does not expire or disable the permanent public bot link.
- `/newlink HTTPS_URL LABEL` creates a permanent bot deep link to an unchanged external URL. It remains available until `/deletelink ENTRY_ID`.
- `/add_fsub CHANNEL_ID normal|request` adds a force-subscription channel. The bot must be an administrator there so Telegram membership checks are reliable.
- `/joinrequests`, `/approve USER_ID CHANNEL_ID` and `/decline USER_ID CHANNEL_ID` provide manual join-request handling. Configure automatic handling with `/setapproval`.
- `/schedulelink CHANNEL_ID YYYY-MM-DDTHH:MM:SS+05:30` stores a durable PostgreSQL job. Use `/scheduledlinks` and `/cancelschedule JOB_ID` to manage pending jobs.
- Shortener configuration is intentionally locked down: set `SHORTENER_ALLOWED_HOSTS` to the exact provider hostname and `SHORTENER_ENCRYPTION_KEY` to a Fernet key before using `/set_api`. API credentials are encrypted before storage. Existing plaintext shortener records from older versions will not be accepted; reconfigure them after setting the key.

# Chat Provider Swap

Team 4's primary Chat provider is Telegram. The service defaults to Telegram
and exposes provider-neutral chat operations through `/chat/...`.

For the HW3 same-vertical provider swap demo, the backing implementation is
selected with `CHAT_CLIENT_PROVIDER`.

| Provider | Env | Channel ID shape |
| --- | --- | --- |
| Telegram | `CHAT_CLIENT_PROVIDER=telegram` | Telegram chat id |
| Slack | `CHAT_CLIENT_PROVIDER=slack` | Slack channel id such as `C1234567890` |

The Slack provider is optional demo support based on imported Team 9 content:

- Team: Team 9, Slack provider
- Source: `components/slack_client_impl` from Team 9's HW3 PR #5
- PR: <https://github.com/HarshithKoriRaj/CS-GY-9223-Open-Source/pull/5>
- Package source: pinned git dependency at commit `91eedf88e6823e1f924cbeb05c6a74aa0a524b34`
- Tree: <https://github.com/HarshithKoriRaj/CS-GY-9223-Open-Source/tree/91eedf88e6823e1f924cbeb05c6a74aa0a524b34/components/slack_client_impl>

This external package is loaded only when `CHAT_CLIENT_PROVIDER=slack`.
Team 4's own provider remains `telegram_client_impl`.
Team 4 wraps the imported Slack client at provider-load time to normalize Slack
`ts` timestamps into the canonical shared API's timezone-aware `datetime`
contract.

## Reusable endpoints

These are the provider-swapped Team 4 service endpoints. They keep the same
HTTP shape for Telegram and Slack; only the provider-specific IDs change.

- `POST /chat/messages`
- `GET /chat/channels`
- `GET /chat/channels/{channel_id}`
- `GET /chat/messages?channel_id=...`
- `GET /chat/messages/{message_id}`
- `DELETE /chat/messages/{message_id}`

| Operation | Telegram ID | Slack ID |
| --- | --- | --- |
| Send/list by channel | Telegram chat id, or `me` for Telegram self-chat | Slack channel id such as `C1234567890` |
| Message id | Existing Telegram opaque message id format | `channel_id:timestamp`, for example `C1234567890:1715200000.000100` |

The standalone Team 9 service used `/messages` and `/channels`; Team 4 keeps
the HW2/HW3 service namespace as `/chat/messages` and `/chat/channels`.

## Auth model

The provider swap is for the chat backend, not for service authentication.
Team 4 still owns HTTP auth:

- Use `X-Session-ID` or `Authorization: Bearer ...` for `/chat/...`.
- The existing `/auth/...` routes are Team 4 Telegram login/session routes.
- They are not Slack OAuth routes, even when `CHAT_CLIENT_PROVIDER=slack`.
- Team 9's Slack OAuth service auth is not imported in this branch.

Team 9's PR includes Slack OAuth service auth using `SLACK_CLIENT_ID`,
`SLACK_CLIENT_SECRET`, and `SLACK_REDIRECT_URI`. This branch does not import
that auth layer; the rubric demo swaps only the `ChatClient` provider behind
`/chat/...`.

## Slack demo env

```bash
CHAT_CLIENT_PROVIDER=slack
SLACK_BOT_TOKEN=xoxb-...
CHAT_CLIENT_ALLOWED_CHANNEL_IDS=C1234567890
```

From Slack itself, the provider-swap path needs only `SLACK_BOT_TOKEN`; it does
not need Slack OAuth client credentials. The other variables are Team 4 service
configuration: provider selection and channel authorization for `/chat/...`.

`CHAT_CLIENT_ALLOWED_CHANNEL_IDS` authorizes provider-neutral channel access for
the generic `/chat` routes. Use a comma-separated list for multiple channels.
Avoid `*` on public deployments unless it is a short-lived demo service.

The Slack bot token must be a Bot User OAuth token installed in the target
workspace. For the operations implemented by Team 9's `SlackClient`, the bot
needs Slack Web API access for posting messages, listing channels, and reading
channel history. At minimum for the demo, use a bot token with scopes for
[`chat:write`](https://docs.slack.dev/reference/scopes/chat.write), channel
listing, and channel history for the conversation types you will show.
Slack's `conversations.history` scopes are conversation-type scoped, so public
channels use public-channel scopes and private channels need private-channel
scopes. Invite the bot to the demo channel before calling `/chat/...`.

## Render variables

For the normal Team 4 deployment, keep:

```bash
CHAT_CLIENT_PROVIDER=telegram
TELEGRAM_BOT_TOKEN=<team-4-bot-token>
SERVICE_BASE_URL=https://csgy9223.onrender.com
TELEGRAM_UPDATE_MODE=polling
```

For the Slack provider-swap demo, either use a separate Render service or
temporarily switch the provider and redeploy/restart with:

```bash
CHAT_CLIENT_PROVIDER=slack
SLACK_BOT_TOKEN=xoxb-...
CHAT_CLIENT_ALLOWED_CHANNEL_IDS=C1234567890
```

Keep the existing Team 4 auth/session variables in place. Do not add
`SLACK_CLIENT_ID`, `SLACK_CLIENT_SECRET`, or `SLACK_REDIRECT_URI` unless you are
building the separate Team 9 Slack OAuth auth integration.

## Example

```bash
curl -X POST "$BASE_URL/chat/messages" \
  -H "Content-Type: application/json" \
  -H "X-Session-ID: $SESSION_ID" \
  -d '{"channel_id":"C1234567890","text":"hello from Slack provider"}'
```

Telegram-only routes are intentionally not reused for Slack:

- `POST /telegram/webhook`
- `GET /auth/login`
- `GET /auth/callback`

The `me` channel alias is also Telegram-only. Slack requests should use Slack
channel IDs such as `C1234567890`.

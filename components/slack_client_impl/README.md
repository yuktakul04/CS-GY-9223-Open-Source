# Slack Client Implementation

This component is imported from Team 9's Slack provider work:

- Team: Team 9, Slack provider
- Source: `components/slack_client_impl` from Team 9's HW3 PR #5
- PR: <https://github.com/HarshithKoriRaj/CS-GY-9223-Open-Source/pull/5>
- Local package: `components/slack_client_impl` as `slack-client-impl`

Team 4's primary provider remains Telegram. This package is included as optional
same-vertical demo support. It implements the shared
`chat_client_api.ChatClient` interface and registers itself when imported.
Configure the service with:

```bash
CHAT_CLIENT_PROVIDER=slack
SLACK_BOT_TOKEN=xoxb-...
CHAT_CLIENT_ALLOWED_CHANNEL_IDS=C1234567890
```

The generic `/chat/...` endpoints stay unchanged. Slack channel IDs are used as
`channel_id`, and Slack message IDs use `channel_id:timestamp`. Telegram-only
routes and the `me` alias are not reused for Slack.

This package does not include Team 9's standalone Slack OAuth auth flow. Team 4
keeps its existing Telegram-backed service auth for `/chat/...`; the Slack
provider uses `SLACK_BOT_TOKEN` as a server-side bot credential only.

# dockhand-mcp

An [MCP (Model Context Protocol)](https://modelcontextprotocol.io) server that exposes the [Dockhand](https://dockhand.pro) Docker management REST API as tools for LLMs such as Claude.

Runs as a Docker-hosted SSE server — deploy it once, connect any MCP client over HTTP.

**This is a fork of [markhaines/dockhand-mcp](https://github.com/markhaines/dockhand-mcp), patched to authenticate via Dockhand's native Bearer token API instead of a session cookie.** Tokens (`dh_...`, generated under Dockhand's Settings/Profile → API Tokens) don't expire by default, unlike a session cookie which requires periodic manual re-extraction from a browser.

## Features

- Manage **containers**: list, inspect, create, start, stop, restart, remove, get logs
- Manage **compose stacks**: list, create, start, stop, restart, remove
- Manage **Git stacks**: list, create, deploy
- Manage **images**: list, pull, push, remove, vulnerability scan
- Manage **volumes**: list, create, remove
- Manage **networks**: list, create, remove
- **Bulk operations**: batch start/stop/restart/remove across containers, images, volumes, networks, or stacks
- **Activity log and schedules**: inspect events and scheduled tasks
- All long-running operations return synchronous JSON results (no job-polling needed)

## Requirements

- Docker + Docker Compose
- A running [Dockhand](https://dockhand.pro) instance, version 1.0.26 or later if using token auth (token auth was introduced in 1.0.25 but had a bug affecting Enterprise licenses, fixed in 1.0.26)

## Deployment

**No pre-built image is published for this fork** — the upstream `ghcr.io/markhaines/dockhand-mcp:latest` image does not include the token-auth patch. Build locally instead:

```bash
git clone https://github.com/m3rrym4n/dockhand-mcp
cd dockhand-mcp
DOCKHAND_URL=http://your-dockhand-host:3000 \
DOCKHAND_TOKEN=dh_your_token_here \
docker compose up -d --build
```

## Configuration

| Variable | Default | Description |
|---|---|---|
| `DOCKHAND_URL` | `http://localhost:3000` | Base URL of your Dockhand instance |
| `DOCKHAND_TOKEN` | _(empty)_ | **Preferred.** Dockhand API token (`dh_...`), generated under Settings/Profile → API Tokens. Sent as `Authorization: Bearer <token>`. Does not expire unless you set an expiry when generating it. |
| `DOCKHAND_COOKIE` | _(empty)_ | Fallback only, used if `DOCKHAND_TOKEN` is not set. Session cookie for authenticated instances (e.g. `connect.sid=s%3A...`), extracted manually from browser DevTools and requiring periodic re-extraction as the session expires. |
| `PORT` | `8000` | Port the MCP server listens on |
| `ROOT_PATH` | _(empty)_ | Public path prefix when serving behind a reverse proxy sub-path (e.g. `/dockhand`) |

**Security note:** Dockhand tokens carry exactly the same permissions as the user account that generated them — there is no token-specific scoping. On Dockhand's free tier (no RBAC), every user is effectively admin, so a token is full-access regardless of which account created it. Using a dedicated, non-personal Dockhand account to generate the token still gives a clean, separately-identifiable audit trail, even though it doesn't reduce privilege on the free tier. Dockhand's Enterprise-tier RBAC would allow a genuinely restricted role/environment scope on the generating user, which the token would then inherit.

## Connecting to Claude

### Claude Desktop

Add this to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "dockhand": {
      "url": "http://your-server:8000/sse"
    }
  }
}
```

### Claude Code

```bash
claude mcp add --transport sse dockhand http://your-server:8000/sse
```

## Available Tools

| Category | Tool | Description |
|---|---|---|
| Environments | `list_environments` | List all configured Docker environments |
| Environments | `get_dashboard_stats` | Get CPU/memory/container stats |
| Containers | `list_containers` | List all containers |
| Containers | `get_container` | Inspect a container |
| Containers | `create_container` | Create a new container |
| Containers | `start_container` | Start a stopped container |
| Containers | `stop_container` | Stop a running container |
| Containers | `restart_container` | Restart a container |
| Containers | `remove_container` | Delete a container |
| Containers | `get_container_logs` | Fetch container logs |
| Bulk | `batch_operation` | Bulk start/stop/restart/remove |
| Stacks | `list_stacks` | List compose stacks |
| Stacks | `create_stack` | Create and deploy a stack |
| Stacks | `start_stack` | Start a stack |
| Stacks | `stop_stack` | Stop a stack |
| Stacks | `restart_stack` | Restart a stack |
| Stacks | `remove_stack` | Remove a stack |
| Git Stacks | `list_git_stacks` | List Git-backed stacks |
| Git Stacks | `create_git_stack` | Create a Git-backed stack |
| Git Stacks | `deploy_git_stack` | Deploy a Git stack |
| Images | `list_images` | List images |
| Images | `pull_image` | Pull an image |
| Images | `push_image` | Push an image |
| Images | `remove_image` | Remove an image |
| Images | `scan_image` | Vulnerability scan |
| Volumes | `list_volumes` | List volumes |
| Volumes | `create_volume` | Create a volume |
| Volumes | `remove_volume` | Remove a volume |
| Networks | `list_networks` | List networks |
| Networks | `create_network` | Create a network |
| Networks | `remove_network` | Remove a network |
| Activity | `get_activity` | Get container event log |
| Schedules | `list_schedules` | List scheduled tasks |

## Multi-environment support

Every tool accepts an optional `env` parameter (integer environment ID). Omit it to use the default environment, or pass the ID returned by `list_environments` to target a specific remote host.

## License

MIT

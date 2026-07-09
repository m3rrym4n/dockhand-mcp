"""
Dockhand MCP Server
Exposes Dockhand's REST API as Model Context Protocol tools.
Runs as an SSE HTTP server suitable for Docker deployment.
"""

import os
import json
import httpx
import uvicorn
from typing import Any
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp import types
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.routing import Mount, Route

# ── Configuration ─────────────────────────────────────────────────────────────
DOCKHAND_URL = os.environ.get("DOCKHAND_URL", "http://localhost:3000")
DOCKHAND_TOKEN = os.environ.get("DOCKHAND_TOKEN", "")
DOCKHAND_COOKIE = os.environ.get("DOCKHAND_COOKIE", "")
PORT = int(os.environ.get("PORT", "8000"))
ROOT_PATH = os.environ.get("ROOT_PATH", "").rstrip("/")

app = Server("dockhand")


# ── HTTP helpers ───────────────────────────────────────────────────────────────

def _headers() -> dict:
    h = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if DOCKHAND_TOKEN:
        h["Authorization"] = f"Bearer {DOCKHAND_TOKEN}"
    elif DOCKHAND_COOKIE:
        h["Cookie"] = DOCKHAND_COOKIE
    return h


def _get(path: str, params: dict | None = None) -> Any:
    url = f"{DOCKHAND_URL}{path}"
    r = httpx.get(url, headers=_headers(), params=params, timeout=60)
    r.raise_for_status()
    return r.json()


def _post(path: str, body: dict | None = None, params: dict | None = None) -> Any:
    url = f"{DOCKHAND_URL}{path}"
    r = httpx.post(url, headers=_headers(), json=body or {}, params=params, timeout=120)
    r.raise_for_status()
    return r.json()


def _delete(path: str, params: dict | None = None) -> Any:
    url = f"{DOCKHAND_URL}{path}"
    r = httpx.delete(url, headers=_headers(), params=params, timeout=60)
    r.raise_for_status()
    try:
        return r.json()
    except Exception:
        return {"success": True}


def _fmt(data: Any) -> str:
    return json.dumps(data, indent=2)


# ── Tool definitions ───────────────────────────────────────────────────────────

TOOLS: list[types.Tool] = [
    # ── Environments ──────────────────────────────────────────────────────────
    types.Tool(
        name="list_environments",
        description="List all configured Docker environments in Dockhand.",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    types.Tool(
        name="get_dashboard_stats",
        description="Get dashboard statistics (container counts, resource usage) for an environment.",
        inputSchema={
            "type": "object",
            "properties": {
                "env": {"type": "integer", "description": "Environment ID (omit for default)"},
            },
            "required": [],
        },
    ),

    # ── Containers ────────────────────────────────────────────────────────────
    types.Tool(
        name="list_containers",
        description="List all containers in an environment.",
        inputSchema={
            "type": "object",
            "properties": {
                "env": {"type": "integer", "description": "Environment ID"},
            },
            "required": [],
        },
    ),
    types.Tool(
        name="get_container",
        description="Get detailed information about a specific container.",
        inputSchema={
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Container ID or name"},
                "env": {"type": "integer", "description": "Environment ID"},
            },
            "required": ["id"],
        },
    ),
    types.Tool(
        name="create_container",
        description=(
            "Create (and optionally start) a new container. "
            "Provide at minimum an 'image' field in the body."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "env": {"type": "integer", "description": "Environment ID"},
                "image": {"type": "string", "description": "Image name and tag, e.g. nginx:latest"},
                "name": {"type": "string", "description": "Container name (optional)"},
                "command": {"type": "string", "description": "Override default command"},
                "ports": {
                    "type": "array",
                    "description": "Port mappings [{hostPort, containerPort, protocol}]",
                    "items": {"type": "object"},
                },
                "volumes": {
                    "type": "array",
                    "description": "Volume mounts [{source, target, readOnly}]",
                    "items": {"type": "object"},
                },
                "env_vars": {
                    "type": "object",
                    "description": "Environment variables as key-value pairs",
                },
                "network": {"type": "string", "description": "Network mode or name"},
                "restart_policy": {
                    "type": "string",
                    "enum": ["no", "always", "unless-stopped", "on-failure"],
                    "description": "Restart policy",
                },
                "cpu_limit": {"type": "number", "description": "CPU limit (e.g. 0.5)"},
                "memory_limit": {"type": "string", "description": "Memory limit (e.g. 512m, 1g)"},
            },
            "required": ["image"],
        },
    ),
    types.Tool(
        name="start_container",
        description="Start a stopped container.",
        inputSchema={
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Container ID or name"},
                "env": {"type": "integer", "description": "Environment ID"},
            },
            "required": ["id"],
        },
    ),
    types.Tool(
        name="stop_container",
        description="Stop a running container.",
        inputSchema={
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Container ID or name"},
                "env": {"type": "integer", "description": "Environment ID"},
            },
            "required": ["id"],
        },
    ),
    types.Tool(
        name="restart_container",
        description="Restart a container.",
        inputSchema={
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Container ID or name"},
                "env": {"type": "integer", "description": "Environment ID"},
            },
            "required": ["id"],
        },
    ),
    types.Tool(
        name="remove_container",
        description="Remove (delete) a container.",
        inputSchema={
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Container ID or name"},
                "env": {"type": "integer", "description": "Environment ID"},
            },
            "required": ["id"],
        },
    ),
    types.Tool(
        name="get_container_logs",
        description="Retrieve recent logs from a container.",
        inputSchema={
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Container ID or name"},
                "env": {"type": "integer", "description": "Environment ID"},
                "tail": {"type": "integer", "description": "Number of log lines to return (default 100)"},
            },
            "required": ["id"],
        },
    ),

    # ── Batch operations ──────────────────────────────────────────────────────
    types.Tool(
        name="batch_operation",
        description=(
            "Perform a bulk operation on multiple containers, images, volumes, networks, or stacks. "
            "operations: start | stop | restart | remove | pause | unpause"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "env": {"type": "integer", "description": "Environment ID"},
                "operation": {
                    "type": "string",
                    "enum": ["start", "stop", "restart", "remove", "pause", "unpause"],
                },
                "entityType": {
                    "type": "string",
                    "enum": ["containers", "images", "volumes", "networks", "stacks"],
                },
                "items": {
                    "type": "array",
                    "description": "Array of items, each with 'id' and optional 'name'",
                    "items": {"type": "object"},
                },
            },
            "required": ["operation", "entityType", "items"],
        },
    ),

    # ── Stacks ────────────────────────────────────────────────────────────────
    types.Tool(
        name="list_stacks",
        description="List all Docker Compose stacks.",
        inputSchema={
            "type": "object",
            "properties": {
                "env": {"type": "integer", "description": "Environment ID"},
            },
            "required": [],
        },
    ),
    types.Tool(
        name="create_stack",
        description="Create and deploy a new Docker Compose stack.",
        inputSchema={
            "type": "object",
            "properties": {
                "env": {"type": "integer", "description": "Environment ID"},
                "name": {"type": "string", "description": "Stack / Compose project name"},
                "composeContent": {"type": "string", "description": "Full docker-compose.yml content"},
                "envVars": {
                    "type": "object",
                    "description": "Environment variables as key-value pairs",
                },
            },
            "required": ["name", "composeContent"],
        },
    ),
    types.Tool(
        name="start_stack",
        description="Start (deploy) an existing stack.",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Stack name"},
                "env": {"type": "integer", "description": "Environment ID"},
            },
            "required": ["name"],
        },
    ),
    types.Tool(
        name="stop_stack",
        description="Stop all containers in a stack.",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Stack name"},
                "env": {"type": "integer", "description": "Environment ID"},
            },
            "required": ["name"],
        },
    ),
    types.Tool(
        name="restart_stack",
        description="Restart all containers in a stack.",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Stack name"},
                "env": {"type": "integer", "description": "Environment ID"},
            },
            "required": ["name"],
        },
    ),
    types.Tool(
        name="remove_stack",
        description="Remove a stack and all its containers.",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Stack name"},
                "env": {"type": "integer", "description": "Environment ID"},
            },
            "required": ["name"],
        },
    ),

    # ── Git stacks ────────────────────────────────────────────────────────────
    types.Tool(
        name="list_git_stacks",
        description="List all Git-backed stacks.",
        inputSchema={
            "type": "object",
            "properties": {
                "env": {"type": "integer", "description": "Environment ID"},
            },
            "required": [],
        },
    ),
    types.Tool(
        name="create_git_stack",
        description="Create a new Git-backed stack.",
        inputSchema={
            "type": "object",
            "properties": {
                "env": {"type": "integer", "description": "Environment ID"},
                "name": {"type": "string", "description": "Stack name"},
                "repository": {"type": "string", "description": "Git repository URL"},
                "branch": {"type": "string", "description": "Branch to track"},
                "composePath": {
                    "type": "string",
                    "description": "Path to compose file in repo (default: docker-compose.yml)",
                },
                "autoSync": {"type": "boolean", "description": "Enable automatic sync"},
            },
            "required": ["name", "repository"],
        },
    ),
    types.Tool(
        name="deploy_git_stack",
        description="Deploy (sync and redeploy) a Git stack.",
        inputSchema={
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Git stack ID"},
                "env": {"type": "integer", "description": "Environment ID"},
            },
            "required": ["id"],
        },
    ),

    # ── Images ────────────────────────────────────────────────────────────────
    types.Tool(
        name="list_images",
        description="List all Docker images in an environment.",
        inputSchema={
            "type": "object",
            "properties": {
                "env": {"type": "integer", "description": "Environment ID"},
            },
            "required": [],
        },
    ),
    types.Tool(
        name="pull_image",
        description="Pull a Docker image from a registry.",
        inputSchema={
            "type": "object",
            "properties": {
                "env": {"type": "integer", "description": "Environment ID"},
                "image": {"type": "string", "description": "Image name and tag, e.g. nginx:latest"},
                "registry": {"type": "string", "description": "Registry name (optional, defaults to Docker Hub)"},
            },
            "required": ["image"],
        },
    ),
    types.Tool(
        name="push_image",
        description="Push a Docker image to a configured registry.",
        inputSchema={
            "type": "object",
            "properties": {
                "env": {"type": "integer", "description": "Environment ID"},
                "image": {"type": "string", "description": "Image name and tag"},
                "registry": {"type": "string", "description": "Target registry name"},
                "tag": {"type": "string", "description": "New tag to apply (optional)"},
            },
            "required": ["image"],
        },
    ),
    types.Tool(
        name="remove_image",
        description="Remove a Docker image.",
        inputSchema={
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Image ID"},
                "env": {"type": "integer", "description": "Environment ID"},
            },
            "required": ["id"],
        },
    ),
    types.Tool(
        name="scan_image",
        description="Scan a Docker image for vulnerabilities using Grype/Trivy.",
        inputSchema={
            "type": "object",
            "properties": {
                "env": {"type": "integer", "description": "Environment ID"},
                "image": {"type": "string", "description": "Image name and tag"},
            },
            "required": ["image"],
        },
    ),

    # ── Volumes ───────────────────────────────────────────────────────────────
    types.Tool(
        name="list_volumes",
        description="List all Docker volumes in an environment.",
        inputSchema={
            "type": "object",
            "properties": {
                "env": {"type": "integer", "description": "Environment ID"},
            },
            "required": [],
        },
    ),
    types.Tool(
        name="create_volume",
        description="Create a new Docker volume.",
        inputSchema={
            "type": "object",
            "properties": {
                "env": {"type": "integer", "description": "Environment ID"},
                "name": {"type": "string", "description": "Volume name"},
                "driver": {"type": "string", "description": "Volume driver (default: local)"},
            },
            "required": ["name"],
        },
    ),
    types.Tool(
        name="remove_volume",
        description="Remove a Docker volume (fails if in use).",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Volume name"},
                "env": {"type": "integer", "description": "Environment ID"},
            },
            "required": ["name"],
        },
    ),

    # ── Networks ──────────────────────────────────────────────────────────────
    types.Tool(
        name="list_networks",
        description="List all Docker networks in an environment.",
        inputSchema={
            "type": "object",
            "properties": {
                "env": {"type": "integer", "description": "Environment ID"},
            },
            "required": [],
        },
    ),
    types.Tool(
        name="create_network",
        description="Create a new Docker network.",
        inputSchema={
            "type": "object",
            "properties": {
                "env": {"type": "integer", "description": "Environment ID"},
                "name": {"type": "string", "description": "Network name"},
                "driver": {
                    "type": "string",
                    "enum": ["bridge", "host", "overlay", "macvlan", "none"],
                    "description": "Network driver (default: bridge)",
                },
                "subnet": {"type": "string", "description": "CIDR subnet, e.g. 172.20.0.0/16"},
                "gateway": {"type": "string", "description": "Gateway IP address"},
                "internal": {"type": "boolean", "description": "Restrict external access"},
                "attachable": {"type": "boolean", "description": "Allow manual container attachment"},
            },
            "required": ["name"],
        },
    ),
    types.Tool(
        name="remove_network",
        description="Remove a Docker network.",
        inputSchema={
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Network ID"},
                "env": {"type": "integer", "description": "Environment ID"},
            },
            "required": ["id"],
        },
    ),

    # ── Activity & Schedules ──────────────────────────────────────────────────
    types.Tool(
        name="get_activity",
        description="Get the container activity / event log.",
        inputSchema={
            "type": "object",
            "properties": {
                "env": {"type": "integer", "description": "Environment ID"},
            },
            "required": [],
        },
    ),
    types.Tool(
        name="list_schedules",
        description="List all scheduled tasks (auto-updates, Git syncs, cleanup jobs).",
        inputSchema={
            "type": "object",
            "properties": {
                "env": {"type": "integer", "description": "Environment ID"},
            },
            "required": [],
        },
    ),
]


# ── Tool handler ───────────────────────────────────────────────────────────────

@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return TOOLS


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    env = arguments.get("env")
    params = {"env": env} if env is not None else {}

    try:
        result: Any = None

        # ── Environments ──────────────────────────────────────────────────────
        if name == "list_environments":
            result = _get("/api/environments")

        elif name == "get_dashboard_stats":
            result = _get("/api/dashboard/stats", params=params)

        # ── Containers ────────────────────────────────────────────────────────
        elif name == "list_containers":
            result = _get("/api/containers", params=params)

        elif name == "get_container":
            result = _get(f"/api/containers/{arguments['id']}", params=params)

        elif name == "create_container":
            body = {"image": arguments["image"]}
            for key in ("name", "command", "ports", "volumes", "env_vars",
                        "network", "restart_policy", "cpu_limit", "memory_limit"):
                if key in arguments:
                    body[key] = arguments[key]
            result = _post("/api/containers", body=body, params=params)

        elif name == "start_container":
            result = _post(f"/api/containers/{arguments['id']}/start", params=params)

        elif name == "stop_container":
            result = _post(f"/api/containers/{arguments['id']}/stop", params=params)

        elif name == "restart_container":
            result = _post(f"/api/containers/{arguments['id']}/restart", params=params)

        elif name == "remove_container":
            result = _delete(f"/api/containers/{arguments['id']}", params=params)

        elif name == "get_container_logs":
            tail = arguments.get("tail", 100)
            log_params = {**params, "tail": tail}
            result = _get(f"/api/containers/{arguments['id']}/logs", params=log_params)

        # ── Batch ─────────────────────────────────────────────────────────────
        elif name == "batch_operation":
            body = {
                "operation": arguments["operation"],
                "entityType": arguments["entityType"],
                "items": arguments["items"],
            }
            result = _post("/api/batch", body=body, params=params)

        # ── Stacks ────────────────────────────────────────────────────────────
        elif name == "list_stacks":
            result = _get("/api/stacks", params=params)

        elif name == "create_stack":
            body = {
                "name": arguments["name"],
                "composeContent": arguments["composeContent"],
            }
            if "envVars" in arguments:
                body["envVars"] = arguments["envVars"]
            result = _post("/api/stacks", body=body, params=params)

        elif name == "start_stack":
            result = _post(f"/api/stacks/{arguments['name']}/start", params=params)

        elif name == "stop_stack":
            result = _post(f"/api/stacks/{arguments['name']}/stop", params=params)

        elif name == "restart_stack":
            result = _post(f"/api/stacks/{arguments['name']}/restart", params=params)

        elif name == "remove_stack":
            result = _delete(f"/api/stacks/{arguments['name']}", params=params)

        # ── Git stacks ────────────────────────────────────────────────────────
        elif name == "list_git_stacks":
            result = _get("/api/git/stacks", params=params)

        elif name == "create_git_stack":
            body = {
                "name": arguments["name"],
                "repository": arguments["repository"],
            }
            for key in ("branch", "composePath", "autoSync"):
                if key in arguments:
                    body[key] = arguments[key]
            result = _post("/api/git/stacks", body=body, params=params)

        elif name == "deploy_git_stack":
            result = _post(f"/api/git/stacks/{arguments['id']}/deploy", params=params)

        # ── Images ────────────────────────────────────────────────────────────
        elif name == "list_images":
            result = _get("/api/images", params=params)

        elif name == "pull_image":
            body = {"image": arguments["image"]}
            if "registry" in arguments:
                body["registry"] = arguments["registry"]
            result = _post("/api/images/pull", body=body, params=params)

        elif name == "push_image":
            body = {"image": arguments["image"]}
            for key in ("registry", "tag"):
                if key in arguments:
                    body[key] = arguments[key]
            result = _post("/api/images/push", body=body, params=params)

        elif name == "remove_image":
            result = _delete(f"/api/images/{arguments['id']}", params=params)

        elif name == "scan_image":
            body = {"image": arguments["image"]}
            result = _post("/api/images/scan", body=body, params=params)

        # ── Volumes ───────────────────────────────────────────────────────────
        elif name == "list_volumes":
            result = _get("/api/volumes", params=params)

        elif name == "create_volume":
            body = {"name": arguments["name"]}
            if "driver" in arguments:
                body["driver"] = arguments["driver"]
            result = _post("/api/volumes", body=body, params=params)

        elif name == "remove_volume":
            result = _delete(f"/api/volumes/{arguments['name']}", params=params)

        # ── Networks ──────────────────────────────────────────────────────────
        elif name == "list_networks":
            result = _get("/api/networks", params=params)

        elif name == "create_network":
            body = {"name": arguments["name"]}
            for key in ("driver", "subnet", "gateway", "internal", "attachable"):
                if key in arguments:
                    body[key] = arguments[key]
            result = _post("/api/networks", body=body, params=params)

        elif name == "remove_network":
            result = _delete(f"/api/networks/{arguments['id']}", params=params)

        # ── Activity & Schedules ──────────────────────────────────────────────
        elif name == "get_activity":
            result = _get("/api/activity", params=params)

        elif name == "list_schedules":
            result = _get("/api/schedules", params=params)

        else:
            return [types.TextContent(type="text", text=f"Unknown tool: {name}")]

        return [types.TextContent(type="text", text=_fmt(result))]

    except httpx.HTTPStatusError as e:
        msg = f"HTTP {e.response.status_code}: {e.response.text}"
        return [types.TextContent(type="text", text=msg)]
    except Exception as e:
        return [types.TextContent(type="text", text=f"Error: {e}")]


# ── SSE transport & Starlette app ──────────────────────────────────────────────

sse = SseServerTransport(f"{ROOT_PATH}/messages/")


async def handle_sse(request: Request):
    async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
        await app.run(streams[0], streams[1], app.create_initialization_options())


starlette_app = Starlette(
    routes=[
        Route("/sse", endpoint=handle_sse),
        Mount("/messages/", app=sse.handle_post_message),
    ]
)


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    uvicorn.run(starlette_app, host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()

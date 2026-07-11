"""
Dockhand MCP Server
Exposes Dockhand's REST API as Model Context Protocol tools.
Runs as a Streamable HTTP server suitable for Docker deployment.
"""

import os
import json
from contextlib import asynccontextmanager
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

# ── Configuration ─────────────────────────────────────────────────────────────
DEFAULT_MCP_ALLOWED_HOSTS = "localhost,127.0.0.1,192.168.1.68,192.168.1.79"
DOCKHAND_URL = os.environ.get("DOCKHAND_URL", "http://localhost:3000")
DOCKHAND_TOKEN = os.environ.get("DOCKHAND_TOKEN", "")
DOCKHAND_COOKIE = os.environ.get("DOCKHAND_COOKIE", "")
MCP_ALLOWED_HOSTS = os.environ.get("MCP_ALLOWED_HOSTS", DEFAULT_MCP_ALLOWED_HOSTS)
PORT = int(os.environ.get("PORT", "8000"))
ROOT_PATH = os.environ.get("ROOT_PATH", "").rstrip("/")


def _parse_allowed_hosts(value: str) -> list[str]:
    hosts: list[str] = []
    seen: set[str] = set()

    for raw_host in value.split(","):
        host = raw_host.strip()
        if not host or host in seen:
            continue

        hosts.append(host)
        seen.add(host)

        if ":" not in host:
            wildcard_port_host = f"{host}:*"
            if wildcard_port_host not in seen:
                hosts.append(wildcard_port_host)
                seen.add(wildcard_port_host)

    return hosts


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


def _call(fn, *args, **kwargs) -> str:
    """Run an HTTP helper and format the result, with uniform error handling for every tool."""
    try:
        return _fmt(fn(*args, **kwargs))
    except httpx.HTTPStatusError as e:
        return f"HTTP {e.response.status_code}: {e.response.text}"
    except Exception as e:
        return f"Error: {e}"


def _env_params(env: int | None) -> dict:
    return {"env": env} if env is not None else {}


# ── MCP server (Streamable HTTP) ────────────────────────────────────────────

mcp = FastMCP(
    "dockhand",
    stateless_http=True,
    streamable_http_path="/",
    transport_security=TransportSecuritySettings(
        allowed_hosts=_parse_allowed_hosts(MCP_ALLOWED_HOSTS),
    ),
)


# ── Environments ─────────────────────────────────────────────────────────────

@mcp.tool()
def list_environments() -> str:
    """List all configured Docker environments in Dockhand."""
    return _call(_get, "/api/environments")


@mcp.tool()
def get_dashboard_stats(env: int | None = None) -> str:
    """Get dashboard statistics (container counts, resource usage) for an environment."""
    return _call(_get, "/api/dashboard/stats", params=_env_params(env))


# ── Containers ───────────────────────────────────────────────────────────────

@mcp.tool()
def list_containers(env: int | None = None) -> str:
    """List all containers in an environment."""
    return _call(_get, "/api/containers", params=_env_params(env))


@mcp.tool()
def get_container(id: str, env: int | None = None) -> str:
    """Get detailed information about a specific container."""
    return _call(_get, f"/api/containers/{id}", params=_env_params(env))


@mcp.tool()
def create_container(
    image: str,
    env: int | None = None,
    name: str | None = None,
    command: str | None = None,
    ports: list | None = None,
    volumes: list | None = None,
    env_vars: dict | None = None,
    network: str | None = None,
    restart_policy: str | None = None,
    cpu_limit: float | None = None,
    memory_limit: str | None = None,
) -> str:
    """Create (and optionally start) a new container. Provide at minimum an 'image'.

    restart_policy must be one of: no, always, unless-stopped, on-failure.
    ports: list of {hostPort, containerPort, protocol}.
    volumes: list of {source, target, readOnly}.
    """
    body: dict[str, Any] = {"image": image}
    for key, value in (
        ("name", name), ("command", command), ("ports", ports), ("volumes", volumes),
        ("env_vars", env_vars), ("network", network), ("restart_policy", restart_policy),
        ("cpu_limit", cpu_limit), ("memory_limit", memory_limit),
    ):
        if value is not None:
            body[key] = value
    return _call(_post, "/api/containers", body=body, params=_env_params(env))


@mcp.tool()
def start_container(id: str, env: int | None = None) -> str:
    """Start a stopped container."""
    return _call(_post, f"/api/containers/{id}/start", params=_env_params(env))


@mcp.tool()
def stop_container(id: str, env: int | None = None) -> str:
    """Stop a running container."""
    return _call(_post, f"/api/containers/{id}/stop", params=_env_params(env))


@mcp.tool()
def restart_container(id: str, env: int | None = None) -> str:
    """Restart a container."""
    return _call(_post, f"/api/containers/{id}/restart", params=_env_params(env))


@mcp.tool()
def remove_container(id: str, env: int | None = None) -> str:
    """Remove (delete) a container."""
    return _call(_delete, f"/api/containers/{id}", params=_env_params(env))


@mcp.tool()
def get_container_logs(id: str, env: int | None = None, tail: int = 100) -> str:
    """Retrieve recent logs from a container."""
    params = {**_env_params(env), "tail": tail}
    return _call(_get, f"/api/containers/{id}/logs", params=params)


# ── Batch operations ──────────────────────────────────────────────────────────

@mcp.tool()
def batch_operation(operation: str, entityType: str, items: list, env: int | None = None) -> str:
    """Perform a bulk operation on multiple containers, images, volumes, networks, or stacks.

    operation must be one of: start, stop, restart, remove, pause, unpause.
    entityType must be one of: containers, images, volumes, networks, stacks.
    items: array of objects, each with 'id' and optional 'name'.
    """
    body = {"operation": operation, "entityType": entityType, "items": items}
    return _call(_post, "/api/batch", body=body, params=_env_params(env))


# ── Stacks ────────────────────────────────────────────────────────────────────

@mcp.tool()
def list_stacks(env: int | None = None) -> str:
    """List all Docker Compose stacks."""
    return _call(_get, "/api/stacks", params=_env_params(env))


@mcp.tool()
def create_stack(name: str, composeContent: str, envVars: dict | None = None, env: int | None = None) -> str:
    """Create and deploy a new Docker Compose stack."""
    body: dict[str, Any] = {"name": name, "composeContent": composeContent}
    if envVars is not None:
        body["envVars"] = envVars
    return _call(_post, "/api/stacks", body=body, params=_env_params(env))


@mcp.tool()
def start_stack(name: str, env: int | None = None) -> str:
    """Start (deploy) an existing stack."""
    return _call(_post, f"/api/stacks/{name}/start", params=_env_params(env))


@mcp.tool()
def stop_stack(name: str, env: int | None = None) -> str:
    """Stop all containers in a stack."""
    return _call(_post, f"/api/stacks/{name}/stop", params=_env_params(env))


@mcp.tool()
def restart_stack(name: str, env: int | None = None) -> str:
    """Restart all containers in a stack."""
    return _call(_post, f"/api/stacks/{name}/restart", params=_env_params(env))


@mcp.tool()
def remove_stack(name: str, env: int | None = None) -> str:
    """Remove a stack and all its containers."""
    return _call(_delete, f"/api/stacks/{name}", params=_env_params(env))


# ── Git stacks ────────────────────────────────────────────────────────────────

@mcp.tool()
def list_git_stacks(env: int | None = None) -> str:
    """List all Git-backed stacks."""
    return _call(_get, "/api/git/stacks", params=_env_params(env))


@mcp.tool()
def create_git_stack(
    name: str,
    repository: str,
    branch: str | None = None,
    composePath: str | None = None,
    autoSync: bool | None = None,
    env: int | None = None,
) -> str:
    """Create a new Git-backed stack."""
    body: dict[str, Any] = {"name": name, "repository": repository}
    for key, value in (("branch", branch), ("composePath", composePath), ("autoSync", autoSync)):
        if value is not None:
            body[key] = value
    return _call(_post, "/api/git/stacks", body=body, params=_env_params(env))


@mcp.tool()
def deploy_git_stack(id: str, env: int | None = None) -> str:
    """Deploy (sync and redeploy) a Git stack."""
    return _call(_post, f"/api/git/stacks/{id}/deploy", params=_env_params(env))


# ── Images ────────────────────────────────────────────────────────────────────

@mcp.tool()
def list_images(env: int | None = None) -> str:
    """List all Docker images in an environment."""
    return _call(_get, "/api/images", params=_env_params(env))


@mcp.tool()
def pull_image(image: str, registry: str | None = None, env: int | None = None) -> str:
    """Pull a Docker image from a registry."""
    body: dict[str, Any] = {"image": image}
    if registry is not None:
        body["registry"] = registry
    return _call(_post, "/api/images/pull", body=body, params=_env_params(env))


@mcp.tool()
def push_image(image: str, registry: str | None = None, tag: str | None = None, env: int | None = None) -> str:
    """Push a Docker image to a configured registry."""
    body: dict[str, Any] = {"image": image}
    for key, value in (("registry", registry), ("tag", tag)):
        if value is not None:
            body[key] = value
    return _call(_post, "/api/images/push", body=body, params=_env_params(env))


@mcp.tool()
def remove_image(id: str, env: int | None = None) -> str:
    """Remove a Docker image."""
    return _call(_delete, f"/api/images/{id}", params=_env_params(env))


@mcp.tool()
def scan_image(image: str, env: int | None = None) -> str:
    """Scan a Docker image for vulnerabilities using Grype/Trivy."""
    body = {"image": image}
    return _call(_post, "/api/images/scan", body=body, params=_env_params(env))


# ── Volumes ───────────────────────────────────────────────────────────────────

@mcp.tool()
def list_volumes(env: int | None = None) -> str:
    """List all Docker volumes in an environment."""
    return _call(_get, "/api/volumes", params=_env_params(env))


@mcp.tool()
def create_volume(name: str, driver: str | None = None, env: int | None = None) -> str:
    """Create a new Docker volume."""
    body: dict[str, Any] = {"name": name}
    if driver is not None:
        body["driver"] = driver
    return _call(_post, "/api/volumes", body=body, params=_env_params(env))


@mcp.tool()
def remove_volume(name: str, env: int | None = None) -> str:
    """Remove a Docker volume (fails if in use)."""
    return _call(_delete, f"/api/volumes/{name}", params=_env_params(env))


# ── Networks ──────────────────────────────────────────────────────────────────

@mcp.tool()
def list_networks(env: int | None = None) -> str:
    """List all Docker networks in an environment."""
    return _call(_get, "/api/networks", params=_env_params(env))


@mcp.tool()
def create_network(
    name: str,
    driver: str | None = None,
    subnet: str | None = None,
    gateway: str | None = None,
    internal: bool | None = None,
    attachable: bool | None = None,
    env: int | None = None,
) -> str:
    """Create a new Docker network.

    driver must be one of: bridge, host, overlay, macvlan, none (defaults to bridge).
    """
    body: dict[str, Any] = {"name": name}
    for key, value in (
        ("driver", driver), ("subnet", subnet), ("gateway", gateway),
        ("internal", internal), ("attachable", attachable),
    ):
        if value is not None:
            body[key] = value
    return _call(_post, "/api/networks", body=body, params=_env_params(env))


@mcp.tool()
def remove_network(id: str, env: int | None = None) -> str:
    """Remove a Docker network."""
    return _call(_delete, f"/api/networks/{id}", params=_env_params(env))


# ── Activity & Schedules ──────────────────────────────────────────────────────

@mcp.tool()
def get_activity(env: int | None = None) -> str:
    """Get the container activity / event log."""
    return _call(_get, "/api/activity", params=_env_params(env))


@mcp.tool()
def list_schedules(env: int | None = None) -> str:
    """List all scheduled tasks (auto-updates, Git syncs, cleanup jobs)."""
    return _call(_get, "/api/schedules", params=_env_params(env))


# ── ASGI app & entry point ───────────────────────────────────────────────────

mcp_app = mcp.streamable_http_app()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with mcp.session_manager.run():
        yield


app = FastAPI(title="dockhand-mcp", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"service": "dockhand-mcp", "status": "ok"}


app.mount(f"{ROOT_PATH}/mcp", mcp_app)


def main():
    uvicorn.run(app, host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()

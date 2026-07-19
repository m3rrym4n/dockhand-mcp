"""Opt-in integration coverage for create_container.

Run with a disposable named volume available on the target Docker host:
    DOCKHAND_LIVE_TEST=1 DOCKHAND_URL=... DOCKHAND_TOKEN=... \
      pytest -m live tests/test_create_container_live.py
"""

import json
import os
import uuid

import pytest

from dockhand_mcp.server import (
    create_container,
    create_volume,
    get_container,
    remove_container,
    remove_volume,
)


pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.getenv("DOCKHAND_LIVE_TEST") != "1",
        reason="set DOCKHAND_LIVE_TEST=1 to run against Dockhand",
    ),
]


def test_create_container_fields_end_to_end():
    name = f"dockhand-mcp-test-{uuid.uuid4().hex[:8]}"
    volume_name = f"{name}-volume"
    json.loads(create_volume(volume_name))
    container_id = None
    try:
        created = json.loads(
            create_container(
                image="alpine:3.22",
                name=name,
                command=["sleep", "3600"],
                ports=[{"hostPort": 0, "containerPort": 8080, "protocol": "tcp"}],
                volumes=[{"source": volume_name, "target": "/data", "readOnly": True}],
                env_vars={"DOCKHAND_MCP_TEST": "true"},
                network="bridge",
                restart_policy="no",
                memory_limit="64m",
                cpu_limit=0.25,
            )
        )
        container_id = created.get("id") or created.get("Id")
        assert container_id, created

        inspected = json.loads(get_container(container_id))
        config = inspected.get("Config", inspected.get("config", {}))
        host_config = inspected.get("HostConfig", inspected.get("hostConfig", {}))
        assert config["Cmd"] == ["sleep", "3600"]
        assert "DOCKHAND_MCP_TEST=true" in config["Env"]
        assert host_config["RestartPolicy"]["Name"] == "no"
        assert host_config["Memory"] == 64 * 1024**2
        assert host_config["NanoCpus"] == 250_000_000
        assert host_config["NetworkMode"] == "bridge"
        assert host_config["Binds"] == [f"{volume_name}:/data:ro"]
        assert host_config["PortBindings"]["8080/tcp"] == [{"HostIp": "", "HostPort": "0"}]
        mounts = inspected.get("Mounts", inspected.get("mounts", []))
        assert any(mount["Name"] == volume_name and mount["Destination"] == "/data" for mount in mounts)
    finally:
        if container_id:
            remove_container(container_id)
        remove_volume(volume_name)

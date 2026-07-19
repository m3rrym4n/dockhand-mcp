import json
from unittest.mock import patch

import pytest

from dockhand_mcp.server import _parse_memory_to_bytes, create_container


def _create_container(**kwargs):
    with patch("dockhand_mcp.server._post", return_value={"id": "created"}) as post:
        result = create_container(**kwargs)
    assert json.loads(result) == {"id": "created"}
    return post.call_args


def test_create_container_translates_all_friendly_fields():
    call = _create_container(
        image="alpine:3.22",
        env=7,
        name="translated",
        command='sh -c "sleep 3600"',
        ports=[
            {"hostPort": 8080, "containerPort": 80},
            {
                "hostPort": "8443",
                "containerPort": 443,
                "protocol": "udp",
                "hostIp": "127.0.0.1",
            },
        ],
        volumes=[
            {"source": "test-vol", "target": "/data"},
            {"source": "/host/config", "target": "/config", "readOnly": True},
        ],
        env_vars={"MODE": "test", "COUNT": 2},
        network="bridge",
        restart_policy="unless-stopped",
        cpu_limit=1.5,
        memory_limit="512m",
    )

    assert call.args == ("/api/containers",)
    assert call.kwargs == {
        "body": {
            "image": "alpine:3.22",
            "name": "translated",
            "cmd": ["sh", "-c", "sleep 3600"],
            "ports": {
                "80/tcp": {"HostPort": "8080"},
                "443/udp": {"HostPort": "8443", "HostIp": "127.0.0.1"},
            },
            "volumeBinds": [
                "test-vol:/data:rw",
                "/host/config:/config:ro",
            ],
            "env": ["MODE=test", "COUNT=2"],
            "networkMode": "bridge",
            "restartPolicy": "unless-stopped",
            "nanoCpus": 1_500_000_000,
            "memory": 536_870_912,
        },
        "params": {"env": 7},
    }


def test_create_container_keeps_list_command_and_omits_unset_fields():
    call = _create_container(image="busybox", command=["sleep", "10"])
    assert call.kwargs == {
        "body": {"image": "busybox", "cmd": ["sleep", "10"]},
        "params": {},
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [("1024", 1024), ("1k", 1024), ("1.5MB", 1_572_864), ("2g", 2_147_483_648)],
)
def test_parse_memory_to_bytes(value, expected):
    assert _parse_memory_to_bytes(value) == expected


@pytest.mark.parametrize("value", ["", "lots", "-1m", "1p"])
def test_parse_memory_to_bytes_rejects_invalid_values(value):
    with pytest.raises(ValueError, match="memory_limit"):
        _parse_memory_to_bytes(value)

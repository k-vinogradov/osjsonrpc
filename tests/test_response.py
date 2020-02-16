import json
import pytest
from tests.common import Request


@pytest.mark.asyncio
async def test_ping(endpoint):
    request = Request(
        {"Content-Type": "application/json", "Accept": "application/json"},
        json.dumps({"jsonrpc": "2.0", "method": "ping", "id": 1}),
    )
    response = json.loads((await endpoint.handle_request(request)).text)
    assert response == {"jsonrpc": "2.0", "result": "pong", "id": 1}


@pytest.mark.asyncio
async def test_renamed_method(endpoint):
    request = Request(
        {"Content-Type": "application/json", "Accept": "application/json"},
        json.dumps({"jsonrpc": "2.0", "method": "ping_renamed", "id": 1}),
    )
    response = json.loads((await endpoint.handle_request(request)).text)
    assert response == {"jsonrpc": "2.0", "result": "pong", "id": 1}


@pytest.mark.asyncio
async def test_positional_args(endpoint):
    request = Request(
        {"Content-Type": "application/json", "Accept": "application/json"},
        json.dumps({"jsonrpc": "2.0", "method": "mirror", "params": [1, 2, 3, "test"], "id": 1}),
    )
    response = json.loads((await endpoint.handle_request(request)).text)
    assert response == {
        "jsonrpc": "2.0",
        "result": {"args": [1, 2, 3, "test"], "kwargs": {}},
        "id": 1,
    }


@pytest.mark.asyncio
async def test_keywords_args(endpoint):
    request = Request(
        {"Content-Type": "application/json", "Accept": "application/json"},
        json.dumps(
            {
                "jsonrpc": "2.0",
                "method": "mirror",
                "params": {"key1": 1, "key2": 2, 3: "test"},
                "id": 1,
            }
        ),
    )
    response = json.loads((await endpoint.handle_request(request)).text)
    assert response == {
        "jsonrpc": "2.0",
        "result": {"args": [], "kwargs": {"3": "test", "key1": 1, "key2": 2}},
        "id": 1,
    }

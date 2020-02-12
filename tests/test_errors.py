import json
import pytest
from aiohttp import web


class Request:
    def __init__(self, headers, json_data):
        self.headers = headers
        self.json_data = json_data

    async def json(self):
        return json.loads(self.json_data)


def check_error(response: web.Response, expected_code):
    __tracebackhide__ = True  # pylint: disable=unused-variable

    assert response.status == 200, "HTTP status code 200 is expected"

    content = json.loads(response.text)
    assert content["jsonrpc"] == "2.0", "Invalid response protocol version"
    assert "error" in content, "'error' field MUST be presented"
    assert "result" not in content, "'result' field MUSTN'T be presented"
    assert content["error"]["code"] == expected_code, f"{expected_code} error code is expected"


@pytest.mark.asyncio
async def test_invalid_content_type(endpoint):
    """
    Check if the handler raises HTTPUnsupportedMediaType
    if the header Content-Type doesn't contain 'application/json'
    """
    request = Request({"Content-Type": "text/html", "Accept": "application/json"}, "")
    with pytest.raises(web.HTTPUnsupportedMediaType):
        await endpoint.handler(request)


@pytest.mark.asyncio
async def test_invalid_json(endpoint):
    request = Request(
        {"Content-Type": "application/json", "Accept": "application/json"}, "invalid_json_string",
    )
    check_error(await endpoint.handler(request), -32700)


@pytest.mark.asyncio
async def test_invalid_request(endpoint):
    request = Request(
        {"Content-Type": "application/json", "Accept": "application/json"}, '{"key": "value"}',
    )
    check_error(await endpoint.handler(request), -32600)


@pytest.mark.asyncio
async def test_invalid_params(endpoint):
    request = Request(
        {"Content-Type": "application/json", "Accept": "application/json"},
        json.dumps({"jsonrpc": "2.0", "method": "ping", "params": {"option": "value"}, "id": 1}),
    )
    check_error(await endpoint.handler(request), -32602)

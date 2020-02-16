import pytest
from aiohttp import web, ClientSession

HOST = "localhost"
PORT = 8080
PATH = "/api"


@pytest.fixture
async def service(endpoint):
    app = web.Application()
    app.add_routes([endpoint.route(PATH)])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, HOST, PORT)
    await site.start()

    yield f"http://{HOST}:{PORT}{PATH}"

    await runner.cleanup()


@pytest.mark.asyncio
async def test_ping(service):  # pylint: disable=redefined-outer-name
    async with ClientSession() as session:
        async with session.post(
            service,
            json={"jsonrpc": "2.0", "method": "ping", "id": 100},
            headers={"content-type": "application/json", "accept": "application/json"},
        ) as resp:
            assert resp.status == 200
            assert (await resp.json())["result"] == "pong"

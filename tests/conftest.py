import pytest
from osjsonrpc import JsonRpcEndpoint


async def ping():
    return "pong"


@pytest.fixture
def endpoint():
    rpc = JsonRpcEndpoint()
    rpc.register_method(ping)
    return rpc

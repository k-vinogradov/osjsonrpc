import pytest
from osjsonrpc import JsonRpcEndpoint


async def ping():
    return "pong"


async def mirror(*args, **kwargs):
    return {"args": args, "kwargs": kwargs}


@pytest.fixture
def endpoint():
    rpc = JsonRpcEndpoint()
    rpc.register_method(ping)
    rpc.register_method(mirror)
    rpc.register_method(ping, name="ping_renamed")
    return rpc

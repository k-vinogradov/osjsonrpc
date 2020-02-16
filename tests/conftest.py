import pytest
from osjsonrpc import JsonRpcEndpoint


async def ping():
    return "pong"


async def mirror(*args, **kwargs):
    return {"args": args, "kwargs": kwargs}


@pytest.fixture
def endpoint():
    return (
        JsonRpcEndpoint()
        .register_method(ping)
        .register_method(mirror)
        .register_method(ping, name="ping_renamed")
    )

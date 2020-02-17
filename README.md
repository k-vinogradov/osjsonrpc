# Over-Simple JSON RPC Implementation

Over-simple [JSON-RPC](https://www.jsonrpc.org/specification) Python implementation for aiohttp

## Install

    pip install osjsonrpc

## Usage

Example:

```python
from aiohttp import web
from osjsonrpc import JsonRpcEndpoint

def ping():
    return "pong"

def multiply(a, b):
    return {"a": a, "b": b, "a*b": a * b}

rpc = (
    JsonRpcEndpoint()
    .register_method(ping)
    .register_method(multiply)
)

app = web.Application()
app.add_routes([rpc.route("/api")])
web.run_app(app)
```

Call the `ping` method without arguments:

    ~ curl -s -H "Content-Type: application/json" -H "Accept: application/json" -X POST \
      -d '{"jsonrpc":"2.0", "method": "ping", "id": 1}' \
      http://localhost:8080/api | jq

    {
      "jsonrpc": "2.0",
      "result": "pong",
      "id": 1
    }

Call the `multiply` with a couple of positional arguments:

    ~ curl -s -H "Content-Type: application/json" -H "Accept: application/json" -X POST \
      -d '{"jsonrpc":"2.0", "method": "multiply", "params": [3, 5], "id": 1}' \
      http://localhost:8080/api | jq

    {
      "jsonrpc": "2.0",
      "result": {
        "a": 3,
        "b": 5,
        "a*b": 15
      },
      "id": 1
    }

Call the `ping` argument with invalid keyword argument:

    ~ curl -s -H "Content-Type: application/json" -H "Accept: application/json" -X POST \
      -d '{"jsonrpc":"2.0", "method": "ping", "params": {"key": "value"}, "id": 1}' \
      http://localhost:8080/api | jq

    {
      "jsonrpc": "2.0",
      "error": {
        "code": -32602,
        "message": "Invalid params",
        "data": {
          "detail": "TypeError: ping() got an unexpected keyword argument 'key'",
          "request": {
            "jsonrpc": "2.0",
            "method": "ping",
            "params": {
              "key": "value"
            },
            "id": 1
          }
        }
      },
      "id": 1
    }

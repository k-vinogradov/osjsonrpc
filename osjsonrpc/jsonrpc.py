import json
from enum import Enum
from typing import Callable, Union, Any
from aiohttp import web


PROTOCOL_VERSION = "2.0"

UNKNOWN_ERROR = "Unknown Error"


class Errors(Enum):
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603

    def message(self) -> str:
        return ERROR_MESSAGES.get(self, UNKNOWN_ERROR)


ERROR_MESSAGES = {
    Errors.PARSE_ERROR: "Parse error",
    Errors.INVALID_REQUEST: "Invalid request",
    Errors.METHOD_NOT_FOUND: "Method not found",
    Errors.INVALID_PARAMS: "Invalid params",
    Errors.INTERNAL_ERROR: "Internal error",
}


class JsonRpcError(RuntimeError):
    def __init__(
        self,
        code: Union[Errors, int] = Errors.INTERNAL_ERROR,
        message: str = None,
        data: Any = None,
        rid: Union[int, str] = None,
    ):
        super().__init__()
        self.code = code  # type: Errors
        if isinstance(code, Errors):
            self.message = message or code.message()
        else:
            self.message = message or UNKNOWN_ERROR
        self.data = data
        self.rid = rid

    def error_content(self) -> dict:
        if isinstance(self.code, Errors):
            code = self.code.value
        else:
            code = self.code
        content = {"code": code, "message": self.message}
        if self.data:
            content["data"] = self.data
        return content

    def response_content(self) -> dict:
        content = {
            "jsonrpc": PROTOCOL_VERSION,
            "error": self.error_content(),
        }
        if self.rid:
            content["id"] = self.rid
        return content

    def http_response(self) -> web.Response:
        return web.json_response(self.response_content())


class JsonRpcEndpoint:
    def __init__(self):
        self.methods = {}
        self.docs = {}

    async def handler(self, request: web.Request) -> web.Response:

        try:
            # Check if the Content-Type and Accept headers both are presented
            # and contain 'application/json'

            if request.headers["Content-Type"] != "application/json":
                raise web.HTTPUnsupportedMediaType(reason="Invalid Content-Type")
            if request.headers["Accept"] != "application/json":
                raise web.HTTPNotAcceptable(reason="Invalid Accept header")
        except KeyError as exp:
            raise web.HTTPNotAcceptable(reason=f"'{exp.args[0]}' header is required")

        try:
            request_data = await request.json()
        except json.JSONDecodeError:
            return JsonRpcError(Errors.PARSE_ERROR).http_response()

        try:
            if isinstance(request_data, list):
                return web.json_response(await self.process_batch_rpc(request_data))
            return web.json_response(await self.process_single_rpc(request_data))
        except JsonRpcError as exp:
            return exp.http_response()

    async def process_single_rpc(self, rpc_data: dict) -> dict:
        try:
            protocol_version = rpc_data["jsonrpc"]
            method_name = rpc_data["method"]
        except KeyError:
            raise JsonRpcError(Errors.INVALID_REQUEST)

        if protocol_version != PROTOCOL_VERSION:
            raise JsonRpcError(
                Errors.INVALID_REQUEST,
                data={"detail": f"Unsupported protocol version {protocol_version}"},
            )

        params = rpc_data.get("params", [])
        rid = rpc_data.get("id", None)

        if method_name not in self.methods:
            raise JsonRpcError(Errors.METHOD_NOT_FOUND, rid=rid, data={"method": method_name})

        if not isinstance(params, (list, dict, None)):
            raise JsonRpcError(Errors.INVALID_PARAMS, rid=rid)

        try:
            if isinstance(params, list):
                result = await self.methods[method_name](*params)
            else:
                result = await self.methods[method_name](**params)
        except TypeError as exp:
            data = {"method": method_name, "detail": exp.args[0]}
            raise JsonRpcError(Errors.INVALID_PARAMS, rid=rid, data=data)

        if not rid:
            raise web.HTTPAccepted()

        return {"jsonrpc": protocol_version, "result": result, "id": rid}

    async def process_batch_rpc(self, batch_data: list) -> list:
        response_content = []
        for rpc in batch_data:
            try:
                response_content.append(await self.process_single_rpc(rpc))
            except web.HTTPAccepted:
                pass
            except JsonRpcError as exp:
                response_content.append(exp.response_content())
            except Exception:  # pylint: disable=broad-except
                exp = JsonRpcError(data={"origin": rpc})
                response_content.append(exp.response_content())
        return response_content

    def register_method(self, handler: Callable, name: str = None, docstring: str = None):
        name = name or handler.__name__
        self.methods[name] = handler
        if docstring:
            self.docs[name] = docstring

    def route(self, path: str) -> web.RouteDef:
        return web.post(path, self.handler)

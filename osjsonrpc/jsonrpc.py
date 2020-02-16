import json
import logging
import sys
from traceback import format_exception, format_exception_only
from enum import Enum
from typing import Callable, Union, Any, Optional
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
        code: Optional[Union[Errors, int]] = Errors.INTERNAL_ERROR,
        message: Optional[str] = None,
        detail: Optional[Any] = None,
        rid: Optional[Union[int, str]] = None,
    ):
        super().__init__()
        self.code = code  # type: Errors

        if isinstance(code, Errors):
            self.message = message or code.message()
        else:
            self.message = message or UNKNOWN_ERROR

        self.data = {}
        if detail:
            self.data["detail"] = detail

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

    def http_response(self) -> web.Response:
        return web.json_response(self.response_content())

    def response_content(self) -> dict:
        content = {
            "jsonrpc": PROTOCOL_VERSION,
            "error": self.error_content(),
        }
        if self.rid:
            content["id"] = self.rid
        return content

    def set_request(self, request):
        self.data["request"] = request


def exp_message(exp):
    return "".join(format_exception_only(exp.__class__, exp)).strip()


class JsonRpcEndpoint:
    """ JSON RPC requests handler. """

    def __init__(self):
        self.methods = {}
        self.docs = {}

    async def handle_request(self, request: web.Request) -> web.Response:

        try:
            # Check if the Content-Type and Accept headers both are presented
            # and contain 'application/json'

            if request.headers["Content-Type"] != "application/json":
                raise web.HTTPUnsupportedMediaType(reason="Invalid Content-Type")
            if request.headers["Accept"] != "application/json":
                raise web.HTTPNotAcceptable(reason="Invalid Accept header")
        except KeyError as exp:
            reason = "{} header is required".format(exp_message(exp))
            raise web.HTTPNotAcceptable(reason=reason)

        try:
            request_data = await request.json()
        except json.JSONDecodeError:
            return JsonRpcError(Errors.PARSE_ERROR).http_response()

        try:
            if isinstance(request_data, list):
                return web.json_response(await self.process_batch_rpc(request_data))
            return web.json_response(await self.process_single_rpc(request_data))
        except JsonRpcError as exp:
            exp.set_request(request_data)
            return exp.http_response()

    async def process_single_rpc(self, rpc_data: dict) -> dict:
        try:
            protocol_version = rpc_data["jsonrpc"]
            method_name = rpc_data["method"]
            params = rpc_data.get("params", [])
            rid = rpc_data.get("id", None)
        except KeyError:
            raise JsonRpcError(Errors.INVALID_REQUEST)

        if protocol_version != PROTOCOL_VERSION:
            raise JsonRpcError(
                Errors.INVALID_REQUEST, detail=f"Unsupported protocol version {protocol_version}",
            )

        if method_name not in self.methods:
            raise JsonRpcError(Errors.METHOD_NOT_FOUND, rid=rid)

        if not isinstance(params, (list, dict, None)):
            raise JsonRpcError(Errors.INVALID_PARAMS, rid=rid)

        try:
            if isinstance(params, list):
                result = await self.methods[method_name](*params)
            else:
                result = await self.methods[method_name](**params)
        except TypeError as exp:
            raise JsonRpcError(Errors.INVALID_PARAMS, rid=rid, detail=exp_message(exp))
        except Exception:  # pylint: disable=broad-except
            exp_class, exp, trace = sys.exc_info()
            logger = logging.getLogger("aiohttp.server")
            logger.error("".join(format_exception(exp_class, exp, trace)))
            raise JsonRpcError(detail=exp_message(exp), rid=rid)

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
                exp.set_request(rpc)
                response_content.append(exp.response_content())
        return response_content

    def register_method(self, handler: Callable, name: str = None, docstring: str = None):
        """Register method for the endpoint

        Arguments:
            handler {Callable} -- method coroutine

        Keyword Arguments:
            name {str} -- method name, if None coroutine function name is used (default: {None})
            docstring {str} -- docstring (default: {None})

        Returns:
            JsonRpcEndpoint -- endpoint self instance
        """
        name = name or handler.__name__
        self.methods[name] = handler
        if docstring:
            self.docs[name] = docstring
        return self

    def route(self, path: str) -> web.RouteDef:
        """Get endpoint route definition

        Arguments:
            path {str} -- HTTP query path

        Returns:
            web.RouteDef -- endpoint route definition
        """
        return web.post(path, self.handle_request)

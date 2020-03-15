import json
import logging
import traceback
import sys
from traceback import format_exception, format_exception_only
from enum import Enum
from time import time
from typing import Callable, Union, Any, Optional
from aiohttp import web

PROTOCOL_VERSION = "2.0"

UNKNOWN_ERROR = "Unknown Error"

DEFAULT_LOGGER = logging.getLogger("aiohttp.server")


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

    def set_context(self, request=None, rid=None):
        if request:
            self.data["request"] = request
        if rid:
            self.rid = rid

    def with_traceback(self, exc_info=None, traceback_exception=None):
        if not traceback_exception:
            traceback_exception = traceback.TracebackException(*(exc_info or sys.exc_info()))
        self.data["traceback_exception"] = "".join(traceback_exception.format()).split("\n")
        return self


def exc_message(exp):
    return "".join(format_exception_only(exp.__class__, exp)).strip()


class JsonRpcEndpoint:
    """ JSON RPC requests handler. """

    def __init__(self, debug=False, logger=DEFAULT_LOGGER):
        self.methods = {}
        self.docs = {}
        self.debug = debug
        self.logger = logger

    async def handle_request(self, request: web.Request) -> web.Response:
        request_time = int(time() * 1000)
        try:
            # Check if the Content-Type and Accept headers both are presented
            # and contain 'application/json'

            if request.headers["Content-Type"] != "application/json":
                raise web.HTTPUnsupportedMediaType(reason="Invalid Content-Type")
            if request.headers["Accept"] != "application/json":
                raise web.HTTPNotAcceptable(reason="Invalid Accept header")
        except KeyError as exp:
            reason = "{} header is required".format(exc_message(exp))
            raise web.HTTPNotAcceptable(reason=reason)

        try:
            request_data = await request.json()
        except json.JSONDecodeError:
            exp = JsonRpcError(Errors.PARSE_ERROR)
            self.log_request(request, request_time, "invalid", exp)
            return exp.http_response()

        try:
            if isinstance(request_data, list):
                response_data = await self.process_batch_rpc(request_data)
                self.log_request(request, request_time)
                return web.json_response(response_data)
            response_data = await self.process_single_rpc(request_data)
            self.log_request(request, request_time, request_data["method"])
            return web.json_response(response_data)
        except JsonRpcError as exp:
            exp.set_context(request_data)
            self.log_request(
                request, request_time, request_data.get("method", "unknown/invalid"), exp
            )
            return exp.http_response()

    def log_request(
        self,
        request: web.Request,
        request_timestamp: int,
        method: str = None,
        exp: JsonRpcError = None,
    ):
        message = "{} JSON RPC {} request done in {}ms: {}".format(
            request.remote,
            method or "batch",
            int(time() * 1000) - request_timestamp,
            exp.message if exp else "OK",
        )
        if exp:
            self.logger.error(message)
        else:
            self.logger.info(message)

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
        except JsonRpcError as exc:
            exc.set_context(rid=rid)
            raise exc
        except TypeError as exc:
            new_exp = JsonRpcError(Errors.INVALID_PARAMS, rid=rid, detail=exc_message(exc))
            raise new_exp.with_traceback() if self.debug else new_exp
        except Exception:  # pylint: disable=broad-except
            exp_class, exc, trace = sys.exc_info()
            logger = logging.getLogger("aiohttp.server")
            logger.error("".join(format_exception(exp_class, exc, trace)))
            kwargs = {"detail": exc_message(exc), "rid": rid}
            if self.debug:
                kwargs["traceback_exception"] = traceback.TracebackException(*sys.exc_info())
            raise JsonRpcError(**kwargs)

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
                exp.set_context(rpc)
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

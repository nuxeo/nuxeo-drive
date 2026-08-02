# coding: utf-8
from collections.abc import Sequence
from os import fsync
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple, Type

from requests import Response

from . import constants
from .endpoint import APIEndpoint
from .exceptions import BadQuery, CorruptedFile
from .models import Blob, Operation
from .utils import get_digester

if TYPE_CHECKING:
    from .client import NuxeoClient

# Types allowed for operations parameters
# See https://docs.oracle.com/javase/tutorial/java/nutsandbolts/datatypes.html
# for default values
PARAM_TYPES = {
    # Operation: ((accepted types), default value if optional))
    "blob": ((str, bytes, Blob), None),
    "boolean": ((bool,), False),
    "date": ((str, bytes), None),
    "document": ((str, bytes), None),
    "documents": ((list,), None),
    "int": ((int,), 0),
    "integer": ((int,), 0),
    "long": ((int, int), 0),
    "list": ((list,), None),
    "map": ((dict,), None),
    "object": ((object,), None),
    "properties": ((dict,), None),
    "resource": ((str, bytes), None),
    "serializable": ((Sequence,), None),
    "string": ((str, bytes), None),
    "stringlist": ((Sequence,), None),
    "validationmethod": ((str, bytes), None),
}  # type: Dict[str, Tuple[Type, ...]]


class API(APIEndpoint):
    """Endpoint for operations."""

    __slots__ = ()

    # Operations cache
    ops = {}  # type: Dict[str, Any]

    def __init__(self, client, endpoint="site/automation", headers=None):
        # type: (NuxeoClient, str, Optional[Dict[str, str]]) -> None
        headers = headers or {}
        headers.update({"Content-Type": "application/json", "X-NXproperties": "*"})
        super().__init__(client, endpoint=endpoint, cls=dict, headers=headers)
        self.endpoint = endpoint

    def get(self, **kwargs):
        # type: (Any) -> Dict[str, Any]
        """Get the list of available operations from the server."""
        return super().get()

    def put(self, **kwargs):
        # type: (Any) -> None
        raise NotImplementedError()

    def delete(self, resource_id):
        # type: (str) -> None
        raise NotImplementedError()

    @property
    def operations(self):
        # type: () -> Dict[str, Any]
        """
        Get a dict of available operations.

        :return: the available operations
        """
        if not self.ops:
            response = self.get()
            for operation in response["operations"]:
                self.ops[operation["id"]] = operation
                for alias in operation.get("aliases", []):
                    self.ops[alias] = operation

        return self.ops

    def check_params(self, command, params):
        # type: (str, Dict[str, Any]) -> None
        """
        Check given parameters of the `command` operation.  It will also
        check for types whenever possible.
        """

        operation = self.operations.get(command)
        if not operation:
            raise BadQuery(f"{command!r} is not a registered operation")

        parameters = {param["name"]: param for param in operation["params"]}

        for name, value in params.items():
            # Check for unexpected parameters.  We use `dict.pop()` to
            # get and delete the parameter from the dict.
            try:
                param = parameters.pop(name)
            except KeyError:
                err = f"unexpected parameter {name!r} for operation {command}"
                raise BadQuery(err)

            # Check types
            types_accepted, default = PARAM_TYPES[param["type"]]
            if not param["required"]:
                # Allow the default value when the parameter is not required
                types_accepted += (type(default),)
            types_accepted = tuple(set(types_accepted))  # Uniquify

            if not isinstance(value, types_accepted):
                types = [type_.__name__ for type_ in types_accepted]
                if len(types) > 1:
                    types = ", ".join(types[:-1]) + " or " + types[-1]
                else:
                    types = types[0]
                err = f"parameter {name}={value!r} should be of type {types} (current is {type(value).__name__})"
                raise BadQuery(err)

        # Check for required parameters.  As of now, `parameters` may contain
        # unclaimed parameters and we just need to check for required ones.
        for (name, parameter) in parameters.items():
            if parameter["required"]:
                err = f"missing required parameter {name!r} for operation {command!r}"
                raise BadQuery(err)

    def execute(
        self,
        operation=None,  # type: Optional[Operation]
        void_op=False,  # type: bool
        headers=None,  # type: Optional[Dict[str, str]]
        file_out=None,  # type: Optional[str]
        ssl_verify=True,  # type: bool
        **kwargs,  # type: Any
    ):
        # type: (...) -> Any
        """
        Execute an operation.

        If there is no operation parameter, the command,
        the input object, and the parameters of the operation
        will be taken from the kwargs.

        :param operation: the operation
        :param void_op: if True, the body of the response
        from the server will be empty
        :param headers: extra HTTP headers
        :param file_out: if not None, path of the file
        where the response will be saved
        :param kwargs: any other parameter
          *callback* is either a single callable or a tuple of callables.
        :return: the result of the execution
        """
        json = kwargs.pop("json", True)
        callback = kwargs.pop("callback", None)
        enrichers = kwargs.pop("enrichers", None)
        check_params = kwargs.pop("check_params", constants.CHECK_PARAMS)
        default = kwargs.pop("default", object)
        timeout = kwargs.pop("timeout", object)

        command, input_obj, params, context = self.get_attributes(operation, **kwargs)

        if check_params:
            self.check_params(command, params)

        url = f"site/automation/{command}"
        if isinstance(input_obj, Blob):
            url = f"{self.client.api_path}/upload/{input_obj.batchId}/{input_obj.fileIdx}/execute/{command}"
            input_obj = None

        headers = headers or {}
        headers.update(self.headers)
        if void_op:
            headers["X-NXVoidOperation"] = "true"

        data = self.build_payload(params, context)

        if input_obj:
            if isinstance(input_obj, list):
                input_obj = "docs:" + ",".join(input_obj)
            data["input"] = input_obj

        resp = self.client.request(
            "POST",
            url,
            data=data,
            headers=headers,
            enrichers=enrichers,
            default=default,
            timeout=timeout,
            ssl_verify=ssl_verify,
        )

        # Save to a file, part by part of chunk_size
        if file_out:
            return self.save_to_file(
                operation, resp, file_out, callback=callback, **kwargs
            )

        # It is likely a JSON response we do not want to save to a file
        if operation:
            operation.progress = int(resp.headers.get("content-length", 0))

        if json:
            try:
                return resp.json()
            except ValueError:
                pass
        return resp.content

    @staticmethod
    def get_attributes(operation, **kwargs):
        # type: (Operation, Any) -> Tuple[str, Any, Dict[str, Any]]
        """Get the operation attributes."""
        if operation:
            command = operation.command
            input_obj = operation.input_obj
            context = operation.context
            params = operation.params
        else:
            command = kwargs.pop("command", None)
            input_obj = kwargs.pop("input_obj", None)
            context = kwargs.pop("context", None)
            params = kwargs.pop("params", kwargs)
        return command, input_obj, params, context

    def build_payload(self, params, context):
        # type: (Dict[str, Any], Dict[str, Any]) -> Dict[str, Any]
        """Create sanitized operation payload."""
        data = {"params": self.sanitize(params)}  # type: Dict[str, Any]
        clean_context = self.sanitize(context)  # type: Dict[str, Any]
        if clean_context:
            data["context"] = clean_context

        return data

    @staticmethod
    def sanitize(obj):
        # type: (Dict[str, Any]) -> Dict[str, Any]
        """Sanitize the operation parameters."""
        if not obj:
            return {}

        clean_obj = {}  # type: Dict[str, Any]

        for k, v in obj.items():
            if v is None:
                continue

            if k != "properties":
                clean_obj[k] = v
                continue

            # v can only be a dict
            contents = [f"{name}={value}" for name, value in v.items()]
            clean_obj[k] = "\n".join(contents)

        return clean_obj

    def new(self, command, **kwargs):
        # type: (str, Any) -> Operation
        """Make a new Operation object."""
        return Operation(command=command, service=self, **kwargs)

    def save_to_file(self, operation, resp, path, **kwargs):
        # type: (Operation, Response, str, Any) -> str
        """
        Save the result of an operation to a file.

        If there is a digest of the file to check
        against the server, it can be passed in
        the kwargs.
        :param operation: the operation
        :param resp: the response from the Platform
        :param path: the path to save the file to
        :param kwargs: additional parameters
        :return:
        """
        digest = kwargs.pop("digest", None)
        digester = get_digester(digest) if digest else None

        unlock_path = kwargs.pop("unlock_path", None)
        lock_path = kwargs.pop("lock_path", None)
        use_lock = callable(unlock_path) and callable(lock_path)

        # Several callbacks are accepted, tuple is used to keep order
        callback = kwargs.pop("callback", None)
        if callback and isinstance(callback, (tuple, list, set)):
            callbacks = tuple(cb for cb in callback if callable(cb))
        else:
            callbacks = tuple([callback] if callable(callback) else [])

        locker = unlock_path(path) if use_lock else None
        try:
            with open(path, "ab") as f:
                chunk_size = kwargs.get("chunk_size", self.client.chunk_size)
                for chunk in resp.iter_content(chunk_size=chunk_size):
                    # Check if synchronization thread was suspended
                    for callback in callbacks:
                        callback(path)
                    if operation:
                        operation.progress += chunk_size
                    f.write(chunk)
                    if digester:
                        digester.update(chunk)

                # Force write of file to disk
                f.flush()
                fsync(f.fileno())
        finally:
            if use_lock:
                lock_path(path, locker)

        if digester:
            computed_digest = digester.hexdigest()
            if digest != computed_digest:
                raise CorruptedFile(path, digest, computed_digest)

        return path

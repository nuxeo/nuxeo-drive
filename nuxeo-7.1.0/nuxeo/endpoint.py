# coding: utf-8
from typing import TYPE_CHECKING, Any, Dict, Optional, Type

from requests import Response

from .exceptions import BadQuery, HTTPError
from .models import Model

if TYPE_CHECKING:
    from .client import NuxeoClient


class APIEndpoint(object):
    """
    Represents an API endpoint for Nuxeo, containing common patterns
    for CRUD operations.
    """

    __slots__ = ("client", "endpoint", "headers", "_cls")

    def __init__(
        self,
        client,  # type: NuxeoClient
        endpoint=None,  # type: Optional[str]
        headers=None,  # type: Optional[Dict[str, str]]
        cls=None,  # type: Optional[Type]
    ):
        # type: (...) -> None
        """
        Creates an instance of the APIEndpoint class.

        :param client: the authenticated REST client
        :param endpoint: the URL path to the resource endpoint
        :param headers: the extra HTTP headers
        :param cls: the Class to use when parsing results
        """
        self.client = client
        if endpoint:
            self.endpoint = f"{client.api_path}/{endpoint}"
        else:
            self.endpoint = client.api_path
        self.headers = headers or {}
        self._cls = cls

    def get(
        self,
        path=None,  # type: Optional[str]
        cls=None,  # type: Optional[Type]
        raw=False,  # type: bool
        single=False,  # type: bool
        ssl_verify=True,  # type: bool
        **kwargs,  # type: Any
    ):
        # type: (...) -> Any
        """
        Gets the details for one or more resources.

        :param path: the endpoint (URL path) for the request
        :param cls: a class to use for parsing, if different
                    than the base resource
        :param raw: if True, directly return the content of
                    the response
        :param single: if True, do not parse as list
        :return: one or more instances of cls parsed from
                 the returned JSON
        """
        endpoint = kwargs.pop("endpoint", "") or self.endpoint

        if not cls:
            cls = self._cls

        if path:
            endpoint = f"{endpoint}/{path}"

        response = self.client.request("GET", endpoint, ssl_verify=ssl_verify, **kwargs)

        if not isinstance(response, Response):
            return response

        if raw or response.status_code == 204:
            return response.content
        json = response.json()

        if cls is dict:
            return json

        if not single and isinstance(json, dict) and "entries" in json:
            json = json["entries"]

        if isinstance(json, list):
            return [cls.parse(resource, service=self) for resource in json]

        return cls.parse(json, service=self)

    def post(self, resource=None, path=None, raw=False, ssl_verify=True, **kwargs):
        # type: (Optional[Any], Optional[str], bool, bool, Any) -> Any
        """
        Creates a new instance of the resource.

        :param resource: the data to post
        :param path: the endpoint (URL path) for the request
        :param raw: if False, parse the outgoing data to JSON
        :return: the created resource
        """
        if resource and not raw and not isinstance(resource, dict):
            if isinstance(resource, self._cls):
                resource = resource.as_dict()
            else:
                raise BadQuery("Data must be a Model object or a dictionary.")

        endpoint = kwargs.pop("endpoint", "") or self.endpoint

        if path:
            endpoint = f"{endpoint}/{path}"

        response = self.client.request(
            "POST", endpoint, data=resource, raw=raw, ssl_verify=ssl_verify, **kwargs
        )

        if isinstance(response, dict):
            return response
        return self._cls.parse(response.json(), service=self)

    def put(self, resource=None, path=None, ssl_verify=True, **kwargs):
        # type: (Optional[Model], Optional[str], bool, Any) -> Any
        """
        Edits an existing resource.

        :param resource: the resource instance
        :param path: the endpoint (URL path) for the request
        :return: the modified resource
        """

        endpoint = f"{self.endpoint}/{path or resource.uid}"

        data = resource.as_dict() if resource else resource

        response = self.client.request(
            "PUT", endpoint, ssl_verify=ssl_verify, data=data, **kwargs
        )

        if resource:
            return self._cls.parse(response.json(), service=self)

    def delete(self, resource_id, ssl_verify=True):
        # type: (str, bool) -> None
        """
        Deletes an existing resource.

        :param resource_id: the resource ID to be deleted
        """

        endpoint = f"{self.endpoint}/{resource_id}"
        self.client.request("DELETE", endpoint, ssl_verify=ssl_verify)

    def exists(self, path, ssl_verify=True):
        # type: (str, bool) -> bool
        """
        Checks if a resource exists.

        :param path: the endpoint (URL path) for the request
        :return: True if it exists, else False
        """
        endpoint = f"{self.endpoint}/{path}"

        try:
            self.client.request("GET", endpoint, ssl_verify=ssl_verify)
            return True
        except HTTPError as e:
            if e.status != 404:
                raise e
        return False

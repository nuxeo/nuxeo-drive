# coding: utf-8
from typing import TYPE_CHECKING, Any, Dict, Optional, Union

from .endpoint import APIEndpoint
from .exceptions import BadQuery
from .models import Directory, DirectoryEntry

if TYPE_CHECKING:
    from .client import NuxeoClient


class API(APIEndpoint):
    """ Endpoint for directories. """

    __slots__ = ()

    def __init__(self, client, endpoint="directory", headers=None):
        # type: (NuxeoClient, str, Optional[Dict[str, str]]) -> None
        super().__init__(client, endpoint=endpoint, cls=DirectoryEntry, headers=headers)

    def get(self, dir_name, dir_entry=None, **params):
        # type: (str, Optional[str], Any) -> Union[Directory, DirectoryEntry]
        """
        Get the entries of a directory.

        If dir_entry is not None, return the corresponding entry.
        Any additionnal arguments will be passed to the *params* parent's call.

        :param dir_name: the name of the directory
        :param dir_entry: the name of an entry
        :return: the directory entries
        """
        path = dir_name
        if dir_entry:
            path = f"{path}/{dir_entry}"

        entries = super().get(path=path, params=params)
        if dir_entry:
            return entries
        return Directory(directoryName=dir_name, entries=entries, service=self)

    def post(self, resource=None, dir_name=None, **kwargs):
        # type: (DirectoryEntry, str, Any) -> DirectoryEntry
        """
        Create a directory entry.

        :param resource: the entry to create
        :param dir_name: the name of the directory
        :return: the created entry
        """
        if dir_name:
            if not isinstance(resource, DirectoryEntry):
                raise BadQuery("The resource should be a directory entry.")
            resource.directoryName = dir_name
        return super().post(resource=resource, path=dir_name)

    create = post  # Alias for clarity

    def put(self, resource, dir_name):
        # type: (DirectoryEntry, str) -> DirectoryEntry
        """
        Update an entry.

        :param resource: the entry to update
        :param dir_name: the name of the directory
        :return: the updated entry
        """
        path = f"{dir_name}/{resource.uid}"
        return super().put(resource, path=path)

    def delete(self, dir_name, dir_entry):
        # type: (str, str) -> None
        """
        Delete a directory entry.

        :param dir_name: the name of the directory
        :param dir_entry: the name of the entry
        """
        path = f"{dir_name}/{dir_entry}"
        super().delete(path)

    def exists(self, dir_name, dir_entry=None):
        # type: (str, Optional[str]) -> bool
        """
        Check if a directory or an entry exists.

        :param dir_name: the name of the directory
        :param dir_entry: the name of the entry
        :return: True if it exists, else False
        """
        path = dir_name
        if dir_entry:
            path = f"{path}/{dir_entry}"
        return super().exists(path)

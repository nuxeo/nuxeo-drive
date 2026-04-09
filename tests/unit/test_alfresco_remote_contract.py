import inspect

from nxdrive.client.alfresco_remote import AlfrescoRemote
from nxdrive.client.remote_client import Remote


def _public_contract_methods(cls):
    names = []
    for name, obj in cls.__dict__.items():
        if name.startswith("_"):
            continue
        if isinstance(obj, property):
            names.append(name)
            continue
        if isinstance(obj, staticmethod):
            names.append(name)
            continue
        if inspect.isfunction(obj):
            names.append(name)
    return sorted(names)


def _signature_for_member(cls, name):
    raw = inspect.getattr_static(cls, name)
    if isinstance(raw, property):
        return inspect.signature(raw.fget)
    if isinstance(raw, staticmethod):
        return inspect.signature(raw.__func__)
    return inspect.signature(getattr(cls, name))


def test_alfresco_remote_keeps_public_method_contract() -> None:
    remote_methods = _public_contract_methods(Remote)
    alfresco_methods = _public_contract_methods(AlfrescoRemote)

    assert alfresco_methods == remote_methods

    for method in remote_methods:
        remote_sig = _signature_for_member(Remote, method)
        alfresco_sig = _signature_for_member(AlfrescoRemote, method)
        assert str(alfresco_sig) == str(remote_sig), method


def test_alfresco_remote_keeps_constructor_contract() -> None:
    assert str(inspect.signature(AlfrescoRemote.__init__)) == str(
        inspect.signature(Remote.__init__)
    )

"""Integration tests for dependency injection through chat_client_adapter."""

import importlib

import chat_client_api
import chat_client_api.client as client_module


def test_importing_adapter_registers_service_backed_client() -> None:
    """Importing chat_client_adapter registers a ServiceBackedChatClient factory.

    After the adapter is imported, chat_client_api.get_client() must return a
    ServiceBackedChatClient — proving location transparency via register().
    """
    # Reset the interface module so _impl starts as None.
    importlib.reload(client_module)
    importlib.reload(chat_client_api)

    # Before the adapter is loaded, get_client() should raise NotImplementedError
    # because no factory has been registered yet.
    try:
        chat_client_api.get_client(interactive=False)
        pre_load_raised = False
    except NotImplementedError:
        pre_load_raised = True

    msg = "get_client() must raise NotImplementedError before any factory is registered"
    assert pre_load_raised, msg

    # Import (and reload) the adapter — this calls chat_client_api.register(...)
    adapter_module = importlib.import_module("chat_client_adapter")
    importlib.reload(adapter_module)

    # Now get_client() should return a ServiceBackedChatClient.
    from chat_client_adapter.client import ServiceBackedChatClient

    injected_client = chat_client_api.get_client(interactive=False)
    assert isinstance(injected_client, ServiceBackedChatClient)

from http import HTTPStatus
from typing import Any
from urllib.parse import quote

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.delete_message_response import DeleteMessageResponse
from ...models.http_validation_error import HTTPValidationError
from ...types import UNSET, Response


def _get_kwargs(
    message_id: str,
    *,
    channel_id: str,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["channel_id"] = channel_id

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "delete",
        "url": "/chat/messages/{message_id}".format(
            message_id=quote(str(message_id), safe="")
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> DeleteMessageResponse | HTTPValidationError | None:
    if response.status_code == 200:
        response_200 = DeleteMessageResponse.from_dict(response.json())

        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[DeleteMessageResponse | HTTPValidationError]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    message_id: str,
    *,
    client: AuthenticatedClient | Client,
    channel_id: str,
) -> Response[DeleteMessageResponse | HTTPValidationError]:
    """Delete Message

     Delete a message through the configured ChatClient provider.

    Args:
        message_id (str):
        channel_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DeleteMessageResponse | HTTPValidationError]

    """
    kwargs = _get_kwargs(
        message_id=message_id,
        channel_id=channel_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    message_id: str,
    *,
    client: AuthenticatedClient | Client,
    channel_id: str,
) -> DeleteMessageResponse | HTTPValidationError | None:
    """Delete Message

     Delete a message through the configured ChatClient provider.

    Args:
        message_id (str):
        channel_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DeleteMessageResponse | HTTPValidationError

    """
    return sync_detailed(
        message_id=message_id,
        client=client,
        channel_id=channel_id,
    ).parsed


async def asyncio_detailed(
    message_id: str,
    *,
    client: AuthenticatedClient | Client,
    channel_id: str,
) -> Response[DeleteMessageResponse | HTTPValidationError]:
    """Delete Message

     Delete a message through the configured ChatClient provider.

    Args:
        message_id (str):
        channel_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[DeleteMessageResponse | HTTPValidationError]

    """
    kwargs = _get_kwargs(
        message_id=message_id,
        channel_id=channel_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    message_id: str,
    *,
    client: AuthenticatedClient | Client,
    channel_id: str,
) -> DeleteMessageResponse | HTTPValidationError | None:
    """Delete Message

     Delete a message through the configured ChatClient provider.

    Args:
        message_id (str):
        channel_id (str):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        DeleteMessageResponse | HTTPValidationError

    """
    return (
        await asyncio_detailed(
            message_id=message_id,
            client=client,
            channel_id=channel_id,
        )
    ).parsed

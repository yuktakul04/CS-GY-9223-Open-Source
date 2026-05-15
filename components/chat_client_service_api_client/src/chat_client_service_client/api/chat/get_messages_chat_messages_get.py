from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.http_validation_error import HTTPValidationError
from ...models.message_model import MessageModel
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    channel_id: str,
    max_results: int | Unset = 10,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["channel_id"] = channel_id

    params["max_results"] = max_results

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/chat/messages",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> HTTPValidationError | list[MessageModel] | None:
    if response.status_code == 200:
        response_200 = []
        _response_200 = response.json()
        for response_200_item_data in _response_200:
            response_200_item = MessageModel.from_dict(response_200_item_data)

            response_200.append(response_200_item)

        return response_200

    if response.status_code == 422:
        response_422 = HTTPValidationError.from_dict(response.json())

        return response_422

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[HTTPValidationError | list[MessageModel]]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    channel_id: str,
    max_results: int | Unset = 10,
) -> Response[HTTPValidationError | list[MessageModel]]:
    """Get Messages

     Retrieve messages from a channel via telegram_client_impl.

    Args:
        channel_id (str):
        max_results (int | Unset):  Default: 10.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | list[MessageModel]]

    """
    kwargs = _get_kwargs(
        channel_id=channel_id,
        max_results=max_results,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    channel_id: str,
    max_results: int | Unset = 10,
) -> HTTPValidationError | list[MessageModel] | None:
    """Get Messages

     Retrieve messages from a channel via telegram_client_impl.

    Args:
        channel_id (str):
        max_results (int | Unset):  Default: 10.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | list[MessageModel]

    """
    return sync_detailed(
        client=client,
        channel_id=channel_id,
        max_results=max_results,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    channel_id: str,
    max_results: int | Unset = 10,
) -> Response[HTTPValidationError | list[MessageModel]]:
    """Get Messages

     Retrieve messages from a channel via telegram_client_impl.

    Args:
        channel_id (str):
        max_results (int | Unset):  Default: 10.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[HTTPValidationError | list[MessageModel]]

    """
    kwargs = _get_kwargs(
        channel_id=channel_id,
        max_results=max_results,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    channel_id: str,
    max_results: int | Unset = 10,
) -> HTTPValidationError | list[MessageModel] | None:
    """Get Messages

     Retrieve messages from a channel via telegram_client_impl.

    Args:
        channel_id (str):
        max_results (int | Unset):  Default: 10.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        HTTPValidationError | list[MessageModel]

    """
    return (
        await asyncio_detailed(
            client=client,
            channel_id=channel_id,
            max_results=max_results,
        )
    ).parsed

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from typing_extensions import Self

from ..types import UNSET, Unset

T = TypeVar("T", bound="OAuthCallbackResponse")


@_attrs_define
class OAuthCallbackResponse:
    """Response payload for OAuth callback placeholder.

    Attributes:
        detail (str):
        code (None | str | Unset):
        state (None | str | Unset):

    """

    detail: str
    code: None | str | Unset = UNSET
    state: None | str | Unset = UNSET
    access_token: None | str | Unset = UNSET
    token_type: None | str | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        detail = self.detail

        code: None | str | Unset
        if isinstance(self.code, Unset):
            code = UNSET
        else:
            code = self.code

        state: None | str | Unset
        if isinstance(self.state, Unset):
            state = UNSET
        else:
            state = self.state

        access_token: None | str | Unset
        if isinstance(self.access_token, Unset):
            access_token = UNSET
        else:
            access_token = self.access_token

        token_type: None | str | Unset
        if isinstance(self.token_type, Unset):
            token_type = UNSET
        else:
            token_type = self.token_type

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "detail": detail,
            }
        )
        if code is not UNSET:
            field_dict["code"] = code
        if state is not UNSET:
            field_dict["state"] = state
        if access_token is not UNSET:
            field_dict["access_token"] = access_token
        if token_type is not UNSET:
            field_dict["token_type"] = token_type

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        detail = d.pop("detail")

        def _parse_optional_str(data: object) -> None | str | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast("None | str | Unset", data)

        code = _parse_optional_str(d.pop("code", UNSET))
        state = _parse_optional_str(d.pop("state", UNSET))
        access_token = _parse_optional_str(d.pop("access_token", UNSET))
        token_type = _parse_optional_str(d.pop("token_type", UNSET))

        o_auth_callback_response = cls(
            detail=detail,
            code=code,
            state=state,
            access_token=access_token,
            token_type=token_type,
        )

        o_auth_callback_response.additional_properties = d
        return o_auth_callback_response

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties

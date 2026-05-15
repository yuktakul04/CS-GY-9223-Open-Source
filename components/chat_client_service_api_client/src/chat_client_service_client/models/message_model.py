from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field
from typing_extensions import Self

T = TypeVar("T", bound="MessageModel")


@_attrs_define
class MessageModel:
    """Transport model for a message.

    Attributes:
        id (str):
        sender (str):
        channel_id (str):
        timestamp (str):
        text (str):

    """

    id: str
    sender: str
    channel_id: str
    timestamp: str
    text: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        id = self.id

        sender = self.sender

        channel_id = self.channel_id

        timestamp = self.timestamp

        text = self.text

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "sender": sender,
                "channel_id": channel_id,
                "timestamp": timestamp,
                "text": text,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls, src_dict: Mapping[str, Any]) -> Self:
        d = dict(src_dict)
        id = d.pop("id")

        sender = d.pop("sender")

        channel_id = d.pop("channel_id")

        timestamp = d.pop("timestamp")

        text = d.pop("text")

        message_model = cls(
            id=id,
            sender=sender,
            channel_id=channel_id,
            timestamp=timestamp,
            text=text,
        )

        message_model.additional_properties = d
        return message_model

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

from __future__ import annotations

from typing import Protocol

from edge_semantic_compress_intelligence.shared.contract import ContractError, EdgeEvent


class MessageCodec(Protocol):
    def encode(self, event: EdgeEvent) -> bytes:
        """Encode an event for the wire protocol."""


class MessagePackCodec:
    def encode(self, event: EdgeEvent) -> bytes:
        try:
            import msgpack
        except ImportError as error:
            raise RuntimeError(
                "MessagePack support requires the 'transport' extra"
            ) from error
        return msgpack.packb(event.to_dict(), use_bin_type=True)

    def decode(self, payload: bytes) -> EdgeEvent:
        try:
            import msgpack
        except ImportError as error:
            raise RuntimeError(
                "MessagePack support requires the 'transport' extra"
            ) from error
        try:
            value = msgpack.unpackb(payload, raw=False, strict_map_key=False)
        except (ValueError, TypeError) as error:
            raise ContractError("payload is not valid MessagePack") from error
        return EdgeEvent.from_mapping(value)

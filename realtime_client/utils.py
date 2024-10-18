import base64
import struct
import random
import datetime
from typing import Union


class RealtimeUtils:
    @staticmethod
    def float_to_16bit_pcm(float32_array: list) -> bytes:
        return struct.pack(
            "<" + "h" * len(float32_array),
            *[
                int(max(-1, min(1, sample)) * (32767 if sample > 0 else 32768))
                for sample in float32_array
            ]
        )

    @staticmethod
    def base64_to_bytes(base64_string: str) -> bytes:
        return base64.b64decode(base64_string)

    @staticmethod
    def bytes_to_base64(data: Union[bytes, bytearray, memoryview]) -> str:
        return base64.b64encode(data).decode("ascii")

    @staticmethod
    def merge_int16_arrays(
        left: Union[bytes, bytearray], right: Union[bytes, bytearray]
    ) -> bytes:
        if not isinstance(left, (bytes, bytearray)) or not isinstance(
            right, (bytes, bytearray)
        ):
            raise TypeError("Both items must be bytes or bytearray")
        return left + right

    @staticmethod
    def generate_id(prefix: str, length: int = 21) -> str:
        # base58; non-repeating chars
        chars = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        return prefix + "".join(
            random.choice(chars) for _ in range(length - len(prefix))
        )

    @staticmethod
    def iso_timestamp() -> str:
        return datetime.datetime.now(datetime.timezone.utc).isoformat()

    @staticmethod
    def parse_json(json_string: str) -> dict:
        import json

        return json.loads(json_string)

    @staticmethod
    def stringify_json(obj: dict) -> str:
        import json

        return json.dumps(obj)

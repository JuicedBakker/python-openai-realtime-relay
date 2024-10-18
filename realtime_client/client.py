from asyncio.log import logger
from typing import Any, List, Dict, Union, Callable, Optional, TypedDict, Literal
from realtime_client.event_handler import RealtimeEventHandler
from realtime_client.api import RealtimeAPI
from realtime_client.conversation import RealtimeConversation
from realtime_client.utils import RealtimeUtils
import asyncio

AudioFormatType = Literal["pcm16", "g711_ulaw", "g711_alaw"]


class AudioTranscriptionType(TypedDict):
    model: Literal["whisper-1"]


class TurnDetectionServerVadType(TypedDict):
    type: Literal["server_vad"]
    threshold: Optional[float]
    prefix_padding_ms: Optional[int]
    silence_duration_ms: Optional[int]


class ToolDefinitionType(TypedDict):
    type: Optional[Literal["function"]]
    name: str
    description: str
    parameters: Dict[str, any]


class SessionResourceType(TypedDict):
    model: Optional[str]
    modalities: Optional[List[str]]
    instructions: Optional[str]
    voice: Optional[Literal["alloy", "shimmer", "echo"]]
    input_audio_format: Optional[AudioFormatType]
    output_audio_format: Optional[AudioFormatType]
    input_audio_transcription: Optional[AudioTranscriptionType]
    turn_detection: Optional[TurnDetectionServerVadType]
    tools: Optional[List[ToolDefinitionType]]
    tool_choice: Optional[
        Union[Literal["auto", "none", "required"], Dict[Literal["type"], str]]
    ]
    temperature: Optional[float]
    max_response_output_tokens: Optional[Union[int, Literal["inf"]]]


ItemStatusType = Literal["in_progress", "completed", "incomplete"]


class InputTextContentType(TypedDict):
    type: Literal["input_text"]
    text: str


class InputAudioContentType(TypedDict):
    type: Literal["input_audio"]
    audio: Optional[str]
    transcript: Optional[str]


class TextContentType(TypedDict):
    type: Literal["text"]
    text: str


class AudioContentType(TypedDict):
    type: Literal["audio"]
    audio: Optional[str]
    transcript: Optional[str]


class SystemItemType(TypedDict):
    previous_item_id: Optional[str]
    type: Literal["message"]
    status: ItemStatusType
    role: Literal["system"]
    content: List[InputTextContentType]


class UserItemType(TypedDict):
    previous_item_id: Optional[str]
    type: Literal["message"]
    status: ItemStatusType
    role: Literal["user"]
    content: List[Union[InputTextContentType, InputAudioContentType]]


class AssistantItemType(TypedDict):
    previous_item_id: Optional[str]
    type: Literal["message"]
    status: ItemStatusType
    role: Literal["assistant"]
    content: List[Union[TextContentType, AudioContentType]]


class FunctionCallItemType(TypedDict):
    previous_item_id: Optional[str]
    type: Literal["function_call"]
    status: ItemStatusType
    call_id: str
    name: str
    arguments: str


class FunctionCallOutputItemType(TypedDict):
    previous_item_id: Optional[str]
    type: Literal["function_call_output"]
    call_id: str
    output: str


class FormattedToolType(TypedDict):
    type: Literal["function"]
    name: str
    call_id: str
    arguments: str


class FormattedPropertyType(TypedDict):
    audio: Optional[bytes]
    text: Optional[str]
    transcript: Optional[str]
    tool: Optional[FormattedToolType]
    output: Optional[str]
    file: Optional[any]


class FormattedItemType(TypedDict):
    id: str
    object: str
    role: Optional[Literal["user", "assistant", "system"]]
    formatted: FormattedPropertyType


ItemType = Union[
    SystemItemType,
    UserItemType,
    AssistantItemType,
    FunctionCallItemType,
    FunctionCallOutputItemType,
    FormattedItemType,
]


class IncompleteResponseStatusType(TypedDict):
    type: Literal["incomplete"]
    reason: Literal["interruption", "max_output_tokens", "content_filter"]


class FailedResponseStatusType(TypedDict):
    type: Literal["failed"]
    error: Optional[Dict[str, str]]


class UsageType(TypedDict):
    total_tokens: int
    input_tokens: int
    output_tokens: int


class ResponseResourceType(TypedDict):
    status: Literal["in_progress", "completed", "incomplete", "cancelled", "failed"]
    status_details: Optional[
        Union[IncompleteResponseStatusType, FailedResponseStatusType]
    ]
    output: List[ItemType]
    usage: Optional[UsageType]


class RealtimeClient(RealtimeEventHandler):
    def __init__(
        self,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
        dangerously_allow_api_key_in_browser: bool = False,
        debug: bool = False,
    ):
        super().__init__()
        self.default_session_config = {
            "modalities": ["text", "audio"],
            "instructions": "",
            "voice": "alloy",
            "input_audio_format": "pcm16",
            "output_audio_format": "pcm16",
            "input_audio_transcription": None,
            "turn_detection": None,
            "tools": [],
            "tool_choice": "auto",
            "temperature": 0.8,
            "max_response_output_tokens": 4096,
        }
        self.session_config = {}
        self.transcription_models = [
            {
                "model": "whisper-1",
            },
        ]
        self.default_server_vad_config = {
            "type": "server_vad",
            "threshold": 0.5,
            "prefix_padding_ms": 300,
            "silence_duration_ms": 200,
        }
        self.realtime = RealtimeAPI(
            url=url,
            api_key=api_key,
            dangerously_allow_api_key_in_browser=dangerously_allow_api_key_in_browser,
            debug=debug,
        )
        self.conversation = RealtimeConversation()
        self._reset_config()
        self._add_api_event_handlers()

    def _reset_config(self) -> bool:
        self.session_created = False
        self.tools = {}
        self.session_config = self.default_session_config.copy()
        self.input_audio_buffer = bytes()
        return True

    def _handler(self, event, *args):
        item, delta = self.conversation.process_event(event, *args)
        return item, delta

    def _handler_with_dispatch(self, event, *args):
        item, delta = self._handler(event, *args)
        if item:
            self.dispatch("conversation.updated", {"item": item, "delta": delta})
        return item, delta

    def _add_api_event_handlers(self) -> bool:
        self.realtime.on(
            "client.*",
            lambda event: self.dispatch(
                "realtime.event",
                {
                    "time": RealtimeUtils.iso_timestamp(),
                    "source": "client",
                    "event": event,
                },
            ),
        )
        self.realtime.on(
            "server.*",
            lambda event: self.dispatch(
                "realtime.event",
                {
                    "time": RealtimeUtils.iso_timestamp(),
                    "source": "server",
                    "event": event,
                },
            ),
        )

        self.realtime.on(
            "server.session.created", lambda _: setattr(self, "session_created", True)
        )

        self.realtime.on("server.response.created", self._handler)
        self.realtime.on("server.response.output_item.added", self._handler)
        self.realtime.on("server.response.content_part.added", self._handler)
        self.realtime.on(
            "server.input_audio_buffer.speech_started",
            lambda event: (
                self._handler(event),
                self.dispatch("conversation.interrupted"),
            ),
        )
        self.realtime.on(
            "server.input_audio_buffer.speech_stopped",
            lambda event: self._handler(event, self.input_audio_buffer),
        )

        self.realtime.on("server.conversation.item.created", self._safe_handler)
        self.realtime.on(
            "server.conversation.item.truncated", self._handler_with_dispatch
        )
        self.realtime.on(
            "server.conversation.item.deleted", self._handler_with_dispatch
        )
        self.realtime.on(
            "server.conversation.item.input_audio_transcription.completed",
            self._handler_with_dispatch,
        )
        self.realtime.on(
            "server.response.audio_transcript.delta", self._handler_with_dispatch
        )
        self.realtime.on("server.response.audio.delta", self._handler_with_dispatch)
        self.realtime.on("server.response.text.delta", self._handler_with_dispatch)
        self.realtime.on(
            "server.response.function_call_arguments.delta", self._handler_with_dispatch
        )
        self.realtime.on(
            "server.response.output_item.done", self._handle_response_output_item_done
        )

        return True

    def _safe_handler(self, event):
        try:
            item = event.get("item")
            if item:
                self.dispatch("conversation.item.appended", {"item": item})
                if item.get("status") == "completed":
                    self.dispatch("conversation.item.completed", {"item": item})
        except Exception as e:
            logger.error(f"Error processing event: {e}")
            logger.debug(f"Event data: {event}")

    def _handle_response_output_item_done(self, event):
        item, _ = self._handler_with_dispatch(event)
        if item:
            if item.get("status") == "completed":
                self.dispatch("conversation.item.completed", {"item": item})
            if item.get("formatted", {}).get("tool"):
                asyncio.create_task(self._call_tool(item["formatted"]["tool"]))

    async def _call_tool(self, tool):
        try:
            json_arguments = RealtimeUtils.parse_json(tool["arguments"])
            tool_config = self.tools.get(tool["name"])
            if not tool_config:
                raise ValueError(f'Tool "{tool["name"]}" has not been added')
            result = await tool_config["handler"](json_arguments)
            self.realtime.send(
                "conversation.item.create",
                {
                    "item": {
                        "type": "function_call_output",
                        "call_id": tool["call_id"],
                        "output": RealtimeUtils.stringify_json(result),
                    },
                },
            )
        except Exception as e:
            self.realtime.send(
                "conversation.item.create",
                {
                    "item": {
                        "type": "function_call_output",
                        "call_id": tool["call_id"],
                        "output": RealtimeUtils.stringify_json({"error": str(e)}),
                    },
                },
            )
        self.create_response()

    def is_connected(self) -> bool:
        return self.realtime.is_connected()

    def reset(self) -> bool:
        self.disconnect()
        self.clear_event_handlers()
        self.realtime.clear_event_handlers()
        self._reset_config()
        self._add_api_event_handlers()
        return True

    async def connect(self) -> bool:
        if self.is_connected():
            raise ConnectionError("Already connected, use .disconnect() first")
        await self.realtime.connect()
        self.update_session()
        return True

    async def wait_for_session_created(self) -> bool:
        if not self.is_connected():
            raise ConnectionError("Not connected, use .connect() first")
        while not self.session_created:
            await RealtimeUtils.sleep(1)
        return True

    def disconnect(self) -> None:
        self.session_created = False
        if self.realtime.is_connected():
            self.realtime.disconnect()
        self.conversation.clear()

    def get_turn_detection_type(self) -> Optional[Literal["server_vad"]]:
        return self.session_config.get("turn_detection", {}).get("type")

    def add_tool(
        self, definition: ToolDefinitionType, handler: Callable
    ) -> Dict[str, Union[ToolDefinitionType, Callable]]:
        if not definition.get("name"):
            raise ValueError("Missing tool name in definition")
        name = definition["name"]
        if name in self.tools:
            raise ValueError(
                f'Tool "{name}" already added. Please use .remove_tool("{name}") before trying to add again.'
            )
        if not callable(handler):
            raise TypeError(f'Tool "{name}" handler must be a function')
        self.tools[name] = {"definition": definition, "handler": handler}
        self.update_session()
        return self.tools[name]

    def remove_tool(self, name: str) -> bool:
        if name not in self.tools:
            raise ValueError(f'Tool "{name}" does not exist, can not be removed.')
        del self.tools[name]
        return True

    def delete_item(self, id: str) -> bool:
        self.realtime.send("conversation.item.delete", {"item_id": id})
        return True

    def update_session(self, **kwargs):
        self.session_config.update({k: v for k, v in kwargs.items() if v is not None})

        use_tools = (kwargs.get("tools") or []) + [
            {"type": "function", **tool["definition"]} for tool in self.tools.values()
        ]

        session = {**self.session_config, "tools": use_tools}

        if self.realtime.is_connected():
            self.realtime.send("session.update", {"session": session})

        return True

    def send_user_message_content(
        self, content: List[Union[InputTextContentType, InputAudioContentType]] = []
    ) -> bool:
        if content:
            for c in content:
                if c["type"] == "input_audio":
                    if isinstance(c["audio"], (bytes, bytearray)):
                        c["audio"] = RealtimeUtils.bytes_to_base64(c["audio"])

            self.realtime.send(
                "conversation.item.create",
                {
                    "item": {
                        "type": "message",
                        "role": "user",
                        "content": content,
                    },
                },
            )

        self.create_response()
        return True

    def append_input_audio(self, audio_bytes: bytes) -> bool:
        if audio_bytes:
            self.realtime.send(
                "input_audio_buffer.append",
                {
                    "audio": RealtimeUtils.bytes_to_base64(audio_bytes),
                },
            )
            self.input_audio_buffer += audio_bytes
        return True

    def create_response(self) -> bool:
        if self.get_turn_detection_type() is None and self.input_audio_buffer:
            self.realtime.send("input_audio_buffer.commit")
            self.conversation.queue_input_audio(self.input_audio_buffer)
            self.input_audio_buffer = bytes()

        self.realtime.send("response.create")
        return True

    def cancel_response(
        self, id: Optional[str] = None, sample_count: int = 0
    ) -> Dict[str, Optional[AssistantItemType]]:
        if not id:
            self.realtime.send("response.cancel")
            return {"item": None}
        else:
            item = self.conversation.get_item(id)
            if not item:
                raise ValueError(f'Could not find item "{id}"')
            if item["type"] != "message":
                raise TypeError('Can only cancelResponse messages with type "message"')
            elif item["role"] != "assistant":
                raise ValueError(
                    'Can only cancelResponse messages with role "assistant"'
                )

            self.realtime.send("response.cancel")
            audio_index = next(
                (i for i, c in enumerate(item["content"]) if c["type"] == "audio"), -1
            )
            if audio_index == -1:
                raise ValueError("Could not find audio on item to cancel")

            self.realtime.send(
                "conversation.item.truncate",
                {
                    "item_id": id,
                    "content_index": audio_index,
                    "audio_end_ms": int(
                        (sample_count / self.conversation.default_frequency) * 1000
                    ),
                },
            )
            return {"item": item}

    def send(self, event_name: str, data: Optional[Dict[str, Any]] = None) -> bool:
        if not self.is_connected():
            logger.error("Attempted to send message while not connected")
            return False
        return self.realtime.send(event_name, data)

    async def wait_for_next_item(self) -> Dict[str, ItemType]:
        event = await self.wait_for_next("conversation.item.appended")
        return {"item": event["item"]}

    async def wait_for_next_completed_item(self) -> Dict[str, ItemType]:
        event = await self.wait_for_next("conversation.item.completed")
        return {"item": event["item"]}

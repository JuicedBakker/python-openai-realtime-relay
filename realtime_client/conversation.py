import logging
from typing import Dict, List, Tuple, Optional, TypedDict
from realtime_client.utils import RealtimeUtils


class ItemContentDeltaType(TypedDict, total=False):
    text: str
    audio: bytes
    arguments: str
    transcript: str


class RealtimeConversation:
    default_frequency = 24_000  # 24,000 Hz

    def __init__(self):
        self.clear()

    def clear(self) -> bool:
        self.item_lookup: Dict[str, Dict] = {}
        self.items: List[Dict] = []
        self.response_lookup: Dict[str, Dict] = {}
        self.responses: List[Dict] = []
        self.queued_speech_items: Dict[str, Dict] = {}
        self.queued_transcript_items: Dict[str, Dict] = {}
        self.queued_input_audio: Optional[bytes] = None
        return True

    def queue_input_audio(self, input_audio: bytes) -> bytes:
        self.queued_input_audio = input_audio
        return input_audio

    def process_event(
        self, event: Dict, *args
    ) -> Tuple[Optional[Dict], Optional[ItemContentDeltaType]]:
        if "event_id" not in event:
            logging.error(f"Missing 'event_id' on event: {event}")
            raise ValueError('Missing "event_id" on event')
        if "type" not in event:
            logging.error(f"Missing 'type' on event: {event}")
            raise ValueError('Missing "type" on event')

        event_processor = self.event_processors.get(event["type"])
        if not event_processor:
            logging.error(f"Missing conversation event processor for '{event['type']}'")
            raise ValueError(
                f'Missing conversation event processor for "{event["type"]}"'
            )

        return event_processor(self, event, *args)

    def get_item(self, id: str) -> Optional[Dict]:
        return self.item_lookup.get(id)

    def get_items(self) -> List[Dict]:
        return self.items.copy()

    def _ensure_item_exists(self, item_id: str, event_type: str) -> Dict:
        item = self.item_lookup.get(item_id)
        if not item:
            logging.warning(
                f"{event_type}: Item '{item_id}' not found. Creating placeholder."
            )
            item = {
                "id": item_id,
                "formatted": {"audio": bytes(), "text": "", "transcript": ""},
                "content": [],
                "status": "in_progress",
            }
            self.item_lookup[item_id] = item
            self.items.append(item)
        return item

    # Event processors
    def conversation_item_created(self, event: Dict) -> Tuple[Dict, None]:
        item = event["item"]
        new_item = item.copy()
        if new_item["id"] not in self.item_lookup:
            self.item_lookup[new_item["id"]] = new_item
            self.items.append(new_item)
        new_item["formatted"] = {
            "audio": bytes(),
            "text": "",
            "transcript": "",
        }
        if new_item["id"] in self.queued_speech_items:
            new_item["formatted"]["audio"] = self.queued_speech_items[new_item["id"]][
                "audio"
            ]
            del self.queued_speech_items[new_item["id"]]
        if "content" in new_item:
            text_content = [
                c for c in new_item["content"] if c["type"] in ["text", "input_text"]
            ]
            for content in text_content:
                new_item["formatted"]["text"] += content["text"]
        if new_item["id"] in self.queued_transcript_items:
            new_item["formatted"]["transcript"] = self.queued_transcript_items[
                new_item["id"]
            ]["transcript"]
            del self.queued_transcript_items[new_item["id"]]
        if new_item["type"] == "message":
            if new_item["role"] == "user":
                new_item["status"] = "completed"
                if self.queued_input_audio:
                    new_item["formatted"]["audio"] = self.queued_input_audio
                    self.queued_input_audio = None
            else:
                new_item["status"] = "in_progress"
        elif new_item["type"] == "function_call":
            new_item["formatted"]["tool"] = {
                "type": "function",
                "name": new_item["name"],
                "call_id": new_item["call_id"],
                "arguments": "",
            }
            new_item["status"] = "in_progress"
        elif new_item["type"] == "function_call_output":
            new_item["status"] = "completed"
            new_item["formatted"]["output"] = new_item["output"]
        logging.info(f"Item created: {new_item['id']}")
        return new_item, None

    def conversation_item_truncated(self, event: Dict) -> Tuple[Dict, None]:
        item = self._ensure_item_exists(event["item_id"], "item.truncated")
        audio_end_ms = event["audio_end_ms"]
        end_index = int((audio_end_ms * self.default_frequency) / 1000)
        item["formatted"]["transcript"] = ""
        item["formatted"]["audio"] = item["formatted"]["audio"][:end_index]
        return item, None

    def conversation_item_deleted(self, event: Dict) -> Tuple[Dict, None]:
        item_id = event["item_id"]
        item = self.item_lookup.get(item_id)
        if not item:
            logging.warning(f"item.deleted: Item '{item_id}' not found")
            return None, None
        del self.item_lookup[item["id"]]
        self.items = [i for i in self.items if i["id"] != item["id"]]
        return item, None

    def conversation_item_input_audio_transcription_completed(
        self, event: Dict
    ) -> Tuple[Optional[Dict], ItemContentDeltaType]:
        item_id, content_index, transcript = (
            event["item_id"],
            event["content_index"],
            event["transcript"],
        )
        item = self._ensure_item_exists(
            item_id, "item.input_audio_transcription.completed"
        )
        formatted_transcript = transcript or " "

        # Ensure the content list is long enough
        while len(item["content"]) <= content_index:
            item["content"].append({})

        item["content"][content_index]["transcript"] = transcript
        item["formatted"]["transcript"] = formatted_transcript
        return item, {"transcript": transcript}

    def input_audio_buffer_speech_started(self, event: Dict) -> Tuple[None, None]:
        item_id, audio_start_ms = event["item_id"], event["audio_start_ms"]
        self.queued_speech_items[item_id] = {"audio_start_ms": audio_start_ms}
        return None, None

    def input_audio_buffer_speech_stopped(
        self, event: Dict, input_audio_buffer: bytes
    ) -> Tuple[None, None]:
        item_id, audio_end_ms = event["item_id"], event["audio_end_ms"]
        if item_id not in self.queued_speech_items:
            self.queued_speech_items[item_id] = {"audio_start_ms": audio_end_ms}
        speech = self.queued_speech_items[item_id]
        speech["audio_end_ms"] = audio_end_ms
        if input_audio_buffer:
            start_index = int(
                (speech["audio_start_ms"] * self.default_frequency) / 1000
            )
            end_index = int((speech["audio_end_ms"] * self.default_frequency) / 1000)
            speech["audio"] = input_audio_buffer[start_index:end_index]
        return None, None

    def response_created(self, event: Dict) -> Tuple[None, None]:
        response = event["response"]
        if response["id"] not in self.response_lookup:
            self.response_lookup[response["id"]] = response
            self.responses.append(response)
        return None, None

    def response_output_item_added(self, event: Dict) -> Tuple[None, None]:
        response_id, item = event["response_id"], event["item"]
        response = self.response_lookup.get(response_id)
        if not response:
            logging.warning(
                f"response.output_item.added: Response '{response_id}' not found"
            )
            return None, None
        response["output"].append(item["id"])
        return None, None

    def response_output_item_done(self, event: Dict) -> Tuple[Dict, None]:
        item = event["item"]
        if not item:
            logging.error("response.output_item.done: Missing 'item'")
            raise ValueError('response.output_item.done: Missing "item"')
        found_item = self._ensure_item_exists(item["id"], "response.output_item.done")
        found_item.update(item)
        found_item["status"] = item["status"]
        return found_item, None

    def response_content_part_added(self, event: Dict) -> Tuple[Dict, None]:
        item = self._ensure_item_exists(event["item_id"], "response.content_part.added")
        item["content"].append(event["part"])
        return item, None

    def response_audio_transcript_delta(
        self, event: Dict
    ) -> Tuple[Dict, ItemContentDeltaType]:
        item = self._ensure_item_exists(
            event["item_id"], "response.audio_transcript.delta"
        )
        content_index, delta = event["content_index"], event["delta"]

        # Ensure the content list is long enough
        while len(item["content"]) <= content_index:
            item["content"].append({})

        if "transcript" not in item["content"][content_index]:
            item["content"][content_index]["transcript"] = ""
        item["content"][content_index]["transcript"] += delta
        item["formatted"]["transcript"] += delta
        return item, {"transcript": delta}

    def response_audio_delta(self, event: Dict) -> Tuple[Dict, ItemContentDeltaType]:
        item = self._ensure_item_exists(event["item_id"], "response.audio.delta")
        content_index, delta = event["content_index"], event["delta"]

        # Ensure the content list is long enough
        while len(item["content"]) <= content_index:
            item["content"].append({})

        if "audio" not in item["content"][content_index]:
            item["content"][content_index]["audio"] = ""
        item["content"][content_index]["audio"] += delta
        append_values = RealtimeUtils.base64_to_bytes(delta)
        item["formatted"]["audio"] += append_values
        return item, {"audio": append_values}

    def response_text_delta(self, event: Dict) -> Tuple[Dict, ItemContentDeltaType]:
        item = self._ensure_item_exists(event["item_id"], "response.text.delta")
        content_index, delta = event["content_index"], event["delta"]

        # Ensure the content list is long enough
        while len(item["content"]) <= content_index:
            item["content"].append({})

        if "text" not in item["content"][content_index]:
            item["content"][content_index]["text"] = ""
        item["content"][content_index]["text"] += delta
        item["formatted"]["text"] += delta
        return item, {"text": delta}

    def response_function_call_arguments_delta(
        self, event: Dict
    ) -> Tuple[Dict, ItemContentDeltaType]:
        item = self._ensure_item_exists(
            event["item_id"], "response.function_call_arguments.delta"
        )
        delta = event["delta"]
        if "arguments" not in item:
            item["arguments"] = ""
        item["arguments"] += delta
        if "formatted" not in item:
            item["formatted"] = {}
        if "tool" not in item["formatted"]:
            item["formatted"]["tool"] = {"arguments": ""}
        item["formatted"]["tool"]["arguments"] += delta
        return item, {"arguments": delta}

    event_processors = {
        "conversation.item.created": conversation_item_created,
        "conversation.item.truncated": conversation_item_truncated,
        "conversation.item.deleted": conversation_item_deleted,
        "conversation.item.input_audio_transcription.completed": conversation_item_input_audio_transcription_completed,
        "input_audio_buffer.speech_started": input_audio_buffer_speech_started,
        "input_audio_buffer.speech_stopped": input_audio_buffer_speech_stopped,
        "response.created": response_created,
        "response.output_item.added": response_output_item_added,
        "response.output_item.done": response_output_item_done,
        "response.content_part.added": response_content_part_added,
        "response.audio_transcript.delta": response_audio_transcript_delta,
        "response.audio.delta": response_audio_delta,
        "response.text.delta": response_text_delta,
        "response.function_call_arguments.delta": response_function_call_arguments_delta,
    }

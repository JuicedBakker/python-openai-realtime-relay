import json
import asyncio
import websockets
from urllib.parse import urlparse, parse_qs
from typing import Dict, Any
from realtime_client.client import RealtimeClient


class RealtimeRelay:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.sockets = {}
        self.items = {}

    async def listen(self, port: int):
        server = await websockets.serve(self.connection_handler, "localhost", port)
        self.log(f"Listening on ws://localhost:{port}")
        await server.wait_closed()

    async def relay_to_browser(self, websocket, event: Dict[str, Any]):
        try:
            self.log(f"Attempting to send event to browser: {event['type']}")
            if not websocket.open:
                self.log("WebSocket is not open. Cannot send message.")
                return
            await websocket.send(json.dumps(event))
            self.log(f"Successfully sent event to browser: {event['type']}")
        except websockets.exceptions.ConnectionClosed:
            self.log("WebSocket connection closed while trying to send message")
        except Exception as e:
            self.log(f"Error sending message to browser: {str(e)}")
            self.log(f"Full event: {json.dumps(event, indent=2)}")

    async def connection_handler(self, websocket, path):
        parsed_path = urlparse(path)
        query_params = parse_qs(parsed_path.query)
        model = query_params.get("model", ["gpt-4o-realtime-preview-2024-10-01"])[0]
        self.log(f"New connection with path: '{path}', model: '{model}'")

        client = RealtimeClient(api_key=self.api_key, debug=True)
        client.realtime.set_client_websocket(websocket)

        # Define a whitelist of events to relay to the browser
        event_whitelist = [
            "response.create",
            "input_audio_buffer.commit",
            "input_audio_buffer.append",
            "response.audio_transcript.done",
            "response.content_part.done",
            "response.output_item.done",
            "response.done",
            "conversation.item.created",
            "conversation.item.appended",
            "conversation.item.completed",
            "conversation.updated",
            "realtime.event",
            # Add any other event types you want to relay
        ]

        async def relay_wrapper(event):
            event_type = event.get("event", {}).get("type")
            if event_type in event_whitelist:
                self.log(f"Relaying whitelisted event to browser: {event_type}")
                await self.relay_to_browser(websocket, event)
            else:
                self.log(f"Skipping non-whitelisted event: {event_type}")

        client.on("realtime.event", relay_wrapper)
        client.on("conversation.updated", relay_wrapper)
        client.on("close", lambda *args: asyncio.create_task(websocket.close()))

        async def message_handler(data: str):
            try:
                event = json.loads(data)
                self.log(f"Received event from browser: {event['type']}")

                # Track items
                if event["type"] == "conversation.item.created":
                    item_id = event["item"]["id"]
                    self.items[item_id] = event["item"]
                elif "item_id" in event:
                    item_id = event["item_id"]
                    if item_id not in self.items:
                        self.log(f"Warning: Item {item_id} not found in tracked items")
                        self.items[item_id] = {
                            "id": item_id
                        }  # Create a placeholder item

                # Send the event to OpenAI
                try:
                    if client.send(event["type"], event):
                        self.log(f"Successfully sent '{event['type']}' to OpenAI")
                    else:
                        self.log(f"Failed to send '{event['type']}' to OpenAI")
                except Exception as e:
                    self.log(f"Error sending event to OpenAI: {str(e)}")

            except json.JSONDecodeError:
                self.log(f"Error parsing event from client: {data}")
            except Exception as e:
                self.log(f"Error handling message: {str(e)}")

        try:
            self.log(f"Connecting to OpenAI with model '{model}'...")
            await client.connect()
            self.log("Connected to OpenAI successfully!")

            async for message in websocket:
                self.log(
                    f"Received message from browser: {message[:100]}..."
                )  # Log first 100 chars
                await message_handler(message)
        except websockets.exceptions.ConnectionClosed:
            self.log("WebSocket connection closed")
        except Exception as e:
            self.log(f"Error in connection handler: {str(e)}")
        finally:
            client.disconnect()
            self.log("Disconnected from OpenAI")

    def log(self, message):
        print(f"[RealtimeRelay] {message}")

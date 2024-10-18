import json
import asyncio
import traceback
import websockets
from typing import Optional, Dict, Any
from realtime_client.event_handler import RealtimeEventHandler
from realtime_client.utils import RealtimeUtils


class RealtimeAPI(RealtimeEventHandler):
    def __init__(
        self,
        url: Optional[str] = None,
        api_key: Optional[str] = None,
        dangerously_allow_api_key_in_browser: bool = False,
        debug: bool = False,
    ):
        super().__init__()
        self.default_url = "wss://api.openai.com/v1/realtime"
        self.url = url or self.default_url
        self.api_key = api_key
        self.debug = debug
        self.ws = None
        self.client_ws = None  # Add this line to store the client WebSocket

        if hasattr(globals(), "document") and self.api_key:
            if not dangerously_allow_api_key_in_browser:
                raise ValueError(
                    "Can not provide API key in the browser without "
                    '"dangerously_allow_api_key_in_browser" set to true'
                )

    def is_connected(self) -> bool:
        return self.ws is not None and self.ws.open

    def log(self, *args) -> bool:
        if self.debug:
            date = RealtimeUtils.iso_timestamp()
            logs = [f"[Websocket/{date}]"] + [
                json.dumps(arg, indent=2) if isinstance(arg, dict) else str(arg)
                for arg in args
            ]
            print(*logs)
        return True

    async def connect(self, model: str = "gpt-4o-realtime-preview-2024-10-01") -> bool:
        if not self.api_key and self.url == self.default_url:
            raise ValueError(f'No apiKey provided for connection to "{self.url}"')
        if self.is_connected():
            raise ConnectionError("Already connected")

        websocket_url = f"{self.url}{'?model=' + model if model else ''}"
        extra_headers = {
            "Authorization": f"Bearer {self.api_key}",
        }

        try:
            self.log(f"Connecting to {websocket_url}")
            self.ws = await websockets.connect(
                websocket_url,
                extra_headers=extra_headers,
                subprotocols=[
                    "realtime",
                    "openai-beta.realtime-v1",
                ],
            )
            self.log(f'Connected to "{self.url}"')

            # Set up message handling
            asyncio.create_task(self._handle_messages())

            # Set up error and close handling
            asyncio.create_task(self._monitor_connection())

            return True
        except Exception as e:
            self.log(f'Could not connect to "{self.url}": {str(e)}')
            self.ws = None
            raise ConnectionError(f'Could not connect to "{self.url}": {str(e)}') from e

    def disconnect(self) -> bool:
        if self.ws:
            asyncio.create_task(self.ws.close())
        self.ws = None
        return True

    async def _handle_messages(self):
        if not self.ws:
            self.log("WebSocket connection is not established.")
            return

        try:
            async for message in self.ws:
                self.log("Received message:", message)
                try:
                    data = json.loads(message)
                    if isinstance(data, dict) and "type" in data:
                        self.receive(data["type"], data)
                        await self.send_to_client(
                            data
                        )  # Add this line to send to client
                    else:
                        self.log("Received message in unexpected format:", data)
                except json.JSONDecodeError:
                    self.log("Error decoding JSON message:", message)
                except Exception as e:
                    self.log("Error processing message:")
                    self.log(f"Message content: {message}")
                    self.log(f"Error type: {type(e).__name__}")
                    self.log(f"Error message: {str(e)}")
                    self.log("Traceback:")
                    self.log(traceback.format_exc())
        except websockets.exceptions.ConnectionClosed:
            self.log("WebSocket connection closed.")
        except Exception as e:
            self.log(f"Error in _handle_messages:")
            self.log(f"Error type: {type(e).__name__}")
            self.log(f"Error message: {str(e)}")
            self.log("Traceback:")
            self.log(traceback.format_exc())
        finally:
            self.disconnect()

    async def send_to_client(self, data: Dict[str, Any]):
        if self.client_ws and self.client_ws.open:
            try:
                await self.client_ws.send(json.dumps(data))
                self.log("Sent message to client:", data)
            except Exception as e:
                self.log(f"Error sending message to client: {str(e)}")
        else:
            self.log("Client WebSocket is not connected. Unable to send message.")

    def set_client_websocket(self, ws):
        self.client_ws = ws

    def receive(self, event_name: str, event: Dict[str, Any]) -> bool:
        self.dispatch(f"server.{event_name}", event)
        self.dispatch("server.*", event)
        return True

    async def _monitor_connection(self):
        while self.is_connected():
            try:
                await self.ws.ping()
            except:
                self.log("Connection lost")
                self.dispatch("close", {"error": True})
                self.disconnect()
                break
            await asyncio.sleep(30)  # Check connection every 30 seconds

    def send(self, event_name: str, data: Optional[Dict[str, Any]] = None) -> bool:
        if not self.is_connected():
            raise ConnectionError("RealtimeAPI is not connected")

        data = data or {}
        if not isinstance(data, dict):
            raise TypeError("data must be a dictionary")

        event = {
            "event_id": RealtimeUtils.generate_id("evt_"),
            "type": event_name,
            **data,
        }
        self.dispatch(f"client.{event_name}", event)
        self.dispatch("client.*", event)
        self.log("sent:", event_name, event)

        asyncio.create_task(self.ws.send(json.dumps(event)))
        return True

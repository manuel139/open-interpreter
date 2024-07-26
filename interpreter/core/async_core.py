import asyncio
import json
import os
import shutil
import socket
import threading
import time
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import shortuuid
from pydantic import BaseModel

from .core import OpenInterpreter

try:
    import janus
    import uvicorn
    from fastapi import (
        APIRouter,
        FastAPI,
        File,
        Form,
        HTTPException,
        Request,
        UploadFile,
        WebSocket,
    )
    from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
    from starlette.status import HTTP_403_FORBIDDEN
except:
    # Server dependencies are not required by the main package.
    pass


complete_message = {"role": "server", "type": "status", "content": "complete"}


class AsyncInterpreter(OpenInterpreter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.respond_thread = None
        self.stop_event = threading.Event()
        self.output_queue = None
        self.id = os.getenv("INTERPRETER_ID", datetime.now().timestamp())
        self.print = True  # Will print output

        self.require_acknowledge = (
            os.getenv("INTERPRETER_REQUIRE_ACKNOWLEDGE", "False").lower() == "true"
        )
        self.acknowledged_outputs = []

        self.server = Server(self)

    async def input(self, chunk):
        """
        Accumulates LMC chunks onto interpreter.messages.
        When it hits an "end" flag, calls interpreter.respond().
        """

        if "start" in chunk:
            # If the user is starting something, the interpreter should stop.
            if self.respond_thread is not None and self.respond_thread.is_alive():
                self.stop_event.set()
                self.respond_thread.join()
            self.accumulate(chunk)
        elif "content" in chunk:
            self.accumulate(chunk)
        elif "end" in chunk:
            # If the user is done talking, the interpreter should respond.

            run_code = None  # Will later default to auto_run unless the user makes a command here

            # But first, process any commands.
            if self.messages[-1].get("type") == "command":
                command = self.messages[-1]["content"]
                self.messages = self.messages[:-1]

                if command == "stop":
                    # Any start flag would have stopped it a moment ago, but to be sure:
                    self.stop_event.set()
                    self.respond_thread.join()
                    return
                if command == "go":
                    # This is to approve code.
                    run_code = True
                    pass

            self.stop_event.clear()
            self.respond_thread = threading.Thread(
                target=self.respond, args=(run_code,)
            )
            self.respond_thread.start()

    async def output(self):
        if self.output_queue == None:
            self.output_queue = janus.Queue()
        return await self.output_queue.async_q.get()

    def respond(self, run_code=None):
        try:
            if run_code == None:
                run_code = self.auto_run

            for chunk_og in self._respond_and_store():
                chunk = (
                    chunk_og.copy()
                )  # This fixes weird double token chunks. Probably a deeper problem?

                if chunk["type"] == "confirmation":
                    if run_code:
                        run_code = False
                        continue
                    else:
                        break

                if self.stop_event.is_set():
                    return

                if self.print:
                    if "start" in chunk:
                        print("\n")
                    if chunk["type"] in ["code", "console"] and "format" in chunk:
                        if "start" in chunk:
                            print("\n------------\n\n```" + chunk["format"], flush=True)
                        if "end" in chunk:
                            print("\n```\n\n------------\n\n", flush=True)
                    if chunk.get("format") != "active_line":
                        print(chunk.get("content", ""), end="", flush=True)

                self.output_queue.sync_q.put(chunk)

            self.output_queue.sync_q.put(complete_message)
        except Exception as e:
            error = traceback.format_exc() + "\n" + str(e)
            error_message = {
                "role": "server",
                "type": "error",
                "content": traceback.format_exc() + "\n" + str(e),
            }
            self.output_queue.sync_q.put(error_message)
            self.output_queue.sync_q.put(complete_message)
            print("\n\n--- SENT ERROR: ---\n\n")
            print(error)
            print("\n\n--- (ERROR ABOVE WAS SENT) ---\n\n")

    def accumulate(self, chunk):
        """
        Accumulates LMC chunks onto interpreter.messages.
        """
        if type(chunk) == str:
            chunk = json.loads(chunk)

        if type(chunk) == dict:
            if chunk.get("format") == "active_line":
                # We don't do anything with these.
                pass

            elif "content" in chunk and not (
                len(self.messages) > 0
                and (
                    (
                        "type" in self.messages[-1]
                        and chunk.get("type") != self.messages[-1].get("type")
                    )
                    or (
                        "format" in self.messages[-1]
                        and chunk.get("format") != self.messages[-1].get("format")
                    )
                )
            ):
                if len(self.messages) == 0:
                    raise Exception(
                        "You must send a 'start: True' chunk first to create this message."
                    )
                # Append to an existing message
                if (
                    "type" not in self.messages[-1]
                ):  # It was created with a type-less start message
                    self.messages[-1]["type"] = chunk["type"]
                if (
                    chunk.get("format") and "format" not in self.messages[-1]
                ):  # It was created with a type-less start message
                    self.messages[-1]["format"] = chunk["format"]
                if "content" not in self.messages[-1]:
                    self.messages[-1]["content"] = chunk["content"]
                else:
                    self.messages[-1]["content"] += chunk["content"]

            # elif "content" in chunk and (len(self.messages) > 0 and self.messages[-1] == {'role': 'user', 'start': True}):
            #     # Last message was {'role': 'user', 'start': True}. Just populate that with this chunk
            #     self.messages[-1] = chunk.copy()

            elif "start" in chunk or (
                len(self.messages) > 0
                and (
                    chunk.get("type") != self.messages[-1].get("type")
                    or chunk.get("format") != self.messages[-1].get("format")
                )
            ):
                # Create a new message
                chunk_copy = (
                    chunk.copy()
                )  # So we don't modify the original chunk, which feels wrong.
                if "start" in chunk_copy:
                    chunk_copy.pop("start")
                if "content" not in chunk_copy:
                    chunk_copy["content"] = ""
                self.messages.append(chunk_copy)

        elif type(chunk) == bytes:
            if self.messages[-1]["content"] == "":  # We initialize as an empty string ^
                self.messages[-1]["content"] = b""  # But it actually should be bytes
            self.messages[-1]["content"] += chunk


def authenticate_function(key):
    """
    This function checks if the provided key is valid for authentication.

    Returns True if the key is valid, False otherwise.
    """
    # Fetch the API key from the environment variables. If it's not set, return True.
    api_key = os.getenv("INTERPRETER_API_KEY", None)

    # If the API key is not set in the environment variables, return True.
    # Otherwise, check if the provided key matches the fetched API key.
    # Return True if they match, False otherwise.
    if api_key is None:
        return True
    else:
        return key == api_key


def create_router(async_interpreter):
    router = APIRouter()

    @router.get("/heartbeat")
    async def heartbeat():
        return {"status": "alive"}

    @router.get("/")
    async def home():
        return PlainTextResponse(
            """
            <!DOCTYPE html>
            <html>
            <head>
                <title>Chat</title>
            </head>
            <body>
                <form action="" onsubmit="sendMessage(event)">
                    <textarea id="messageInput" rows="10" cols="50" autocomplete="off"></textarea>
                    <button>Send</button>
                </form>
                <button id="approveCodeButton">Approve Code</button>
                <button id="authButton">Send Auth</button>
                <div id="messages"></div>
                <script>
                    var ws = new WebSocket("ws://"""
            + async_interpreter.server.host
            + ":"
            + str(async_interpreter.server.port)
            + """/");
                    var lastMessageElement = null;

                    ws.onmessage = function(event) {

                        var eventData = JSON.parse(event.data);

                        """
            + (
                """
                        
                        // Acknowledge receipt
                        var acknowledge_message = {
                            "ack": eventData.id
                        };
                        ws.send(JSON.stringify(acknowledge_message));

                        """
                if async_interpreter.require_acknowledge
                else ""
            )
            + """

                        if (lastMessageElement == null) {
                            lastMessageElement = document.createElement('p');
                            document.getElementById('messages').appendChild(lastMessageElement);
                            lastMessageElement.innerHTML = "<br>"
                        }

                        if ((eventData.role == "assistant" && eventData.type == "message" && eventData.content) ||
                            (eventData.role == "computer" && eventData.type == "console" && eventData.format == "output" && eventData.content) ||
                            (eventData.role == "assistant" && eventData.type == "code" && eventData.content)) {
                            lastMessageElement.innerHTML += eventData.content;
                        } else {
                            lastMessageElement.innerHTML += "<br><br>" + JSON.stringify(eventData) + "<br><br>";
                        }
                    };
                    function sendMessage(event) {
                        event.preventDefault();
                        var input = document.getElementById("messageInput");
                        var message = input.value;
                        if (message.startsWith('{') && message.endsWith('}')) {
                            message = JSON.stringify(JSON.parse(message));
                            ws.send(message);
                        } else {
                            var startMessageBlock = {
                                "role": "user",
                                //"type": "message",
                                "start": true
                            };
                            ws.send(JSON.stringify(startMessageBlock));

                            var messageBlock = {
                                "role": "user",
                                "type": "message",
                                "content": message
                            };
                            ws.send(JSON.stringify(messageBlock));

                            var endMessageBlock = {
                                "role": "user",
                                //"type": "message",
                                "end": true
                            };
                            ws.send(JSON.stringify(endMessageBlock));
                        }
                        var userMessageElement = document.createElement('p');
                        userMessageElement.innerHTML = '<b>' + input.value + '</b><br>';
                        document.getElementById('messages').appendChild(userMessageElement);
                        lastMessageElement = document.createElement('p');
                        document.getElementById('messages').appendChild(lastMessageElement);
                        input.value = '';
                    }
                function approveCode() {
                    var startCommandBlock = {
                        "role": "user",
                        "type": "command",
                        "start": true
                    };
                    ws.send(JSON.stringify(startCommandBlock));

                    var commandBlock = {
                        "role": "user",
                        "type": "command",
                        "content": "go"
                    };
                    ws.send(JSON.stringify(commandBlock));

                    var endCommandBlock = {
                        "role": "user",
                        "type": "command",
                        "end": true
                    };
                    ws.send(JSON.stringify(endCommandBlock));
                }
                function authenticate() {
                    var authBlock = {
                        "auth": "dummy-api-key"
                    };
                    ws.send(JSON.stringify(authBlock));
                }

                document.getElementById("approveCodeButton").addEventListener("click", approveCode);
                document.getElementById("authButton").addEventListener("click", authenticate);
                </script>
            </body>
            </html>
            """,
            media_type="text/html",
        )

    @router.websocket("/")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket.accept()

        try:

            async def receive_input():
                authenticated = False
                while True:
                    try:
                        data = await websocket.receive()

                        if not authenticated:
                            if "text" in data:
                                data = json.loads(data["text"])
                                if "auth" in data:
                                    if async_interpreter.server.authenticate(
                                        data["auth"]
                                    ):
                                        authenticated = True
                                        await websocket.send_text(
                                            json.dumps({"auth": True})
                                        )
                            if not authenticated:
                                await websocket.send_text(json.dumps({"auth": False}))
                            continue

                        if data.get("type") == "websocket.receive":
                            if "text" in data:
                                data = json.loads(data["text"])
                                if (
                                    async_interpreter.require_acknowledge
                                    and "ack" in data
                                ):
                                    async_interpreter.acknowledged_outputs.append(
                                        data["ack"]
                                    )
                                    continue
                            elif "bytes" in data:
                                data = data["bytes"]
                            await async_interpreter.input(data)
                        elif data.get("type") == "websocket.disconnect":
                            print("Disconnecting.")
                            return
                        else:
                            print("Invalid data:", data)
                            continue

                    except Exception as e:
                        error = traceback.format_exc() + "\n" + str(e)
                        error_message = {
                            "role": "server",
                            "type": "error",
                            "content": traceback.format_exc() + "\n" + str(e),
                        }
                        await websocket.send_text(json.dumps(error_message))
                        await websocket.send_text(json.dumps(complete_message))
                        print("\n\n--- SENT ERROR: ---\n\n")
                        print(error)
                        print("\n\n--- (ERROR ABOVE WAS SENT) ---\n\n")

            async def send_output():
                while True:
                    try:
                        output = await async_interpreter.output()
                        # print("Attempting to send the following output:", output)

                        id = shortuuid.uuid()

                        for attempt in range(100):
                            try:
                                if isinstance(output, bytes):
                                    await websocket.send_bytes(output)
                                else:
                                    if async_interpreter.require_acknowledge:
                                        output["id"] = id

                                    await websocket.send_text(json.dumps(output))

                                    if async_interpreter.require_acknowledge:
                                        acknowledged = False
                                        for _ in range(1000):
                                            # print(async_interpreter.acknowledged_outputs)
                                            if (
                                                id
                                                in async_interpreter.acknowledged_outputs
                                            ):
                                                async_interpreter.acknowledged_outputs.remove(
                                                    id
                                                )
                                                acknowledged = True
                                                break
                                            await asyncio.sleep(0.0001)

                                        if acknowledged:
                                            break
                                        else:
                                            raise Exception(
                                                "Acknowledgement not received."
                                            )
                                    else:
                                        break

                            except Exception as e:
                                print(
                                    "Failed to send output on attempt number:",
                                    attempt + 1,
                                    ". Output was:",
                                    output,
                                )
                                print("Error:", str(e))
                                await asyncio.sleep(0.05)
                        else:
                            raise Exception(
                                "Failed to send after 100 attempts. Output was:",
                                str(output),
                            )
                    except Exception as e:
                        error = traceback.format_exc() + "\n" + str(e)
                        error_message = {
                            "role": "server",
                            "type": "error",
                            "content": traceback.format_exc() + "\n" + str(e),
                        }
                        await websocket.send_text(json.dumps(error_message))
                        await websocket.send_text(json.dumps(complete_message))
                        print("\n\n--- SENT ERROR: ---\n\n")
                        print(error)
                        print("\n\n--- (ERROR ABOVE WAS SENT) ---\n\n")

            await asyncio.gather(receive_input(), send_output())
        except Exception as e:
            try:
                error = traceback.format_exc() + "\n" + str(e)
                error_message = {
                    "role": "server",
                    "type": "error",
                    "content": traceback.format_exc() + "\n" + str(e),
                }
                await websocket.send_text(json.dumps(error_message))
                await websocket.send_text(json.dumps(complete_message))
                print("\n\n--- SENT ERROR: ---\n\n")
                print(error)
                print("\n\n--- (ERROR ABOVE WAS SENT) ---\n\n")
            except:
                # If we can't send it, that's fine.
                pass
        finally:
            await websocket.close()

    # TODO
    @router.post("/")
    async def post_input(payload: Dict[str, Any]):
        try:
            async_interpreter.input(payload)
            return {"status": "success"}
        except Exception as e:
            return {"error": str(e)}, 500

    @router.post("/settings")
    async def set_settings(payload: Dict[str, Any]):
        for key, value in payload.items():
            print(f"Updating settings: {key} = {value}")
            if key in ["llm", "computer"] and isinstance(value, dict):
                if key == "auto_run":
                    return {
                        "error": f"The setting {key} is not modifiable through the server due to security constraints."
                    }, 403
                if hasattr(async_interpreter, key):
                    for sub_key, sub_value in value.items():
                        if hasattr(getattr(async_interpreter, key), sub_key):
                            setattr(getattr(async_interpreter, key), sub_key, sub_value)
                        else:
                            return {
                                "error": f"Sub-setting {sub_key} not found in {key}"
                            }, 404
                else:
                    return {"error": f"Setting {key} not found"}, 404
            elif hasattr(async_interpreter, key):
                setattr(async_interpreter, key, value)
            else:
                return {"error": f"Setting {key} not found"}, 404

        return {"status": "success"}

    @router.get("/settings/{setting}")
    async def get_setting(setting: str):
        if hasattr(async_interpreter, setting):
            setting_value = getattr(async_interpreter, setting)
            try:
                return json.dumps({setting: setting_value})
            except TypeError:
                return {"error": "Failed to serialize the setting value"}, 500
        else:
            return json.dumps({"error": "Setting not found"}), 404

    if os.getenv("INTERPRETER_INSECURE_ROUTES", "").lower() == "true":

        @router.post("/run")
        async def run_code(payload: Dict[str, Any]):
            language, code = payload.get("language"), payload.get("code")
            if not (language and code):
                return {"error": "Both 'language' and 'code' are required."}, 400
            try:
                print(f"Running {language}:", code)
                output = async_interpreter.computer.run(language, code)
                print("Output:", output)
                return {"output": output}
            except Exception as e:
                return {"error": str(e)}, 500

        @router.post("/upload")
        async def upload_file(file: UploadFile = File(...), path: str = Form(...)):
            try:
                with open(path, "wb") as output_file:
                    shutil.copyfileobj(file.file, output_file)
                return {"status": "success"}
            except Exception as e:
                return {"error": str(e)}, 500

        @router.get("/download/{filename}")
        async def download_file(filename: str):
            try:
                return StreamingResponse(
                    open(filename, "rb"), media_type="application/octet-stream"
                )
            except Exception as e:
                return {"error": str(e)}, 500

    ### OPENAI COMPATIBLE ENDPOINT

    class ChatMessage(BaseModel):
        role: str
        content: Union[str, List[Dict[str, Any]]]

    class ChatCompletionRequest(BaseModel):
        model: str = "default-model"
        messages: List[ChatMessage]
        max_tokens: Optional[int] = None
        temperature: Optional[float] = None
        stream: Optional[bool] = False

    async def openai_compatible_generator():
        for i, chunk in enumerate(async_interpreter._respond_and_store()):
            output_content = None

            if chunk["type"] == "message" and "content" in chunk:
                output_content = chunk["content"]
            if chunk["type"] == "code" and "start" in chunk:
                output_content = " "

            if output_content:
                await asyncio.sleep(0)
                output_chunk = {
                    "id": i,
                    "object": "chat.completion.chunk",
                    "created": time.time(),
                    "model": "open-interpreter",
                    "choices": [{"delta": {"content": output_content}}],
                }
                yield f"data: {json.dumps(output_chunk)}\n\n"

    @router.post("/openai/chat/completions")
    async def chat_completion(request: ChatCompletionRequest):
        # Convert to LMC

        user_messages = []
        for message in reversed(request.messages):
            if message.role == "user":
                user_messages.append(message)
            else:
                break
        user_messages.reverse()

        for message in user_messages:
            if type(message.content) == str:
                async_interpreter.messages.append(
                    {"role": "user", "type": "message", "content": message.content}
                )
            if type(message.content) == list:
                for content in message.content:
                    if content["type"] == "text":
                        async_interpreter.messages.append(
                            {"role": "user", "type": "message", "content": content}
                        )
                    elif content["type"] == "image_url":
                        if "url" not in content["image_url"]:
                            raise Exception("`url` must be in `image_url`.")
                        url = content["image_url"]["url"]
                        print(url[:100])
                        if "base64," not in url:
                            raise Exception(
                                '''Image must be in the format: "data:image/jpeg;base64,{base64_image}"'''
                            )

                        # data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAA6oA...

                        data = url.split("base64,")[1]
                        format = "base64." + url.split(";")[0].split("/")[1]
                        async_interpreter.messages.append(
                            {
                                "role": "user",
                                "type": "image",
                                "format": format,
                                "content": data,
                            }
                        )

        if request.stream:
            return StreamingResponse(
                openai_compatible_generator(), media_type="application/x-ndjson"
            )
        else:
            messages = async_interpreter.chat(message="", stream=False, display=True)
            content = messages[-1]["content"]
            return {
                "id": "200",
                "object": "chat.completion",
                "created": time.time(),
                "model": request.model,
                "choices": [{"message": {"role": "assistant", "content": content}}],
            }

    return router


class Server:
    DEFAULT_HOST = "127.0.0.1"
    DEFAULT_PORT = 8000

    def __init__(self, async_interpreter, host=None, port=None):
        self.app = FastAPI()
        router = create_router(async_interpreter)
        self.authenticate = authenticate_function

        # Add authentication middleware
        @self.app.middleware("http")
        async def validate_api_key(request: Request, call_next):
            api_key = request.headers.get("X-API-KEY")
            if self.authenticate(api_key):
                response = await call_next(request)
                return response
            else:
                return JSONResponse(
                    status_code=HTTP_403_FORBIDDEN,
                    content={"detail": "Authentication failed"},
                )

        self.app.include_router(router)
        h = host or os.getenv("HOST", Server.DEFAULT_HOST)
        p = port or int(os.getenv("PORT", Server.DEFAULT_PORT))
        self.config = uvicorn.Config(app=self.app, host=h, port=p)
        self.uvicorn_server = uvicorn.Server(self.config)

    @property
    def host(self):
        return self.config.host

    @host.setter
    def host(self, value):
        self.config.host = value
        self.uvicorn_server = uvicorn.Server(self.config)

    @property
    def port(self):
        return self.config.port

    @port.setter
    def port(self, value):
        self.config.port = value
        self.uvicorn_server = uvicorn.Server(self.config)

    def run(self, host=None, port=None, retries=5):
        if host is not None:
            self.host = host
        if port is not None:
            self.port = port

        # Print server information
        if self.host == "0.0.0.0":
            print(
                "Warning: Using host `0.0.0.0` will expose Open Interpreter over your local network."
            )
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))  # Google's public DNS server
            print(f"Server will run at http://{s.getsockname()[0]}:{self.port}")
            s.close()
        else:
            print(f"Server will run at http://{self.host}:{self.port}")

        for _ in range(retries):
            try:
                self.uvicorn_server.run()
                break
            except KeyboardInterrupt:
                break
            except ImportError as e:
                if _ == 4:  # If this is the last attempt
                    raise ImportError(
                        str(e)
                        + """\n\nPlease ensure you have run `pip install "open-interpreter[server]"` to install server dependencies."""
                    )
            except:
                print("An unexpected error occurred:", traceback.format_exc())
                print("Server restarting.")

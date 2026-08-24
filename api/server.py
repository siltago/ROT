"""WebSocket gateway between tablet perception and the Robot Brain."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, ValidationError

from app.config import settings
from app.main import build_agent
from brain.agent import RobotAgent, TurnResult
from brain.models import IntentType

logger = logging.getLogger(__name__)


class DeviceMessage(BaseModel):
    version: int = 1
    type: str
    device_id: str
    timestamp: int
    payload: dict[str, Any] = Field(default_factory=dict)


def outgoing_message(message_type: str, device_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    message: dict[str, Any] = {
        "version": 1,
        "type": message_type,
        "device_id": device_id,
        "timestamp": int(time.time() * 1000),
    }
    if payload is not None:
        message["payload"] = payload
    return message


@dataclass
class DeviceSession:
    device_id: str
    websocket: WebSocket
    capabilities: set[str] = field(default_factory=set)


class DeviceRegistry:
    def __init__(self) -> None:
        self._sessions: dict[str, DeviceSession] = {}

    def connect(self, session: DeviceSession) -> None:
        self._sessions[session.device_id] = session

    def disconnect(self, device_id: str, websocket: WebSocket) -> None:
        current = self._sessions.get(device_id)
        if current and current.websocket is websocket:
            self._sessions.pop(device_id, None)

    def get(self, device_id: str) -> DeviceSession | None:
        return self._sessions.get(device_id)

    def count(self) -> int:
        return len(self._sessions)


def expression_for_result(result: TurnResult, mood: str) -> str:
    if result.decision.type == IntentType.AMBIGUOUS:
        return "confused"
    if result.decision.type == IntentType.QUESTION:
        return "curious"
    return {
        "cheerful": "happy",
        "curious": "curious",
        "tired": "sleepy",
        "down": "sad",
        "irritated": "confused",
    }.get(mood, "neutral")


SendMessage = Callable[[dict[str, Any]], Awaitable[None]]


class TabletBrainBridge:
    def __init__(self, agent: RobotAgent) -> None:
        self.agent = agent
        self._turn_lock = asyncio.Lock()

    async def process_text(self, *, text: str, device_id: str, send: SendMessage) -> None:
        cleaned = text.strip()
        if not cleaned:
            return
        await send(outgoing_message("set_state", device_id, {"state": "THINKING"}))
        await send(
            outgoing_message(
                "show_transcript",
                device_id,
                {"text": cleaned, "final": True},
            )
        )
        try:
            async with self._turn_lock:
                result = await self.agent.process_turn(cleaned)
                mood = self.agent.emotional_engine.state.mood_label()
            expression = expression_for_result(result, mood)
            await send(
                outgoing_message(
                    "set_expression",
                    device_id,
                    {"expression": expression, "intensity": 0.8, "mood": mood},
                )
            )
            await send(
                outgoing_message(
                    "show_message",
                    device_id,
                    {"title": "Robot", "message": result.reply},
                )
            )
            await send(
                outgoing_message(
                    "speak",
                    device_id,
                    {"text": result.reply, "language": "pt-BR"},
                )
            )
            await send(outgoing_message("set_state", device_id, {"state": "IDLE"}))
        except Exception:
            logger.exception("Failed to process tablet speech")
            await send(outgoing_message("set_state", device_id, {"state": "ERROR"}))
            await send(
                outgoing_message(
                    "show_message",
                    device_id,
                    {
                        "title": "Erro",
                        "message": "Não consegui consultar o cérebro agora. Verifique o Ollama.",
                        "is_error": True,
                    },
                )
            )


def create_app(agent: RobotAgent | None = None) -> FastAPI:
    application = FastAPI(title="Robot Brain Tablet API", version="0.1.0")
    registry = DeviceRegistry()
    bridge = TabletBrainBridge(agent or build_agent(interactive_confirmation=False))
    application.state.registry = registry
    application.state.bridge = bridge

    @application.get("/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok", "devices": registry.count(), "llm": settings.llm_provider}

    @application.websocket("/ws/device")
    async def device_socket(websocket: WebSocket) -> None:
        await websocket.accept()
        device_id = "unknown"
        try:
            while True:
                raw = await websocket.receive_json()
                try:
                    message = DeviceMessage.model_validate(raw)
                except ValidationError:
                    logger.warning("Ignoring invalid device message")
                    continue
                device_id = message.device_id
                if message.type == "device_hello":
                    capabilities = {str(value) for value in message.payload.get("capabilities", [])}
                    registry.connect(DeviceSession(device_id, websocket, capabilities))
                    await websocket.send_json(
                        outgoing_message("set_state", device_id, {"state": "LISTENING"})
                    )
                elif message.type == "recognized_speech" and message.payload.get("is_final", False):
                    await bridge.process_text(
                        text=str(message.payload.get("text", "")),
                        device_id=device_id,
                        send=websocket.send_json,
                    )
                elif message.type == "device_status":
                    logger.debug("Status from %s: %s", device_id, message.payload)
        except WebSocketDisconnect:
            pass
        finally:
            registry.disconnect(device_id, websocket)

    return application


app = create_app()


def main() -> None:
    uvicorn.run(app, host=settings.api_host, port=settings.api_port, reload=False)


if __name__ == "__main__":
    main()

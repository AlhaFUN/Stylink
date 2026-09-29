#!/usr/bin/env python3
"""Connect to the Android USB-tether service and inject Windows synthetic pen input."""

from __future__ import annotations

import argparse
import asyncio
import base64
import ctypes
import json
import math
import sys
from dataclasses import dataclass
from typing import Any

PORT = 8765
MAX_LINE = 2 * 1024 * 1024
AUTH_TOKEN = "MySecretToken123"
SERVICE_GREETING = {"type": "service", "name": "s23-drawing-tablet", "v": 1}

if sys.platform != "win32":
    raise SystemExit("This host injector requires Windows 10 1809+ (desktop).")


UINT32 = ctypes.c_uint32
INT32 = ctypes.c_int32
DWORD = ctypes.c_uint32
HANDLE = ctypes.c_void_p
HWND = ctypes.c_void_p


class POINT(ctypes.Structure):
    _fields_ = [("x", INT32), ("y", INT32)]


class POINTER_INFO(ctypes.Structure):
    _fields_ = [
        ("pointerType", INT32),
        ("pointerId", UINT32),
        ("frameId", UINT32),
        ("pointerFlags", UINT32),
        ("sourceDevice", HANDLE),
        ("hwndTarget", HWND),
        ("ptPixelLocation", POINT),
        ("ptHimetricLocation", POINT),
        ("ptPixelLocationRaw", POINT),
        ("ptHimetricLocationRaw", POINT),
        ("dwTime", DWORD),
        ("historyCount", UINT32),
        ("InputData", INT32),
        ("dwKeyStates", DWORD),
        ("PerformanceCount", ctypes.c_uint64),
        ("ButtonChangeType", INT32),
    ]


class POINTER_PEN_INFO(ctypes.Structure):
    _fields_ = [
        ("pointerInfo", POINTER_INFO),
        ("penFlags", UINT32),
        ("penMask", UINT32),
        ("pressure", UINT32),
        ("rotation", UINT32),
        ("tiltX", INT32),
        ("tiltY", INT32),
    ]


class POINTER_TYPE_INFO_UNION(ctypes.Union):
    _fields_ = [("penInfo", POINTER_PEN_INFO)]


class POINTER_TYPE_INFO(ctypes.Structure):
    _anonymous_ = ("data",)
    _fields_ = [("type", INT32), ("data", POINTER_TYPE_INFO_UNION)]


# Win32 constants from winuser.h.
PT_PEN = 3
POINTER_FEEDBACK_NONE = 3
PEN_MASK_PRESSURE = 0x0001
PEN_MASK_TILT_X = 0x0004
PEN_MASK_TILT_Y = 0x0008
PEN_FLAG_BARREL = 0x0001
PEN_FLAG_INVERTED = 0x0002
PEN_FLAG_ERASER = 0x0004

POINTER_FLAG_NEW = 0x00000001
POINTER_FLAG_INRANGE = 0x00000002
POINTER_FLAG_INCONTACT = 0x00000004
POINTER_FLAG_FIRSTBUTTON = 0x00000010
POINTER_FLAG_SECONDBUTTON = 0x00000020
POINTER_FLAG_PRIMARY = 0x00002000
POINTER_FLAG_CANCELED = 0x00008000
POINTER_FLAG_DOWN = 0x00010000
POINTER_FLAG_UPDATE = 0x00020000
POINTER_FLAG_UP = 0x00040000

POINTER_CHANGE_NONE = 0
POINTER_CHANGE_FIRSTBUTTON_DOWN = 1
POINTER_CHANGE_FIRSTBUTTON_UP = 2
POINTER_CHANGE_SECONDBUTTON_DOWN = 3
POINTER_CHANGE_SECONDBUTTON_UP = 4

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79


user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.CreateSyntheticPointerDevice.argtypes = [INT32, UINT32, INT32]
user32.CreateSyntheticPointerDevice.restype = HANDLE
user32.InjectSyntheticPointerInput.argtypes = [HANDLE, ctypes.POINTER(POINTER_TYPE_INFO), UINT32]
user32.InjectSyntheticPointerInput.restype = ctypes.c_int
user32.DestroySyntheticPointerDevice.argtypes = [HANDLE]
user32.DestroySyntheticPointerDevice.restype = None
user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.GetSystemMetrics.restype = ctypes.c_int


@dataclass
class ScreenRect:
    left: int
    top: int
    width: int
    height: int


class PenInjector:
    def __init__(self, rect: ScreenRect) -> None:
        self.rect = rect
        self.device = user32.CreateSyntheticPointerDevice(PT_PEN, 1, POINTER_FEEDBACK_NONE)
        if not self.device:
            raise ctypes.WinError(ctypes.get_last_error())
        self.frame_id = 0
        self.in_range = False
        self.in_contact = False
        self.barrel = False
        self.eraser = False
        self.last: dict[str, Any] = {"x": 0.5, "y": 0.5, "pressure": 0.0, "tilt_x": 0.0, "tilt_y": 0.0, "buttons": {}}

    def close(self) -> None:
        if self.device:
            user32.DestroySyntheticPointerDevice(self.device)
            self.device = None

    def inject(self, packet: dict[str, Any]) -> None:
        phase = packet.get("phase")
        if phase not in {"down", "move", "up", "hover", "leave", "cancel"}:
            raise ValueError("invalid phase")
        x = _number(packet, "x", 0.0, 1.0)
        y = _number(packet, "y", 0.0, 1.0)
        pressure = _number(packet, "pressure", 0.0, 1.0)
        tilt_x = int(round(_number(packet, "tilt_x", -90.0, 90.0)))
        tilt_y = int(round(_number(packet, "tilt_y", -90.0, 90.0)))
        buttons = packet.get("buttons", {})
        if not isinstance(buttons, dict):
            raise ValueError("buttons must be an object")
        barrel = buttons.get("primary") is True
        eraser = buttons.get("secondary") is True
        inverted = packet.get("inverted") is True
        self._inject_sample(phase, x, y, pressure, tilt_x, tilt_y, barrel, eraser, inverted)
        self.last = {"x": x, "y": y, "pressure": pressure, "tilt_x": tilt_x, "tilt_y": tilt_y, "buttons": buttons}

    def release_after_disconnect(self) -> None:
        if self.in_contact or self.in_range:
            p = self.last
            phase = "cancel" if self.in_contact else "leave"
            self._inject_sample(phase, p["x"], p["y"], 0.0, p["tilt_x"], p["tilt_y"], False, False, False)

    def _inject_sample(self, phase: str, x: float, y: float, pressure: float,
                       tilt_x: int, tilt_y: int, barrel: bool, eraser: bool, inverted: bool) -> None:
        was_contact, was_range = self.in_contact, self.in_range
        self.frame_id = (self.frame_id + 1) & 0xFFFFFFFF

        px = self.rect.left + int(round(x * max(0, self.rect.width - 1)))
        py = self.rect.top + int(round(y * max(0, self.rect.height - 1)))
        flags = POINTER_FLAG_PRIMARY
        if phase in {"down", "move", "hover"} and not was_range:
            flags |= POINTER_FLAG_NEW

        if phase == "down":
            flags |= POINTER_FLAG_INRANGE | POINTER_FLAG_INCONTACT | POINTER_FLAG_DOWN
        elif phase == "move":
            flags |= POINTER_FLAG_INRANGE | POINTER_FLAG_INCONTACT | (POINTER_FLAG_UPDATE if was_contact else POINTER_FLAG_DOWN)
        elif phase == "hover":
            flags |= POINTER_FLAG_INRANGE | POINTER_FLAG_UPDATE
        elif phase == "up":
            flags |= POINTER_FLAG_INRANGE | POINTER_FLAG_UP
        elif phase == "leave":
            flags |= POINTER_FLAG_UP if was_contact else POINTER_FLAG_UPDATE
        elif phase == "cancel":
            flags |= POINTER_FLAG_UP | POINTER_FLAG_CANCELED

        contact = phase in {"down", "move"}
        if phase == "move" and not was_contact:
            contact = True
        if phase in {"up", "leave", "cancel"}:
            contact = False
        in_range = phase not in {"leave", "cancel"}
        if in_range and phase != "up":
            flags |= POINTER_FLAG_INRANGE
        if contact:
            flags |= POINTER_FLAG_INCONTACT

        if barrel:
            flags |= POINTER_FLAG_SECONDBUTTON
        elif contact:
            flags |= POINTER_FLAG_FIRSTBUTTON
        if eraser:
            flags |= POINTER_FLAG_SECONDBUTTON

        pen_flags = (
            (PEN_FLAG_BARREL if barrel else 0)
            | (PEN_FLAG_ERASER if eraser else 0)
            | (PEN_FLAG_INVERTED if inverted else 0)
        )
        button_change = POINTER_CHANGE_NONE
        if barrel != self.barrel:
            button_change = POINTER_CHANGE_SECONDBUTTON_DOWN if barrel else POINTER_CHANGE_SECONDBUTTON_UP
        elif contact != was_contact:
            button_change = POINTER_CHANGE_FIRSTBUTTON_DOWN if contact else POINTER_CHANGE_FIRSTBUTTON_UP

        info = POINTER_TYPE_INFO()
        info.type = PT_PEN
        pen = POINTER_PEN_INFO()
        pen.pointerInfo.pointerType = PT_PEN
        pen.pointerInfo.pointerId = 1
        pen.pointerInfo.frameId = self.frame_id
        pen.pointerInfo.pointerFlags = flags
        pen.pointerInfo.ptPixelLocation = POINT(px, py)
        pen.pointerInfo.ptPixelLocationRaw = POINT(px, py)
        pen.pointerInfo.historyCount = 1
        pen.pointerInfo.ButtonChangeType = button_change
        pen.penFlags = pen_flags
        pen.penMask = PEN_MASK_PRESSURE | PEN_MASK_TILT_X | PEN_MASK_TILT_Y
        pen.pressure = int(round((pressure if contact else 0.0) * 1024.0))
        pen.tiltX = tilt_x
        pen.tiltY = tilt_y
        info.penInfo = pen

        if not user32.InjectSyntheticPointerInput(self.device, ctypes.byref(info), 1):
            raise ctypes.WinError(ctypes.get_last_error())
        self.in_contact = contact
        self.in_range = in_range
        self.barrel = barrel
        self.eraser = eraser


def _number(packet: dict[str, Any], key: str, low: float, high: float) -> float:
    value = packet.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be a finite number")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError(f"{key} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{key} must be a finite number")
    return max(low, min(high, number))


def get_screen_rect(args: argparse.Namespace) -> ScreenRect:
    if args.left is not None or args.top is not None or args.width is not None or args.height is not None:
        if None in (args.left, args.top, args.width, args.height):
            raise SystemExit("Set all of --left, --top, --width, and --height together.")
        if args.width <= 0 or args.height <= 0:
            raise SystemExit("--width and --height must be positive.")
        return ScreenRect(args.left, args.top, args.width, args.height)
    rect = ScreenRect(
        user32.GetSystemMetrics(SM_XVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_YVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_CXVIRTUALSCREEN),
        user32.GetSystemMetrics(SM_CYVIRTUALSCREEN),
    )
    if rect.width <= 0 or rect.height <= 0:
        raise SystemExit("Windows reported an invalid virtual desktop size.")
    return rect


async def connect_to_phone(
    args: argparse.Namespace,
    phone_ip: str,
    *,
    stop_event: Any | None = None,
    on_client_state: Any | None = None,
    timeout: float = 1.0,
) -> None:
    """Connect outward to the phone's USB-tethered TCP service.

    The phone sends a harmless service greeting first. Credentials are sent
    only after that greeting matches, so checking gateway addresses cannot
    disclose the session token to unrelated network devices.
    """
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection(phone_ip, PORT, limit=MAX_LINE), timeout=timeout
    )
    injector: PenInjector | None = None
    authenticated = False
    preview_task: asyncio.Task[Any] | None = None
    capture_rect = None
    if all(getattr(args, key, None) is not None for key in ("left", "top", "width", "height")):
        from pc.screen_capture import CaptureRect

        capture_rect = CaptureRect(args.left, args.top, args.width, args.height)

    async def send_screen_preview(writer: asyncio.StreamWriter) -> None:
        from pc.screen_capture import jpeg_preview

        while True:
            try:
                image, width, height = await asyncio.to_thread(jpeg_preview, capture_rect)
                message = {
                    "type": "screen",
                    "jpeg": base64.b64encode(image).decode("ascii"),
                    "width": width,
                    "height": height,
                }
                writer.write((json.dumps(message, separators=(",", ":")) + "\n").encode("utf-8"))
                await writer.drain()
                await asyncio.sleep(0.2)
            except asyncio.CancelledError:
                raise
            except (ConnectionError, BrokenPipeError):
                return
            except Exception as exc:
                print(f"Screen preview paused: {exc}")
                await asyncio.sleep(1.0)

    peer = writer.get_extra_info("peername")
    try:
        raw = await asyncio.wait_for(reader.readline(), timeout=2.0)
        if not raw or len(raw) > MAX_LINE:
            raise ValueError("phone did not send a service greeting")
        greeting = json.loads(raw)
        if greeting != SERVICE_GREETING:
            raise ValueError("network device did not identify as the S23 Drawing Tablet app")

        # Identify the phone before creating the pointer or sending credentials.
        injector = PenInjector(get_screen_rect(args))
        hello = {"type": "hello", "v": 1, "token": AUTH_TOKEN}
        writer.write((json.dumps(hello, separators=(",", ":")) + "\n").encode("utf-8"))
        await writer.drain()
        raw = await asyncio.wait_for(reader.readline(), timeout=5.0)
        if not raw or len(raw) > MAX_LINE:
            raise ValueError("phone did not confirm the session")
        response = json.loads(raw)
        if not isinstance(response, dict) or response.get("type") != "ready" or response.get("v") != 1:
            raise ValueError("phone rejected the session; update both apps from the same release")

        authenticated = True
        if on_client_state is not None:
            on_client_state(True, str(peer))
        print(f"Connected to phone: {peer}; virtual screen={injector.rect}")
        if capture_rect is not None:
            preview_task = asyncio.create_task(send_screen_preview(writer))

        while stop_event is None or not stop_event.is_set():
            try:
                raw = await asyncio.wait_for(reader.readline(), timeout=0.25)
            except asyncio.TimeoutError:
                continue
            if not raw:
                break
            if len(raw) > MAX_LINE:
                raise ValueError("oversized pen packet")
            packet = json.loads(raw)
            if not isinstance(packet, dict) or packet.get("type") != "pen" or packet.get("v") != 1:
                raise ValueError("unsupported packet")
            try:
                injector.inject(packet)
            except (ValueError, OSError) as exc:
                print(f"Dropped invalid/injection-failed packet from {peer}: {exc}")
    except (asyncio.TimeoutError, asyncio.LimitOverrunError, json.JSONDecodeError, ValueError) as exc:
        print(f"Connection ended ({peer}): {exc}")
        raise
    except (ConnectionError, BrokenPipeError):
        pass
    finally:
        if preview_task is not None:
            preview_task.cancel()
            await asyncio.gather(preview_task, return_exceptions=True)
        if authenticated and on_client_state is not None:
            on_client_state(False, str(peer))
        if injector is not None:
            injector.release_after_disconnect()
            injector.close()
        writer.close()
        try:
            await writer.wait_closed()
        except ConnectionError:
            pass
        print(f"Disconnected from phone: {peer}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phone-ip", required=True, help="USB-tether gateway address reported by Windows.")
    parser.add_argument("--left", type=int)
    parser.add_argument("--top", type=int)
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    return parser.parse_args()


if __name__ == "__main__":
    try:
        parsed = parse_args()
        asyncio.run(connect_to_phone(parsed, parsed.phone_ip))
    except KeyboardInterrupt:
        pass

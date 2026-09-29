from __future__ import annotations

import asyncio
import json
import subprocess
import threading
import unittest
from argparse import Namespace
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from host import tablet_host
from pc.screen_capture import CaptureRect
from pc.tether_network import GatewayCandidate, find_gateway_candidates, parse_gateway_output


class TetherDiscoveryTests(unittest.TestCase):
    def test_parses_gateways_and_prioritizes_android_usb_adapters(self) -> None:
        output = json.dumps([
            {"interface_alias": "Wi-Fi", "description": "Intel Wireless", "gateways": ["192.168.1.1"]},
            {"interface_alias": "Ethernet 4", "description": "SAMSUNG Mobile USB Remote NDIS Network Device", "gateways": ["192.168.42.129"]},
            {"interface_alias": "VPN", "description": "Tunnel", "gateways": ["not-an-ip", "2001:db8::1"]},
        ])
        candidates = parse_gateway_output(output)
        self.assertEqual([item.address for item in candidates], ["192.168.42.129", "192.168.1.1"])
        self.assertTrue(candidates[0].is_usb_tether)
        self.assertEqual(candidates[0].label, "Ethernet 4")

    def test_accepts_single_adapter_object_and_empty_output(self) -> None:
        candidate = parse_gateway_output(json.dumps({
            "interface_alias": "Remote NDIS", "description": "Android USB", "gateways": "192.168.42.129"
        }))
        self.assertEqual(candidate, [GatewayCandidate("Remote NDIS", "Android USB", "192.168.42.129")])
        self.assertEqual(parse_gateway_output(""), [])

    def test_reports_malformed_windows_output(self) -> None:
        with self.assertRaises(ValueError):
            parse_gateway_output("this is not JSON")

    def test_queries_windows_without_opening_a_terminal(self) -> None:
        output = json.dumps({"interface_alias": "RNDIS", "description": "USB tether", "gateways": ["192.168.42.129"]})
        with patch("pc.tether_network.subprocess.run", return_value=SimpleNamespace(stdout=output)) as run:
            candidates = find_gateway_candidates()
        self.assertEqual([candidate.address for candidate in candidates], ["192.168.42.129"])
        self.assertIn("Get-NetIPConfiguration", run.call_args.args[0][-1])
        self.assertEqual(run.call_args.kwargs["timeout"], 5)
        self.assertEqual(run.call_args.kwargs["creationflags"], getattr(subprocess, "CREATE_NO_WINDOW", 0))


class ScreenRegionTests(unittest.TestCase):
    def test_drag_edges_normalize_and_keep_negative_monitor_coordinates(self) -> None:
        self.assertEqual(CaptureRect.from_edges(-150, 600, 450, 100), CaptureRect(-150, 100, 600, 500))

    def test_rejects_tiny_selection(self) -> None:
        with self.assertRaises(ValueError):
            CaptureRect.from_edges(0, 0, 12, 24)


class FakeInjector:
    latest: FakeInjector | None = None

    def __init__(self, rect: tablet_host.ScreenRect) -> None:
        self.rect = rect
        self.packets: list[dict[str, object]] = []
        self.closed = False
        FakeInjector.latest = self

    def inject(self, packet: dict[str, object]) -> None:
        self.packets.append(packet)

    def release_after_disconnect(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


class MemoryReader:
    def __init__(self, lines: list[bytes], *, tail_delay: float = 0) -> None:
        self.lines = list(lines)
        self.tail_delay = tail_delay
        self.tail_event: asyncio.Event | None = None

    async def readline(self) -> bytes:
        if self.lines:
            return self.lines.pop(0)
        if self.tail_delay:
            if self.tail_event is None:
                self.tail_event = asyncio.Event()
                asyncio.get_running_loop().call_later(self.tail_delay, self.tail_event.set)
            await self.tail_event.wait()
            self.tail_delay = 0
        return b""


class MemoryWriter:
    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.closed = False
        self.preview_ready = asyncio.Event()

    def write(self, data: bytes) -> None:
        self.writes.append(data)

    async def drain(self) -> None:
        for item in self.writes:
            try:
                if json.loads(item).get("type") == "screen":
                    self.preview_ready.set()
            except (json.JSONDecodeError, AttributeError):
                pass

    def get_extra_info(self, _name: str) -> tuple[str, int]:
        return ("192.168.42.129", 52000)

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        pass


class PhoneConnectionTests(unittest.IsolatedAsyncioTestCase):
    def args(self, *, capture: bool = False) -> Namespace:
        return Namespace(left=10 if capture else None, top=20 if capture else None,
                         width=300 if capture else None, height=200 if capture else None)

    async def test_authenticates_only_the_identified_phone_and_cleans_up(self) -> None:
        reader = MemoryReader([
            (json.dumps(tablet_host.SERVICE_GREETING) + "\n").encode(),
            b'{"type":"ready","v":1}\n',
            b'{"type":"pen","v":1,"phase":"down","x":0.5,"y":0.5,"pressure":0.8}\n',
        ], tail_delay=0.3)
        writer = MemoryWriter()
        states: list[bool] = []
        stop_event = threading.Event()
        with (
            patch.object(tablet_host.asyncio, "open_connection", new=AsyncMock(return_value=(reader, writer))),
            patch.object(tablet_host, "PenInjector", FakeInjector),
            patch.object(tablet_host, "get_screen_rect", return_value=tablet_host.ScreenRect(0, 0, 100, 100)),
        ):
            await tablet_host.connect_to_phone(
                self.args(), "192.168.42.129", stop_event=stop_event,
                on_client_state=lambda connected, _peer: states.append(connected), timeout=2,
            )

        hello = json.loads(writer.writes[0])
        self.assertEqual(hello, {"type": "hello", "v": 1, "token": "MySecretToken123"})
        self.assertEqual(states, [True, False])
        self.assertEqual(FakeInjector.latest.packets[0]["phase"], "down")
        self.assertTrue(FakeInjector.latest.closed)
        self.assertTrue(writer.closed)

    async def test_does_not_send_token_to_unrecognized_gateway(self) -> None:
        reader = MemoryReader([b'{"type":"other-service"}\n'])
        writer = MemoryWriter()
        with (
            patch.object(tablet_host.asyncio, "open_connection", new=AsyncMock(return_value=(reader, writer))),
            patch.object(tablet_host, "PenInjector") as injector,
        ):
            with self.assertRaisesRegex(ValueError, "did not identify"):
                await tablet_host.connect_to_phone(self.args(), "192.168.1.1", timeout=2)
        self.assertEqual(writer.writes, [])
        self.assertTrue(writer.closed)
        injector.assert_not_called()

    async def test_selected_screen_region_streams_jpeg_preview(self) -> None:
        reader = MemoryReader([
            (json.dumps(tablet_host.SERVICE_GREETING) + "\n").encode(),
            b'{"type":"ready","v":1}\n',
        ], tail_delay=0.35)
        writer = MemoryWriter()
        from pc import screen_capture

        with (
            patch.object(tablet_host.asyncio, "open_connection", new=AsyncMock(return_value=(reader, writer))),
            patch.object(tablet_host, "PenInjector", FakeInjector),
            patch.object(tablet_host, "get_screen_rect", return_value=tablet_host.ScreenRect(10, 20, 300, 200)),
            patch.object(screen_capture, "jpeg_preview", return_value=(b"jpeg-data", 32, 18)),
        ):
            await tablet_host.connect_to_phone(self.args(capture=True), "192.168.42.129", timeout=2)

        preview = next(json.loads(item) for item in writer.writes if json.loads(item).get("type") == "screen")
        self.assertEqual(preview["width"], 32)
        self.assertEqual(preview["height"], 18)
        self.assertEqual(preview["jpeg"], "anBlZy1kYXRh")


if __name__ == "__main__":
    unittest.main()

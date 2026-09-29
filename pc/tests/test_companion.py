from __future__ import annotations

import asyncio
import re
import unittest
from argparse import Namespace
from unittest.mock import patch

from host import tablet_host
from pc.tablet_companion import has_reverse_route, parse_adb_devices


class AdbOutputTests(unittest.TestCase):
    def test_parses_ready_and_unauthorized_devices(self) -> None:
        output = """List of devices attached
R5CT123456A\tdevice product:dm3q model:SM_S918U
R5CT654321B\tunauthorized usb:1-2

"""
        self.assertEqual(
            parse_adb_devices(output),
            [("R5CT123456A", "device"), ("R5CT654321B", "unauthorized")],
        )

    def test_empty_device_list(self) -> None:
        self.assertEqual(parse_adb_devices("List of devices attached\n\n"), [])

    def test_detects_only_the_expected_reverse_tunnel(self) -> None:
        self.assertTrue(has_reverse_route("R5CT123456A tcp:8765 tcp:8765\n"))
        self.assertFalse(has_reverse_route("R5CT123456A tcp:8765 tcp:9999\n"))


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


class ReceiverLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_authenticated_phone_and_clean_stop(self) -> None:
        listening = asyncio.Event()
        stopped = asyncio.Event()
        locations: list[str] = []
        client_states: list[bool] = []
        stop_event = asyncio.Event()
        args = Namespace(host="127.0.0.1", port=0, left=None, top=None, width=None, height=None)

        def on_listening(value: str) -> None:
            locations.append(value)
            listening.set()

        def on_client_state(connected: bool, _peer: str) -> None:
            client_states.append(connected)
            if not connected:
                stopped.set()

        with (
            patch.object(tablet_host, "PenInjector", FakeInjector),
            patch.object(tablet_host, "get_screen_rect", return_value=tablet_host.ScreenRect(0, 0, 100, 100)),
        ):
            server_task = asyncio.create_task(
                tablet_host.run_server(
                    args,
                    stop_event=stop_event,
                    on_listening=on_listening,
                    on_client_state=on_client_state,
                )
            )
            await asyncio.wait_for(listening.wait(), timeout=3)
            match = re.search(r"\('127\.0\.0\.1', (\d+)\)", locations[0])
            self.assertIsNotNone(match, locations)
            port = int(match.group(1))

            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(b'{"type":"hello","v":1,"token":"MySecretToken123"}\n')
            await writer.drain()
            self.assertIn('"ready"', (await asyncio.wait_for(reader.readline(), timeout=3)).decode())
            await asyncio.wait_for(asyncio.to_thread(self._wait_for_connected, client_states), timeout=3)

            writer.write(b'{"type":"pen","v":1,"phase":"down","x":0.5,"y":0.5,"pressure":0.8}\n')
            await writer.drain()
            await asyncio.sleep(0.05)
            self.assertEqual(len(FakeInjector.latest.packets), 1)

            stop_event.set()
            await asyncio.wait_for(server_task, timeout=3)
            self.assertTrue(FakeInjector.latest.closed)
            self.assertTrue(stopped.is_set())
            self.assertEqual(client_states, [True, False])
            writer.close()
            await writer.wait_closed()

    @staticmethod
    def _wait_for_connected(states: list[bool]) -> None:
        import time

        deadline = time.monotonic() + 2
        while not states and time.monotonic() < deadline:
            time.sleep(0.01)
        if not states:
            raise AssertionError("server did not report an authenticated phone")


if __name__ == "__main__":
    unittest.main()

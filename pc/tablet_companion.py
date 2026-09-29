"""Small Windows desktop companion for the S23 Drawing Tablet Android app."""

from __future__ import annotations

import asyncio
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from host import tablet_host


APP_NAME = "S23 Drawing Tablet"
APP_PACKAGE = "dev.example.galaxytabled"
PORT = tablet_host.PORT
PLATFORM_TOOLS_PAGE = "https://developer.android.com/tools/releases/platform-tools"
ADB_REVERSE_ARGS = ("reverse", "tcp:8765", "tcp:8765")


def parse_adb_devices(output: str) -> list[tuple[str, str]]:
    """Return (serial, state) pairs from `adb devices` output."""
    devices: list[tuple[str, str]] = []
    for line in output.splitlines():
        fields = line.strip().split()
        if len(fields) >= 2 and fields[0] != "List":
            devices.append((fields[0], fields[1]))
    return devices


def has_reverse_route(output: str) -> bool:
    """Check whether `adb reverse --list` contains the tablet's USB tunnel."""
    return any(line.strip().split()[-2:] == ["tcp:8765", "tcp:8765"] for line in output.splitlines())


def app_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    folder = Path(base) / "S23DrawingTablet"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def find_adb(saved_path: str | None = None) -> Path | None:
    candidates: list[Path] = []
    if saved_path:
        candidates.append(Path(saved_path))
    local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    candidates.extend(
        [
            local / "Android" / "Sdk" / "platform-tools" / "adb.exe",
            Path("C:/platform-tools/adb.exe"),
        ]
    )
    path_adb = shutil.which("adb.exe") or shutil.which("adb")
    if path_adb:
        candidates.append(Path(path_adb))
    for candidate in candidates:
        if candidate.is_file() and candidate.name.lower() == "adb.exe":
            return candidate.resolve()
    return None


def run_process(executable: Path, *args: str, timeout: float = 20.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(executable), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


class TabletCompanion:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(f"{APP_NAME} — Windows companion")
        self.root.geometry("600x600")
        self.root.minsize(540, 540)
        self.root.configure(bg="#f4f6fa")

        self.messages: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.busy = False
        self.running = False
        self.pen_connected = False
        self.closing = False
        self.serial: str | None = None
        self.adb: Path | None = None
        self.receiver_loop: asyncio.AbstractEventLoop | None = None
        self.receiver_stop_event: asyncio.Event | None = None
        self.receiver_thread: threading.Thread | None = None
        self.receiver_ready = threading.Event()
        self.receiver_done = threading.Event()
        self.receiver_failure: str | None = None
        self.monitor_stop = threading.Event()
        self.cancel_setup = threading.Event()
        self.worker_thread: threading.Thread | None = None
        self.shutdown_done = threading.Event()

        self._load_saved_adb()
        self._build_ui()
        self._refresh_buttons()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._drain_messages)

    def _load_saved_adb(self) -> None:
        try:
            settings_path = app_data_dir() / "settings.json"
            settings = json.loads(settings_path.read_text(encoding="utf-8")) if settings_path.exists() else {}
            saved = settings.get("adb_path") if isinstance(settings, dict) else None
        except (OSError, json.JSONDecodeError):
            saved = None
        self.adb = find_adb(saved if isinstance(saved, str) else None)

    def _save_adb(self, path: Path) -> None:
        self.adb = path.resolve()
        settings_path = app_data_dir() / "settings.json"
        settings_path.write_text(json.dumps({"adb_path": str(self.adb)}, indent=2), encoding="utf-8")

    def _build_ui(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background="#f4f6fa")
        style.configure("Card.TFrame", background="#ffffff")
        style.configure("TLabel", background="#f4f6fa", foreground="#17243a", font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI", 23, "bold"), foreground="#17243a")
        style.configure("Sub.TLabel", font=("Segoe UI", 10), foreground="#536176")
        style.configure("Status.TLabel", background="#ffffff", font=("Segoe UI", 12, "bold"), foreground="#174a83")
        style.configure("CardSub.TLabel", background="#ffffff", font=("Segoe UI", 10), foreground="#536176")
        style.configure("TButton", font=("Segoe UI", 10), padding=(12, 8))
        style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"), padding=(14, 10))

        page = ttk.Frame(self.root, padding=(24, 20))
        page.pack(fill="both", expand=True)
        ttk.Label(page, text=APP_NAME, style="Title.TLabel").pack(anchor="w")
        ttk.Label(page, text="Connect your Galaxy S23 Ultra to Windows over USB.", style="Sub.TLabel").pack(anchor="w", pady=(2, 16))

        card = ttk.Frame(page, style="Card.TFrame", padding=16)
        card.pack(fill="x")
        ttk.Label(card, textvariable=self._make_status_var(), style="Status.TLabel", wraplength=500).pack(anchor="w")
        self.status_detail = ttk.Label(card, text="", style="CardSub.TLabel", wraplength=500)
        self.status_detail.pack(anchor="w", pady=(6, 0))

        ttk.Label(
            page,
            text="1. Connect the phone with a USB data cable and approve USB debugging.\n"
                 "2. The first time, locate adb.exe once. Then click Connect phone.\n"
                 "3. This app starts the receiver, connects the USB tunnel, and opens the phone app.",
            justify="left",
            wraplength=530,
        ).pack(anchor="w", pady=(18, 12))

        controls = ttk.Frame(page)
        controls.pack(fill="x", pady=(4, 6))
        self.connect_button = ttk.Button(controls, text="Connect phone", style="Primary.TButton", command=self._toggle_connection)
        self.connect_button.pack(side="left")
        self.install_button = ttk.Button(controls, text="Install phone APK…", command=self._choose_apk)
        self.install_button.pack(side="left", padx=(8, 0))

        tools = ttk.Frame(page)
        tools.pack(fill="x", pady=(2, 10))
        self.adb_button = ttk.Button(tools, text="Locate adb.exe…", command=self._choose_adb)
        self.adb_button.pack(side="left")
        ttk.Button(tools, text="Get ADB from Google…", command=lambda: webbrowser.open(PLATFORM_TOOLS_PAGE)).pack(side="left", padx=(8, 0))

        ttk.Label(page, text="Activity", style="Sub.TLabel").pack(anchor="w", pady=(4, 4))
        self.log = tk.Text(
            page,
            height=8,
            wrap="word",
            state="disabled",
            relief="flat",
            bg="#ffffff",
            fg="#344256",
            font=("Segoe UI", 9),
            padx=10,
            pady=8,
        )
        self.log.pack(fill="both", expand=True)
        self._make_status_var()
        if self.adb:
            self.status_var.set("Ready. Connect your phone and click Connect phone.")
            self.status_detail.configure(text=f"ADB found: {self.adb}")
            self._append_log("ADB is ready.")
        else:
            self.status_var.set("One-time setup: locate Android Platform-Tools (adb.exe).")
            self.status_detail.configure(text="If needed, click Get ADB from Google, download and unzip Platform-Tools, then locate adb.exe.")
            self._append_log("Android Studio is not needed. ADB is part of Google's small Platform-Tools download.")

    def _make_status_var(self) -> tk.StringVar:
        if not hasattr(self, "status_var"):
            self.status_var = tk.StringVar(value="Starting…")
        return self.status_var

    def _append_log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _post(self, kind: str, value: Any = None) -> None:
        self.messages.put((kind, value))

    def _refresh_buttons(self) -> None:
        if not hasattr(self, "connect_button"):
            return
        self.connect_button.configure(text="Disconnect" if self.running else "Connect phone")
        self.connect_button.configure(state="disabled" if self.busy or (not self.running and not self.adb) else "normal")
        self.install_button.configure(state="normal" if self.serial and not self.busy else "disabled")
        self.adb_button.configure(state="disabled" if self.busy else "normal")

    def _choose_adb(self) -> None:
        selected = filedialog.askopenfilename(
            title="Select adb.exe from the platform-tools folder",
            filetypes=[("Android Debug Bridge", "adb.exe"), ("Executable files", "*.exe")],
        )
        if not selected:
            return
        path = Path(selected)
        if path.name.lower() != "adb.exe":
            messagebox.showerror("Choose adb.exe", "Select adb.exe inside the platform-tools folder.", parent=self.root)
            return
        try:
            self._save_adb(path)
        except OSError as error:
            messagebox.showerror("Could not save setting", str(error), parent=self.root)
            return
        self.status_var.set("ADB is ready. Connect your phone and click Connect phone.")
        self.status_detail.configure(text=f"ADB found: {self.adb}")
        self._append_log("Saved the ADB location for next time.")
        self._refresh_buttons()

    def _choose_apk(self) -> None:
        if not self.serial:
            return
        selected = filedialog.askopenfilename(
            title="Select the S23 Drawing Tablet APK",
            filetypes=[("Android app", "*.apk")],
        )
        if not selected:
            return
        self.busy = True
        self._refresh_buttons()
        self.worker_thread = threading.Thread(target=self._install_apk_worker, args=(Path(selected),), daemon=True)
        self.worker_thread.start()

    def _toggle_connection(self) -> None:
        if self.busy:
            return
        self.busy = True
        self._refresh_buttons()
        if self.running:
            self.worker_thread = threading.Thread(target=self._disconnect_worker, daemon=True)
            self.worker_thread.start()
        else:
            self.cancel_setup.clear()
            self.worker_thread = threading.Thread(target=self._connect_worker, daemon=True)
            self.worker_thread.start()

    def _adb(self, *args: str, timeout: float = 20.0) -> subprocess.CompletedProcess[str]:
        if not self.adb:
            raise RuntimeError("Locate adb.exe first. It is included in Google's Android Platform-Tools.")
        result = run_process(self.adb, *args, timeout=timeout)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise RuntimeError(detail or f"ADB command failed: {' '.join(args)}")
        return result

    def _wait_for_phone(self) -> str:
        self._adb("start-server")
        deadline = time.monotonic() + 30
        last_status = ""
        while time.monotonic() < deadline and not self.cancel_setup.is_set():
            result = self._adb("devices", timeout=10)
            devices = parse_adb_devices(result.stdout)
            authorized = [serial for serial, state in devices if state == "device"]
            unauthorized = [serial for serial, state in devices if state == "unauthorized"]
            if len(authorized) == 1:
                return authorized[0]
            if len(authorized) > 1:
                raise RuntimeError("More than one Android device is connected. Disconnect the others and try again.")
            if unauthorized:
                message = "Unlock your phone and tap Allow on the USB debugging prompt. Waiting…"
            else:
                message = "Connect the phone with a USB data cable. Waiting for it to appear…"
            if message != last_status:
                self._post("status", (message, "Keep the phone unlocked while USB debugging is authorized."))
                last_status = message
            time.sleep(1)
        if self.cancel_setup.is_set():
            raise RuntimeError("Connection cancelled.")
        raise RuntimeError("Phone not found. Check the USB cable, enable USB debugging, and approve its prompt.")

    def _connect_worker(self) -> None:
        try:
            self._post("status", ("Looking for your phone…", "Unlock the phone and approve USB debugging if prompted."))
            self._post("log", "Starting ADB and looking for the phone.")
            serial = self._wait_for_phone()
            if self.cancel_setup.is_set():
                raise RuntimeError("Connection cancelled.")
            self.serial = serial
            self._post("log", f"Phone found: {serial}")
            self._start_receiver()
            if self.cancel_setup.is_set():
                raise RuntimeError("Connection cancelled.")
            self._adb("-s", serial, *ADB_REVERSE_ARGS)
            self._post("log", "USB connection is ready.")

            package = self._adb("-s", serial, "shell", "pm", "path", APP_PACKAGE, timeout=15)
            installed = "package:" in package.stdout
            if installed:
                self._adb("-s", serial, "shell", "monkey", "-p", APP_PACKAGE, "1", timeout=15)
                status = ("USB connected. Opening the S23 app…", "Wait for the phone app to say Connected — ready to draw.")
            else:
                status = ("USB connected. Install the phone APK to finish setup.", "Click Install phone APK, choose app-debug.apk, then this app will open it.")
            self.monitor_stop.clear()
            threading.Thread(target=self._monitor_phone, args=(serial,), daemon=True).start()
            self._post("connected", status)
        except Exception as error:
            self._remove_reverse()
            self._stop_receiver()
            self.serial = None
            self._post("failed", str(error))

    def _start_receiver(self) -> None:
        self.receiver_ready.clear()
        self.receiver_done.clear()
        self.receiver_failure = None

        def worker() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            stop_event = asyncio.Event()
            self.receiver_loop = loop
            self.receiver_stop_event = stop_event

            def listening(locations: str) -> None:
                self.receiver_ready.set()
                self._post("log", f"Windows receiver listening on {locations}.")

            def client_state(connected: bool, peer: str) -> None:
                self._post("pen_client", (connected, peer))

            args = type("ReceiverArgs", (), {"host": "127.0.0.1", "port": PORT,
                                               "left": None, "top": None,
                                               "width": None, "height": None})()
            try:
                loop.run_until_complete(
                    tablet_host.run_server(
                        args,
                        stop_event=stop_event,
                        on_listening=listening,
                        on_client_state=client_state,
                    )
                )
            except Exception as error:
                self.receiver_failure = str(error)
                self._post("receiver_error", str(error))
            finally:
                loop.close()
                self.receiver_loop = None
                self.receiver_stop_event = None
                self.receiver_done.set()

        self.receiver_thread = threading.Thread(target=worker, name="S23PenReceiver", daemon=True)
        self.receiver_thread.start()
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and not self.receiver_ready.is_set() and not self.receiver_done.is_set():
            self.receiver_done.wait(timeout=0.1)
        if not self.receiver_ready.is_set():
            detail = self.receiver_failure or "The Windows receiver did not start within 15 seconds."
            raise RuntimeError(detail)

    def _stop_receiver(self) -> None:
        loop = self.receiver_loop
        stop_event = self.receiver_stop_event
        if loop is not None and stop_event is not None and loop.is_running():
            loop.call_soon_threadsafe(stop_event.set)
        thread = self.receiver_thread
        if thread and thread.is_alive():
            thread.join(timeout=5)
        self.receiver_thread = None

    def _remove_reverse(self) -> None:
        if self.adb and self.serial:
            try:
                run_process(self.adb, "-s", self.serial, "reverse", "--remove", "tcp:8765", timeout=8)
            except (OSError, subprocess.TimeoutExpired):
                pass

    def _monitor_phone(self, serial: str) -> None:
        online = True
        tunnel_active = True
        while not self.monitor_stop.wait(3):
            try:
                if not self.adb:
                    return
                result = run_process(self.adb, "devices", timeout=10)
                present = result.returncode == 0 and (serial, "device") in parse_adb_devices(result.stdout)
                if present:
                    listing = run_process(self.adb, "-s", serial, "reverse", "--list", timeout=10)
                    route_exists = listing.returncode == 0 and has_reverse_route(listing.stdout)
                    if not route_exists:
                        reverse = run_process(self.adb, "-s", serial, *ADB_REVERSE_ARGS, timeout=10)
                        tunnel_active = reverse.returncode == 0
                    else:
                        tunnel_active = True
                    if tunnel_active and (not online or not route_exists):
                        self._post("phone_transport", True)
                elif not present and online:
                    self._post("phone_transport", False)
                    tunnel_active = False
                online = present
            except (OSError, subprocess.TimeoutExpired):
                continue

    def _install_apk_worker(self, apk: Path) -> None:
        try:
            if not self.serial:
                raise RuntimeError("Connect your phone first.")
            if apk.suffix.lower() != ".apk" or not apk.is_file():
                raise RuntimeError("Choose the app-debug.apk file from the S23-Tablet-App download.")
            self._post("status", ("Installing the phone app…", "Keep the phone connected and unlocked."))
            result = self._adb("-s", self.serial, "install", "-r", str(apk), timeout=120)
            if "success" not in result.stdout.lower():
                raise RuntimeError(result.stdout.strip() or "Android did not confirm the installation.")
            self._adb("-s", self.serial, "shell", "monkey", "-p", APP_PACKAGE, "1", timeout=15)
            self._post("log", "Phone app installed and opened.")
            self._post("installed", "App installed. Wait for the phone to say Connected — ready to draw.")
        except Exception as error:
            self._post("install_failed", str(error))

    def _disconnect_worker(self) -> None:
        self.monitor_stop.set()
        self._remove_reverse()
        self._stop_receiver()
        self.serial = None
        self._post("disconnected", None)

    def _on_close(self) -> None:
        if self.closing:
            return
        self.closing = True
        self.cancel_setup.set()
        self.monitor_stop.set()
        threading.Thread(target=self._shutdown_worker, daemon=True).start()
        self.root.after(100, self._wait_for_shutdown)

    def _shutdown_worker(self) -> None:
        worker = self.worker_thread
        if worker and worker.is_alive() and worker is not threading.current_thread():
            worker.join(timeout=35)
        self.monitor_stop.set()
        self._remove_reverse()
        self._stop_receiver()
        self.shutdown_done.set()

    def _wait_for_shutdown(self) -> None:
        if not self.shutdown_done.is_set():
            self.root.after(100, self._wait_for_shutdown)
            return
        self.root.destroy()

    def _drain_messages(self) -> None:
        if self.closing:
            return
        while True:
            try:
                kind, value = self.messages.get_nowait()
            except queue.Empty:
                break
            if kind == "status":
                title, detail = value
                self.status_var.set(title)
                self.status_detail.configure(text=detail)
            elif kind == "log":
                self._append_log(value)
            elif kind == "connected":
                self.busy = False
                self.running = True
                if not self.pen_connected:
                    self.status_var.set(value[0])
                    self.status_detail.configure(text=value[1])
                self._append_log("USB link and Windows receiver are ready.")
                self._refresh_buttons()
            elif kind == "pen_client":
                connected, peer = value
                self.pen_connected = connected
                if connected:
                    self.status_var.set("Connected — ready to draw")
                    self.status_detail.configure(text="S Pen input is reaching Windows. Draw in Paint or another app.")
                    self._append_log(f"Phone app connected ({peer}).")
                elif self.running:
                    self.status_var.set("Receiver is ready; waiting for the phone app…")
                    self.status_detail.configure(text="Keep the USB connection active and open the S23 app.")
                    self._append_log("Phone app disconnected; waiting for it to reconnect.")
            elif kind == "phone_transport":
                if value:
                    self.status_var.set("USB restored. Waiting for the phone app…")
                    self.status_detail.configure(text="The USB tunnel was restored automatically.")
                else:
                    self.status_var.set("Phone disconnected. Waiting for USB…")
                    self.status_detail.configure(text="Reconnect the cable; this app will restore adb reverse automatically.")
            elif kind == "failed":
                self.busy = False
                self.running = False
                self.status_var.set("Could not connect")
                self.status_detail.configure(text=value)
                self._append_log(value)
                self._refresh_buttons()
            elif kind == "install_failed":
                self.busy = False
                self.status_var.set("Could not install the phone app")
                self.status_detail.configure(text=value)
                self._append_log(value)
                self._refresh_buttons()
            elif kind == "installed":
                self.busy = False
                if not self.pen_connected:
                    self.status_var.set(value)
                    self.status_detail.configure(text="The phone app should connect in a moment.")
                self._refresh_buttons()
            elif kind == "disconnected":
                self.busy = False
                self.running = False
                self.pen_connected = False
                self.serial = None
                self.status_var.set("Disconnected")
                self.status_detail.configure(text="Connect your phone and click Connect phone when you want to draw.")
                self._append_log("Receiver stopped and USB tunnel removed.")
                self._refresh_buttons()
            elif kind == "receiver_error":
                if not self.closing:
                    self.running = False
                    self.pen_connected = False
                    self.monitor_stop.set()
                    self.status_var.set("Windows receiver stopped")
                    self.status_detail.configure(text=value)
                    self._append_log(value)
                    self._refresh_buttons()
        self.root.after(100, self._drain_messages)


def main() -> None:
    # A windowed PyInstaller build has no console; keep receiver print calls harmless.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    root = tk.Tk()
    TabletCompanion(root)
    root.mainloop()


if __name__ == "__main__":
    main()

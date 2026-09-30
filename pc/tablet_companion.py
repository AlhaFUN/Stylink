"""Friendly Windows companion app for USB-tethered Android stylus input."""

from __future__ import annotations

import asyncio
import json
import os
import queue
import re
import sys
import threading
import tkinter as tk
from argparse import Namespace
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from host import tablet_host
from pc.pairing import new_session_token, protect_session_token, unprotect_session_token
from pc.screen_capture import CaptureRect, select_capture_rect
from pc.tether_network import find_gateway_candidates

APP_NAME = "Stylink"
LEGACY_DATA_FOLDERS = ("VirtualDT", "S23DrawingTablet")
PREVIEW_QUALITY_PRESETS = {
    "Performance": (640, 42),
    "Balanced": (960, 58),
    "High detail": (1280, 76),
}
PREVIEW_FPS_OPTIONS = (5, 10, 15, 20, 30)


def app_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    folder = Path(base) / APP_NAME
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def load_settings() -> dict[str, Any]:
    paths = [app_data_dir() / "settings.json"]
    for folder in LEGACY_DATA_FOLDERS:
        legacy_path = app_data_dir().parent / folder / "settings.json"
        if legacy_path not in paths:
            paths.append(legacy_path)
    for path in paths:
        try:
            loaded = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
            if isinstance(loaded, dict):
                return loaded
        except (OSError, json.JSONDecodeError):
            continue
    return {}


def save_settings(settings: dict[str, Any]) -> None:
    path = app_data_dir() / "settings.json"
    path.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def update_settings(**values: Any) -> None:
    settings = load_settings()
    settings.update(values)
    save_settings(settings)


def load_capture_rect() -> CaptureRect | None:
    try:
        raw = load_settings().get("capture_rect")
        if isinstance(raw, dict):
            rect = CaptureRect(int(raw["left"]), int(raw["top"]), int(raw["width"]), int(raw["height"]))
            if rect.width >= 32 and rect.height >= 32:
                return rect
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        pass
    return None


def save_capture_rect(rect: CaptureRect | None) -> None:
    settings = load_settings()
    if rect is None:
        settings.pop("capture_rect", None)
    else:
        settings["capture_rect"] = rect.as_dict()
    save_settings(settings)


def load_preview_settings() -> tuple[str, int]:
    settings = load_settings()
    quality = settings.get("preview_quality", "Balanced")
    fps = settings.get("preview_fps", 15)
    if quality not in PREVIEW_QUALITY_PRESETS:
        quality = "Balanced"
    try:
        fps = int(fps)
    except (TypeError, ValueError):
        fps = 15
    if fps not in PREVIEW_FPS_OPTIONS:
        fps = 15
    return quality, fps


def load_pairing_token() -> str | None:
    protected = load_settings().get("pairing_token")
    return unprotect_session_token(protected) if isinstance(protected, str) else None


def save_pairing_token(token: str) -> None:
    update_settings(pairing_token=protect_session_token(token))


def app_icon_path() -> Path:
    bundle_root = Path(getattr(sys, "_MEIPASS", PROJECT_ROOT))
    return bundle_root / "pc" / "assets" / "stylink.ico"


class TabletCompanion:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(f"{APP_NAME} — Windows companion")
        self.root.geometry("790x800")
        self.root.minsize(700, 740)
        self.root.configure(bg="#f3f6fb")
        self.root.option_add("*Font", ("Segoe UI", 10))

        self.messages: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.running = False
        self.busy = False
        self.pen_connected = False
        self.closing = False
        self.cancel_setup = threading.Event()
        self.worker_thread: threading.Thread | None = None
        self.capture_rect = load_capture_rect()
        self.preview_quality, self.preview_fps = load_preview_settings()
        self.pairing_token = load_pairing_token()
        self.pending_pairing_code: str | None = None
        self.pending_pairing_token: str | None = None

        self._build_ui()
        self._refresh_buttons()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._drain_messages)

    def _build_ui(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("Page.TFrame", background="#f3f6fb")
        style.configure("Card.TFrame", background="#ffffff")
        style.configure("Hero.TFrame", background="#13243d")
        style.configure("HeroTitle.TLabel", background="#13243d", foreground="#ffffff", font=("Segoe UI", 23, "bold"))
        style.configure("HeroSub.TLabel", background="#13243d", foreground="#c7d4e6", font=("Segoe UI", 10))
        style.configure("Section.TLabel", background="#f3f6fb", foreground="#1e2d43", font=("Segoe UI", 12, "bold"))
        style.configure("Sub.TLabel", background="#f3f6fb", foreground="#64748b", font=("Segoe UI", 9))
        style.configure("CardTitle.TLabel", background="#ffffff", foreground="#1e2d43", font=("Segoe UI", 12, "bold"))
        style.configure("CardSub.TLabel", background="#ffffff", foreground="#5d6c80", font=("Segoe UI", 9))
        style.configure("Status.TLabel", background="#ffffff", foreground="#174a83", font=("Segoe UI", 13, "bold"))
        style.configure("TButton", font=("Segoe UI", 9), padding=(10, 8))
        style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"), padding=(15, 10), background="#2368c4", foreground="#ffffff")
        style.map("Primary.TButton", background=[("active", "#1759af"), ("disabled", "#9aacc3")], foreground=[("disabled", "#ffffff")])

        page = ttk.Frame(self.root, style="Page.TFrame", padding=(26, 22))
        page.pack(fill="both", expand=True)
        hero = ttk.Frame(page, style="Hero.TFrame", padding=(22, 18))
        hero.pack(fill="x")
        logo = tk.Label(hero, text="VDT", bg="#2b75d6", fg="white", font=("Segoe UI", 12, "bold"), padx=10, pady=8)
        logo.pack(side="left", padx=(0, 15))
        title_box = ttk.Frame(hero, style="Hero.TFrame")
        title_box.pack(side="left", fill="x", expand=True)
        ttk.Label(title_box, text=APP_NAME, style="HeroTitle.TLabel").pack(anchor="w")
        ttk.Label(title_box, text="Your Android stylus, now a Windows drawing pen.", style="HeroSub.TLabel").pack(anchor="w", pady=(3, 0))

        status_card = ttk.Frame(page, style="Card.TFrame", padding=(18, 16))
        status_card.pack(fill="x", pady=(16, 13))
        top_line = ttk.Frame(status_card, style="Card.TFrame")
        top_line.pack(fill="x")
        self.status_dot = tk.Label(top_line, text="●", bg="#ffffff", fg="#94a3b8", font=("Segoe UI", 13))
        self.status_dot.pack(side="left", padx=(0, 9))
        self.status_var = tk.StringVar(value="Ready to connect")
        ttk.Label(top_line, textvariable=self.status_var, style="Status.TLabel").pack(side="left", anchor="w")
        self.status_detail = ttk.Label(
            status_card,
            text="Connect your Android device by USB, turn on USB tethering, then click Connect phone.",
            style="CardSub.TLabel", wraplength=680,
        )
        self.status_detail.pack(anchor="w", padx=(25, 0), pady=(5, 0))

        ttk.Label(page, text="Get connected", style="Section.TLabel").pack(anchor="w", pady=(1, 7))
        steps = ttk.Frame(page, style="Card.TFrame", padding=(18, 14))
        steps.pack(fill="x")
        for text in (
            "1. Connect the phone and PC with a USB data cable.",
            "2. On the phone, turn on Settings → Connections → Mobile Hotspot and Tethering → USB tethering.",
            "3. Open Stylink on the phone, then click Connect phone below. Pair once with the code shown on the phone.",
        ):
            ttk.Label(steps, text=text, style="CardSub.TLabel", wraplength=700).pack(anchor="w", pady=3)

        controls = ttk.Frame(page, style="Page.TFrame")
        controls.pack(fill="x", pady=(14, 8))
        self.connect_button = ttk.Button(controls, text="Connect phone", style="Primary.TButton", command=self._toggle_connection)
        self.connect_button.pack(side="left")
        ttk.Button(controls, text="Select screen area…", command=self._choose_capture_area).pack(side="left", padx=(9, 0))
        ttk.Button(controls, text="Show full screen", command=self._clear_capture_area).pack(side="left", padx=(9, 0))

        ttk.Label(page, text="Phone preview", style="Section.TLabel").pack(anchor="w", pady=(6, 5))
        self.capture_var = tk.StringVar()
        ttk.Label(page, textvariable=self.capture_var, style="Sub.TLabel", wraplength=700).pack(anchor="w", pady=(0, 10))
        self._update_capture_label()

        preview_options = ttk.Frame(page, style="Card.TFrame", padding=(13, 10))
        preview_options.pack(fill="x", pady=(0, 11))
        options_row = ttk.Frame(preview_options, style="Card.TFrame")
        options_row.pack(fill="x")
        ttk.Label(options_row, text="Image quality", style="CardTitle.TLabel").pack(side="left")
        self.quality_var = tk.StringVar(value=self.preview_quality)
        self.quality_combo = ttk.Combobox(
            options_row, textvariable=self.quality_var,
            values=tuple(PREVIEW_QUALITY_PRESETS), state="readonly", width=15,
        )
        self.quality_combo.pack(side="left", padx=(8, 24))
        self.quality_combo.bind("<<ComboboxSelected>>", self._on_preview_settings_changed)
        ttk.Label(options_row, text="FPS limit", style="CardTitle.TLabel").pack(side="left")
        self.fps_var = tk.StringVar(value=str(self.preview_fps))
        self.fps_combo = ttk.Combobox(
            options_row, textvariable=self.fps_var,
            values=tuple(str(value) for value in PREVIEW_FPS_OPTIONS), state="readonly", width=7,
        )
        self.fps_combo.pack(side="left", padx=(8, 0))
        self.fps_combo.bind("<<ComboboxSelected>>", self._on_preview_settings_changed)
        ttk.Label(
            preview_options,
            text="Performance uses a smaller, lighter preview. Changes apply the next time you connect.",
            style="CardSub.TLabel",
        ).pack(anchor="w", pady=(7, 0))

        activity_head = ttk.Frame(page, style="Page.TFrame")
        activity_head.pack(fill="x", pady=(1, 5))
        ttk.Label(activity_head, text="Activity", style="Section.TLabel").pack(side="left")
        ttk.Label(activity_head, text="Connection details", style="Sub.TLabel").pack(side="right")
        self.log = tk.Text(page, height=8, wrap="word", state="disabled", relief="flat", bd=0,
                           bg="#ffffff", fg="#526176", font=("Segoe UI", 9), padx=12, pady=9)
        self.log.pack(fill="both", expand=True)
        self._append_log("Stylink connects over the phone's USB-tether network. It does not use ADB or USB debugging.")
        self._append_log("No inbound firewall rule is needed; the PC connects out to the phone.")

    def _append_log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", message.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _post(self, kind: str, value: Any = None) -> None:
        self.messages.put((kind, value))

    def _set_status(self, title: str, detail: str, *, connected: bool = False, searching: bool = False) -> None:
        self.status_var.set(title)
        self.status_detail.configure(text=detail)
        self.status_dot.configure(fg="#20a36a" if connected else ("#e0a130" if searching else "#94a3b8"))

    def _refresh_buttons(self) -> None:
        if not hasattr(self, "connect_button"):
            return
        self.connect_button.configure(text="Disconnect" if self.running else "Connect phone")
        self.connect_button.configure(state="disabled" if self.busy else "normal")
        for control in (getattr(self, "quality_combo", None), getattr(self, "fps_combo", None)):
            if control is not None:
                control.configure(state="disabled" if self.running else "readonly")

    def _on_preview_settings_changed(self, _event: Any = None) -> None:
        if self.running:
            return
        quality = self.quality_var.get()
        try:
            fps = int(self.fps_var.get())
        except ValueError:
            return
        if quality not in PREVIEW_QUALITY_PRESETS or fps not in PREVIEW_FPS_OPTIONS:
            return
        self.preview_quality, self.preview_fps = quality, fps
        try:
            update_settings(preview_quality=quality, preview_fps=fps)
        except OSError as error:
            messagebox.showerror("Could not save preview settings", str(error), parent=self.root)
            return
        max_width, jpeg_quality = PREVIEW_QUALITY_PRESETS[quality]
        self._append_log(f"Preview set to {quality.lower()} ({max_width}px, JPEG {jpeg_quality}) at up to {fps} FPS.")

    def _choose_capture_area(self) -> None:
        if self.running:
            messagebox.showinfo("Disconnect first", "Disconnect before changing the selected screen area.", parent=self.root)
            return
        select_capture_rect(self.root, self._capture_area_selected)

    def _capture_area_selected(self, rect: CaptureRect | None) -> None:
        if rect is None:
            return
        self.capture_rect = rect
        try:
            save_capture_rect(rect)
        except OSError as error:
            messagebox.showerror("Could not save screen area", str(error), parent=self.root)
        self._update_capture_label()
        self._append_log(f"Selected a {rect.width} × {rect.height} pixel PC screen area.")

    def _clear_capture_area(self) -> None:
        if self.running:
            messagebox.showinfo("Disconnect first", "Disconnect before changing the selected screen area.", parent=self.root)
            return
        self.capture_rect = None
        try:
            save_capture_rect(None)
        except OSError as error:
            messagebox.showerror("Could not save setting", str(error), parent=self.root)
        self._update_capture_label()
        self._append_log("Full-screen PC mapping selected. The phone preview is off.")

    def _update_capture_label(self) -> None:
        if self.capture_rect:
            rect = self.capture_rect
            self.capture_var.set(f"Showing {rect.width} × {rect.height} pixels at ({rect.left}, {rect.top}) on the phone.")
        else:
            self.capture_var.set("No preview selected. The Android stylus maps across the full Windows desktop.")

    def _toggle_connection(self) -> None:
        if self.busy:
            return
        if self.running:
            self.busy = True
            self.cancel_setup.set()
            self._set_status("Disconnecting…", "Closing the tablet link.", searching=True)
            self._refresh_buttons()
            return
        self.cancel_setup.clear()
        self.busy = True
        self._refresh_buttons()
        self.worker_thread = threading.Thread(target=self._connection_worker, name="StylinkTetherConnection", daemon=True)
        self.worker_thread.start()

    def _connection_worker(self) -> None:
        self._post("started")
        rect = self.capture_rect
        args = Namespace(
            left=rect.left if rect else None,
            top=rect.top if rect else None,
            width=rect.width if rect else None,
            height=rect.height if rect else None,
            preview_max_width=PREVIEW_QUALITY_PRESETS[self.preview_quality][0],
            preview_quality=PREVIEW_QUALITY_PRESETS[self.preview_quality][1],
            preview_fps=self.preview_fps,
            pairing_token=self.pairing_token,
            pairing_code=self.pending_pairing_code,
            new_pairing_token=self.pending_pairing_token,
            on_pairing_established=self._pairing_established,
        )
        failure: str | None = None
        try:
            asyncio.run(self._connection_loop(args))
        except Exception as error:
            failure = str(error)
        finally:
            self._post("stopped", failure)

    def _pairing_established(self, token: str) -> None:
        save_pairing_token(token)
        self.pairing_token = token
        self.pending_pairing_code = None
        self.pending_pairing_token = None
        self._post("paired")

    def _prompt_pairing(self, message: str | None = None) -> None:
        if self.closing:
            return
        if self.running or self.busy:
            self.root.after(100, lambda: self._prompt_pairing(message))
            return
        prompt = "Enter the 8-character code shown in Stylink on your phone. Ignore the dash; you only need to do this once."
        if message:
            prompt = f"{message}\n\n{prompt}"
        code = simpledialog.askstring("Pair Stylink", prompt, parent=self.root)
        if code is None:
            self._set_status("Ready to connect", "You can pair this phone later by clicking Connect phone.")
            return
        code = code.strip().upper().replace("-", "").replace(" ", "")
        if not re.fullmatch(r"[A-HJ-NP-Z2-9]{8}", code):
            messagebox.showerror("Invalid pairing code", "Enter the 8 characters shown in the phone app.", parent=self.root)
            return
        self.pending_pairing_code = code
        self.pending_pairing_token = new_session_token()
        self._toggle_connection()

    async def _connection_loop(self, args: Namespace) -> None:
        last_message = ""
        cached_gateways = []
        next_refresh = 0.0
        event_loop = asyncio.get_running_loop()
        while not self.cancel_setup.is_set():
            if event_loop.time() >= next_refresh:
                try:
                    cached_gateways = await asyncio.to_thread(find_gateway_candidates)
                    last_message = ""
                except Exception as error:
                    message = f"Could not read Windows network adapters: {error}"
                    if message != last_message:
                        self._post("log", message)
                        last_message = message
                    cached_gateways = []
                next_refresh = event_loop.time() + 1.5

            if not cached_gateways:
                self._post("status", ("Waiting for USB tethering…", "Connect the USB cable and turn on USB tethering in the phone settings."))
                await asyncio.sleep(0.4)
                continue

            tether_gateways = [gateway for gateway in cached_gateways if gateway.is_usb_tether]
            if not tether_gateways:
                self._post("status", ("Waiting for USB network…", "Windows has not detected the phone's USB tether adapter yet. Check USB tethering and the cable."))
                await asyncio.sleep(0.4)
                continue

            for gateway in tether_gateways:
                if self.cancel_setup.is_set():
                    break
                self._post("status", ("Looking for your phone…", f"Checking {gateway.label} for Stylink."))
                try:
                    await tablet_host.connect_to_phone(
                        args,
                        gateway.address,
                        stop_event=self.cancel_setup,
                        on_client_state=lambda connected, peer: self._post("client", (connected, peer)),
                        timeout=0.8,
                    )
                except asyncio.CancelledError:
                    raise
                except tablet_host.PairingCodeRequired:
                    self._post("pairing_required")
                    return
                except tablet_host.PairingRejected as error:
                    self.pending_pairing_code = None
                    self.pending_pairing_token = None
                    self._post("pairing_retry", str(error))
                    return
                except tablet_host.PairingMismatch:
                    raise
                except Exception:
                    # A gateway is only a candidate. The host confirms the
                    # Stylink greeting before it performs pairing/authentication.
                    continue
            await asyncio.sleep(0.35)

    def _on_close(self) -> None:
        if self.closing:
            return
        self.closing = True
        self.cancel_setup.set()
        self._wait_for_worker()

    def _wait_for_worker(self) -> None:
        worker = self.worker_thread
        if worker and worker.is_alive():
            self.root.after(100, self._wait_for_worker)
        else:
            self.root.destroy()

    def _drain_messages(self) -> None:
        if self.closing:
            return
        while True:
            try:
                kind, value = self.messages.get_nowait()
            except queue.Empty:
                break
            if kind == "started":
                self.busy = False
                self.running = True
                self._set_status("Looking for your phone…", "Turn on USB tethering on the phone. The PC app will find it automatically.", searching=True)
                self._append_log("Searching the active USB-tether network for the phone app…")
                self._refresh_buttons()
            elif kind == "status":
                self._set_status(value[0], value[1], searching=True)
            elif kind == "client":
                connected, peer = value
                self.pen_connected = connected
                if connected:
                    self._set_status("Connected — ready to draw", "Stylus input is active. Draw on the Android device or select a PC screen area to preview.", connected=True)
                    self._append_log("Android device connected. Stylus input is ready.")
                elif self.running and not self.cancel_setup.is_set():
                    self._set_status("Phone disconnected. Reconnecting…", "Check the USB cable and make sure USB tethering stays on.", searching=True)
                    self._append_log("Phone link ended; searching again.")
            elif kind == "pairing_required":
                self.root.after(0, self._prompt_pairing)
            elif kind == "pairing_retry":
                self.root.after(0, lambda message=value: self._prompt_pairing(message))
            elif kind == "paired":
                self._append_log("Pairing key saved. Future connections authenticate automatically.")
            elif kind == "log":
                self._append_log(value)
            elif kind == "stopped":
                self.running = False
                self.busy = False
                self.pen_connected = False
                if value:
                    self._append_log(value)
                    self._set_status("Could not connect", value)
                else:
                    self._set_status("Disconnected", "Connect the phone, turn on USB tethering, then click Connect phone.")
                self._refresh_buttons()
                if self.closing:
                    self.root.after(0, self.root.destroy)
        self.root.after(100, self._drain_messages)


def enable_dpi_awareness() -> None:
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def main() -> None:
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    enable_dpi_awareness()
    try:
        root = tk.Tk()
    except tk.TclError as error:
        messagebox.showerror(APP_NAME, f"Could not open the Windows app window.\n\n{error}")
        return
    try:
        root.iconbitmap(str(app_icon_path()))
    except tk.TclError:
        pass
    TabletCompanion(root)
    root.mainloop()


if __name__ == "__main__":
    main()

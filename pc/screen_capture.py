"""Screen-region selection and efficient JPEG preview capture."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Any, Callable


@dataclass(frozen=True)
class CaptureRect:
    left: int
    top: int
    width: int
    height: int

    @classmethod
    def from_edges(cls, x1: int, y1: int, x2: int, y2: int) -> "CaptureRect":
        left, right = sorted((int(x1), int(x2)))
        top, bottom = sorted((int(y1), int(y2)))
        if right - left < 32 or bottom - top < 32:
            raise ValueError("Select a screen area at least 32 by 32 pixels.")
        return cls(left, top, right - left, bottom - top)

    def as_dict(self) -> dict[str, int]:
        return {"left": self.left, "top": self.top, "width": self.width, "height": self.height}


class PreviewCapture:
    """Keep one MSS capture session alive while preview frames are produced."""

    def __init__(self) -> None:
        try:
            import mss
        except ImportError as error:
            raise RuntimeError("Screen preview support is missing from this PC app build.") from error
        self._capture = mss.mss()

    def capture(
        self,
        rect: CaptureRect,
        *,
        max_width: int = 960,
        quality: int = 58,
    ) -> tuple[bytes, int, int]:
        """Capture only the selected region, scale, and encode it as JPEG."""
        try:
            from PIL import Image
        except ImportError as error:
            raise RuntimeError("Screen preview support is missing from this PC app build.") from error

        shot = self._capture.grab(rect.as_dict())
        # MSS exposes BGRA directly; Pillow can discard alpha during decode,
        # avoiding the extra full-frame RGB byte copy made by shot.rgb.
        image = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        if image.width > max_width:
            height = max(1, round(image.height * max_width / image.width))
            image = image.resize((max_width, height), Image.Resampling.BILINEAR)
        output = BytesIO()
        image.save(
            output,
            format="JPEG",
            quality=max(30, min(90, int(quality))),
            optimize=False,
            progressive=False,
            subsampling=1,
        )
        return output.getvalue(), image.width, image.height

    def close(self) -> None:
        self._capture.close()


def jpeg_preview(rect: CaptureRect, *, max_width: int = 960, quality: int = 58) -> tuple[bytes, int, int]:
    """Capture one JPEG frame for callers that do not keep a capture session."""
    try:
        capture = PreviewCapture()
    except RuntimeError:
        raise
    try:
        return capture.capture(rect, max_width=max_width, quality=quality)
    finally:
        capture.close()


def select_capture_rect(root: Any, on_selected: Callable[[CaptureRect | None], None]) -> None:
    """Open a translucent full-desktop drag selector using the current screen image."""
    import tkinter as tk
    from tkinter import messagebox

    try:
        import mss
        from PIL import Image, ImageTk

        with mss.mss() as capture:
            virtual = capture.monitors[0]
            shot = capture.grab(virtual)
        screenshot = Image.frombytes("RGB", shot.size, shot.rgb)
    except Exception as error:
        messagebox.showerror("Could not read the PC screen", str(error), parent=root)
        return

    overlay = tk.Toplevel(root)
    overlay.overrideredirect(True)
    overlay.attributes("-topmost", True)
    overlay.geometry(
        f"{virtual['width']}x{virtual['height']}{virtual['left']:+d}{virtual['top']:+d}"
    )
    photo = ImageTk.PhotoImage(screenshot)
    canvas = tk.Canvas(overlay, width=virtual["width"], height=virtual["height"], highlightthickness=0, cursor="crosshair")
    canvas.pack(fill="both", expand=True)
    canvas.create_image(0, 0, image=photo, anchor="nw")
    canvas.create_rectangle(0, 0, virtual["width"], 42, fill="#17243a", stipple="gray50", outline="")
    canvas.create_text(
        16, 21,
        text="Drag to select the part of the PC screen to show on your phone  •  Esc to cancel",
        fill="white", anchor="w", font=("Segoe UI", 12, "bold"),
    )
    state: dict[str, int | None] = {"x": None, "y": None, "shape": None}

    def begin(event: Any) -> None:
        state["x"], state["y"] = event.x, event.y
        state["shape"] = canvas.create_rectangle(event.x, event.y, event.x, event.y, outline="#47a3ff", width=3)

    def move(event: Any) -> None:
        shape = state["shape"]
        x, y = state["x"], state["y"]
        if shape is not None and x is not None and y is not None:
            canvas.coords(shape, x, y, event.x, event.y)

    def finish(event: Any) -> None:
        x, y = state["x"], state["y"]
        if x is None or y is None:
            return
        try:
            rect = CaptureRect.from_edges(
                virtual["left"] + x,
                virtual["top"] + y,
                virtual["left"] + event.x,
                virtual["top"] + event.y,
            )
        except ValueError as error:
            messagebox.showinfo("Choose a larger area", str(error), parent=overlay)
            return
        overlay.destroy()
        on_selected(rect)

    def cancel(_event: Any = None) -> None:
        overlay.destroy()
        on_selected(None)

    canvas.bind("<ButtonPress-1>", begin)
    canvas.bind("<B1-Motion>", move)
    canvas.bind("<ButtonRelease-1>", finish)
    overlay.bind("<Escape>", cancel)
    overlay.focus_force()
    overlay._preview_photo = photo

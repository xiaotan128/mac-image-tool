# -*- coding: utf-8 -*-
from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from tkinter import BOTH, LEFT, TOP, X, Button, Canvas, Entry, Frame, Label, StringVar, Tk, filedialog, messagebox

from PIL import Image, ImageTk


Image.MAX_IMAGE_PIXELS = None

TARGET_RATIO = 9 / 14
OUTPUT_SIZE = (10008, 15568)
TARGET_BYTES = 2 * 1024 * 1024
MIN_CROP_WIDTH = 90
DEFAULT_INPUT_DIR = Path.home() / "Pictures"
DEFAULT_OUTPUT_DIR = Path.home() / "Pictures" / "成品图"

WINDOW_WIDTH = 980
WINDOW_HEIGHT = 820
WINDOW_MIN_WIDTH = 820
WINDOW_MIN_HEIGHT = 640
HANDLE_SIZE = 8
PAD = 10


@dataclass
class Candidate:
    png_bytes: bytes
    block_size: int

    @property
    def size_bytes(self) -> int:
        return len(self.png_bytes)


def centered_crop_box(img_w: int, img_h: int) -> list[float]:
    crop_w = img_w
    crop_h = crop_w / TARGET_RATIO
    if crop_h > img_h:
        crop_h = img_h
        crop_w = crop_h * TARGET_RATIO
    x1 = (img_w - crop_w) / 2
    y1 = (img_h - crop_h) / 2
    return [x1, y1, x1 + crop_w, y1 + crop_h]


def encode_png_rgb(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="PNG", optimize=True, compress_level=9)
    return buffer.getvalue()


def build_small_png(cropped_image: Image.Image) -> Candidate:
    source = cropped_image.convert("RGB")
    last_candidate: Candidate | None = None
    for block_size in (24, 28, 32, 36, 40, 48, 56, 64, 80, 96):
        low_size = (
            max(1, round(OUTPUT_SIZE[0] / block_size)),
            max(1, round(OUTPUT_SIZE[1] / block_size)),
        )
        low = source.resize(low_size, Image.Resampling.LANCZOS)
        out = low.resize(OUTPUT_SIZE, Image.Resampling.NEAREST)
        candidate = Candidate(encode_png_rgb(out), block_size)
        last_candidate = candidate
        if candidate.size_bytes <= TARGET_BYTES:
            return candidate
    assert last_candidate is not None
    return last_candidate


def unique_output_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    index = 1
    while True:
        candidate = path.with_name(f"{stem}_{index}{suffix}")
        if not candidate.exists():
            return candidate
        index += 1


class CropApp:
    def __init__(self) -> None:
        self.root = Tk()
        self.root.title("框选导出 PNG（10008x15568 / 小于2MB）")
        self.root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.root.minsize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)

        self.path_var = StringVar()
        self.status_var = StringVar(value="选择图片后拖动裁剪框，四角可以调整大小。")
        self.image_path: Path | None = None
        self.original_image: Image.Image | None = None
        self.preview_photo: ImageTk.PhotoImage | None = None
        self.scale = 1.0
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.crop_box: list[float] | None = None
        self.drag_mode: str | None = None
        self.drag_last: tuple[float, float] | None = None

        self._build_ui()

    def _build_ui(self) -> None:
        top = Frame(self.root)
        top.pack(side=TOP, fill=X, padx=PAD, pady=PAD)

        Label(top, text="图片路径").pack(side=LEFT)
        Entry(top, textvariable=self.path_var).pack(side=LEFT, fill=X, expand=True, padx=(PAD, PAD))
        Button(top, text="选择图片", command=self.choose_image).pack(side=LEFT)

        self.canvas = Canvas(self.root, bg="#111111", highlightthickness=1, highlightbackground="#444444")
        self.canvas.pack(side=TOP, fill=BOTH, expand=True, padx=PAD)
        self.canvas.bind("<Configure>", self.on_canvas_resize)
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)

        bottom = Frame(self.root)
        bottom.pack(side=TOP, fill=X, padx=PAD, pady=PAD)
        Button(bottom, text="重置框选", command=self.reset_crop).pack(side=LEFT)
        Button(bottom, text="导出 PNG", command=self.export_image).pack(side=LEFT, padx=(PAD, 0))
        Label(bottom, textvariable=self.status_var, anchor="w", justify="left").pack(side=LEFT, fill=X, expand=True, padx=(PAD, 0))

    def choose_image(self) -> None:
        path = filedialog.askopenfilename(
            title="选择图片",
            initialdir=str(DEFAULT_INPUT_DIR if DEFAULT_INPUT_DIR.exists() else Path.home()),
            filetypes=[
                ("Image Files", "*.png;*.jpg;*.jpeg;*.webp;*.bmp"),
                ("All Files", "*.*"),
            ],
        )
        if not path:
            return
        try:
            image = Image.open(path)
            image.load()
            self.original_image = image.convert("RGB")
        except Exception as exc:
            messagebox.showerror("读取失败", f"图片读取失败：\n{exc}")
            return

        self.image_path = Path(path)
        self.path_var.set(str(self.image_path))
        self.crop_box = centered_crop_box(*self.original_image.size)
        self.status_var.set(f"已载入：{self.original_image.width} x {self.original_image.height}")
        self.refresh_preview()

    def reset_crop(self) -> None:
        if self.original_image is None:
            return
        self.crop_box = centered_crop_box(*self.original_image.size)
        self.refresh_preview()

    def on_canvas_resize(self, _event=None) -> None:
        self.refresh_preview()

    def refresh_preview(self) -> None:
        self.canvas.delete("all")
        if self.original_image is None or self.crop_box is None:
            return

        canvas_w = max(1, self.canvas.winfo_width())
        canvas_h = max(1, self.canvas.winfo_height())
        img_w, img_h = self.original_image.size
        self.scale = min(canvas_w / img_w, canvas_h / img_h)
        preview_w = max(1, int(round(img_w * self.scale)))
        preview_h = max(1, int(round(img_h * self.scale)))
        self.offset_x = (canvas_w - preview_w) / 2
        self.offset_y = (canvas_h - preview_h) / 2

        preview = self.original_image.resize((preview_w, preview_h), Image.Resampling.LANCZOS)
        self.preview_photo = ImageTk.PhotoImage(preview)
        self.canvas.create_image(self.offset_x, self.offset_y, image=self.preview_photo, anchor="nw", tags=("image",))
        self.draw_crop_overlay()

    def image_to_canvas(self, x: float, y: float) -> tuple[float, float]:
        return self.offset_x + x * self.scale, self.offset_y + y * self.scale

    def canvas_to_image(self, x: float, y: float) -> tuple[float, float]:
        return (x - self.offset_x) / self.scale, (y - self.offset_y) / self.scale

    def draw_crop_overlay(self) -> None:
        if self.crop_box is None:
            return
        self.canvas.delete("crop")
        x1, y1, x2, y2 = self.crop_box
        cx1, cy1 = self.image_to_canvas(x1, y1)
        cx2, cy2 = self.image_to_canvas(x2, y2)

        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        self.canvas.create_rectangle(0, 0, width, cy1, fill="#000000", stipple="gray50", outline="", tags=("crop",))
        self.canvas.create_rectangle(0, cy2, width, height, fill="#000000", stipple="gray50", outline="", tags=("crop",))
        self.canvas.create_rectangle(0, cy1, cx1, cy2, fill="#000000", stipple="gray50", outline="", tags=("crop",))
        self.canvas.create_rectangle(cx2, cy1, width, cy2, fill="#000000", stipple="gray50", outline="", tags=("crop",))

        self.canvas.create_rectangle(cx1, cy1, cx2, cy2, outline="#00e5ff", width=2, tags=("crop",))
        for p in (1 / 3, 2 / 3):
            x = cx1 + (cx2 - cx1) * p
            y = cy1 + (cy2 - cy1) * p
            self.canvas.create_line(x, cy1, x, cy2, fill="#eeeeee", dash=(8, 5), width=1, tags=("crop",))
            self.canvas.create_line(cx1, y, cx2, y, fill="#eeeeee", dash=(8, 5), width=1, tags=("crop",))

        for x, y in ((cx1, cy1), (cx2, cy1), (cx1, cy2), (cx2, cy2)):
            s = HANDLE_SIZE
            self.canvas.create_rectangle(x - s, y - s, x + s, y + s, fill="#ffffff", outline="#00e5ff", width=2, tags=("crop",))

    def hit_test(self, x: float, y: float) -> str | None:
        if self.crop_box is None:
            return None
        x1, y1, x2, y2 = self.crop_box
        cx1, cy1 = self.image_to_canvas(x1, y1)
        cx2, cy2 = self.image_to_canvas(x2, y2)
        handles = {
            "nw": (cx1, cy1),
            "ne": (cx2, cy1),
            "sw": (cx1, cy2),
            "se": (cx2, cy2),
        }
        for mode, (hx, hy) in handles.items():
            if abs(x - hx) <= HANDLE_SIZE * 2 and abs(y - hy) <= HANDLE_SIZE * 2:
                return mode
        if cx1 <= x <= cx2 and cy1 <= y <= cy2:
            return "move"
        return None

    def on_mouse_down(self, event) -> None:
        mode = self.hit_test(event.x, event.y)
        if mode:
            self.drag_mode = mode
            self.drag_last = (event.x, event.y)

    def on_mouse_drag(self, event) -> None:
        if self.original_image is None or self.crop_box is None or self.drag_mode is None or self.drag_last is None:
            return
        last_x, last_y = self.drag_last
        dx = (event.x - last_x) / self.scale
        dy = (event.y - last_y) / self.scale
        self.drag_last = (event.x, event.y)

        if self.drag_mode == "move":
            self.crop_box[0] += dx
            self.crop_box[1] += dy
            self.crop_box[2] += dx
            self.crop_box[3] += dy
        else:
            self.resize_crop(self.drag_mode, dx)

        self.clamp_crop()
        self.draw_crop_overlay()

    def on_mouse_up(self, _event) -> None:
        self.drag_mode = None
        self.drag_last = None

    def resize_crop(self, mode: str, dx: float) -> None:
        if self.crop_box is None:
            return
        x1, y1, x2, y2 = self.crop_box
        old_w = x2 - x1
        old_h = y2 - y1
        if "w" in mode:
            new_w = old_w - dx
            x1 = x2 - new_w
        else:
            new_w = old_w + dx
            x2 = x1 + new_w
        new_h = new_w / TARGET_RATIO
        if "n" in mode:
            y1 = y2 - new_h
        else:
            y2 = y1 + new_h
        self.crop_box = [x1, y1, x2, y2]

    def clamp_crop(self) -> None:
        if self.original_image is None or self.crop_box is None:
            return
        img_w, img_h = self.original_image.size
        x1, y1, x2, y2 = self.crop_box
        crop_w = max(MIN_CROP_WIDTH, x2 - x1)
        crop_h = crop_w / TARGET_RATIO
        if crop_h > img_h:
            crop_h = img_h
            crop_w = crop_h * TARGET_RATIO
        if crop_w > img_w:
            crop_w = img_w
            crop_h = crop_w / TARGET_RATIO

        if x2 < x1:
            x1, x2 = x2, x1
        if y2 < y1:
            y1, y2 = y2, y1
        x1 = min(max(0, x1), img_w - crop_w)
        y1 = min(max(0, y1), img_h - crop_h)
        self.crop_box = [x1, y1, x1 + crop_w, y1 + crop_h]

    def export_image(self) -> None:
        if self.original_image is None or self.crop_box is None or self.image_path is None:
            messagebox.showwarning("提示", "请先选择图片。")
            return

        DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        default_name = f"{self.image_path.stem}_10008x15568_2mb.png"
        output_path = filedialog.asksaveasfilename(
            title="保存 PNG",
            initialdir=str(DEFAULT_OUTPUT_DIR),
            initialfile=default_name,
            defaultextension=".png",
            filetypes=[("PNG Image", "*.png")],
        )
        if not output_path:
            return

        try:
            self.status_var.set("正在导出，请稍等...")
            self.root.update_idletasks()
            crop = tuple(round(v) for v in self.crop_box)
            cropped = self.original_image.crop(crop)
            candidate = build_small_png(cropped)
            Path(output_path).write_bytes(candidate.png_bytes)
        except Exception as exc:
            messagebox.showerror("导出失败", f"导出失败：\n{exc}")
            return

        mib = candidate.size_bytes / 1024 / 1024
        result = "已满足小于 2MB" if candidate.size_bytes <= TARGET_BYTES else "未压到 2MB 以下"
        self.status_var.set(f"已导出：{Path(output_path).name}，{mib:.3f} MiB，像素块 {candidate.block_size}")
        messagebox.showinfo(
            "导出完成",
            "\n".join(
                [
                    f"尺寸：{OUTPUT_SIZE[0]} x {OUTPUT_SIZE[1]}",
                    f"大小：{mib:.3f} MiB",
                    f"像素块：{candidate.block_size}",
                    result,
                ]
            ),
        )

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    CropApp().run()

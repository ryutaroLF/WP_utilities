from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageOps, ImageTk

from _base import BaseTabPlugin


IMAGE_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".bmp",
    ".webp", ".tif", ".tiff",
)
THUMB_SIZE = 170
EDITOR_CANVAS_W = 820
EDITOR_CANVAS_H = 620
EDITOR_FRAME_SIZE = 500
DEFAULT_OUTPUT_SIZE = 1024
ZOOM_STEP = 1.08
MAX_SCALE_RATIO = 20.0


@dataclass
class ImageItem:
    path: Path
    image: Image.Image
    scale: float = 1.0
    min_scale: float = 1.0
    offset_x: float = 0.0
    offset_y: float = 0.0
    has_custom_crop: bool = False

    @property
    def basename(self) -> str:
        return self.path.name

    def reset_crop(self) -> None:
        self.min_scale = max(
            EDITOR_FRAME_SIZE / self.image.width,
            EDITOR_FRAME_SIZE / self.image.height,
        )
        self.scale = self.min_scale
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.has_custom_crop = False
        clamp_item_offset(self)


def clamp_item_offset(item: ImageItem) -> None:
    disp_w = item.image.width * item.scale
    disp_h = item.image.height * item.scale

    max_dx = max(0.0, (disp_w - EDITOR_FRAME_SIZE) / 2)
    max_dy = max(0.0, (disp_h - EDITOR_FRAME_SIZE) / 2)

    item.offset_x = max(-max_dx, min(item.offset_x, max_dx))
    item.offset_y = max(-max_dy, min(item.offset_y, max_dy))


def crop_box_on_source(item: ImageItem):
    crop_size_src = EDITOR_FRAME_SIZE / item.scale
    cx_src = item.image.width / 2 - item.offset_x / item.scale
    cy_src = item.image.height / 2 - item.offset_y / item.scale

    return (
        cx_src - crop_size_src / 2,
        cy_src - crop_size_src / 2,
        cx_src + crop_size_src / 2,
        cy_src + crop_size_src / 2,
    )


def make_circle_cropped_image(
    item: ImageItem,
    output_size: int,
) -> Image.Image:
    cropped = item.image.crop(crop_box_on_source(item))
    cropped = cropped.resize(
        (output_size, output_size),
        Image.Resampling.LANCZOS,
    )

    mask = Image.new("L", (output_size, output_size), 0)
    ImageDraw.Draw(mask).ellipse(
        (0, 0, output_size - 1, output_size - 1),
        fill=255,
    )

    result = Image.new(
        "RGBA",
        (output_size, output_size),
        (0, 0, 0, 0),
    )
    result.paste(cropped, (0, 0))
    result.putalpha(mask)
    return result


def make_square_preview(item: ImageItem, size: int) -> Image.Image:
    img = item.image.copy()
    img.thumbnail((size, size), Image.Resampling.LANCZOS)

    bg = Image.new("RGBA", (size, size), (42, 42, 46, 255))
    bg.alpha_composite(
        img,
        ((size - img.width) // 2, (size - img.height) // 2),
    )
    return bg


def make_circle_preview(item: ImageItem, size: int) -> Image.Image:
    result = make_circle_cropped_image(item, size)
    bg = Image.new("RGBA", (size, size), (42, 42, 46, 255))
    bg.alpha_composite(result)
    return bg


class CropEditor(ctk.CTkToplevel):
    def __init__(self, plugin: "Crop360Tab", item_index: int):
        super().__init__(plugin.app)
        self.plugin = plugin
        self.item = plugin.items[item_index]

        self.title(f"Adjust Crop - {self.item.basename}")
        self.geometry("900x760")
        self.minsize(820, 700)
        self.transient(plugin.app)
        self.grab_set()

        self.tk_img = None
        self.dragging = False
        self.last_mouse_x = 0
        self.last_mouse_y = 0

        self.build_ui()
        self.redraw()
        self.update_info()

    def build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        top = ctk.CTkFrame(self)
        top.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=14,
            pady=(14, 8),
        )
        top.grid_columnconfigure(2, weight=1)

        ctk.CTkButton(
            top,
            text="Reset",
            width=110,
            command=self.reset_current,
        ).grid(row=0, column=0, padx=6, pady=8)

        ctk.CTkButton(
            top,
            text="Save Adjustment",
            width=150,
            command=self.save_and_close,
        ).grid(row=0, column=1, padx=6, pady=8)

        self.info_label = ctk.CTkLabel(top, text="")
        self.info_label.grid(
            row=0,
            column=2,
            sticky="w",
            padx=12,
        )

        frame = ctk.CTkFrame(self)
        frame.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=14,
            pady=8,
        )
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(
            frame,
            width=EDITOR_CANVAS_W,
            height=EDITOR_CANVAS_H,
            bg="#303034",
            highlightthickness=0,
        )
        self.canvas.grid(row=0, column=0, padx=10, pady=10)

        ctk.CTkLabel(
            self,
            text=(
                "Drag = move / Mouse wheel = zoom / "
                "White square = crop area / Red circle = final mask"
            ),
        ).grid(row=2, column=0, sticky="w", padx=22, pady=(8, 14))

        self.canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)
        self.canvas.bind("<Button-4>", self.on_mouse_wheel)
        self.canvas.bind("<Button-5>", self.on_mouse_wheel)

    def frame_rect(self):
        cx = EDITOR_CANVAS_W / 2
        cy = EDITOR_CANVAS_H / 2
        half = EDITOR_FRAME_SIZE / 2
        return cx - half, cy - half, cx + half, cy + half

    def redraw(self) -> None:
        self.canvas.delete("all")

        disp_w = max(1, int(self.item.image.width * self.item.scale))
        disp_h = max(1, int(self.item.image.height * self.item.scale))
        displayed = self.item.image.resize(
            (disp_w, disp_h),
            Image.Resampling.LANCZOS,
        )
        self.tk_img = ImageTk.PhotoImage(displayed)

        cx = EDITOR_CANVAS_W / 2 + self.item.offset_x
        cy = EDITOR_CANVAS_H / 2 + self.item.offset_y
        self.canvas.create_image(
            cx - disp_w / 2,
            cy - disp_h / 2,
            anchor="nw",
            image=self.tk_img,
        )

        x1, y1, x2, y2 = self.frame_rect()
        self.canvas.create_rectangle(
            0, 0, EDITOR_CANVAS_W, y1,
            fill="#000000", stipple="gray50", outline="",
        )
        self.canvas.create_rectangle(
            0, y2, EDITOR_CANVAS_W, EDITOR_CANVAS_H,
            fill="#000000", stipple="gray50", outline="",
        )
        self.canvas.create_rectangle(
            0, y1, x1, y2,
            fill="#000000", stipple="gray50", outline="",
        )
        self.canvas.create_rectangle(
            x2, y1, EDITOR_CANVAS_W, y2,
            fill="#000000", stipple="gray50", outline="",
        )
        self.canvas.create_rectangle(
            x1, y1, x2, y2,
            outline="white", width=2,
        )
        self.canvas.create_oval(
            x1, y1, x2, y2,
            outline="#ff4b4b", width=3,
        )

    def update_info(self) -> None:
        self.info_label.configure(
            text=(
                f"{self.item.basename}   "
                f"{self.item.image.width}x{self.item.image.height}   "
                f"zoom={self.item.scale / self.item.min_scale:.2f}x"
            )
        )

    def reset_current(self) -> None:
        self.item.reset_crop()
        self.redraw()
        self.update_info()

    def save_and_close(self) -> None:
        self.item.has_custom_crop = True
        self.plugin.show_crop_preview = True
        self.plugin.refresh_grid()
        self.destroy()

    def on_mouse_down(self, event) -> None:
        self.dragging = True
        self.last_mouse_x = event.x
        self.last_mouse_y = event.y

    def on_mouse_drag(self, event) -> None:
        if not self.dragging:
            return

        self.item.offset_x += event.x - self.last_mouse_x
        self.item.offset_y += event.y - self.last_mouse_y
        self.last_mouse_x = event.x
        self.last_mouse_y = event.y

        clamp_item_offset(self.item)
        self.redraw()
        self.update_info()

    def on_mouse_up(self, _event) -> None:
        self.dragging = False

    def on_mouse_wheel(self, event) -> None:
        if getattr(event, "num", None) == 4:
            factor = ZOOM_STEP
        elif getattr(event, "num", None) == 5:
            factor = 1 / ZOOM_STEP
        else:
            factor = ZOOM_STEP if event.delta > 0 else 1 / ZOOM_STEP

        old_scale = self.item.scale
        new_scale = max(
            self.item.min_scale,
            min(
                old_scale * factor,
                self.item.min_scale * MAX_SCALE_RATIO,
            ),
        )

        if abs(new_scale - old_scale) < 1e-12:
            return

        mx, my = event.x, event.y
        old_w = self.item.image.width * old_scale
        old_h = self.item.image.height * old_scale
        old_cx = EDITOR_CANVAS_W / 2 + self.item.offset_x
        old_cy = EDITOR_CANVAS_H / 2 + self.item.offset_y
        old_left = old_cx - old_w / 2
        old_top = old_cy - old_h / 2

        src_x = (mx - old_left) / old_scale
        src_y = (my - old_top) / old_scale

        new_w = self.item.image.width * new_scale
        new_h = self.item.image.height * new_scale
        new_left = mx - src_x * new_scale
        new_top = my - src_y * new_scale

        self.item.scale = new_scale
        self.item.offset_x = (
            new_left + new_w / 2 - EDITOR_CANVAS_W / 2
        )
        self.item.offset_y = (
            new_top + new_h / 2 - EDITOR_CANVAS_H / 2
        )

        clamp_item_offset(self.item)
        self.redraw()
        self.update_info()


class Crop360Tab(BaseTabPlugin):
    TAB_TITLE = "Crop360"
    ORDER = 50

    def __init__(self, app, tabview) -> None:
        super().__init__(app, tabview)
        self.items: list[ImageItem] = []
        self.preview_images: list[ImageTk.PhotoImage] = []
        self.show_crop_preview = False

    def create_ui(self) -> None:
        tab = self.tab
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        top = ctk.CTkFrame(tab)
        top.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=14,
            pady=(14, 8),
        )
        top.grid_columnconfigure(9, weight=1)

        controls = [
            ("Browse Images", 140, self.load_images),
            ("Clear", 90, self.clear_images),
            ("View Crop", 120, self.view_crop_all),
            ("Reset All", 110, self.reset_all),
            ("Crop All", 120, self.crop_all),
        ]

        for column, (text, width, command) in enumerate(controls):
            ctk.CTkButton(
                top,
                text=text,
                width=width,
                command=command,
            ).grid(
                row=0,
                column=column,
                padx=5,
                pady=10,
            )

        ctk.CTkLabel(
            top,
            text="Output Size:",
        ).grid(row=0, column=5, padx=(18, 6), pady=10)

        self.output_entry = ctk.CTkEntry(top, width=82)
        self.output_entry.insert(0, str(DEFAULT_OUTPUT_SIZE))
        self.output_entry.grid(
            row=0,
            column=6,
            padx=6,
            pady=10,
        )

        self.status_label = ctk.CTkLabel(
            top,
            text="Select multiple images. Click a thumbnail to adjust it.",
            anchor="w",
        )
        self.status_label.grid(
            row=0,
            column=9,
            sticky="ew",
            padx=16,
            pady=10,
        )

        self.scroll = ctk.CTkScrollableFrame(tab)
        self.scroll.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=14,
            pady=(8, 14),
        )

        self.refresh_grid()

    def load_images(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Select images",
            filetypes=[
                (
                    "Image files",
                    "*.png;*.jpg;*.jpeg;*.bmp;*.webp;*.tif;*.tiff",
                ),
                ("All files", "*.*"),
            ],
        )
        if not paths:
            return

        loaded = 0
        failed = []

        for raw_path in paths:
            path = Path(raw_path)

            if path.suffix.lower() not in IMAGE_EXTENSIONS:
                failed.append(
                    f"{path.name}: unsupported extension"
                )
                continue

            try:
                image = Image.open(path)
                image = ImageOps.exif_transpose(image).convert("RGBA")
            except Exception as error:
                failed.append(f"{path.name}: {error}")
                continue

            item = ImageItem(path=path, image=image)
            item.reset_crop()
            self.items.append(item)
            loaded += 1

        self.show_crop_preview = False
        self.refresh_grid()

        if failed:
            messagebox.showwarning(
                "Some files were skipped",
                "Loaded: "
                + str(loaded)
                + "\n\n"
                + "\n".join(failed[:12]),
            )

    def clear_images(self) -> None:
        self.items.clear()
        self.preview_images.clear()
        self.show_crop_preview = False
        self.refresh_grid()

    def reset_all(self) -> None:
        for item in self.items:
            item.reset_crop()
        self.show_crop_preview = False
        self.refresh_grid()

    def view_crop_all(self) -> None:
        if not self.items:
            messagebox.showwarning(
                "Warning",
                "Please select images first.",
            )
            return

        self.show_crop_preview = True
        self.refresh_grid()

    def open_editor(self, index: int) -> None:
        if 0 <= index < len(self.items):
            CropEditor(self, index)

    def refresh_grid(self) -> None:
        for widget in self.scroll.winfo_children():
            widget.destroy()

        self.preview_images.clear()

        if not self.items:
            ctk.CTkLabel(
                self.scroll,
                text="No images selected. Use Browse Images.",
                font=ctk.CTkFont(size=18),
            ).grid(row=0, column=0, padx=24, pady=36)

            self.status_label.configure(
                text="No images selected."
            )
            return

        columns = max(
            2,
            min(5, math.ceil(math.sqrt(len(self.items)))),
        )

        for column in range(columns):
            self.scroll.grid_columnconfigure(column, weight=1)

        for index, item in enumerate(self.items):
            row = index // columns
            column = index % columns

            card = ctk.CTkFrame(self.scroll)
            card.grid(
                row=row,
                column=column,
                sticky="n",
                padx=10,
                pady=10,
            )

            preview = (
                make_circle_preview(item, THUMB_SIZE)
                if self.show_crop_preview
                else make_square_preview(item, THUMB_SIZE)
            )

            tk_image = ImageTk.PhotoImage(preview)
            self.preview_images.append(tk_image)

            image_label = ctk.CTkLabel(
                card,
                image=tk_image,
                text="",
            )
            image_label.pack(
                padx=10,
                pady=(10, 6),
            )
            image_label.bind(
                "<Button-1>",
                lambda _event, idx=index: self.open_editor(idx),
            )

            name = item.basename
            if len(name) > 28:
                name = name[:12] + "..." + name[-12:]

            ctk.CTkLabel(
                card,
                text=name,
                width=THUMB_SIZE,
            ).pack(padx=10, pady=(0, 2))

            ctk.CTkLabel(
                card,
                text=(
                    "adjusted"
                    if item.has_custom_crop
                    else "auto"
                ),
                text_color="#a7a7a7",
            ).pack(padx=10, pady=(0, 10))

        self.status_label.configure(
            text=(
                f"{len(self.items)} image(s). "
                "View Crop previews the circle mask. "
                "Crop All writes PNG files to crop folders."
            )
        )

    def get_output_size(self):
        try:
            value = int(self.output_entry.get())
            if value <= 0:
                raise ValueError
            return value
        except Exception:
            messagebox.showerror(
                "Error",
                "Output Size must be a positive integer.",
            )
            return None

    def crop_all(self) -> None:
        if not self.items:
            messagebox.showwarning(
                "Warning",
                "Please select images first.",
            )
            return

        output_size = self.get_output_size()
        if output_size is None:
            return

        saved = []
        failed = []

        for item in self.items:
            try:
                result = make_circle_cropped_image(
                    item,
                    output_size,
                )

                save_dir = item.path.parent / "crop"
                save_dir.mkdir(
                    parents=True,
                    exist_ok=True,
                )

                save_path = (
                    save_dir
                    / f"{item.path.stem}_crop.png"
                )
                result.save(save_path)
                saved.append(save_path)

            except Exception as error:
                failed.append(
                    f"{item.basename}: {error}"
                )

        self.show_crop_preview = True
        self.refresh_grid()

        message = f"Saved {len(saved)} file(s)."

        if saved:
            parents = sorted(
                {str(path.parent) for path in saved}
            )
            message += (
                "\n\nOutput folder(s):\n"
                + "\n".join(parents)
            )

        if failed:
            message += (
                "\n\nFailed:\n"
                + "\n".join(failed[:12])
            )
            messagebox.showwarning(
                "Crop finished with errors",
                message,
            )
        else:
            messagebox.showinfo(
                "Crop finished",
                message,
            )


TAB_PLUGIN = Crop360Tab

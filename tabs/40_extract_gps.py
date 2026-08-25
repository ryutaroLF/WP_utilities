from __future__ import annotations

import os
import subprocess
import sys
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import ExifTags, Image, UnidentifiedImageError
from tkinterdnd2 import DND_FILES

from _base import BaseTabPlugin


class ExtractGpsTab(BaseTabPlugin):
    TAB_TITLE = "Extract GPS"
    ORDER = 40

    def __init__(self, app, tabview) -> None:
        super().__init__(app, tabview)
        self.current_image_path = ""
        self.current_coordinates = ""

    def create_ui(self) -> None:
        tab = self.tab
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            tab,
            text=(
                "GPS情報を含む画像を選択するか、"
                "下の領域へドラッグ＆ドロップしてください。"
            ),
            anchor="w",
            text_color=("gray35", "gray70"),
        ).grid(row=0, column=0, sticky="ew", padx=22, pady=(18, 14))

        ctk.CTkButton(
            tab,
            text="画像を選択",
            height=44,
            command=self.select_image,
        ).grid(row=1, column=0, sticky="ew", padx=22, pady=(0, 14))

        self.drop_frame = ctk.CTkFrame(
            tab,
            corner_radius=16,
            border_width=2,
            height=190,
        )
        self.drop_frame.grid(
            row=2,
            column=0,
            sticky="nsew",
            padx=22,
            pady=(0, 18),
        )
        self.drop_frame.grid_propagate(False)
        self.drop_frame.grid_columnconfigure(0, weight=1)
        self.drop_frame.grid_rowconfigure(0, weight=1)

        self.drop_label = ctk.CTkLabel(
            self.drop_frame,
            text=(
                "画像をここへドラッグ＆ドロップ\n\n"
                "JPEG / TIFF / HEIC※ / PNGなど"
            ),
            font=ctk.CTkFont(size=17, weight="bold"),
            justify="center",
        )
        self.drop_label.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=20,
            pady=20,
        )

        for widget in (self.drop_frame, self.drop_label):
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self.on_file_drop)

        details = ctk.CTkFrame(tab)
        details.grid(
            row=3,
            column=0,
            sticky="ew",
            padx=22,
            pady=(0, 16),
        )
        details.grid_columnconfigure(1, weight=1)

        self.file_path_label = self.add_row(
            details, 0, "画像", readonly_label=True
        )
        self.latitude_entry = self.add_row(details, 1, "緯度")
        self.longitude_entry = self.add_row(details, 2, "経度")
        self.coordinate_entry = self.add_row(
            details, 3, "検索用座標"
        )

        buttons = ctk.CTkFrame(tab, fg_color="transparent")
        buttons.grid(
            row=4,
            column=0,
            sticky="ew",
            padx=22,
            pady=(0, 12),
        )
        buttons.grid_columnconfigure((0, 1), weight=1)

        self.copy_button = ctk.CTkButton(
            buttons,
            text="座標をコピー",
            height=44,
            state="disabled",
            command=self.copy_coordinates,
        )
        self.copy_button.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 6),
        )

        self.maps_button = ctk.CTkButton(
            buttons,
            text="Google Mapsで開く",
            height=44,
            state="disabled",
            command=self.open_maps,
        )
        self.maps_button.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(6, 0),
        )

        lower = ctk.CTkFrame(tab, fg_color="transparent")
        lower.grid(
            row=5,
            column=0,
            sticky="ew",
            padx=22,
            pady=(0, 12),
        )
        lower.grid_columnconfigure(0, weight=1)

        self.open_button = ctk.CTkButton(
            lower,
            text="画像の場所を開く",
            height=40,
            fg_color="transparent",
            border_width=1,
            text_color=("gray15", "gray90"),
            state="disabled",
            command=self.open_location,
        )
        self.open_button.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 6),
        )

        ctk.CTkButton(
            lower,
            text="Clear",
            width=110,
            height=40,
            fg_color="transparent",
            border_width=1,
            text_color=("gray15", "gray90"),
            command=self.clear,
        ).grid(row=0, column=1, padx=(6, 0))

        self.status = ctk.CTkLabel(
            tab,
            text="※ HEIC画像は環境によって追加ライブラリが必要です。",
            anchor="w",
        )
        self.status.grid(
            row=6,
            column=0,
            sticky="ew",
            padx=22,
            pady=(0, 12),
        )

    @staticmethod
    def add_row(parent, row, title, readonly_label=False):
        ctk.CTkLabel(
            parent,
            text=title,
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        ).grid(
            row=row,
            column=0,
            sticky="w",
            padx=(18, 12),
            pady=10,
        )

        if readonly_label:
            widget = ctk.CTkLabel(
                parent,
                text="未選択",
                anchor="w",
                justify="left",
                wraplength=700,
            )
        else:
            widget = ctk.CTkEntry(parent, height=38)

        widget.grid(
            row=row,
            column=1,
            sticky="ew",
            padx=(0, 18),
            pady=10,
        )
        return widget

    def select_image(self) -> None:
        path = filedialog.askopenfilename(
            title="GPS情報を抽出する画像を選択",
            filetypes=[
                (
                    "画像ファイル",
                    "*.jpg *.jpeg *.tif *.tiff *.png *.webp *.heic *.heif",
                ),
                ("すべてのファイル", "*.*"),
            ],
        )
        if path:
            self.process_image(path)

    def on_file_drop(self, event) -> None:
        paths = self.app.tk.splitlist(event.data)
        if paths:
            self.process_image(paths[0])

    def process_image(self, file_path: str) -> None:
        file_path = os.path.abspath(file_path)
        if not os.path.isfile(file_path):
            messagebox.showwarning(
                "ファイルエラー",
                "選択されたファイルが見つかりません。",
            )
            return

        try:
            latitude, longitude = self.extract_gps(file_path)
        except UnidentifiedImageError:
            messagebox.showerror(
                "画像エラー",
                "画像ファイルとして読み込めませんでした。",
            )
            return
        except Exception as error:
            messagebox.showerror(
                "読み取りエラー",
                f"画像のEXIF情報を読み取れませんでした。\n\n{error}",
            )
            return

        self.current_image_path = file_path
        self.file_path_label.configure(text=file_path)
        self.open_button.configure(state="normal")

        if latitude is None or longitude is None:
            self.clear_entries()
            self.copy_button.configure(state="disabled")
            self.maps_button.configure(state="disabled")
            self.status.configure(
                text="この画像にはGPS座標が保存されていません。"
            )
            return

        coordinates = f"{latitude:.8f}, {longitude:.8f}"
        self.current_coordinates = coordinates

        self.set_entry(self.latitude_entry, f"{latitude:.8f}")
        self.set_entry(self.longitude_entry, f"{longitude:.8f}")
        self.set_entry(self.coordinate_entry, coordinates)

        self.copy_button.configure(state="normal")
        self.maps_button.configure(state="normal")
        self.drop_label.configure(
            text=f"GPS座標を抽出しました\n\n{Path(file_path).name}"
        )
        self.status.configure(
            text="EXIF GPS情報を10進数の座標へ変換しました。"
        )

    @staticmethod
    def extract_gps(file_path: str):
        with Image.open(file_path) as image:
            exif = image.getexif()
            if not exif:
                return None, None

            gps_ifd = None
            if hasattr(exif, "get_ifd"):
                try:
                    gps_ifd = exif.get_ifd(
                        ExifTags.IFD.GPSInfo
                    )
                except Exception:
                    gps_ifd = None

            if not gps_ifd:
                gps_tag_id = next(
                    (
                        tag_id
                        for tag_id, name in ExifTags.TAGS.items()
                        if name == "GPSInfo"
                    ),
                    None,
                )
                if gps_tag_id is not None:
                    gps_ifd = exif.get(gps_tag_id)

            if not gps_ifd:
                return None, None

            gps_data = {
                ExifTags.GPSTAGS.get(key, key): value
                for key, value in gps_ifd.items()
            }

            lat = gps_data.get("GPSLatitude")
            lat_ref = gps_data.get("GPSLatitudeRef")
            lon = gps_data.get("GPSLongitude")
            lon_ref = gps_data.get("GPSLongitudeRef")

            if not all((lat, lat_ref, lon, lon_ref)):
                return None, None

            return (
                ExtractGpsTab.dms_to_decimal(lat, lat_ref),
                ExtractGpsTab.dms_to_decimal(lon, lon_ref),
            )

    @staticmethod
    def rational_to_float(value) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            pass

        if isinstance(value, tuple) and len(value) == 2:
            numerator, denominator = value
            if denominator == 0:
                raise ValueError("EXIFの分母が0です。")
            return float(numerator) / float(denominator)

        if hasattr(value, "numerator") and hasattr(value, "denominator"):
            if value.denominator == 0:
                raise ValueError("EXIFの分母が0です。")
            return float(value.numerator) / float(value.denominator)

        raise ValueError(f"GPS値を数値へ変換できません: {value}")

    @staticmethod
    def dms_to_decimal(dms, direction) -> float:
        value = (
            ExtractGpsTab.rational_to_float(dms[0])
            + ExtractGpsTab.rational_to_float(dms[1]) / 60
            + ExtractGpsTab.rational_to_float(dms[2]) / 3600
        )

        if isinstance(direction, bytes):
            direction = direction.decode(
                "ascii",
                errors="ignore",
            )

        if str(direction).upper().strip() in {"S", "W"}:
            value *= -1

        return value

    @staticmethod
    def set_entry(entry, value: str) -> None:
        entry.delete(0, "end")
        entry.insert(0, value)

    def clear_entries(self) -> None:
        for entry in (
            self.latitude_entry,
            self.longitude_entry,
            self.coordinate_entry,
        ):
            entry.delete(0, "end")
        self.current_coordinates = ""

    def copy_coordinates(self) -> None:
        value = self.coordinate_entry.get().strip()
        if not value:
            return

        self.copy_to_clipboard(value)
        self.copy_button.configure(text="Copied!")
        self.status.configure(
            text="座標をクリップボードにコピーしました。"
        )
        self.app.after(
            1500,
            lambda: self.copy_button.configure(text="座標をコピー"),
        )

    def open_maps(self) -> None:
        value = self.coordinate_entry.get().strip()
        if not value:
            return

        webbrowser.open(
            "https://www.google.com/maps/search/"
            f"?api=1&query={value.replace(' ', '')}"
        )

    def open_location(self) -> None:
        if not self.current_image_path:
            return

        path = os.path.abspath(self.current_image_path)

        if sys.platform.startswith("win"):
            subprocess.run(
                ["explorer", "/select,", os.path.normpath(path)],
                check=False,
            )
        elif sys.platform == "darwin":
            subprocess.run(["open", "-R", path], check=False)
        else:
            subprocess.run(
                ["xdg-open", os.path.dirname(path)],
                check=False,
            )

    def clear(self) -> None:
        self.current_image_path = ""
        self.current_coordinates = ""
        self.file_path_label.configure(text="未選択")
        self.clear_entries()
        self.copy_button.configure(state="disabled")
        self.maps_button.configure(state="disabled")
        self.open_button.configure(state="disabled")
        self.drop_label.configure(
            text=(
                "画像をここへドラッグ＆ドロップ\n\n"
                "JPEG / TIFF / HEIC※ / PNGなど"
            )
        )
        self.status.configure(
            text="※ HEIC画像は環境によって追加ライブラリが必要です。"
        )


TAB_PLUGIN = ExtractGpsTab

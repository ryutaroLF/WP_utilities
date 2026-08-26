from __future__ import annotations

import math
import os
import re
import shutil
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable

import customtkinter as ctk
import mapbox_vector_tile
import requests
import tkinter as tk
from PIL import Image, ImageTk
from tkinter import messagebox

from _base import BaseTabPlugin


# ============================================================
# Plugin
# ============================================================

TAB_TITLE = "map2svg"
TAB_ORDER = 100

DEFAULT_COORDINATE = "57.654013290513504, -6.376423612690427"
DEFAULT_ZOOM = 12.0

PROJECT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_DIR / "downloaded_maps"
CACHE_ROOT = PROJECT_DIR / ".map2svg_cache"
PREVIEW_CACHE_DIR = CACHE_ROOT / "preview_osm"
VECTOR_CACHE_DIR = CACHE_ROOT / "openfreemap"

PREVIEW_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
OPENFREEMAP_TILEJSON_URL = "https://tiles.openfreemap.org/planet"
USER_AGENT = "CherryUtility-map2svg/1.0"

# Pure-vector output colors.
LAND_COLOR = "#F2EDDF"
GREEN_COLOR = "#CDF1D7"
WATER_COLOR = "#8DD3E6"
ROAD_COLOR = "#A7ADB2"

SVG_WIDTH = 1600
SHOW_ATTRIBUTION = True
SHOW_WATERWAYS = True
SHOW_MINOR_ROADS = True
SHOW_SERVICE_ROADS = True
SHOW_PATHS = False

ROAD_WIDTH = {
    "motorway": 6.5,
    "trunk": 5.8,
    "primary": 5.2,
    "secondary": 4.4,
    "tertiary": 3.7,
    "minor": 2.5,
    "service": 1.6,
    "track": 1.2,
    "path": 1.0,
}

GREEN_LANDCOVER_CLASSES = {
    "farmland",
    "wood",
    "grass",
    "wetland",
}

ASPECT_RATIOS = {
    "1:1": (1, 1),
    "3:4": (3, 4),
    "4:3": (4, 3),
    "16:9": (16, 9),
    "9:16": (9, 16),
}


# ============================================================
# Coordinate / Web Mercator helpers
# ============================================================

def parse_google_coordinate(text: str) -> tuple[float, float]:
    nums = re.findall(r"[-+]?\d+(?:\.\d+)?", text)

    if len(nums) < 2:
        raise ValueError(
            "Enter coordinates as: latitude, longitude"
        )

    lat = float(nums[0])
    lon = float(nums[1])

    if not -90 <= lat <= 90:
        raise ValueError(
            "Latitude must be between -90 and 90."
        )

    if not -180 <= lon <= 180:
        raise ValueError(
            "Longitude must be between -180 and 180."
        )

    return lat, lon


def lonlat_to_world(
    lon: float,
    lat: float,
) -> tuple[float, float]:

    lat = max(
        min(lat, 85.05112878),
        -85.05112878,
    )

    x = (
        lon + 180.0
    ) / 360.0

    y = (
        1.0
        -
        math.asinh(
            math.tan(
                math.radians(lat)
            )
        )
        / math.pi
    ) / 2.0

    return x, y


def world_to_lonlat(
    x: float,
    y: float,
) -> tuple[float, float]:

    lon = (
        x * 360.0
        - 180.0
    )

    lat = math.degrees(
        math.atan(
            math.sinh(
                math.pi
                * (
                    1.0
                    - 2.0 * y
                )
            )
        )
    )

    return lon, lat


# ============================================================
# Smooth preview map
# ============================================================

class SmoothMapPreview(ctk.CTkFrame):
    """
    Lightweight interactive map with true fractional zoom.

    The raster OSM tiles are used ONLY for the GUI preview.

    The exported SVG does not contain these tiles.
    SVG output is independently generated from vector tiles.
    """

    TILE_SIZE = 256

    MIN_ZOOM = 2.0
    MAX_ZOOM = 19.0

    # Fine zoom step.
    #
    # Normal mouse wheel:
    #     1 notch = 0.18 zoom
    #
    # Much finer than TkinterMapView's default Windows behavior.
    ZOOM_STEP = 0.18


    def __init__(
        self,
        parent,
        cache_dir: Path,
        center_lat: float,
        center_lon: float,
        zoom: float,
    ) -> None:

        super().__init__(
            parent,
            corner_radius=0,
            fg_color="#d9d9d9",
        )

        self.cache_dir = cache_dir

        self.cache_dir.mkdir(
            parents=True,
            exist_ok=True,
        )


        self.center_x, self.center_y = (
            lonlat_to_world(
                center_lon,
                center_lat,
            )
        )


        self.zoom = float(
            zoom
        )


        self.marker_latlon: (
            tuple[float, float]
            | None
        ) = None


        # ----------------------------------------------------
        # Canvas
        # ----------------------------------------------------

        self.canvas = tk.Canvas(
            self,
            highlightthickness=0,
            bd=0,
            bg="#d9d9d9",
            cursor="fleur",
        )


        self.canvas.pack(
            fill="both",
            expand=True,
        )


        # ----------------------------------------------------
        # Rendering state
        # ----------------------------------------------------

        self._photo: (
            ImageTk.PhotoImage
            | None
        ) = None


        self._image_id: (
            int
            | None
        ) = None


        self._render_after_id = None

        self._render_generation = 0

        self._render_lock = (
            threading.Lock()
        )


        # ----------------------------------------------------
        # Drag state
        # ----------------------------------------------------

        self._drag_start_xy: (
            tuple[int, int]
            | None
        ) = None


        self._drag_start_center: (
            tuple[float, float]
            | None
        ) = None


        # ----------------------------------------------------
        # Bind
        # ----------------------------------------------------

        self.canvas.bind(
            "<Configure>",
            self._on_configure,
        )


        self.canvas.bind(
            "<ButtonPress-1>",
            self._on_drag_start,
        )


        self.canvas.bind(
            "<B1-Motion>",
            self._on_drag_move,
        )


        self.canvas.bind(
            "<ButtonRelease-1>",
            self._on_drag_end,
        )


        self.canvas.bind(
            "<MouseWheel>",
            self._on_mousewheel,
        )


        # Linux
        self.canvas.bind(
            "<Button-4>",
            self._on_mousewheel_linux,
        )

        self.canvas.bind(
            "<Button-5>",
            self._on_mousewheel_linux,
        )


        self.after(
            100,
            lambda:
                self.request_render(
                    delay=0
                ),
        )


    # ========================================================
    # Public state
    # ========================================================

    def set_position(
        self,
        lat: float,
        lon: float,
    ) -> None:

        self.center_x, self.center_y = (
            lonlat_to_world(
                lon,
                lat,
            )
        )


        self._normalize_center()


        self.request_render(
            delay=20
        )


        self._draw_overlays()


    def get_position(
        self,
    ) -> tuple[float, float]:

        lon, lat = (
            world_to_lonlat(
                self.center_x,
                self.center_y,
            )
        )

        return (
            lat,
            lon,
        )


    def set_marker(
        self,
        lat: float,
        lon: float,
    ) -> None:

        self.marker_latlon = (
            lat,
            lon,
        )

        self._draw_overlays()


    def get_zoom(
        self,
    ) -> float:

        return self.zoom


    def zoom_by(
        self,
        delta: float,
    ) -> None:

        w = max(
            1,
            self.canvas.winfo_width(),
        )

        h = max(
            1,
            self.canvas.winfo_height(),
        )


        self._set_zoom_around(
            self.zoom + delta,
            w / 2.0,
            h / 2.0,
        )


    def get_bbox(
        self,
    ) -> tuple[
        float,
        float,
        float,
        float,
    ]:

        w = max(
            1,
            self.canvas.winfo_width(),
        )


        h = max(
            1,
            self.canvas.winfo_height(),
        )


        world_px = (
            self.TILE_SIZE
            *
            (
                2.0
                ** self.zoom
            )
        )


        left = (
            self.center_x
            -
            (
                w / 2.0
            )
            / world_px
        )


        right = (
            self.center_x
            +
            (
                w / 2.0
            )
            / world_px
        )


        top = max(
            0.0,
            self.center_y
            -
            (
                h / 2.0
            )
            / world_px,
        )


        bottom = min(
            1.0,
            self.center_y
            +
            (
                h / 2.0
            )
            / world_px,
        )


        west, north = (
            world_to_lonlat(
                left,
                top,
            )
        )


        east, south = (
            world_to_lonlat(
                right,
                bottom,
            )
        )


        return (
            south,
            west,
            north,
            east,
        )


    # ========================================================
    # Mouse interaction
    # ========================================================

    def _on_drag_start(
        self,
        event,
    ) -> str:

        self._drag_start_xy = (
            event.x,
            event.y,
        )


        self._drag_start_center = (
            self.center_x,
            self.center_y,
        )


        return "break"


    def _on_drag_move(
        self,
        event,
    ) -> str:

        if (
            self._drag_start_xy
            is None
            or
            self._drag_start_center
            is None
        ):

            return "break"


        dx = (
            event.x
            -
            self._drag_start_xy[0]
        )


        dy = (
            event.y
            -
            self._drag_start_xy[1]
        )


        world_px = (
            self.TILE_SIZE
            *
            (
                2.0
                ** self.zoom
            )
        )


        self.center_x = (
            self._drag_start_center[0]
            -
            dx / world_px
        )


        self.center_y = (
            self._drag_start_center[1]
            -
            dy / world_px
        )


        self._normalize_center()


        # ----------------------------------------------------
        # Move already-rendered bitmap immediately.
        #
        # This makes dragging feel responsive without waiting
        # for a tile re-render.
        # ----------------------------------------------------

        if (
            self._image_id
            is not None
        ):

            w = (
                self.canvas.winfo_width()
            )

            h = (
                self.canvas.winfo_height()
            )


            self.canvas.coords(
                self._image_id,
                w / 2.0 + dx,
                h / 2.0 + dy,
            )


        self._draw_overlays()


        return "break"


    def _on_drag_end(
        self,
        _event,
    ) -> str:

        self._drag_start_xy = None

        self._drag_start_center = None


        if (
            self._image_id
            is not None
        ):

            self.canvas.coords(
                self._image_id,
                self.canvas.winfo_width()
                / 2.0,
                self.canvas.winfo_height()
                / 2.0,
            )


        self.request_render(
            delay=10
        )


        return "break"


    # ========================================================
    # Smooth wheel zoom
    # ========================================================

    def _on_mousewheel(
        self,
        event,
    ) -> str:

        # Windows normally returns +/-120 per notch.
        #
        # Trackpads can return smaller values, so fractional
        # deltas are intentionally preserved.

        steps = (
            event.delta
            / 120.0
        )


        if steps == 0:

            return "break"


        self._set_zoom_around(

            self.zoom
            +
            steps
            *
            self.ZOOM_STEP,

            event.x,
            event.y,

        )


        return "break"


    def _on_mousewheel_linux(
        self,
        event,
    ) -> str:

        direction = (
            1.0
            if event.num == 4
            else -1.0
        )


        self._set_zoom_around(

            self.zoom
            +
            direction
            *
            self.ZOOM_STEP,

            event.x,
            event.y,

        )


        return "break"


    def _set_zoom_around(
        self,
        new_zoom: float,
        px: float,
        py: float,
    ) -> None:

        new_zoom = max(

            self.MIN_ZOOM,

            min(
                self.MAX_ZOOM,
                float(
                    new_zoom
                ),
            ),

        )


        if (
            abs(
                new_zoom
                -
                self.zoom
            )
            <
            1e-9
        ):

            return


        w = max(
            1,
            self.canvas.winfo_width(),
        )


        h = max(
            1,
            self.canvas.winfo_height(),
        )


        old_world_px = (
            self.TILE_SIZE
            *
            (
                2.0
                ** self.zoom
            )
        )


        # ----------------------------------------------------
        # Geographic point currently under the cursor
        # ----------------------------------------------------

        pointer_world_x = (
            self.center_x
            +
            (
                px
                -
                w / 2.0
            )
            /
            old_world_px
        )


        pointer_world_y = (
            self.center_y
            +
            (
                py
                -
                h / 2.0
            )
            /
            old_world_px
        )


        new_world_px = (
            self.TILE_SIZE
            *
            (
                2.0
                ** new_zoom
            )
        )


        # ----------------------------------------------------
        # Keep that geographic point under the mouse.
        # ----------------------------------------------------

        self.center_x = (
            pointer_world_x
            -
            (
                px
                -
                w / 2.0
            )
            /
            new_world_px
        )


        self.center_y = (
            pointer_world_y
            -
            (
                py
                -
                h / 2.0
            )
            /
            new_world_px
        )


        self.zoom = (
            new_zoom
        )


        self._normalize_center()


        self._draw_overlays()


        self.request_render(
            delay=25
        )


    def _normalize_center(
        self,
    ) -> None:

        self.center_x %= (
            1.0
        )


        self.center_y = max(
            0.0,
            min(
                1.0,
                self.center_y,
            ),
        )


    # ========================================================
    # Rendering
    # ========================================================

    def _on_configure(
        self,
        _event=None,
    ) -> None:

        self._draw_overlays()

        self.request_render(
            delay=80
        )


    def request_render(
        self,
        delay: int = 50,
    ) -> None:

        if (
            self._render_after_id
            is not None
        ):

            try:

                self.after_cancel(
                    self._render_after_id
                )

            except Exception:

                pass


        self._render_after_id = (
            self.after(
                delay,
                self._start_render,
            )
        )


    def _start_render(
        self,
    ) -> None:

        self._render_after_id = None


        w = max(
            2,
            self.canvas.winfo_width(),
        )


        h = max(
            2,
            self.canvas.winfo_height(),
        )


        if (
            w < 20
            or
            h < 20
        ):

            return


        self._render_generation += (
            1
        )


        generation = (
            self._render_generation
        )


        snapshot = (
            self.center_x,
            self.center_y,
            self.zoom,
            w,
            h,
        )


        threading.Thread(

            target=
                self._render_worker,

            args=(
                generation,
                snapshot,
            ),

            daemon=True,

        ).start()


    def _render_worker(
        self,
        generation: int,
        snapshot: tuple[
            float,
            float,
            float,
            int,
            int,
        ],
    ) -> None:

        with self._render_lock:

            if (
                generation
                !=
                self._render_generation
            ):

                return


            try:

                image = (
                    self._build_map_image(
                        *snapshot
                    )
                )

            except Exception:

                return


        if (
            generation
            !=
            self._render_generation
        ):

            return


        try:

            self.after(

                0,

                lambda:
                    self._apply_render(
                        generation,
                        image,
                    ),

            )

        except Exception:

            pass


    # ========================================================
    # Fractional raster rendering
    # ========================================================

    def _build_map_image(
        self,
        center_x: float,
        center_y: float,
        zoom: float,
        width: int,
        height: int,
    ) -> Image.Image:

        # ----------------------------------------------------
        # Get actual OSM tiles from nearest integer zoom.
        #
        # The displayed result is then continuously scaled
        # according to the fractional zoom.
        # ----------------------------------------------------

        tile_zoom = int(
            round(
                zoom
            )
        )


        tile_zoom = max(
            0,
            min(
                19,
                tile_zoom,
            ),
        )


        scale = (
            2.0
            **
            (
                zoom
                -
                tile_zoom
            )
        )


        source_world_px = (
            self.TILE_SIZE
            *
            (
                2
                **
                tile_zoom
            )
        )


        center_px_x = (
            center_x
            *
            source_world_px
        )


        center_px_y = (
            center_y
            *
            source_world_px
        )


        source_w = (
            width
            /
            scale
        )


        source_h = (
            height
            /
            scale
        )


        left = (
            center_px_x
            -
            source_w / 2.0
        )


        top = (
            center_px_y
            -
            source_h / 2.0
        )


        right = (
            center_px_x
            +
            source_w / 2.0
        )


        bottom = (
            center_px_y
            +
            source_h / 2.0
        )


        tx0 = math.floor(
            left
            /
            self.TILE_SIZE
        )


        ty0 = math.floor(
            top
            /
            self.TILE_SIZE
        )


        tx1 = math.floor(
            (
                right
                -
                1e-6
            )
            /
            self.TILE_SIZE
        )


        ty1 = math.floor(
            (
                bottom
                -
                1e-6
            )
            /
            self.TILE_SIZE
        )


        cols = (
            tx1
            -
            tx0
            +
            1
        )


        rows = (
            ty1
            -
            ty0
            +
            1
        )


        mosaic = Image.new(

            "RGB",

            (
                cols
                *
                self.TILE_SIZE,

                rows
                *
                self.TILE_SIZE,
            ),

            "#e8e8e8",

        )


        n = (
            2
            **
            tile_zoom
        )


        for ty in range(
            ty0,
            ty1 + 1,
        ):

            for tx in range(
                tx0,
                tx1 + 1,
            ):

                if (
                    0
                    <=
                    ty
                    <
                    n
                ):

                    tile = (
                        self._load_preview_tile(

                            tile_zoom,

                            tx % n,

                            ty,

                        )
                    )

                else:

                    tile = Image.new(

                        "RGB",

                        (
                            self.TILE_SIZE,
                            self.TILE_SIZE,
                        ),

                        "#e8e8e8",

                    )


                mosaic.paste(

                    tile,

                    (
                        (
                            tx
                            -
                            tx0
                        )
                        *
                        self.TILE_SIZE,

                        (
                            ty
                            -
                            ty0
                        )
                        *
                        self.TILE_SIZE,
                    ),

                )


        offset_x = (
            left
            -
            tx0
            *
            self.TILE_SIZE
        )


        offset_y = (
            top
            -
            ty0
            *
            self.TILE_SIZE
        )


        inv_scale = (
            1.0
            /
            scale
        )


        affine = (

            inv_scale,
            0.0,
            offset_x,

            0.0,
            inv_scale,
            offset_y,

        )


        transform_enum = getattr(
            Image,
            "Transform",
            None,
        )


        affine_mode = (
            transform_enum.AFFINE
            if transform_enum
            is not None
            else Image.AFFINE
        )


        resampling_enum = getattr(
            Image,
            "Resampling",
            None,
        )


        resample = (
            resampling_enum.BILINEAR
            if resampling_enum
            is not None
            else Image.BILINEAR
        )


        return mosaic.transform(

            (
                width,
                height,
            ),

            affine_mode,

            affine,

            resample=resample,

        )


    # ========================================================
    # Preview tile cache
    # ========================================================

    def _load_preview_tile(
        self,
        z: int,
        x: int,
        y: int,
    ) -> Image.Image:

        path = (

            self.cache_dir

            /
            str(z)

            /
            str(x)

            /
            f"{y}.png"

        )


        if (
            path.exists()
        ):

            try:

                with Image.open(
                    path
                ) as image:

                    return (
                        image.convert(
                            "RGB"
                        )
                    )

            except Exception:

                try:

                    path.unlink()

                except Exception:

                    pass


        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )


        url = (

            PREVIEW_TILE_URL

            .replace(
                "{z}",
                str(z),
            )

            .replace(
                "{x}",
                str(x),
            )

            .replace(
                "{y}",
                str(y),
            )

        )


        response = requests.get(

            url,

            timeout=20,

            headers={
                "User-Agent":
                    USER_AGENT
            },

        )


        response.raise_for_status()


        path.write_bytes(
            response.content
        )


        with Image.open(
            path
        ) as image:

            return (
                image.convert(
                    "RGB"
                )
            )


    # ========================================================
    # Apply rendered map
    # ========================================================

    def _apply_render(
        self,
        generation: int,
        image: Image.Image,
    ) -> None:

        if (
            generation
            !=
            self._render_generation
            or
            not self.winfo_exists()
        ):

            return


        self._photo = (
            ImageTk.PhotoImage(
                image
            )
        )


        w = (
            self.canvas.winfo_width()
        )


        h = (
            self.canvas.winfo_height()
        )


        if (
            self._image_id
            is None
        ):

            self._image_id = (
                self.canvas.create_image(

                    w / 2.0,
                    h / 2.0,

                    image=
                        self._photo,

                    anchor=
                        "center",

                    tags=(
                        "map-image",
                    ),

                )
            )

        else:

            self.canvas.itemconfigure(

                self._image_id,

                image=
                    self._photo,

            )


            self.canvas.coords(

                self._image_id,

                w / 2.0,
                h / 2.0,

            )


        self.canvas.tag_lower(
            "map-image"
        )


        self._draw_overlays()


    # ========================================================
    # Marker / attribution
    # ========================================================

    def _draw_overlays(
        self,
    ) -> None:

        if not hasattr(
            self,
            "canvas",
        ):

            return


        self.canvas.delete(
            "map-overlay"
        )


        w = max(
            1,
            self.canvas.winfo_width(),
        )


        h = max(
            1,
            self.canvas.winfo_height(),
        )


        # ----------------------------------------------------
        # Target marker
        # ----------------------------------------------------

        if (
            self.marker_latlon
            is not None
        ):

            lat, lon = (
                self.marker_latlon
            )


            marker_x, marker_y = (
                self._latlon_to_canvas(
                    lat,
                    lon,
                )
            )


            if (
                -50
                <=
                marker_x
                <=
                w + 50
                and
                -50
                <=
                marker_y
                <=
                h + 50
            ):

                r = 6


                self.canvas.create_oval(

                    marker_x - r,
                    marker_y - r,

                    marker_x + r,
                    marker_y + r,

                    fill="#dc2626",

                    outline="#ffffff",

                    width=2,

                    tags=(
                        "map-overlay",
                    ),

                )


                self.canvas.create_text(

                    marker_x,

                    marker_y - 15,

                    text="Target",

                    fill="#222222",

                    font=(
                        "Arial",
                        9,
                        "bold",
                    ),

                    tags=(
                        "map-overlay",
                    ),

                )


        # ----------------------------------------------------
        # Attribution for preview
        # ----------------------------------------------------

        self.canvas.create_text(

            w - 6,
            h - 5,

            anchor="se",

            text=(
                "© OpenStreetMap contributors"
            ),

            fill="#555555",

            font=(
                "Arial",
                8,
            ),

            tags=(
                "map-overlay",
            ),

        )


    def _latlon_to_canvas(
        self,
        lat: float,
        lon: float,
    ) -> tuple[
        float,
        float,
    ]:

        x, y = (
            lonlat_to_world(
                lon,
                lat,
            )
        )


        dx = (
            x
            -
            self.center_x
        )


        # Horizontal map wrap.
        if dx > 0.5:

            dx -= 1.0

        elif dx < -0.5:

            dx += 1.0


        world_px = (
            self.TILE_SIZE
            *
            (
                2.0
                **
                self.zoom
            )
        )


        sx = (
            self.canvas.winfo_width()
            / 2.0
            +
            dx
            *
            world_px
        )


        sy = (
            self.canvas.winfo_height()
            / 2.0
            +
            (
                y
                -
                self.center_y
            )
            *
            world_px
        )


        return (
            sx,
            sy,
        )


# ============================================================
# OpenFreeMap vector tiles -> pure SVG
# ============================================================

class VectorSvgExporter:

    def __init__(
        self,
        cache_dir: Path,
        progress:
            Callable[[str], None]
            | None = None,
    ) -> None:

        self.cache_dir = (
            cache_dir
        )


        self.progress = (
            progress
            or
            (
                lambda _text:
                    None
            )
        )


        self.green_paths: (
            list[str]
        ) = []


        self.water_paths: (
            list[str]
        ) = []


        self.waterways: list[
            tuple[
                float,
                str,
            ]
        ] = []


        self.roads: list[
            tuple[
                float,
                str,
                str,
            ]
        ] = []


    # ========================================================
    # Export
    # ========================================================

    def export(
        self,
        south: float,
        west: float,
        north: float,
        east: float,
        requested_zoom: int,
        output_path: Path,
    ) -> Path:

        if (
            south >= north
            or
            west >= east
        ):

            raise ValueError(
                "Invalid map bounds."
            )


        self.south = south
        self.west = west

        self.north = north
        self.east = east


        self.green_paths.clear()

        self.water_paths.clear()

        self.waterways.clear()

        self.roads.clear()


        (
            template,
            min_zoom,
            max_zoom,
        ) = (
            self._get_tilejson()
        )


        self.zoom = max(

            min_zoom,

            min(
                max_zoom,
                requested_zoom,
            ),

        )


        self._prepare_projection()


        (
            x0,
            y0,
            x1,
            y1,
        ) = (
            self._tile_range()
        )


        total = (

            (
                x1
                -
                x0
                +
                1
            )

            *

            (
                y1
                -
                y0
                +
                1
            )

        )


        done = 0


        for tile_y in range(
            y0,
            y1 + 1,
        ):

            for tile_x in range(
                x0,
                x1 + 1,
            ):

                self.progress(

                    f"Vector tiles "
                    f"{done}/{total} "
                    f"· z{self.zoom}"

                )


                raw = (
                    self._download_tile(

                        template,

                        self.zoom,

                        tile_x,
                        tile_y,

                    )
                )


                self._process_tile(

                    raw,

                    tile_x,
                    tile_y,

                )


                done += 1


        self.progress(

            f"Vector tiles "
            f"{total}/{total} "
            f"· writing SVG…"

        )


        output_path.parent.mkdir(

            parents=True,

            exist_ok=True,

        )


        self._write_svg(
            output_path
        )


        return (
            output_path
        )


    # ========================================================
    # TileJSON
    # ========================================================

    def _get_tilejson(
        self,
    ) -> tuple[
        str,
        int,
        int,
    ]:

        self.progress(
            "Reading OpenFreeMap…"
        )


        response = requests.get(

            OPENFREEMAP_TILEJSON_URL,

            timeout=60,

            headers={
                "User-Agent":
                    USER_AGENT
            },

        )


        response.raise_for_status()


        data = (
            response.json()
        )


        tiles = (
            data.get(
                "tiles",
                [],
            )
        )


        if not tiles:

            raise RuntimeError(
                "OpenFreeMap TileJSON contains no tile URL."
            )


        return (

            str(
                tiles[0]
            ),

            int(
                data.get(
                    "minzoom",
                    0,
                )
            ),

            int(
                data.get(
                    "maxzoom",
                    14,
                )
            ),

        )


    # ========================================================
    # Tile cache
    # ========================================================

    def _download_tile(
        self,
        template: str,
        z: int,
        x: int,
        y: int,
    ) -> bytes:

        path = (

            self.cache_dir

            /
            str(z)

            /
            str(x)

            /
            f"{y}.pbf"

        )


        if (
            path.exists()
        ):

            return (
                path.read_bytes()
            )


        path.parent.mkdir(

            parents=True,

            exist_ok=True,

        )


        url = (

            template

            .replace(
                "{z}",
                str(z),
            )

            .replace(
                "{x}",
                str(x),
            )

            .replace(
                "{y}",
                str(y),
            )

        )


        response = requests.get(

            url,

            timeout=60,

            headers={
                "User-Agent":
                    USER_AGENT
            },

        )


        response.raise_for_status()


        path.write_bytes(
            response.content
        )


        return (
            response.content
        )


    # ========================================================
    # SVG projection
    # ========================================================

    def _prepare_projection(
        self,
    ) -> None:

        (
            self.left,
            self.top,
        ) = (
            lonlat_to_world(
                self.west,
                self.north,
            )
        )


        (
            self.right,
            self.bottom,
        ) = (
            lonlat_to_world(
                self.east,
                self.south,
            )
        )


        self.world_w = (
            self.right
            -
            self.left
        )


        self.world_h = (
            self.bottom
            -
            self.top
        )


        self.draw_w = float(
            SVG_WIDTH
        )


        self.draw_h = (
            self.draw_w
            *
            self.world_h
            /
            self.world_w
        )


        self.svg_h = int(
            round(
                self.draw_h
            )
        )


    # ========================================================
    # Tile range
    # ========================================================

    def _tile_float(
        self,
        lon: float,
        lat: float,
    ) -> tuple[
        float,
        float,
    ]:

        x, y = (
            lonlat_to_world(
                lon,
                lat,
            )
        )


        n = (
            2
            **
            self.zoom
        )


        return (
            x * n,
            y * n,
        )


    def _tile_range(
        self,
    ) -> tuple[
        int,
        int,
        int,
        int,
    ]:

        x0, y0 = (
            self._tile_float(
                self.west,
                self.north,
            )
        )


        x1, y1 = (
            self._tile_float(
                self.east,
                self.south,
            )
        )


        return (

            math.floor(x0),
            math.floor(y0),

            math.floor(x1),
            math.floor(y1),

        )


    # ========================================================
    # Tile local -> SVG
    # ========================================================

    def _tile_point_to_svg(
        self,
        tile_x: int,
        tile_y: int,
        extent: int,
        px: float,
        py: float,
    ) -> tuple[
        float,
        float,
    ]:

        n = (
            2
            **
            self.zoom
        )


        world_x = (
            tile_x
            +
            px / extent
        ) / n


        world_y = (
            tile_y
            +
            py / extent
        ) / n


        x = (
            (
                world_x
                -
                self.left
            )
            /
            self.world_w
            *
            self.draw_w
        )


        y = (
            (
                world_y
                -
                self.top
            )
            /
            self.world_h
            *
            self.draw_h
        )


        return (
            x,
            y,
        )


    # ========================================================
    # Geometry -> SVG
    # ========================================================

    def _line_path(
        self,
        coords,
        tile_x: int,
        tile_y: int,
        extent: int,
        close: bool = False,
    ) -> str:

        parts: list[str] = []


        for index, point in enumerate(
            coords
        ):

            x, y = (
                self._tile_point_to_svg(

                    tile_x,
                    tile_y,
                    extent,

                    point[0],
                    point[1],

                )
            )


            command = (
                "M"
                if index == 0
                else "L"
            )


            parts.append(

                f"{command} "
                f"{x:.3f},{y:.3f}"

            )


        if (
            close
            and
            parts
        ):

            parts.append(
                "Z"
            )


        return " ".join(
            parts
        )


    def _geometry_paths(
        self,
        geometry: dict,
        tile_x: int,
        tile_y: int,
        extent: int,
    ) -> list[str]:

        kind = (
            geometry.get(
                "type"
            )
        )


        coords = (
            geometry.get(
                "coordinates"
            )
        )


        if not coords:

            return []


        if (
            kind
            ==
            "LineString"
        ):

            return [

                self._line_path(

                    coords,

                    tile_x,
                    tile_y,
                    extent,

                )

            ]


        if (
            kind
            ==
            "MultiLineString"
        ):

            return [

                self._line_path(

                    line,

                    tile_x,
                    tile_y,
                    extent,

                )

                for line
                in coords

            ]


        if (
            kind
            ==
            "Polygon"
        ):

            path = " ".join(

                self._line_path(

                    ring,

                    tile_x,
                    tile_y,
                    extent,

                    close=True,

                )

                for ring
                in coords

            )


            return (
                [path]
                if path
                else []
            )


        if (
            kind
            ==
            "MultiPolygon"
        ):

            return [

                " ".join(

                    self._line_path(

                        ring,

                        tile_x,
                        tile_y,
                        extent,

                        close=True,

                    )

                    for ring
                    in polygon

                )

                for polygon
                in coords

            ]


        return []


    @staticmethod
    def _feature_class(
        feature: dict,
    ) -> str | None:

        return (

            feature

            .get(
                "properties",
                {},
            )

            .get(
                "class"
            )

        )


    @staticmethod
    def _is_polygon(
        feature: dict,
    ) -> bool:

        return (

            feature

            .get(
                "geometry",
                {},
            )

            .get(
                "type"
            )

            in {

                "Polygon",
                "MultiPolygon",

            }

        )


    # ========================================================
    # Process vector tile
    # ========================================================

    def _process_tile(
        self,
        raw: bytes,
        tile_x: int,
        tile_y: int,
    ) -> None:

        if not raw:

            return


        decoded = (
            mapbox_vector_tile.decode(

                raw,

                default_options={
                    "y_coord_down":
                        True
                },

            )
        )


        # ====================================================
        # Green landcover
        # ====================================================

        layer = (
            decoded.get(
                "landcover"
            )
        )


        if layer:

            extent = (
                layer.get(
                    "extent",
                    4096,
                )
            )


            for feature in (
                layer.get(
                    "features",
                    [],
                )
            ):

                if (
                    self._feature_class(
                        feature
                    )
                    not in
                    GREEN_LANDCOVER_CLASSES
                ):

                    continue


                if not (
                    self._is_polygon(
                        feature
                    )
                ):

                    continue


                self.green_paths += (
                    self._geometry_paths(

                        feature[
                            "geometry"
                        ],

                        tile_x,
                        tile_y,
                        extent,

                    )
                )


        # ====================================================
        # Parks
        # ====================================================

        layer = (
            decoded.get(
                "park"
            )
        )


        if layer:

            extent = (
                layer.get(
                    "extent",
                    4096,
                )
            )


            for feature in (
                layer.get(
                    "features",
                    [],
                )
            ):

                if not (
                    self._is_polygon(
                        feature
                    )
                ):

                    continue


                self.green_paths += (
                    self._geometry_paths(

                        feature[
                            "geometry"
                        ],

                        tile_x,
                        tile_y,
                        extent,

                    )
                )


        # ====================================================
        # Water
        # ====================================================

        layer = (
            decoded.get(
                "water"
            )
        )


        if layer:

            extent = (
                layer.get(
                    "extent",
                    4096,
                )
            )


            for feature in (
                layer.get(
                    "features",
                    [],
                )
            ):

                if not (
                    self._is_polygon(
                        feature
                    )
                ):

                    continue


                self.water_paths += (
                    self._geometry_paths(

                        feature[
                            "geometry"
                        ],

                        tile_x,
                        tile_y,
                        extent,

                    )
                )


        # ====================================================
        # Waterways
        # ====================================================

        if SHOW_WATERWAYS:

            layer = (
                decoded.get(
                    "waterway"
                )
            )


            if layer:

                extent = (
                    layer.get(
                        "extent",
                        4096,
                    )
                )


                widths = {

                    "river":
                        1.8,

                    "canal":
                        1.3,

                    "stream":
                        0.8,

                }


                for feature in (
                    layer.get(
                        "features",
                        [],
                    )
                ):

                    feature_class = (
                        self._feature_class(
                            feature
                        )
                    )


                    if (
                        feature_class
                        not in
                        widths
                    ):

                        continue


                    for path in (
                        self._geometry_paths(

                            feature[
                                "geometry"
                            ],

                            tile_x,
                            tile_y,
                            extent,

                        )
                    ):

                        self.waterways.append(
                            (
                                widths[
                                    feature_class
                                ],
                                path,
                            )
                        )


        # ====================================================
        # Roads
        # ====================================================

        layer = (
            decoded.get(
                "transportation"
            )
        )


        if layer:

            extent = (
                layer.get(
                    "extent",
                    4096,
                )
            )


            for feature in (
                layer.get(
                    "features",
                    [],
                )
            ):

                feature_class = (
                    self._feature_class(
                        feature
                    )
                )


                if (
                    feature_class
                    not in
                    ROAD_WIDTH
                ):

                    continue


                if (
                    feature_class
                    ==
                    "minor"
                    and
                    not
                    SHOW_MINOR_ROADS
                ):

                    continue


                if (
                    feature_class
                    ==
                    "service"
                    and
                    not
                    SHOW_SERVICE_ROADS
                ):

                    continue


                if (
                    feature_class
                    in {
                        "track",
                        "path",
                    }
                    and
                    not
                    SHOW_PATHS
                ):

                    continue


                geometry_type = (

                    feature

                    .get(
                        "geometry",
                        {},
                    )

                    .get(
                        "type",
                        "",
                    )

                )


                for path in (
                    self._geometry_paths(

                        feature[
                            "geometry"
                        ],

                        tile_x,
                        tile_y,
                        extent,

                    )
                ):

                    self.roads.append(

                        (
                            ROAD_WIDTH[
                                feature_class
                            ],

                            geometry_type,

                            path,
                        )

                    )


    # ========================================================
    # Write SVG
    # ========================================================

    def _write_svg(
        self,
        path: Path,
    ) -> None:

        svg: list[str] = []


        svg.append(
            '<?xml version="1.0" encoding="UTF-8"?>'
        )


        svg.append(
            f'''
<svg
    xmlns="http://www.w3.org/2000/svg"
    xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape"
    width="{SVG_WIDTH}"
    height="{self.svg_h}"
    viewBox="0 0 {SVG_WIDTH} {self.svg_h}">
'''
        )


        svg.append(
            '''
<desc>
Pure vector map.
Map data © OpenStreetMap contributors.
OpenMapTiles / OpenFreeMap.
</desc>
'''
        )


        # ====================================================
        # Clip
        # ====================================================

        svg.append(
            f'''
<defs>

    <clipPath id="mapClip">

        <rect
            x="0"
            y="0"
            width="{self.draw_w}"
            height="{self.draw_h}"
        />

    </clipPath>

</defs>
'''
        )


        # ====================================================
        # Land
        # ====================================================

        svg.append(
            f'''
<g
    inkscape:groupmode="layer"
    inkscape:label="01 Land"
    id="land">

    <rect
        x="0"
        y="0"
        width="{self.draw_w}"
        height="{self.draw_h}"
        fill="{LAND_COLOR}"
    />

</g>
'''
        )


        # ====================================================
        # Green
        # ====================================================

        svg.append(
            '''
<g
    inkscape:groupmode="layer"
    inkscape:label="02 Green areas"
    id="green-areas"
    clip-path="url(#mapClip)">
'''
        )


        for path_data in (
            self.green_paths
        ):

            svg.append(
                f'''
    <path
        d="{path_data}"
        fill="{GREEN_COLOR}"
        stroke="none"
        fill-rule="evenodd"
    />
'''
            )


        svg.append(
            "</g>"
        )


        # ====================================================
        # Water
        # ====================================================

        svg.append(
            '''
<g
    inkscape:groupmode="layer"
    inkscape:label="03 Water"
    id="water"
    clip-path="url(#mapClip)">
'''
        )


        for path_data in (
            self.water_paths
        ):

            svg.append(
                f'''
    <path
        d="{path_data}"
        fill="{WATER_COLOR}"
        stroke="none"
        fill-rule="evenodd"
    />
'''
            )


        for (
            width,
            path_data,
        ) in (
            self.waterways
        ):

            svg.append(
                f'''
    <path
        d="{path_data}"
        fill="none"
        stroke="{WATER_COLOR}"
        stroke-width="{width:.2f}"
        stroke-linecap="round"
        stroke-linejoin="round"
    />
'''
            )


        svg.append(
            "</g>"
        )


        # ====================================================
        # Roads
        # ====================================================

        svg.append(
            '''
<g
    inkscape:groupmode="layer"
    inkscape:label="04 Roads"
    id="roads"
    clip-path="url(#mapClip)">
'''
        )


        for (
            width,
            geometry_type,
            path_data,
        ) in sorted(

            self.roads,

            key=lambda item:
                item[0],

        ):

            if (
                geometry_type
                in {
                    "Polygon",
                    "MultiPolygon",
                }
            ):

                svg.append(
                    f'''
    <path
        d="{path_data}"
        fill="{ROAD_COLOR}"
        stroke="none"
        fill-rule="evenodd"
    />
'''
                )

            else:

                svg.append(
                    f'''
    <path
        d="{path_data}"
        fill="none"
        stroke="{ROAD_COLOR}"
        stroke-width="{width:.2f}"
        stroke-linecap="round"
        stroke-linejoin="round"
    />
'''
                )


        svg.append(
            "</g>"
        )


        # ====================================================
        # Attribution
        # ====================================================

        if SHOW_ATTRIBUTION:

            svg.append(
                f'''
<g
    inkscape:groupmode="layer"
    inkscape:label="05 Attribution"
    id="attribution">

    <text
        x="{SVG_WIDTH - 10}"
        y="{self.svg_h - 8}"
        text-anchor="end"
        font-family="Arial, sans-serif"
        font-size="10"
        fill="{ROAD_COLOR}">
        © OpenStreetMap contributors · OpenMapTiles · OpenFreeMap
    </text>

</g>
'''
            )


        svg.append(
            "</svg>"
        )


        path.write_text(

            "\n".join(
                svg
            ),

            encoding="utf-8",

        )


# ============================================================
# Cherry Utility tab
# ============================================================

class Map2SvgTab(
    BaseTabPlugin
):

    TAB_TITLE = TAB_TITLE

    ORDER = TAB_ORDER


    def __init__(
        self,
        app,
        tabview,
    ) -> None:

        super().__init__(
            app,
            tabview,
        )


        self.ratio_name = (
            "4:3"
        )


        self.ratio_buttons: dict[
            str,
            ctk.CTkButton,
        ] = {}


        self.last_svg: (
            Path
            | None
        ) = None


        self.export_running = (
            False
        )


        self._layout_job = None


    # ========================================================
    # UI
    # ========================================================

    def create_ui(
        self,
    ) -> None:

        tab = (
            self.tab
        )


        tab.grid_columnconfigure(
            0,
            weight=1,
        )


        tab.grid_rowconfigure(
            3,
            weight=1,
        )


        # ====================================================
        # Header
        # ====================================================

        header = ctk.CTkFrame(
            tab,
            fg_color="transparent",
        )


        header.grid(

            row=0,
            column=0,

            sticky="ew",

            padx=22,
            pady=(16, 8),

        )


        ctk.CTkLabel(

            header,

            text="map2svg",

            anchor="w",

            font=ctk.CTkFont(
                size=23,
                weight="bold",
            ),

        ).pack(
            anchor="w"
        )


        ctk.CTkLabel(

            header,

            text=(
                "Paste a Google Maps coordinate, "
                "fine-tune the area interactively, "
                "then export the visible area "
                "as a pure-vector SVG."
            ),

            anchor="w",

            text_color=(
                "gray40",
                "gray68",
            ),

            font=ctk.CTkFont(
                size=12,
            ),

        ).pack(

            anchor="w",

            pady=(2, 0),

        )


        # ====================================================
        # Coordinate
        # ====================================================

        coord = ctk.CTkFrame(
            tab,
            corner_radius=12,
        )


        coord.grid(

            row=1,
            column=0,

            sticky="ew",

            padx=14,
            pady=(0, 8),

        )


        coord.grid_columnconfigure(
            1,
            weight=1,
        )


        ctk.CTkLabel(

            coord,

            text="Coordinate",

            font=ctk.CTkFont(
                size=13,
                weight="bold",
            ),

        ).grid(

            row=0,
            column=0,

            padx=(16, 10),
            pady=12,

        )


        self.coord_entry = (
            ctk.CTkEntry(

                coord,

                height=40,

                font=ctk.CTkFont(
                    family="Consolas",
                    size=13,
                ),

            )
        )


        self.coord_entry.grid(

            row=0,
            column=1,

            sticky="ew",

            padx=(0, 10),
            pady=12,

        )


        self.coord_entry.insert(
            0,
            DEFAULT_COORDINATE,
        )


        self.coord_entry.bind(
            "<Return>",
            self._go,
        )


        ctk.CTkButton(

            coord,

            text="Go",

            width=86,
            height=40,

            command=self._go,

        ).grid(

            row=0,
            column=2,

            padx=(0, 16),
            pady=12,

        )


        # ====================================================
        # Aspect / fine zoom
        # ====================================================

        ratio = ctk.CTkFrame(
            tab,
            corner_radius=12,
        )


        ratio.grid(

            row=2,
            column=0,

            sticky="ew",

            padx=14,
            pady=(0, 8),

        )


        ratio.grid_columnconfigure(
            1,
            weight=1,
        )


        ctk.CTkLabel(

            ratio,

            text="Aspect ratio",

            font=ctk.CTkFont(
                size=13,
                weight="bold",
            ),

        ).grid(

            row=0,
            column=0,

            padx=(16, 12),
            pady=12,

        )


        ratio_buttons = (
            ctk.CTkFrame(

                ratio,

                fg_color=
                    "transparent",

            )
        )


        ratio_buttons.grid(

            row=0,
            column=1,

            sticky="w",

            pady=8,

        )


        for (
            index,
            name,
        ) in enumerate(
            ASPECT_RATIOS
        ):

            button = (
                ctk.CTkButton(

                    ratio_buttons,

                    text=name,

                    width=68,
                    height=34,

                    border_width=1,

                    command=(
                        lambda n=name:
                            self._select_ratio(
                                n
                            )
                    ),

                )
            )


            button.grid(

                row=0,
                column=index,

                padx=(
                    0
                    if index == 0
                    else 5,
                    0,
                ),

            )


            self.ratio_buttons[
                name
            ] = (
                button
            )


        # ====================================================
        # Fine zoom buttons
        # ====================================================

        ctk.CTkButton(

            ratio,

            text="−",

            width=34,
            height=34,

            command=lambda:
                self.preview.zoom_by(
                    -
                    SmoothMapPreview
                    .ZOOM_STEP
                ),

        ).grid(

            row=0,
            column=2,

            padx=(8, 3),

        )


        ctk.CTkButton(

            ratio,

            text="+",

            width=34,
            height=34,

            command=lambda:
                self.preview.zoom_by(
                    SmoothMapPreview
                    .ZOOM_STEP
                ),

        ).grid(

            row=0,
            column=3,

            padx=(0, 8),

        )


        self.view_info = (
            ctk.CTkLabel(

                ratio,

                text="",

                text_color=(
                    "gray42",
                    "gray66",
                ),

                font=ctk.CTkFont(
                    size=11,
                ),

            )
        )


        self.view_info.grid(

            row=0,
            column=4,

            padx=(0, 16),

            sticky="e",

        )


        # ====================================================
        # Map stage
        # ====================================================

        self.stage = (
            ctk.CTkFrame(

                tab,

                corner_radius=12,

                fg_color=(
                    "gray90",
                    "gray17",
                ),

            )
        )


        self.stage.grid(

            row=3,
            column=0,

            sticky="nsew",

            padx=14,
            pady=(0, 8),

        )


        self.stage.bind(

            "<Configure>",

            self._stage_resize,

        )


        # ----------------------------------------------------
        # Actual aspect-ratio frame
        # ----------------------------------------------------

        self.map_frame = (
            ctk.CTkFrame(

                self.stage,

                width=800,
                height=600,

                corner_radius=4,

                fg_color="black",

            )
        )


        self.map_frame.pack_propagate(
            False
        )


        # ----------------------------------------------------
        # Initial map
        # ----------------------------------------------------

        lat, lon = (
            parse_google_coordinate(
                DEFAULT_COORDINATE
            )
        )


        self.preview = (
            SmoothMapPreview(

                self.map_frame,

                cache_dir=
                    PREVIEW_CACHE_DIR,

                center_lat=
                    lat,

                center_lon=
                    lon,

                zoom=
                    DEFAULT_ZOOM,

            )
        )


        self.preview.pack(

            fill="both",

            expand=True,

            padx=1,
            pady=1,

        )


        self.preview.set_marker(
            lat,
            lon,
        )


        # ====================================================
        # Footer
        # ====================================================

        footer = ctk.CTkFrame(
            tab,
            corner_radius=12,
        )


        footer.grid(

            row=4,
            column=0,

            sticky="ew",

            padx=14,
            pady=(0, 14),

        )


        footer.grid_columnconfigure(
            0,
            weight=1,
        )


        self.status = (
            ctk.CTkLabel(

                footer,

                text="Ready",

                anchor="w",

                text_color=(
                    "gray38",
                    "gray70",
                ),

                font=ctk.CTkFont(
                    size=12,
                ),

            )
        )


        self.status.grid(

            row=0,
            column=0,

            sticky="ew",

            padx=16,
            pady=14,

        )


        self.dl_button = (
            ctk.CTkButton(

                footer,

                text="DL map",

                width=120,
                height=38,

                command=
                    self._download,

            )
        )


        self.dl_button.grid(

            row=0,
            column=1,

            padx=(8, 8),
            pady=10,

        )


        self.open_button = (
            ctk.CTkButton(

                footer,

                text="Open",

                width=100,
                height=38,

                state="disabled",

                command=
                    self._open,

            )
        )


        self.open_button.grid(

            row=0,
            column=2,

            padx=(0, 16),
            pady=10,

        )


        self._refresh_ratio_buttons()


        self.app.after(
            120,
            self._layout_map,
        )


        self._update_view_info()


    # ========================================================
    # Coordinate
    # ========================================================

    def _go(
        self,
        _event=None,
    ) -> None:

        try:

            lat, lon = (
                parse_google_coordinate(
                    self.coord_entry.get()
                )
            )

        except ValueError as error:

            messagebox.showerror(
                "Invalid coordinate",
                str(error),
            )

            return


        self.preview.set_position(
            lat,
            lon,
        )


        self.preview.set_marker(
            lat,
            lon,
        )


        self.status.configure(

            text=(
                f"Centered on "
                f"{lat:.6f}, "
                f"{lon:.6f}"
            )

        )


    # ========================================================
    # Aspect ratio
    # ========================================================

    def _select_ratio(
        self,
        name: str,
    ) -> None:

        self.ratio_name = (
            name
        )


        self._refresh_ratio_buttons()


        self._layout_map()


    def _refresh_ratio_buttons(
        self,
    ) -> None:

        for (
            name,
            button,
        ) in (
            self.ratio_buttons.items()
        ):

            if (
                name
                ==
                self.ratio_name
            ):

                button.configure(

                    fg_color=(
                        "#dbeafe",
                        "#1e3a5f",
                    ),

                    border_color=(
                        "#3b82f6",
                        "#60a5fa",
                    ),

                    text_color=(
                        "#153e75",
                        "#dbeafe",
                    ),

                )

            else:

                button.configure(

                    fg_color=
                        "transparent",

                    border_color=(
                        "gray68",
                        "gray38",
                    ),

                    text_color=(
                        "gray20",
                        "gray88",
                    ),

                )


    # ========================================================
    # Resize map
    # ========================================================

    def _stage_resize(
        self,
        _event=None,
    ) -> None:

        if (
            self._layout_job
            is not None
        ):

            try:

                self.app.after_cancel(
                    self._layout_job
                )

            except Exception:

                pass


        self._layout_job = (
            self.app.after(
                40,
                self._layout_map,
            )
        )


    def _layout_map(
        self,
    ) -> None:

        self._layout_job = None


        available_width = max(

            100,

            self.stage.winfo_width()
            -
            24,

        )


        available_height = max(

            100,

            self.stage.winfo_height()
            -
            24,

        )


        (
            ratio_width,
            ratio_height,
        ) = (
            ASPECT_RATIOS[
                self.ratio_name
            ]
        )


        target_ratio = (
            ratio_width
            /
            ratio_height
        )


        if (
            available_width
            /
            available_height
            >=
            target_ratio
        ):

            height = (
                available_height
            )


            width = int(
                round(
                    height
                    *
                    target_ratio
                )
            )

        else:

            width = (
                available_width
            )


            height = int(
                round(
                    width
                    /
                    target_ratio
                )
            )


        width = max(
            100,
            width,
        )


        height = max(
            100,
            height,
        )


        # CTk requires size change through configure(),
        # not place(width=..., height=...).

        self.map_frame.configure(

            width=width,

            height=height,

        )


        self.map_frame.place(

            relx=0.5,

            rely=0.5,

            anchor="center",

        )


        self.map_frame.update_idletasks()


        self.preview.request_render(
            delay=60
        )


    # ========================================================
    # View information
    # ========================================================

    def _update_view_info(
        self,
    ) -> None:

        try:

            lat, lon = (
                self.preview.get_position()
            )


            zoom = (
                self.preview.get_zoom()
            )


            self.view_info.configure(

                text=(
                    f"Center "
                    f"{lat:.5f}, "
                    f"{lon:.5f}   "
                    f"Zoom "
                    f"{zoom:.2f}"
                )

            )

        except Exception:

            pass


        try:

            self.app.after(

                250,

                self._update_view_info,

            )

        except Exception:

            pass


    # ========================================================
    # DL map
    # ========================================================

    def _download(
        self,
    ) -> None:

        if (
            self.export_running
        ):

            return


        try:

            (
                south,
                west,
                north,
                east,
            ) = (
                self.preview.get_bbox()
            )


            vector_zoom = int(
                round(
                    self.preview
                    .get_zoom()
                )
            )

        except Exception as error:

            messagebox.showerror(
                "Map error",
                str(error),
            )

            return


        OUTPUT_DIR.mkdir(

            parents=True,

            exist_ok=True,

        )


        timestamp = (

            datetime.now()

            .strftime(
                "%Y%m%d_%H%M%S_%f"
            )[:-3]

        )


        ratio_tag = (

            self.ratio_name

            .replace(
                ":",
                "x",
            )

        )


        output_path = (

            OUTPUT_DIR

            /

            (
                f"map_"
                f"{timestamp}_"
                f"{ratio_tag}.svg"
            )

        )


        self.export_running = (
            True
        )


        self.last_svg = (
            None
        )


        self.dl_button.configure(

            state="disabled",

            text="Downloading…",

        )


        self.open_button.configure(
            state="disabled"
        )


        self.status.configure(
            text="Preparing SVG…"
        )


        threading.Thread(

            target=
                self._export_worker,

            args=(

                south,
                west,
                north,
                east,

                vector_zoom,

                output_path,

            ),

            daemon=True,

        ).start()


    # ========================================================
    # Background export
    # ========================================================

    def _export_worker(
        self,
        south: float,
        west: float,
        north: float,
        east: float,
        zoom: int,
        output_path: Path,
    ) -> None:

        try:

            exporter = (
                VectorSvgExporter(

                    VECTOR_CACHE_DIR,

                    self._thread_status,

                )
            )


            exporter.export(

                south,
                west,
                north,
                east,

                zoom,

                output_path,

            )

        except Exception as error:

            self.app.after(

                0,

                lambda err=error:
                    self._export_failed(
                        err
                    ),

            )

            return


        self.app.after(

            0,

            lambda path=output_path:
                self._export_finished(
                    path
                ),

        )


    def _thread_status(
        self,
        text: str,
    ) -> None:

        try:

            self.app.after(

                0,

                lambda t=text:
                    self.status.configure(
                        text=t
                    ),

            )

        except Exception:

            pass


    # ========================================================
    # Export result
    # ========================================================

    def _export_finished(
        self,
        path: Path,
    ) -> None:

        self.export_running = (
            False
        )


        self.last_svg = (
            path
        )


        self.dl_button.configure(

            state="normal",

            text="DL map",

        )


        self.open_button.configure(
            state="normal"
        )


        self.status.configure(

            text=(
                f"Saved: "
                f"{path.name}"
            )

        )


    def _export_failed(
        self,
        error: Exception,
    ) -> None:

        self.export_running = (
            False
        )


        self.dl_button.configure(

            state="normal",

            text="DL map",

        )


        self.open_button.configure(
            state="disabled"
        )


        self.status.configure(
            text="Export failed"
        )


        messagebox.showerror(

            "SVG export failed",

            str(error),

        )


    # ========================================================
    # Windows Explorer
    # ========================================================

    def _open(
        self,
    ) -> None:

        if (
            self.last_svg
            is None
            or
            not
            self.last_svg.exists()
        ):

            messagebox.showwarning(

                "Open",

                "No exported SVG "
                "is available yet.",

            )

            return


        path = (
            self.last_svg.resolve()
        )


        try:

            # Windows
            if (
                os.name
                ==
                "nt"
            ):

                subprocess.Popen(

                    [
                        "explorer.exe",
                        "/select,",
                        str(path),
                    ]

                )

                return


            # WSL
            if (
                shutil.which(
                    "explorer.exe"
                )
                and
                shutil.which(
                    "wslpath"
                )
            ):

                windows_path = (

                    subprocess
                    .check_output(

                        [
                            "wslpath",
                            "-w",
                            str(path),
                        ],

                        text=True,

                    )
                    .strip()

                )


                subprocess.Popen(

                    [
                        "explorer.exe",
                        "/select,",
                        windows_path,
                    ]

                )


                return


            # Linux
            if (
                shutil.which(
                    "xdg-open"
                )
            ):

                subprocess.Popen(

                    [
                        "xdg-open",
                        str(
                            path.parent
                        ),
                    ]

                )

                return


            raise RuntimeError(
                "Could not find a file explorer command."
            )


        except Exception as error:

            messagebox.showerror(

                "Open failed",

                str(error),

            )


# ============================================================
# Plugin registration
# ============================================================

TAB_PLUGIN = Map2SvgTab
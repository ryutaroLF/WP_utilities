from __future__ import annotations

import html
import tkinter as tk

import customtkinter as ctk

from _base import BaseTabPlugin


# ============================================================
# H1 style / font definitions
# ============================================================

STYLE_DEFS = {
    "1": {
        "name": "Fold + Dashed",
        "css": """
.rt-h1-style-1 {
  position: relative;
  background: #dfefff;
  box-shadow: 0px 0px 0px 5px #dfefff;
  border: dashed 2px white;
  padding: 0.2em 0.5em;
  color: #454545;
}

.rt-h1-style-1:after {
  position: absolute;
  content: '';
  left: -7px;
  top: -7px;
  border-width: 0 0 15px 15px;
  border-style: solid;
  border-color: #fff #fff #a8d4ff;
  box-shadow: 1px 1px 1px rgba(0, 0, 0, 0.15);
}
""".strip(),
    },
    "2": {
        "name": "Dashed Blue",
        "css": """
.rt-h1-style-2 {
  background: #dfefff;
  box-shadow: 0px 0px 0px 5px #dfefff;
  border: dashed 2px white;
  padding: 0.2em 0.5em;
}
""".strip(),
    },
    "3": {
        "name": "Double Line",
        "css": """
.rt-h1-style-3 {
  position: relative;
  padding: 0.25em 1em;
  border-top: solid 2px black;
  border-bottom: solid 2px black;
}

.rt-h1-style-3:before,
.rt-h1-style-3:after {
  content: '';
  position: absolute;
  top: -7px;
  width: 2px;
  height: -webkit-calc(100% + 14px);
  height: calc(100% + 14px);
  background-color: black;
}

.rt-h1-style-3:before {
  left: 7px;
}

.rt-h1-style-3:after {
  right: 7px;
}
""".strip(),
    },
    "4": {
        "name": "Corner Dots",
        "css": """
.rt-h1-style-4 {
  position: relative;
  padding: 0.25em 1em;
  border: solid 2px black;
  border-radius: 3px 0 3px 0;
}

.rt-h1-style-4:before,
.rt-h1-style-4:after {
  content: '';
  position: absolute;
  width: 10px;
  height: 10px;
  border: solid 2px black;
  border-radius: 50%;
}

.rt-h1-style-4:after {
  top: -12px;
  left: -12px;
}

.rt-h1-style-4:before {
  bottom: -12px;
  right: -12px;
}
""".strip(),
    },
}


FONT_DEFS = {
    "old_english": {
        "label": "Old English",
        # Old English is generated as Unicode Fraktur characters.
        # This avoids depending on a locally installed web font.
        "css": '"Cambria Math", "STIX Two Math", "Noto Sans Math", serif',
        "transform": "fraktur",
    },
    "arial": {
        "label": "Arial",
        "css": 'Arial, Helvetica, sans-serif',
        "transform": None,
    },
    "georgia": {
        "label": "Georgia",
        "css": 'Georgia, "Times New Roman", serif',
        "transform": None,
    },
    "times": {
        "label": "Times New Roman",
        "css": '"Times New Roman", Times, serif',
        "transform": None,
    },
}


# Unicode Mathematical Fraktur.
_NORMAL_UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_FRAKTUR_UPPER = "𝔄𝔅ℭ𝔇𝔈𝔉𝔊ℌℑ𝔍𝔎𝔏𝔐𝔑𝔒𝔓𝔔ℜ𝔖𝔗𝔘𝔙𝔚𝔛𝔜ℨ"

_NORMAL_LOWER = "abcdefghijklmnopqrstuvwxyz"
_FRAKTUR_LOWER = "𝔞𝔟𝔠𝔡𝔢𝔣𝔤𝔥𝔦𝔧𝔨𝔩𝔪𝔫𝔬𝔭𝔮𝔯𝔰𝔱𝔲𝔳𝔴𝔵𝔶𝔷"

_FRAKTUR_TRANSLATION = str.maketrans(
    _NORMAL_UPPER + _NORMAL_LOWER,
    _FRAKTUR_UPPER + _FRAKTUR_LOWER,
)


def to_fraktur(text: str) -> str:
    """Convert ASCII A-Z / a-z to Unicode Mathematical Fraktur."""
    return text.translate(_FRAKTUR_TRANSLATION)


# ============================================================
# Preview widget
# ============================================================

class StylePreview(tk.Canvas):
    """Small clickable Canvas that approximates one CSS H1 style."""

    WIDTH = 220
    HEIGHT = 112

    def __init__(self, parent, style_id: str, command) -> None:
        super().__init__(
            parent,
            width=self.WIDTH,
            height=self.HEIGHT,
            highlightthickness=0,
            bd=0,
            bg="#ffffff",
            cursor="hand2",
        )

        self.style_id = style_id
        self.command = command
        self.selected = False
        self.preview_text = "Heading"
        self.font_key = "arial"

        self.bind("<Button-1>", self._on_click)
        self.bind("<Configure>", lambda _event: self.redraw())

        self.redraw()

    def _on_click(self, _event=None) -> None:
        self.command(self.style_id)

    def set_selected(self, selected: bool) -> None:
        self.selected = selected
        self.redraw()

    def set_preview(self, text: str, font_key: str) -> None:
        self.preview_text = text or "Heading"
        self.font_key = font_key
        self.redraw()

    def _font_tuple(self, size: int, weight: str = "bold"):
        # For the Old English option the displayed characters themselves are
        # Fraktur Unicode, so the OS can choose a suitable fallback glyph font.
        if self.font_key == "arial":
            return ("Arial", size, weight)
        if self.font_key == "georgia":
            return ("Georgia", size, weight)
        if self.font_key == "times":
            return ("Times New Roman", size, weight)
        return ("Cambria Math", size, weight)

    def _display_text(self) -> str:
        text = self.preview_text
        if self.font_key == "old_english":
            return to_fraktur(text)
        return text

    def redraw(self) -> None:
        self.delete("all")

        w = max(self.winfo_width(), self.WIDTH)
        h = max(self.winfo_height(), self.HEIGHT)

        # Card background / selected state.
        border = "#3b82f6" if self.selected else "#d8d8d8"
        border_width = 3 if self.selected else 1

        self.create_rectangle(
            2,
            2,
            w - 3,
            h - 3,
            fill="#ffffff",
            outline=border,
            width=border_width,
        )

        x1 = 18
        x2 = w - 18
        y1 = 31
        y2 = h - 25

        text = self._display_text()
        text_font = self._font_tuple(18, "bold")

        if self.style_id == "1":
            # #dfefff + white dashed border + folded corner.
            self.create_rectangle(
                x1,
                y1,
                x2,
                y2,
                fill="#dfefff",
                outline="#ffffff",
                width=2,
                dash=(5, 4),
            )

            # Approximate the 5px box-shadow as an outer blue border.
            self.create_rectangle(
                x1 - 5,
                y1 - 5,
                x2 + 5,
                y2 + 5,
                outline="#dfefff",
                width=5,
            )

            # Fold at top-left.
            self.create_polygon(
                x1 - 7,
                y1 - 7,
                x1 + 8,
                y1 - 7,
                x1 - 7,
                y1 + 8,
                fill="#a8d4ff",
                outline="",
            )

            self.create_text(
                (x1 + x2) / 2,
                (y1 + y2) / 2,
                text=text,
                fill="#454545",
                font=text_font,
            )

        elif self.style_id == "2":
            self.create_rectangle(
                x1 - 5,
                y1 - 5,
                x2 + 5,
                y2 + 5,
                outline="#dfefff",
                width=5,
            )
            self.create_rectangle(
                x1,
                y1,
                x2,
                y2,
                fill="#dfefff",
                outline="#ffffff",
                width=2,
                dash=(5, 4),
            )
            self.create_text(
                (x1 + x2) / 2,
                (y1 + y2) / 2,
                text=text,
                fill="#111111",
                font=text_font,
            )

        elif self.style_id == "3":
            self.create_line(x1, y1, x2, y1, fill="#000000", width=2)
            self.create_line(x1, y2, x2, y2, fill="#000000", width=2)
            self.create_line(x1 + 7, y1 - 7, x1 + 7, y2 + 7, fill="#000000", width=2)
            self.create_line(x2 - 7, y1 - 7, x2 - 7, y2 + 7, fill="#000000", width=2)
            self.create_text(
                (x1 + x2) / 2,
                (y1 + y2) / 2,
                text=text,
                fill="#111111",
                font=text_font,
            )

        elif self.style_id == "4":
            self.create_rectangle(
                x1,
                y1,
                x2,
                y2,
                outline="#000000",
                width=2,
            )

            # Two circle ornaments outside opposite corners.
            r = 6
            cx1 = x1 - 6
            cy1 = y1 - 6
            cx2 = x2 + 6
            cy2 = y2 + 6

            self.create_oval(
                cx1 - r,
                cy1 - r,
                cx1 + r,
                cy1 + r,
                outline="#000000",
                width=2,
            )
            self.create_oval(
                cx2 - r,
                cy2 - r,
                cx2 + r,
                cy2 + r,
                outline="#000000",
                width=2,
            )
            self.create_text(
                (x1 + x2) / 2,
                (y1 + y2) / 2,
                text=text,
                fill="#111111",
                font=text_font,
            )


# ============================================================
# Main tab
# ============================================================

class H1GeneratorTab(BaseTabPlugin):
    TAB_TITLE = "H1 Generator"
    ORDER = 90

    AUTO_COPY_DELAY_MS = 450

    def __init__(self, app, tabview) -> None:
        super().__init__(app, tabview)

        self.style_var = tk.StringVar(master=app, value="1")
        self.font_var = tk.StringVar(master=app, value="old_english")
        self.text_var = tk.StringVar(master=app, value="British Band")

        self.preview_widgets: dict[str, StylePreview] = {}
        self.font_buttons: dict[str, ctk.CTkButton] = {}

        self._copy_after_id = None

    def create_ui(self) -> None:
        tab = self.tab
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        # ------------------------------------------------------------
        # Header
        # ------------------------------------------------------------
        header = ctk.CTkFrame(tab, fg_color="transparent")
        header.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=22,
            pady=(16, 10),
        )
        header.grid_columnconfigure(0, weight=1)

        title_box = ctk.CTkFrame(header, fg_color="transparent")
        title_box.grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            title_box,
            text="H1 Generator",
            anchor="w",
            font=ctk.CTkFont(size=23, weight="bold"),
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            title_box,
            text="Choose a CSS style and font, type a heading, then paste into a WordPress Custom HTML block.",
            anchor="w",
            text_color=("gray40", "gray68"),
            font=ctk.CTkFont(size=12),
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

        self.copy_status = ctk.CTkLabel(
            header,
            text="  Ready  ",
            height=30,
            corner_radius=15,
            fg_color=("gray88", "gray24"),
            text_color=("gray30", "gray78"),
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.copy_status.grid(row=0, column=1, rowspan=2, sticky="e")

        # ------------------------------------------------------------
        # Scrollable page
        # ------------------------------------------------------------
        page = ctk.CTkScrollableFrame(
            tab,
            corner_radius=12,
            fg_color="transparent",
        )
        page.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=14,
            pady=(0, 14),
        )
        page.grid_columnconfigure(0, weight=1)

        # ------------------------------------------------------------
        # 1. CSS style
        # ------------------------------------------------------------
        style_card = self._card(page, "1. CSS style")
        style_card.grid(
            row=0,
            column=0,
            sticky="ew",
            pady=(0, 10),
        )

        previews = ctk.CTkFrame(style_card, fg_color="transparent")
        previews.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=14,
            pady=(2, 14),
        )

        for col in range(4):
            previews.grid_columnconfigure(col, weight=1)

        for col, style_id in enumerate(("1", "2", "3", "4")):
            wrapper = ctk.CTkFrame(
                previews,
                corner_radius=10,
                fg_color=("gray97", "gray16"),
            )
            wrapper.grid(
                row=0,
                column=col,
                sticky="nsew",
                padx=(0 if col == 0 else 5, 0 if col == 3 else 5),
            )

            canvas = StylePreview(
                wrapper,
                style_id=style_id,
                command=self._select_style,
            )
            canvas.pack(fill="x", expand=True, padx=7, pady=(7, 3))

            # Make the label clickable too.
            label = ctk.CTkLabel(
                wrapper,
                text=f"{style_id}. {STYLE_DEFS[style_id]['name']}",
                font=ctk.CTkFont(size=11, weight="bold"),
                cursor="hand2",
            )
            label.pack(padx=6, pady=(0, 7))
            label.bind(
                "<Button-1>",
                lambda _event, sid=style_id: self._select_style(sid),
            )

            self.preview_widgets[style_id] = canvas

        # ------------------------------------------------------------
        # 2. Font
        # ------------------------------------------------------------
        font_card = self._card(page, "2. Font")
        font_card.grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(0, 10),
        )

        font_row = ctk.CTkFrame(font_card, fg_color="transparent")
        font_row.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=14,
            pady=(2, 14),
        )

        for col in range(len(FONT_DEFS)):
            font_row.grid_columnconfigure(col, weight=1)

        for col, (font_key, info) in enumerate(FONT_DEFS.items()):
            button_text = info["label"]
            if font_key == "old_english":
                button_text = to_fraktur("Old English")

            button = ctk.CTkButton(
                font_row,
                text=button_text,
                height=44,
                corner_radius=10,
                fg_color="transparent",
                border_width=1,
                text_color=("gray20", "gray88"),
                hover_color=("gray88", "gray24"),
                command=lambda key=font_key: self._select_font(key),
            )
            button.grid(
                row=0,
                column=col,
                sticky="ew",
                padx=(0 if col == 0 else 5, 0 if col == len(FONT_DEFS) - 1 else 5),
            )
            self.font_buttons[font_key] = button

        ctk.CTkLabel(
            font_card,
            text=(
                "Old English uses Unicode Fraktur characters "
                "(e.g. British Band → 𝔅𝔯𝔦𝔱𝔦𝔰𝔥 𝔅𝔞𝔫𝔡), "
                "so no web-font file is required."
            ),
            anchor="w",
            justify="left",
            text_color=("gray44", "gray64"),
            font=ctk.CTkFont(size=11),
        ).grid(
            row=2,
            column=0,
            sticky="w",
            padx=14,
            pady=(0, 12),
        )

        # ------------------------------------------------------------
        # 3. H1 text
        # ------------------------------------------------------------
        text_card = self._card(page, "3. H1 text")
        text_card.grid(
            row=2,
            column=0,
            sticky="ew",
            pady=(0, 10),
        )
        text_card.grid_columnconfigure(0, weight=1)

        self.title_entry = ctk.CTkEntry(
            text_card,
            textvariable=self.text_var,
            height=48,
            font=ctk.CTkFont(size=18),
            placeholder_text="Type an English H1 title...",
        )
        self.title_entry.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=14,
            pady=(2, 8),
        )

        ctk.CTkLabel(
            text_card,
            text="After you stop typing for 0.45 s, the generated HTML is copied to the clipboard automatically.",
            anchor="w",
            text_color=("gray44", "gray64"),
            font=ctk.CTkFont(size=11),
        ).grid(
            row=2,
            column=0,
            sticky="w",
            padx=14,
            pady=(0, 14),
        )

        # ------------------------------------------------------------
        # 4. Generated HTML
        # ------------------------------------------------------------
        output_card = self._card(page, "4. Generated HTML")
        output_card.grid(
            row=3,
            column=0,
            sticky="ew",
            pady=(0, 6),
        )
        output_card.grid_columnconfigure(0, weight=1)

        output_actions = ctk.CTkFrame(output_card, fg_color="transparent")
        output_actions.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=14,
            pady=(0, 8),
        )
        output_actions.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            output_actions,
            text="Paste this directly into a WordPress Custom HTML block.",
            anchor="w",
            text_color=("gray42", "gray65"),
            font=ctk.CTkFont(size=11),
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            output_actions,
            text="Copy now",
            width=100,
            height=34,
            command=self._copy_now,
        ).grid(row=0, column=1, sticky="e")

        self.output_text = ctk.CTkTextbox(
            output_card,
            height=260,
            wrap="none",
            corner_radius=10,
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self.output_text.grid(
            row=2,
            column=0,
            sticky="ew",
            padx=14,
            pady=(0, 14),
        )

        # React to typing.
        self.text_var.trace_add("write", self._on_text_changed)

        # Initial state.
        self._refresh_selection_ui()
        self._refresh_output(copy_to_clipboard=False)

        self.title_entry.focus_set()
        self.title_entry.icursor("end")

    # ============================================================
    # UI helpers
    # ============================================================

    def _card(self, parent, title: str):
        card = ctk.CTkFrame(parent, corner_radius=12)
        ctk.CTkLabel(
            card,
            text=title,
            anchor="w",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(
            row=0,
            column=0,
            sticky="ew",
            padx=14,
            pady=(12, 8),
        )
        return card

    def _select_style(self, style_id: str) -> None:
        if style_id not in STYLE_DEFS:
            return

        self.style_var.set(style_id)
        self._refresh_selection_ui()
        self._schedule_auto_copy(short_delay=True)

    def _select_font(self, font_key: str) -> None:
        if font_key not in FONT_DEFS:
            return

        self.font_var.set(font_key)
        self._refresh_selection_ui()
        self._schedule_auto_copy(short_delay=True)

    def _refresh_selection_ui(self) -> None:
        selected_style = self.style_var.get()
        selected_font = self.font_var.get()

        preview_source = self.text_var.get().strip() or "Heading"

        # Keep previews short enough to fit in the cards.
        if len(preview_source) > 18:
            preview_source = preview_source[:17] + "…"

        for style_id, preview in self.preview_widgets.items():
            preview.set_selected(style_id == selected_style)
            preview.set_preview(preview_source, selected_font)

        for font_key, button in self.font_buttons.items():
            if font_key == selected_font:
                button.configure(
                    fg_color=("#dbeafe", "#1e3a5f"),
                    border_color=("#3b82f6", "#60a5fa"),
                    text_color=("#153e75", "#dbeafe"),
                )
            else:
                button.configure(
                    fg_color="transparent",
                    border_color=("gray70", "gray38"),
                    text_color=("gray20", "gray88"),
                )

        self._refresh_output(copy_to_clipboard=False)

    # ============================================================
    # Output generation
    # ============================================================

    def _transformed_text(self) -> str:
        value = self.text_var.get()
        font_key = self.font_var.get()
        font_info = FONT_DEFS[font_key]

        if font_info["transform"] == "fraktur":
            return to_fraktur(value)

        return value

    def _generate_html(self) -> str:
        style_id = self.style_var.get()
        font_key = self.font_var.get()

        css = STYLE_DEFS[style_id]["css"]
        font_css = FONT_DEFS[font_key]["css"]

        title = html.escape(
            self._transformed_text(),
            quote=False,
        )

        return (
            "<style>\n"
            f"{css}\n"
            "</style>\n\n"
            f'<h1 class="rt-h1-style-{style_id}" '
            f'style="font-family: {font_css};">{title}</h1>'
        )

    def _refresh_output(self, copy_to_clipboard: bool) -> None:
        code = self._generate_html()

        self.output_text.configure(state="normal")
        self.output_text.delete("1.0", "end")
        self.output_text.insert("1.0", code)
        self.output_text.configure(state="disabled")

        if copy_to_clipboard and self.text_var.get().strip():
            self._copy_code(code)

    # ============================================================
    # Auto copy
    # ============================================================

    def _on_text_changed(self, *_args) -> None:
        self._refresh_selection_ui()
        self._schedule_auto_copy(short_delay=False)

    def _schedule_auto_copy(self, short_delay: bool = False) -> None:
        if self._copy_after_id is not None:
            try:
                self.app.after_cancel(self._copy_after_id)
            except Exception:
                pass

        delay = 80 if short_delay else self.AUTO_COPY_DELAY_MS

        self.copy_status.configure(
            text="  Editing…  ",
            fg_color=("gray88", "gray24"),
            text_color=("gray30", "gray78"),
        )

        self._copy_after_id = self.app.after(
            delay,
            self._auto_copy,
        )

    def _auto_copy(self) -> None:
        self._copy_after_id = None

        if not self.text_var.get().strip():
            self.copy_status.configure(
                text="  Empty  ",
                fg_color=("gray88", "gray24"),
                text_color=("gray30", "gray78"),
            )
            return

        self._refresh_output(copy_to_clipboard=True)

    def _copy_now(self) -> None:
        code = self._generate_html()

        if not self.text_var.get().strip():
            self.copy_status.configure(
                text="  Empty  ",
                fg_color=("gray88", "gray24"),
                text_color=("gray30", "gray78"),
            )
            return

        self._copy_code(code)

    def _copy_code(self, code: str) -> None:
        try:
            self.app.clipboard_clear()
            self.app.clipboard_append(code)

            # Keep clipboard ownership alive after returning to the event loop.
            self.app.update_idletasks()

            self.copy_status.configure(
                text="  Copied ✓  ",
                fg_color=("#d1fae5", "#14532d"),
                text_color=("#065f46", "#dcfce7"),
            )
        except Exception:
            self.copy_status.configure(
                text="  Copy failed  ",
                fg_color=("#fee2e2", "#7f1d1d"),
                text_color=("#991b1b", "#fee2e2"),
            )


TAB_PLUGIN = H1GeneratorTab

from __future__ import annotations

import html
from tkinter import messagebox

import customtkinter as ctk

from _base import BaseTabPlugin


class PhotoTagTab(BaseTabPlugin):
    TAB_TITLE = "Photo Tag"
    ORDER = 70

    def __init__(self, app, tabview) -> None:
        super().__init__(app, tabview)
        self._copy_after_id = None
        self.entries: dict[str, ctk.CTkEntry] = {}
        self.include_css_var = ctk.BooleanVar(value=True)

    def create_ui(self) -> None:
        tab = self.tab
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(
            tab,
            text=(
                "写真の下に置く撮影情報ラベルを生成します。"
                " WordPress の「カスタムHTML」ブロックへそのまま貼り付けられます。"
            ),
            anchor="w",
            text_color=("gray35", "gray70"),
        ).grid(
            row=0,
            column=0,
            sticky="ew",
            padx=22,
            pady=(18, 12),
        )

        # ------------------------------------------------------------
        # Inputs
        # ------------------------------------------------------------
        form = ctk.CTkFrame(tab)
        form.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=22,
            pady=(0, 12),
        )
        form.grid_columnconfigure(1, weight=1)
        form.grid_columnconfigure(3, weight=1)

        fields = [
            ("location", "撮影地", "千葉・野島崎付近　銀鱗橋"),
            ("camera", "カメラ", "Nikon Z50II"),
            ("focal", "焦点距離", "18mm"),
            ("aperture", "絞り", "f/2.8"),
            ("exposure", "露光時間", "600s"),
            ("iso", "ISO", "ISO 800"),
            ("process", "処理", "Stacked"),
        ]

        for index, (key, label_text, placeholder) in enumerate(fields):
            row = index // 2
            side = index % 2
            label_col = side * 2
            entry_col = label_col + 1

            ctk.CTkLabel(
                form,
                text=label_text,
                width=78,
                anchor="w",
                font=ctk.CTkFont(size=13, weight="bold"),
            ).grid(
                row=row,
                column=label_col,
                sticky="w",
                padx=(14 if side == 0 else 20, 6),
                pady=8,
            )

            entry = ctk.CTkEntry(
                form,
                height=38,
                placeholder_text=placeholder,
            )
            entry.grid(
                row=row,
                column=entry_col,
                sticky="ew",
                padx=(0, 14),
                pady=8,
            )
            entry.bind("<KeyRelease>", self.on_changed)
            self.entries[key] = entry

        # Useful defaults
        self.entries["camera"].insert(0, "Nikon Z50II")
        self.entries["process"].insert(0, "Stacked")

        options = ctk.CTkFrame(tab, fg_color="transparent")
        options.grid(
            row=2,
            column=0,
            sticky="ew",
            padx=22,
            pady=(0, 12),
        )
        options.grid_columnconfigure(3, weight=1)

        ctk.CTkCheckBox(
            options,
            text="CSSを含める",
            variable=self.include_css_var,
            command=self.update_preview,
        ).grid(row=0, column=0, padx=(0, 12))

        ctk.CTkButton(
            options,
            text="今回の例を入力",
            width=130,
            height=36,
            command=self.fill_example,
        ).grid(row=0, column=1, padx=6)

        ctk.CTkButton(
            options,
            text="Clear",
            width=90,
            height=36,
            fg_color="transparent",
            border_width=1,
            text_color=("gray15", "gray90"),
            command=self.clear,
        ).grid(row=0, column=2, padx=6)

        ctk.CTkLabel(
            options,
            text="※ 同じページで2個目以降は「CSSを含める」をOFFにできます。",
            anchor="e",
            text_color=("gray40", "gray65"),
        ).grid(row=0, column=3, sticky="e")

        # ------------------------------------------------------------
        # Preview
        # ------------------------------------------------------------
        preview_frame = ctk.CTkFrame(tab, fg_color="transparent")
        preview_frame.grid(
            row=3,
            column=0,
            sticky="nsew",
            padx=22,
            pady=(0, 12),
        )
        preview_frame.grid_columnconfigure(0, weight=1)
        preview_frame.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            preview_frame,
            text="Generated HTML",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", pady=(0, 6))

        self.preview = ctk.CTkTextbox(
            preview_frame,
            wrap="none",
            font=ctk.CTkFont(family="Consolas", size=12),
            corner_radius=10,
        )
        self.preview.grid(
            row=1,
            column=0,
            sticky="nsew",
        )

        bottom = ctk.CTkFrame(tab, fg_color="transparent")
        bottom.grid(
            row=4,
            column=0,
            sticky="ew",
            padx=22,
            pady=(0, 16),
        )
        bottom.grid_columnconfigure(0, weight=1)

        self.copy_button = ctk.CTkButton(
            bottom,
            text="Copy HTML",
            height=46,
            command=self.copy_html,
        )
        self.copy_button.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 8),
        )

        self.status = ctk.CTkLabel(
            bottom,
            text="",
            width=230,
            anchor="w",
            text_color=("gray35", "gray70"),
        )
        self.status.grid(
            row=0,
            column=1,
            sticky="w",
        )

        self.update_preview()

    # ------------------------------------------------------------
    # Values / HTML generation
    # ------------------------------------------------------------
    def get_values(self) -> dict[str, str]:
        return {
            key: entry.get().strip()
            for key, entry in self.entries.items()
        }

    def generate_css(self) -> str:
        return """<style>
.rm-star-photo-label01 {
    margin: 14px 0 34px;
    padding: 13px 16px;
    background: #f4f4f2;
    border: 1px solid #e3e3df;
    border-radius: 4px;
    box-sizing: border-box;
    font-family:
        -apple-system,
        BlinkMacSystemFont,
        "Helvetica Neue",
        "Hiragino Kaku Gothic ProN",
        "Yu Gothic",
        sans-serif;
    color: #2f2f2f;
}

.rm-star-photo-label01-location {
    display: flex;
    align-items: center;
    gap: 7px;
    margin-bottom: 6px;
    font-size: 14px;
    font-weight: 600;
    letter-spacing: 0.04em;
}

.rm-star-photo-label01-location svg {
    width: 14px;
    height: 14px;
    flex: 0 0 auto;
    opacity: 0.55;
}

.rm-star-photo-label01-meta {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    font-size: 12px;
    line-height: 1.7;
    letter-spacing: 0.04em;
    color: #707070;
}

.rm-star-photo-label01-item {
    display: inline-flex;
    white-space: nowrap;
}

.rm-star-photo-label01-item:not(:last-child)::after {
    content: "·";
    margin: 0 9px;
    color: #aaa;
}

.rm-star-photo-label01-process {
    text-transform: uppercase;
    font-size: 10px;
    letter-spacing: 0.11em;
}

@media (max-width: 600px) {
    .rm-star-photo-label01 {
        padding: 11px 13px;
    }

    .rm-star-photo-label01-meta {
        font-size: 11px;
    }
}
</style>"""

    def generate_html(self) -> str:
        values = self.get_values()

        location = html.escape(values["location"])

        meta_keys = (
            "camera",
            "focal",
            "aperture",
            "exposure",
            "iso",
            "process",
        )

        lines: list[str] = []

        if self.include_css_var.get():
            lines.append(self.generate_css())
            lines.append("")

        lines.append('<div class="rm-star-photo-label01">')

        if location:
            lines.extend([
                '  <div class="rm-star-photo-label01-location">',
                '    <svg viewBox="0 0 24 24" fill="none"',
                '         stroke="currentColor" stroke-width="1.7"',
                '         stroke-linecap="round" stroke-linejoin="round"',
                '         aria-hidden="true">',
                '      <path d="M20 10c0 5-8 12-8 12S4 15 4 10a8 8 0 1 1 16 0z"></path>',
                '      <circle cx="12" cy="10" r="2.5"></circle>',
                '    </svg>',
                f"    <span>{location}</span>",
                "  </div>",
            ])

        meta_items: list[str] = []

        for key in meta_keys:
            value = values[key]
            if not value:
                continue

            escaped = html.escape(value)
            extra_class = (
                " rm-star-photo-label01-process"
                if key == "process"
                else ""
            )
            meta_items.append(
                f'    <span class="rm-star-photo-label01-item{extra_class}">'
                f"{escaped}</span>"
            )

        if meta_items:
            lines.append('  <div class="rm-star-photo-label01-meta">')
            lines.extend(meta_items)
            lines.append("  </div>")

        lines.append("</div>")

        return "\n".join(lines)

    def update_preview(self) -> None:
        self.set_textbox_value(
            self.preview,
            self.generate_html(),
        )

    def on_changed(self, _event=None) -> None:
        self.update_preview()
        self.status.configure(text="")

    # ------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------
    def copy_html(self) -> None:
        values = self.get_values()

        if not any(values.values()):
            messagebox.showwarning(
                "入力エラー",
                "撮影情報を1項目以上入力してください。",
            )
            return

        result = self.generate_html()
        self.copy_to_clipboard(result)

        self.copy_button.configure(text="Copied!")
        self.status.configure(text="HTMLをコピーしました。")

        if self._copy_after_id:
            self.app.after_cancel(self._copy_after_id)

        self._copy_after_id = self.app.after(
            1500,
            self.reset_copy_button,
        )

    def reset_copy_button(self) -> None:
        self.copy_button.configure(text="Copy HTML")
        self._copy_after_id = None

    def fill_example(self) -> None:
        example = {
            "location": "千葉・野島崎付近　銀鱗橋",
            "camera": "Nikon Z50II",
            "focal": "18mm",
            "aperture": "",
            "exposure": "600s",
            "iso": "",
            "process": "Stacked",
        }

        for key, value in example.items():
            self.entries[key].delete(0, "end")
            if value:
                self.entries[key].insert(0, value)

        self.update_preview()
        self.status.configure(text="今回の例を入力しました。")

    def clear(self) -> None:
        for entry in self.entries.values():
            entry.delete(0, "end")

        # Frequently reused defaults
        self.entries["camera"].insert(0, "Nikon Z50II")
        self.entries["process"].insert(0, "Stacked")

        self.update_preview()
        self.status.configure(text="入力内容を消去しました。")

        self.entries["location"].focus_set()


TAB_PLUGIN = PhotoTagTab

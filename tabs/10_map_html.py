from __future__ import annotations

import html
import re
from tkinter import messagebox

import customtkinter as ctk

from _base import BaseTabPlugin


CSS = """<style>
.rt-map-overlay {
  position: relative;
  width: min(100%, 720px);
  margin: 2rem auto;
  aspect-ratio: 4 / 3;
  overflow: hidden;
  border-radius: 22px;
  background: #dfe5dc;
  box-shadow: 0 22px 55px rgba(28, 32, 25, 0.18);
}

.rt-map-overlay iframe {
  position: absolute;
  inset: 0;
  display: block;
  width: 100%;
  height: 100%;
  border: 0;
}

.rt-map-overlay::after {
  content: "";
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  height: 38%;
  pointer-events: none;
  background:
    linear-gradient(
      to top,
      rgba(13, 21, 17, 0.82),
      transparent
    );
}

.rt-map-overlay__text {
  position: absolute;
  z-index: 2;
  right: 24px;
  bottom: 22px;
  left: 24px;
  color: #fff;
}

.rt-map-overlay__text small {
  display: block;
  margin-bottom: 4px;
  color: rgba(255, 255, 255, 0.74);
  font-size: 12px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.rt-map-overlay__text strong {
  display: block;
  font-family: Georgia, "Times New Roman", serif;
  font-size: clamp(25px, 4vw, 38px);
  font-weight: 500;
}
</style>"""


class MapHtmlTab(BaseTabPlugin):
    TAB_TITLE = "Generate HTML"
    ORDER = 10

    def create_ui(self) -> None:
        tab = self.tab
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(7, weight=1)

        ctk.CTkLabel(
            tab,
            text=(
                "Google Mapsの「地図を埋め込む」からコピーした"
                "iframeコードを、そのまま貼り付けてください。"
            ),
            text_color=("gray35", "gray70"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=22, pady=(18, 20))

        ctk.CTkLabel(
            tab,
            text="Google Maps iframeコード",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", padx=22)

        self.iframe_textbox = ctk.CTkTextbox(
            tab,
            height=120,
            corner_radius=10,
            wrap="word",
        )
        self.iframe_textbox.grid(
            row=2,
            column=0,
            sticky="ew",
            padx=22,
            pady=(6, 16),
        )
        self.iframe_textbox.bind("<KeyRelease>", self.on_changed)

        fields = ctk.CTkFrame(tab, fg_color="transparent")
        fields.grid(
            row=3,
            column=0,
            sticky="ew",
            padx=22,
            pady=(0, 14),
        )
        fields.grid_columnconfigure((0, 1), weight=1)

        left = ctk.CTkFrame(fields, fg_color="transparent")
        left.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        left.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            left,
            text="タイトル",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", pady=(0, 6))

        self.title_entry = ctk.CTkEntry(
            left,
            height=42,
            placeholder_text="例：Overnight Stop",
        )
        self.title_entry.grid(row=1, column=0, sticky="ew")
        self.title_entry.bind("<KeyRelease>", self.on_changed)

        right = ctk.CTkFrame(fields, fg_color="transparent")
        right.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        right.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            right,
            text="サブタイトル",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", pady=(0, 6))

        self.subtitle_entry = ctk.CTkEntry(
            right,
            height=42,
            placeholder_text="例：Exmoor National Park",
        )
        self.subtitle_entry.grid(row=1, column=0, sticky="ew")
        self.subtitle_entry.bind("<KeyRelease>", self.on_changed)

        ctk.CTkLabel(
            tab,
            text=(
                "iframeのsrc属性からURLを自動抽出します。"
                "iframeのtitle属性にはサブタイトルを設定します。"
            ),
            text_color=("gray40", "gray65"),
            anchor="w",
        ).grid(row=4, column=0, sticky="ew", padx=22, pady=(0, 14))

        buttons = ctk.CTkFrame(tab, fg_color="transparent")
        buttons.grid(
            row=5,
            column=0,
            sticky="ew",
            padx=22,
            pady=(0, 18),
        )
        buttons.grid_columnconfigure(0, weight=1)

        self.copy_button = ctk.CTkButton(
            buttons,
            text="Copy HTML",
            height=46,
            command=self.copy_html,
        )
        self.copy_button.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 6),
        )

        ctk.CTkButton(
            buttons,
            text="Clear",
            width=110,
            height=46,
            fg_color="transparent",
            border_width=1,
            text_color=("gray15", "gray90"),
            command=self.clear,
        ).grid(row=0, column=1, padx=(6, 0))

        ctk.CTkLabel(
            tab,
            text="Generated HTML",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        ).grid(row=6, column=0, sticky="ew", padx=22, pady=(0, 6))

        self.preview = ctk.CTkTextbox(
            tab,
            corner_radius=10,
            wrap="none",
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self.preview.grid(
            row=7,
            column=0,
            sticky="nsew",
            padx=22,
            pady=(0, 10),
        )

        self.status = ctk.CTkLabel(
            tab,
            text="",
            height=24,
            anchor="w",
            text_color=("gray35", "gray70"),
        )
        self.status.grid(
            row=8,
            column=0,
            sticky="ew",
            padx=22,
            pady=(0, 14),
        )

        self.update_preview()

    @staticmethod
    def extract_src(code: str) -> str:
        match = re.search(
            r"""src\s*=\s*(["'])(.*?)\1""",
            code,
            flags=re.IGNORECASE | re.DOTALL,
        )
        return match.group(2).strip() if match else ""

    def generate_html(self) -> str:
        iframe_code = self.iframe_textbox.get("1.0", "end").strip()
        title = self.title_entry.get().strip()
        subtitle = self.subtitle_entry.get().strip()
        url = self.extract_src(iframe_code)

        return f"""{CSS}

<div class="rt-map-overlay">
  <iframe
    src="{html.escape(url, quote=True)}"
    title="{html.escape(subtitle, quote=True)}"
    loading="lazy"
    allowfullscreen=""
    referrerpolicy="strict-origin-when-cross-origin">
  </iframe>

  <div class="rt-map-overlay__text">
    <small>{html.escape(subtitle)}</small>
    <strong>{html.escape(title)}</strong>
  </div>
</div>"""

    def update_preview(self) -> None:
        self.set_textbox_value(self.preview, self.generate_html())

    def on_changed(self, _event=None) -> None:
        self.update_preview()
        self.status.configure(text="")

    def copy_html(self) -> None:
        code = self.iframe_textbox.get("1.0", "end").strip()
        title = self.title_entry.get().strip()
        subtitle = self.subtitle_entry.get().strip()
        url = self.extract_src(code)

        if not code:
            messagebox.showwarning("入力エラー", "iframeコードを入力してください。")
            return
        if not url:
            messagebox.showwarning("入力エラー", "src属性を抽出できませんでした。")
            return
        if not title or not subtitle:
            messagebox.showwarning(
                "入力エラー",
                "タイトルとサブタイトルを入力してください。",
            )
            return

        result = self.generate_html()
        self.copy_to_clipboard(result)
        self.copy_button.configure(text="Copied!")
        self.status.configure(text="HTMLをクリップボードにコピーしました。")
        self.app.after(
            1500,
            lambda: self.copy_button.configure(text="Copy HTML"),
        )

    def clear(self) -> None:
        self.iframe_textbox.delete("1.0", "end")
        self.title_entry.delete(0, "end")
        self.subtitle_entry.delete(0, "end")
        self.update_preview()
        self.status.configure(text="入力内容を消去しました。")


TAB_PLUGIN = MapHtmlTab

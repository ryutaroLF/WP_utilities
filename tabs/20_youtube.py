from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse
from tkinter import messagebox

import customtkinter as ctk

from _base import BaseTabPlugin


YOUTUBE_TEMPLATE = """<div class="clean-youtube" data-video-id="{video_id}">
  <button class="clean-youtube__cover" type="button" aria-label="動画を再生">
    <img
      src="https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg"
      alt="YouTube動画のサムネイル"
      loading="lazy"
    >
    <span class="clean-youtube__play" aria-hidden="true"></span>
  </button>
</div>

<style>
.clean-youtube {{
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  overflow: hidden;
  background: #000;
  border-radius: 10px;
}}

.clean-youtube__cover {{
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  padding: 0;
  border: 0;
  background: #000;
  cursor: pointer;
}}

.clean-youtube__cover img {{
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition:
    transform 0.25s ease,
    opacity 0.25s ease;
}}

.clean-youtube__play {{
  position: absolute;
  top: 50%;
  left: 50%;
  width: 70px;
  height: 50px;
  border-radius: 14px;
  background: rgba(0, 0, 0, 0.72);
  transform: translate(-50%, -50%);
  transition:
    transform 0.2s ease,
    background 0.2s ease;
}}

.clean-youtube__play::after {{
  content: "";
  position: absolute;
  top: 50%;
  left: 52%;
  transform: translate(-50%, -50%);
  border-top: 11px solid transparent;
  border-bottom: 11px solid transparent;
  border-left: 18px solid #fff;
}}

.clean-youtube__cover:hover img {{
  transform: scale(1.02);
  opacity: 0.88;
}}

.clean-youtube__cover:hover .clean-youtube__play {{
  transform: translate(-50%, -50%) scale(1.08);
  background: #ff0033;
}}

.clean-youtube__cover:focus-visible {{
  outline: 3px solid #fff;
  outline-offset: -5px;
}}

.clean-youtube iframe {{
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  border: 0;
}}
</style>

<script>
document.querySelectorAll(".clean-youtube").forEach(function (container) {{
  const button = container.querySelector(".clean-youtube__cover");
  const image = container.querySelector("img");
  const videoId = container.dataset.videoId;

  if (!button || !videoId) {{
    return;
  }}

  if (image) {{
    image.addEventListener("error", function () {{
      image.src =
        "https://i.ytimg.com/vi/" +
        encodeURIComponent(videoId) +
        "/hqdefault.jpg";
    }});
  }}

  button.addEventListener("click", function () {{
    const iframe = document.createElement("iframe");

    iframe.src =
      "https://www.youtube-nocookie.com/embed/" +
      encodeURIComponent(videoId) +
      "?autoplay=1&rel=0";

    iframe.title = "YouTube動画";
    iframe.allow =
      "accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share";
    iframe.allowFullscreen = true;

    container.replaceChildren(iframe);
  }});
}});
</script>"""


class YouTubeTab(BaseTabPlugin):
    TAB_TITLE = "YouTube"
    ORDER = 20

    def create_ui(self) -> None:
        tab = self.tab
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(5, weight=1)

        ctk.CTkLabel(
            tab,
            text=(
                "YouTube URLを貼り付けると動画IDを抽出し、"
                "HTML全文を生成して自動コピーします。"
            ),
            anchor="w",
            text_color=("gray35", "gray70"),
        ).grid(row=0, column=0, sticky="ew", padx=22, pady=(18, 18))

        ctk.CTkLabel(
            tab,
            text="YouTube URL",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", padx=22)

        self.url_entry = ctk.CTkEntry(
            tab,
            height=44,
            placeholder_text="https://youtu.be/8MPAx3kEB7A",
        )
        self.url_entry.grid(
            row=2,
            column=0,
            sticky="ew",
            padx=22,
            pady=(6, 14),
        )
        self.url_entry.bind("<KeyRelease>", self.on_url_changed)

        self.status = ctk.CTkLabel(
            tab,
            text="",
            anchor="w",
            text_color=("gray35", "gray70"),
        )
        self.status.grid(
            row=3,
            column=0,
            sticky="ew",
            padx=22,
            pady=(0, 10),
        )

        ctk.CTkLabel(
            tab,
            text="Generated HTML",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        ).grid(row=4, column=0, sticky="ew", padx=22, pady=(0, 6))

        self.preview = ctk.CTkTextbox(
            tab,
            wrap="none",
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self.preview.grid(
            row=5,
            column=0,
            sticky="nsew",
            padx=22,
            pady=(0, 12),
        )

        self.copy_button = ctk.CTkButton(
            tab,
            text="Copy HTML",
            height=44,
            command=self.copy_html,
        )
        self.copy_button.grid(
            row=6,
            column=0,
            sticky="ew",
            padx=22,
            pady=(0, 16),
        )

        self._copy_after_id = None

    @staticmethod
    def extract_video_id(value: str) -> str:
        value = value.strip()
        if not value:
            return ""

        if re.fullmatch(r"[A-Za-z0-9_-]{11}", value):
            return value

        try:
            parsed = urlparse(value)
        except Exception:
            return ""

        host = parsed.netloc.lower().split(":")[0]
        path_parts = [part for part in parsed.path.split("/") if part]

        if host in {"youtu.be", "www.youtu.be"}:
            candidate = path_parts[0] if path_parts else ""

        elif host.endswith("youtube.com"):
            if parsed.path == "/watch":
                candidate = parse_qs(parsed.query).get("v", [""])[0]
            elif path_parts and path_parts[0] in {
                "embed",
                "shorts",
                "live",
                "v",
            }:
                candidate = path_parts[1] if len(path_parts) > 1 else ""
            else:
                candidate = ""

        else:
            candidate = ""

        return candidate if re.fullmatch(r"[A-Za-z0-9_-]{11}", candidate) else ""

    def on_url_changed(self, _event=None) -> None:
        if self._copy_after_id:
            self.app.after_cancel(self._copy_after_id)
            self._copy_after_id = None

        value = self.url_entry.get().strip()
        video_id = self.extract_video_id(value)

        if not value:
            self.set_textbox_value(self.preview, "")
            self.status.configure(text="")
            return

        if not video_id:
            self.set_textbox_value(self.preview, "")
            self.status.configure(text="有効なYouTube URLを認識できません。")
            return

        generated = YOUTUBE_TEMPLATE.format(video_id=video_id)
        self.set_textbox_value(self.preview, generated)
        self.status.configure(text=f"Video ID: {video_id}")

        self._copy_after_id = self.app.after(
            250,
            self.copy_html,
        )

    def copy_html(self) -> None:
        video_id = self.extract_video_id(self.url_entry.get())

        if not video_id:
            messagebox.showwarning(
                "入力エラー",
                "有効なYouTube URLを入力してください。",
            )
            return

        generated = YOUTUBE_TEMPLATE.format(video_id=video_id)
        self.copy_to_clipboard(generated)
        self.copy_button.configure(text="Copied!")
        self.status.configure(
            text=f"Copied! Video ID: {video_id}"
        )
        self.app.after(
            1500,
            lambda: self.copy_button.configure(text="Copy HTML"),
        )


TAB_PLUGIN = YouTubeTab

from __future__ import annotations

import html
from datetime import datetime
from tkinter import messagebox

import customtkinter as ctk

from _base import BaseTabPlugin


CARD_CSS = """<style>
.cherry-travel-card-wrap {
  position: relative !important;
  display: block !important;
  width: min(100%, 720px) !important;
  max-width: 720px !important;
  margin: 36px auto !important;
  padding: 0 !important;
  box-sizing: border-box !important;
}

.cherry-travel-card {
  position: relative !important;
  display: block !important;
  width: 100% !important;
  aspect-ratio: 4 / 3 !important;
  margin: 0 !important;
  padding: 0 !important;
  overflow: hidden !important;
  border: 0 !important;
  border-radius: 18px !important;
  color: #ffffff !important;
  text-decoration: none !important;
  background-image:
    linear-gradient(
      180deg,
      rgba(8, 12, 18, 0.03) 0%,
      rgba(8, 12, 18, 0.06) 38%,
      rgba(8, 14, 22, 0.48) 68%,
      rgba(8, 14, 22, 0.92) 100%
    ),
    var(--cherry-card-image) !important;
  background-position: center center !important;
  background-repeat: no-repeat !important;
  background-size: cover !important;
  box-shadow:
    0 12px 32px rgba(0, 0, 0, 0.22) !important;
  box-sizing: border-box !important;
  isolation: isolate !important;
  transition:
    transform 0.3s ease,
    box-shadow 0.3s ease !important;
}

.cherry-travel-card,
.cherry-travel-card * {
  box-sizing: border-box !important;
}

.cherry-travel-card::before {
  content: "" !important;
  position: absolute !important;
  inset: 0 !important;
  z-index: -1 !important;
  background-image: var(--cherry-card-image) !important;
  background-position: center center !important;
  background-repeat: no-repeat !important;
  background-size: cover !important;
  opacity: 0 !important;
  transform: scale(1) !important;
  transition:
    opacity 0.3s ease,
    transform 0.6s ease !important;
}

.cherry-travel-card__content {
  position: absolute !important;
  inset: 0 !important;
  z-index: 2 !important;
  display: flex !important;
  flex-direction: column !important;
  align-items: flex-start !important;
  justify-content: flex-end !important;
  width: 100% !important;
  height: 100% !important;
  padding: 34px 36px !important;
  color: #ffffff !important;
  text-align: left !important;
  pointer-events: none !important;
}

.cherry-travel-card__meta {
  display: flex !important;
  flex-wrap: wrap !important;
  align-items: center !important;
  gap: 8px 14px !important;
  margin: 0 0 8px !important;
  color: rgba(255, 255, 255, 0.82) !important;
  font-family: inherit !important;
  font-size: 12px !important;
  font-style: normal !important;
  font-weight: 600 !important;
  line-height: 1.4 !important;
  letter-spacing: 0.13em !important;
  text-transform: uppercase !important;
}

.cherry-travel-card__day::before {
  content: "•" !important;
  display: inline-block !important;
  margin-right: 14px !important;
  color: rgba(255, 255, 255, 0.55) !important;
}

.cherry-travel-card__title {
  display: block !important;
  max-width: calc(100% - 60px) !important;
  margin: 0 0 16px !important;
  padding: 0 !important;
  color: #ffffff !important;
  font-family: inherit !important;
  font-size: clamp(25px, 4vw, 38px) !important;
  font-style: normal !important;
  font-weight: 700 !important;
  line-height: 1.12 !important;
  letter-spacing: -0.025em !important;
  text-shadow:
    0 2px 12px rgba(0, 0, 0, 0.42) !important;
}

.cherry-travel-card__places {
  display: flex !important;
  flex-wrap: wrap !important;
  gap: 8px !important;
  width: 100% !important;
  margin: 0 !important;
  padding: 0 58px 0 0 !important;
}

.cherry-travel-card__place {
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  min-height: 36px !important;
  margin: 0 !important;
  padding: 7px 13px !important;
  border:
    1px solid rgba(255, 255, 255, 0.48) !important;
  border-radius: 999px !important;
  background:
    rgba(20, 27, 35, 0.48) !important;
  color: #ffffff !important;
  font-family: inherit !important;
  font-size: 13px !important;
  font-style: normal !important;
  font-weight: 500 !important;
  line-height: 1.35 !important;
  letter-spacing: 0 !important;
  text-shadow:
    0 1px 4px rgba(0, 0, 0, 0.35) !important;
  backdrop-filter: blur(7px) !important;
  -webkit-backdrop-filter: blur(7px) !important;
}

.cherry-travel-card__arrow {
  position: absolute !important;
  right: 30px !important;
  bottom: 32px !important;
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  width: 42px !important;
  height: 42px !important;
  border:
    1px solid rgba(255, 255, 255, 0.55) !important;
  border-radius: 50% !important;
  background:
    rgba(20, 27, 35, 0.46) !important;
  color: #ffffff !important;
  font-size: 21px !important;
  font-weight: 400 !important;
  line-height: 1 !important;
  backdrop-filter: blur(7px) !important;
  -webkit-backdrop-filter: blur(7px) !important;
  transition:
    color 0.3s ease,
    background-color 0.3s ease,
    transform 0.3s ease !important;
}

.cherry-travel-card:hover {
  color: #ffffff !important;
  text-decoration: none !important;
  transform: translateY(-5px) !important;
  box-shadow:
    0 19px 44px rgba(0, 0, 0, 0.30) !important;
}

.cherry-travel-card:hover .cherry-travel-card__arrow {
  color: #20262d !important;
  background: rgba(255, 255, 255, 0.95) !important;
  transform: translateX(4px) !important;
}

.cherry-travel-card:hover .cherry-travel-card__place {
  border-color: rgba(255, 255, 255, 0.7) !important;
  background: rgba(20, 27, 35, 0.62) !important;
}

.cherry-travel-card:focus-visible {
  outline: 3px solid #ffffff !important;
  outline-offset: 5px !important;
}

@media screen and (max-width: 600px) {
  .cherry-travel-card {
    aspect-ratio: 4 / 5 !important;
    border-radius: 14px !important;
  }

  .cherry-travel-card__content {
    padding: 26px 22px !important;
  }

  .cherry-travel-card__meta {
    margin-bottom: 7px !important;
    font-size: 10px !important;
    gap: 6px 10px !important;
  }

  .cherry-travel-card__day::before {
    margin-right: 10px !important;
  }

  .cherry-travel-card__title {
    max-width: 100% !important;
    margin-bottom: 14px !important;
    font-size: 27px !important;
  }

  .cherry-travel-card__places {
    gap: 7px !important;
    padding-right: 0 !important;
    padding-bottom: 51px !important;
  }

  .cherry-travel-card__place {
    min-height: 32px !important;
    padding: 6px 11px !important;
    font-size: 12px !important;
  }

  .cherry-travel-card__arrow {
    right: 21px !important;
    bottom: 24px !important;
    width: 39px !important;
    height: 39px !important;
  }
}

@media (prefers-reduced-motion: reduce) {
  .cherry-travel-card,
  .cherry-travel-card__arrow {
    transition: none !important;
  }
}
</style>"""


class ImageThumbnailTab(BaseTabPlugin):
    TAB_TITLE = "Image-Thumbnail"
    ORDER = 30

    def create_ui(self) -> None:
        tab = self.tab
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(8, weight=1)

        form = ctk.CTkScrollableFrame(tab)
        form.grid(
            row=0,
            column=0,
            rowspan=9,
            sticky="nsew",
            padx=16,
            pady=16,
        )
        form.grid_columnconfigure(0, weight=1)

        self.image_url = self.add_entry(
            form,
            0,
            "WebP画像URL",
            "https://example.com/image.webp",
        )
        self.page_url = self.add_entry(
            form,
            2,
            "ページ遷移先URL",
            "https://example.com/page/",
        )
        self.date_entry = self.add_entry(
            form,
            4,
            "日付",
            "2025-12-30 または 30 December 2025",
        )
        self.day_entry = self.add_entry(
            form,
            6,
            "DAY",
            "1 または Day 1",
        )
        self.title_entry = self.add_entry(
            form,
            8,
            "タイトル（任意）",
            "この日のタイトル",
        )
        self.tags_entry = self.add_entry(
            form,
            10,
            "カテゴリータグ",
            "バスツアー, ディナー, 街歩き",
        )

        ctk.CTkLabel(
            form,
            text=(
                "カテゴリータグは半角コンマ区切りで入力してください。"
                "日本語タグも使用できます。例：バスツアー, ディナー"
            ),
            anchor="w",
            text_color=("gray40", "gray65"),
            wraplength=820,
            justify="left",
        ).grid(row=12, column=0, sticky="ew", pady=(0, 14))

        buttons = ctk.CTkFrame(form, fg_color="transparent")
        buttons.grid(row=13, column=0, sticky="ew", pady=(0, 14))
        buttons.grid_columnconfigure(0, weight=1)

        self.copy_button = ctk.CTkButton(
            buttons,
            text="Copy HTML",
            height=44,
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
            height=44,
            fg_color="transparent",
            border_width=1,
            text_color=("gray15", "gray90"),
            command=self.clear,
        ).grid(row=0, column=1, padx=(6, 0))

        ctk.CTkLabel(
            form,
            text="Generated HTML",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        ).grid(row=14, column=0, sticky="ew", pady=(0, 6))

        self.preview = ctk.CTkTextbox(
            form,
            height=330,
            wrap="none",
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self.preview.grid(row=15, column=0, sticky="ew", pady=(0, 10))

        self.status = ctk.CTkLabel(
            form,
            text="",
            anchor="w",
            text_color=("gray35", "gray70"),
        )
        self.status.grid(row=16, column=0, sticky="ew")

        for entry in (
            self.image_url,
            self.page_url,
            self.date_entry,
            self.day_entry,
            self.title_entry,
            self.tags_entry,
        ):
            entry.bind("<KeyRelease>", self.on_changed)

        self.update_preview()

    @staticmethod
    def add_entry(parent, row, label, placeholder):
        ctk.CTkLabel(
            parent,
            text=label,
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        ).grid(row=row, column=0, sticky="ew", pady=(0, 6))

        entry = ctk.CTkEntry(
            parent,
            height=42,
            placeholder_text=placeholder,
        )
        entry.grid(row=row + 1, column=0, sticky="ew", pady=(0, 14))
        return entry

    def parse_date(self, value: str) -> tuple[str, str]:
        value = value.strip()
        if not value:
            return "", ""

        for fmt in ("%Y-%m-%d", "%d %B %Y", "%d %b %Y"):
            try:
                dt = datetime.strptime(value, fmt)
                return dt.strftime("%Y-%m-%d"), dt.strftime("%d %B %Y").lstrip("0")
            except ValueError:
                pass

        return value, value

    def parse_day(self, value: str) -> str:
        value = value.strip()
        if not value:
            return ""
        if value.lower().startswith("day"):
            return value
        return f"Day {value}"

    def parse_tags(self) -> list[str]:
        return [
            tag.strip()
            for tag in self.tags_entry.get().split(",")
            if tag.strip()
        ]

    def generate_html(self) -> str:
        image_url = self.image_url.get().strip()
        page_url = self.page_url.get().strip()
        date_machine, date_display = self.parse_date(
            self.date_entry.get()
        )
        day = self.parse_day(self.day_entry.get())
        title = self.title_entry.get().strip()
        tags = self.parse_tags()

        title_html = ""
        if title:
            title_html = f"""
      <span class="cherry-travel-card__title">
        {html.escape(title)}
      </span>
"""

        tags_html = "\n".join(
            f"""        <span class="cherry-travel-card__place">
          {html.escape(tag)}
        </span>"""
            for tag in tags
        )

        return f"""{CARD_CSS}

<div class="cherry-travel-card-wrap">

  <a
    class="cherry-travel-card"
    href="{html.escape(page_url, quote=True)}"
    style="--cherry-card-image: url('{html.escape(image_url, quote=True)}');">

    <span class="cherry-travel-card__content">

      <span class="cherry-travel-card__meta">
        <time datetime="{html.escape(date_machine, quote=True)}">
          {html.escape(date_display)}
        </time>

        <span class="cherry-travel-card__day">
          {html.escape(day)}
        </span>
      </span>
{title_html}
      <span class="cherry-travel-card__places">
{tags_html}
      </span>

      <span class="cherry-travel-card__arrow" aria-hidden="true">
        →
      </span>

    </span>

  </a>

</div>"""

    def on_changed(self, _event=None) -> None:
        self.update_preview()
        self.status.configure(text="")

    def update_preview(self) -> None:
        self.set_textbox_value(self.preview, self.generate_html())

    def copy_html(self) -> None:
        required = {
            "WebP画像URL": self.image_url.get().strip(),
            "ページ遷移先URL": self.page_url.get().strip(),
            "日付": self.date_entry.get().strip(),
            "DAY": self.day_entry.get().strip(),
        }
        missing = [name for name, value in required.items() if not value]

        if missing:
            messagebox.showwarning(
                "入力エラー",
                "次を入力してください：\n" + "\n".join(missing),
            )
            return

        generated = self.generate_html()
        self.copy_to_clipboard(generated)
        self.copy_button.configure(text="Copied!")
        self.status.configure(text="HTMLをクリップボードにコピーしました。")
        self.app.after(
            1500,
            lambda: self.copy_button.configure(text="Copy HTML"),
        )

    def clear(self) -> None:
        for entry in (
            self.image_url,
            self.page_url,
            self.date_entry,
            self.day_entry,
            self.title_entry,
            self.tags_entry,
        ):
            entry.delete(0, "end")

        self.update_preview()
        self.status.configure(text="入力内容を消去しました。")


TAB_PLUGIN = ImageThumbnailTab

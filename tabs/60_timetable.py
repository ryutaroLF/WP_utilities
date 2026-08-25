from __future__ import annotations

import html
from tkinter import messagebox

import customtkinter as ctk

from _base import BaseTabPlugin


class TimetableTab(BaseTabPlugin):
    TAB_TITLE = "Timetable"
    ORDER = 60

    INITIAL_ROWS = 6

    def __init__(self, app, tabview) -> None:
        super().__init__(app, tabview)
        self.rows: list[dict[str, object]] = []
        self._copy_after_id = None

    def create_ui(self) -> None:
        tab = self.tab
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(
            tab,
            text=(
                "時間と項目を表形式で入力すると、"
                '<ul class="travel-timeline">...</ul> を生成します。'
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
        # Input table
        # ------------------------------------------------------------
        table_outer = ctk.CTkFrame(tab)
        table_outer.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=22,
            pady=(0, 12),
        )
        table_outer.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(
            table_outer,
            fg_color=("gray88", "gray22"),
            corner_radius=8,
        )
        header.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=8,
            pady=(8, 4),
        )
        header.grid_columnconfigure(1, weight=0)
        header.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(
            header,
            text="#",
            width=44,
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=0, column=0, padx=(8, 4), pady=8)

        ctk.CTkLabel(
            header,
            text="時間",
            width=140,
            anchor="w",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=0, column=1, sticky="ew", padx=4, pady=8)

        ctk.CTkLabel(
            header,
            text="項目",
            anchor="w",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=0, column=2, sticky="ew", padx=4, pady=8)

        ctk.CTkLabel(
            header,
            text="",
            width=42,
        ).grid(row=0, column=3, padx=(4, 8), pady=8)

        self.rows_frame = ctk.CTkScrollableFrame(
            table_outer,
            height=265,
            fg_color="transparent",
        )
        self.rows_frame.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=8,
            pady=(0, 8),
        )
        self.rows_frame.grid_columnconfigure(2, weight=1)

        for _ in range(self.INITIAL_ROWS):
            self.add_row(update_preview=False)

        buttons = ctk.CTkFrame(tab, fg_color="transparent")
        buttons.grid(
            row=2,
            column=0,
            sticky="ew",
            padx=22,
            pady=(0, 12),
        )
        buttons.grid_columnconfigure(3, weight=1)

        ctk.CTkButton(
            buttons,
            text="+ 行を追加",
            width=120,
            height=38,
            command=self.add_row,
        ).grid(row=0, column=0, padx=(0, 6))

        ctk.CTkButton(
            buttons,
            text="空行を削除",
            width=120,
            height=38,
            fg_color="transparent",
            border_width=1,
            text_color=("gray15", "gray90"),
            command=self.remove_empty_rows,
        ).grid(row=0, column=1, padx=6)

        ctk.CTkButton(
            buttons,
            text="Clear",
            width=90,
            height=38,
            fg_color="transparent",
            border_width=1,
            text_color=("gray15", "gray90"),
            command=self.clear,
        ).grid(row=0, column=2, padx=6)

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
            width=210,
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
    # Row management
    # ------------------------------------------------------------
    def add_row(self, update_preview: bool = True) -> None:
        row_index = len(self.rows)

        number_label = ctk.CTkLabel(
            self.rows_frame,
            text=str(row_index + 1),
            width=44,
            text_color=("gray40", "gray65"),
        )
        number_label.grid(
            row=row_index,
            column=0,
            padx=(4, 4),
            pady=4,
        )

        time_entry = ctk.CTkEntry(
            self.rows_frame,
            width=140,
            height=38,
            placeholder_text="10:30",
        )
        time_entry.grid(
            row=row_index,
            column=1,
            sticky="ew",
            padx=4,
            pady=4,
        )

        item_entry = ctk.CTkEntry(
            self.rows_frame,
            height=38,
            placeholder_text="Avebury",
        )
        item_entry.grid(
            row=row_index,
            column=2,
            sticky="ew",
            padx=4,
            pady=4,
        )

        delete_button = ctk.CTkButton(
            self.rows_frame,
            text="×",
            width=38,
            height=38,
            fg_color="transparent",
            border_width=1,
            text_color=("gray20", "gray85"),
            hover_color=("gray82", "gray28"),
        )
        delete_button.grid(
            row=row_index,
            column=3,
            padx=(4, 4),
            pady=4,
        )

        row_data = {
            "number": number_label,
            "time": time_entry,
            "item": item_entry,
            "delete": delete_button,
        }
        self.rows.append(row_data)

        delete_button.configure(
            command=lambda row=row_data: self.delete_row(row)
        )

        time_entry.bind("<KeyRelease>", self.on_changed)
        item_entry.bind("<KeyRelease>", self.on_changed)

        # Excel-like keyboard movement.
        time_entry.bind(
            "<Return>",
            lambda event, row=row_data: self.focus_next_row(row, "time"),
        )
        item_entry.bind(
            "<Return>",
            lambda event, row=row_data: self.focus_next_row(row, "item"),
        )

        if update_preview:
            self.refresh_rows()
            self.update_preview()

    def delete_row(self, row_data: dict[str, object]) -> None:
        if row_data not in self.rows:
            return

        for widget in row_data.values():
            widget.destroy()

        self.rows.remove(row_data)

        if not self.rows:
            self.add_row(update_preview=False)

        self.refresh_rows()
        self.update_preview()

    def refresh_rows(self) -> None:
        for index, row_data in enumerate(self.rows):
            row_data["number"].configure(text=str(index + 1))

            row_data["number"].grid_configure(row=index)
            row_data["time"].grid_configure(row=index)
            row_data["item"].grid_configure(row=index)
            row_data["delete"].grid_configure(row=index)

    def remove_empty_rows(self) -> None:
        rows_to_remove = []

        for row_data in self.rows:
            time_value = row_data["time"].get().strip()
            item_value = row_data["item"].get().strip()

            if not time_value and not item_value:
                rows_to_remove.append(row_data)

        # Keep at least one row.
        if len(rows_to_remove) == len(self.rows):
            rows_to_remove = rows_to_remove[:-1]

        for row_data in rows_to_remove:
            for widget in row_data.values():
                widget.destroy()
            self.rows.remove(row_data)

        self.refresh_rows()
        self.update_preview()
        self.status.configure(
            text=f"空行を {len(rows_to_remove)} 行削除しました。"
        )

    def focus_next_row(
        self,
        current_row: dict[str, object],
        column: str,
    ) -> str:
        try:
            index = self.rows.index(current_row)
        except ValueError:
            return "break"

        next_index = index + 1

        if next_index >= len(self.rows):
            self.add_row(update_preview=False)
            self.refresh_rows()

        self.rows[next_index][column].focus_set()
        self.update_preview()
        return "break"

    # ------------------------------------------------------------
    # HTML generation
    # ------------------------------------------------------------
    def get_values(self) -> list[tuple[str, str]]:
        values = []

        for row_data in self.rows:
            time_value = row_data["time"].get().strip()
            item_value = row_data["item"].get().strip()

            # Completely empty rows do not become HTML.
            if not time_value and not item_value:
                continue

            values.append((time_value, item_value))

        return values

    def generate_html(self) -> str:
        values = self.get_values()

        lines = ['<ul class="travel-timeline">']

        for time_value, item_value in values:
            escaped_time = html.escape(time_value)
            escaped_item = html.escape(item_value)

            lines.append("  <li>")

            if time_value:
                lines.append(f"    <time>{escaped_time}</time>")

            if item_value:
                lines.append(f"    {escaped_item}")

            lines.append("  </li>")

        lines.append("</ul>")

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

        if not values:
            messagebox.showwarning(
                "入力エラー",
                "時間または項目を1行以上入力してください。",
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

    def clear(self) -> None:
        for row_data in self.rows:
            row_data["time"].delete(0, "end")
            row_data["item"].delete(0, "end")

        self.update_preview()
        self.status.configure(text="入力内容を消去しました.")

        if self.rows:
            self.rows[0]["time"].focus_set()


TAB_PLUGIN = TimetableTab

from __future__ import annotations

import customtkinter as ctk


class BaseTabPlugin:
    TAB_TITLE = "Untitled"
    ORDER = 999

    def __init__(self, app, tabview) -> None:
        self.app = app
        self.tabview = tabview
        self.tab = None

    def build(self) -> None:
        self.tab = self.tabview.add(self.TAB_TITLE)
        self.create_ui()

    def create_ui(self) -> None:
        raise NotImplementedError

    def copy_to_clipboard(self, text: str) -> None:
        self.app.clipboard_clear()
        self.app.clipboard_append(text)
        self.app.update()

    @staticmethod
    def set_textbox_value(textbox: ctk.CTkTextbox, value: str) -> None:
        textbox.configure(state="normal")
        textbox.delete("1.0", "end")
        textbox.insert("1.0", value)
        textbox.configure(state="disabled")

from __future__ import annotations

import importlib.util
import sys
import traceback
from pathlib import Path

import customtkinter as ctk
from tkinterdnd2 import TkinterDnD


APP_TITLE = "Cherry Utility"
APP_GEOMETRY = "1180x900"
APP_MINSIZE = (980, 760)


class CherryUtilityApp(TkinterDnD.DnDWrapper, ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        self.TkdndVersion = TkinterDnD._require(self)

        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")

        self.title(APP_TITLE)
        self.geometry(APP_GEOMETRY)
        self.minsize(*APP_MINSIZE)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.main_frame = ctk.CTkFrame(
            self,
            corner_radius=20,
            border_width=1,
        )
        self.main_frame.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=20,
            pady=20,
        )
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(1, weight=1)

        title = ctk.CTkLabel(
            self.main_frame,
            text=APP_TITLE,
            font=ctk.CTkFont(size=28, weight="bold"),
            anchor="w",
        )
        title.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=26,
            pady=(22, 12),
        )

        self.tabview = ctk.CTkTabview(
            self.main_frame,
            corner_radius=14,
        )
        self.tabview.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=18,
            pady=(0, 18),
        )

        self.loaded_plugins = []
        self.load_tab_plugins()

    def load_tab_plugins(self) -> None:
        tabs_path = Path(__file__).resolve().parent / "tabs"

        if not tabs_path.exists():
            raise RuntimeError(f"tabs directory not found: {tabs_path}")

        if str(tabs_path) not in sys.path:
            sys.path.insert(0, str(tabs_path))

        plugin_files = sorted(
            path
            for path in tabs_path.glob("*.py")
            if not path.name.startswith("_")
        )

        loaded_count = 0
        errors: list[str] = []

        for plugin_path in plugin_files:
            try:
                module_name = f"cherry_tab_{plugin_path.stem}"

                spec = importlib.util.spec_from_file_location(
                    module_name,
                    plugin_path,
                )
                if spec is None or spec.loader is None:
                    raise ImportError(
                        f"Could not create import spec: {plugin_path.name}"
                    )

                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)

                plugin_class = getattr(module, "TAB_PLUGIN", None)
                if plugin_class is None:
                    continue

                plugin = plugin_class(
                    app=self,
                    tabview=self.tabview,
                )

                if not hasattr(plugin, "build"):
                    raise TypeError(
                        f"{plugin_path.name}: TAB_PLUGIN must provide build()."
                    )

                plugin.build()
                self.loaded_plugins.append(plugin)
                loaded_count += 1

            except Exception:
                errors.append(
                    f"{plugin_path.name}\n"
                    f"{traceback.format_exc()}"
                )

        if loaded_count == 0:
            empty_tab = self.tabview.add("No Tabs")
            label = ctk.CTkLabel(
                empty_tab,
                text=(
                    "読み込めるタブがありません。\n"
                    "tabsフォルダへTAB_PLUGINを定義した.pyを追加してください。"
                ),
                justify="center",
            )
            label.pack(expand=True, padx=20, pady=20)

        if errors:
            print("\n\n".join(errors), file=sys.stderr)


if __name__ == "__main__":
    app = CherryUtilityApp()
    app.mainloop()

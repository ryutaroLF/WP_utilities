# Cherry Utility - Modular Tab Application

## 起動

```bash
pip install -r requirements.txt
python main.py
```

## 構成

```text
map_utility_modular/
├─ main.py
├─ requirements.txt
├─ README.md
└─ tabs/
   ├─ _base.py
   ├─ 10_map_html.py
   ├─ 20_youtube.py
   ├─ 30_image_thumbnail.py
   ├─ 40_extract_gps.py
   └─ 50_crop360.py
```

`main.py` は `tabs` フォルダ直下の `.py` ファイルを自動検索します。

ただし、ファイル名が `_` で始まるファイルは読み込み対象外です。
`_base.py` は共通処理なので自動タブ化されません。

## 新しいタブの追加方法

`tabs/60_example.py` のようなファイルを追加します。

```python
import customtkinter as ctk
from _base import BaseTabPlugin


class ExampleTab(BaseTabPlugin):
    TAB_TITLE = "Example"

    def create_ui(self):
        ctk.CTkLabel(
            self.tab,
            text="新しいタブ",
        ).pack(padx=20, pady=20)


TAB_PLUGIN = ExampleTab
```

アプリを再起動すると、自動で読み込まれます。

## 現在のタブ

- Generate HTML
- YouTube
- Image-Thumbnail
- Extract GPS
- Crop360

## 注意事項

- YouTubeタブは、URL入力後にHTMLを自動コピーします。
- Image-Thumbnailのカテゴリータグは半角コンマ区切りです。
- Crop360は元画像のフォルダ内に `crop` フォルダを作成します。

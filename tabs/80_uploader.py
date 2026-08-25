import base64
import csv
import json
import shlex
import queue
import threading
import subprocess
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

from _base import BaseTabPlugin

try:
    from PIL import Image, ImageOps
except ImportError:
    Image = None
    ImageOps = None


# ============================================================
# User-editable constants
# ============================================================
# ここを変えると，GUI起動時の初期値と生成ファイル名が変わります。
#
# 現在の既定値:
#   raw    : オリジナルをそのまま転送
#   medium : 本文表示用。長辺 720px / WebP q80
#   small  : 一覧表示用。長辺 240px / WebP q60
#   large  : 作らない。manifest上の large_src は medium_src と同じにする。
#
# 一覧表示をさらに軽くしたい場合の候補:
#   DEFAULT_SMALL_MAX_SIDE = 160
#   DEFAULT_SMALL_WEBP_QUALITY = 45
# ============================================================

SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
OUTPUT_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

DEFAULT_PI_LOGIN = "cherry@192.168.1.33"
DEFAULT_REMOTE_UPLOADS_ROOT = "/mnt/crucial/WP/wp-content/uploads"

DEFAULT_MEDIUM_MAX_SIDE = 720
DEFAULT_MEDIUM_WEBP_QUALITY = 80

DEFAULT_SMALL_MAX_SIDE = 160
DEFAULT_SMALL_WEBP_QUALITY = 45

DEFAULT_FORCE_REBUILD_MEDIUM_SMALL = False

DEFAULT_WP_CONTAINER = "my-wordpress-wordpress-1"
DEFAULT_WP_NETWORK = "my-wordpress_default"
DEFAULT_WP_DB_HOST = "db"
DEFAULT_WP_DB_USER = "cherry"
DEFAULT_WP_DB_PASSWORD = ""
DEFAULT_WP_DB_NAME = "wordpress"

JOB_LIST_HEIGHT = 180
LOG_TEXT_HEIGHT = 28


# =========================
# Image resize functions
# =========================

def _validate_positive_int(value: str, name: str) -> int:
    try:
        ivalue = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer: {value}") from exc
    if ivalue <= 0:
        raise ValueError(f"{name} must be positive: {value}")
    return ivalue


def resize_keep_aspect(img, max_side: int):
    """Resize an image so that the longer side becomes max_side."""
    width, height = img.size

    if width <= 0 or height <= 0:
        raise ValueError(f"Invalid image size: {width}x{height}")

    if width >= height:
        new_width = max_side
        new_height = round(height * max_side / width)
    else:
        new_height = max_side
        new_width = round(width * max_side / height)

    return img.resize((new_width, new_height), Image.Resampling.LANCZOS)


def make_resized_image(
    src_path: Path,
    dst_path: Path,
    max_side: int,
    quality: int,
    output_format: str,
) -> tuple[int, int]:
    if Image is None or ImageOps is None:
        raise RuntimeError("Pillow is not installed. Please run: pip install pillow")

    output_format = output_format.upper().strip()
    if output_format not in {"JPEG", "WEBP"}:
        raise ValueError(f"Unsupported output format: {output_format}")

    with Image.open(src_path) as img:
        # EXIFのOrientationを反映して，画像本体を正しい向きにする。
        img = ImageOps.exif_transpose(img)
        img = resize_keep_aspect(img, max_side)

        dst_path.parent.mkdir(parents=True, exist_ok=True)

        if output_format == "JPEG":
            # JPEGはアルファチャンネルを持てないのでRGBへ変換する。
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")

            # 元のEXIFは保存しない。
            # 古いOrientation情報が残ると，縦画像が横向きになる原因になる。
            img.save(
                dst_path,
                "JPEG",
                quality=quality,
                optimize=True,
                progressive=True,
            )

        elif output_format == "WEBP":
            # 写真用途なので基本はRGBにそろえる。
            # 透過PNG等を扱う必要がある場合はRGBA保持に変えてもよい。
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")

            img.save(
                dst_path,
                "WEBP",
                quality=quality,
                method=6,
            )

        return img.size


def make_variant_output_name(
    src_path: Path,
    index: int,
    label: str,
    max_side: int,
    quality: int,
    ext: str,
) -> str:
    """
    Build a name that encodes the generated image settings.

    Example:
        0001_IMG_1234_m720_q80.webp
        0001_IMG_1234_s480_q72.webp

    This makes it safe to reuse an existing file when the same settings are used,
    while naturally generating a new file when the size or quality changes.
    """
    ext = ext if ext.startswith(".") else f".{ext}"
    return f"{index:04d}_{src_path.stem}_{label}{max_side}_q{quality}{ext.lower()}"


def get_image_size(path: Path) -> tuple[int, int]:
    if Image is None:
        raise RuntimeError("Pillow is not installed. Please run: pip install pillow")
    with Image.open(path) as img:
        return img.size


def make_resized_image_if_needed(
    src_path: Path,
    dst_path: Path,
    max_side: int,
    quality: int,
    output_format: str,
    force: bool,
    log,
) -> tuple[int, int]:
    """
    Create a resized image when needed.

    If force=False and a same-name output already exists, reuse it only when
    the image dimensions match the requested max_side. The quality and format
    are encoded in the filename, so a different quality naturally produces a
    different output file.
    """
    existed_before = dst_path.exists() and dst_path.is_file()

    if existed_before and not force:
        width, height = get_image_size(dst_path)
        if max(width, height) == max_side:
            log(f"  skip existing: {dst_path.name} ({width}x{height}, {output_format}, q={quality})")
            return width, height

        log(
            f"  existing size mismatch, recreate: {dst_path.name} "
            f"({width}x{height}, expected long side={max_side})"
        )

    width, height = make_resized_image(
        src_path=src_path,
        dst_path=dst_path,
        max_side=max_side,
        quality=quality,
        output_format=output_format,
    )
    action = "recreated" if existed_before else "created"
    log(f"  {action}: {dst_path.name} ({width}x{height}, {output_format}, q={quality})")
    return width, height


def clean_generated_images(folder: Path, log):
    """Remove old generated image files from a generated output folder."""
    if not folder.exists():
        return

    removed = 0
    for path in folder.iterdir():
        if path.is_file() and path.suffix.lower() in OUTPUT_IMAGE_EXTS:
            path.unlink()
            removed += 1

    if removed:
        log(f"  removed old generated images from {folder.name}: {removed} files")


def raw_dir_has_images(raw_dir: Path) -> bool:
    if not raw_dir.is_dir():
        return False
    try:
        return any(
            p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
            for p in raw_dir.iterdir()
        )
    except OSError:
        return False


def find_raw_dirs(parent_dir: Path) -> list[Path]:
    """Find all directories named raw under parent_dir that contain supported images."""
    parent_dir = parent_dir.resolve()
    if not parent_dir.exists():
        raise FileNotFoundError(f"Parent folder does not exist: {parent_dir}")
    if not parent_dir.is_dir():
        raise NotADirectoryError(f"Parent path is not a folder: {parent_dir}")

    raw_dirs = []
    for path in parent_dir.rglob("*"):
        if path.is_dir() and path.name.lower() == "raw" and raw_dir_has_images(path):
            raw_dirs.append(path.resolve())

    return sorted(raw_dirs, key=lambda p: str(p).lower())


def make_subdir_from_raw_parent(search_parent: Path, raw_dir: Path) -> str:
    """
    Build an upload subfolder from the raw folder's parent.

    Example:
        search_parent = F:/Trip
        raw_dir       = F:/Trip/day1/raw
        subdir        = day1

        search_parent = F:/Trip
        raw_dir       = F:/Trip/taiwan/day1/raw
        subdir        = taiwan/day1
    """
    search_parent = search_parent.resolve()
    raw_parent = raw_dir.resolve().parent

    try:
        rel = raw_parent.relative_to(search_parent)
        subdir = rel.as_posix()
    except ValueError:
        subdir = raw_parent.name

    if subdir in {"", "."}:
        subdir = raw_parent.name

    return normalize_subdir(subdir)


def resize_images(
    raw_dir: Path,
    upload_subdir: str,
    medium_side: int,
    small_side: int,
    medium_quality: int,
    small_quality: int,
    force_rebuild_medium_small: bool,
    log,
) -> Path:
    raw_dir = raw_dir.resolve()
    if not raw_dir.exists():
        raise FileNotFoundError(f"raw_dir does not exist: {raw_dir}")
    if not raw_dir.is_dir():
        raise NotADirectoryError(f"raw_dir is not a directory: {raw_dir}")

    base_dir = raw_dir.parent
    medium_dir = base_dir / "medium"
    small_dir = base_dir / "small"

    medium_dir.mkdir(parents=True, exist_ok=True)
    small_dir.mkdir(parents=True, exist_ok=True)

    # 方針：
    # - raw: オリジナルをそのまま使う。
    # - medium: 本文表示用。WebP, 長辺 medium_side px, quality medium_quality。
    # - small: 一覧表示用。WebP, 長辺 small_side px, quality small_quality。
    # - large: 作らない。
    #
    # 互換性のため，manifest のキー名は medium_src / small_src を維持する。
    # さらに，既存JSが large_src を参照していても壊れないように，large_src には medium_src と同じURLを入れる。
    medium_ext = ".webp"
    small_ext = ".webp"

    images = sorted(
        p for p in raw_dir.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
    )

    if not images:
        raise RuntimeError(f"No supported images found in: {raw_dir}")

    manifest_path = base_dir / "gallery-manifest.json"
    tmp_manifest_path = base_dir / "gallery-manifest.json.tmp"

    upload_url_base = f"/wp-content/uploads/{upload_subdir}"

    log(f"Raw folder:    {raw_dir}")
    log(f"Medium folder: {medium_dir} (WebP, long side={medium_side}, q={medium_quality})")
    log(f"Small folder:  {small_dir}  (WebP, long side={small_side}, q={small_quality})")
    log(f"Manifest JSON: {manifest_path}")
    log("")

    manifest = {
        "version": 2,
        "base_url": upload_url_base,
        "manifest_url": f"{upload_url_base}/gallery-manifest.json",
        "images": [],
    }

    # Rebuild gallery-manifest.json from the current raw folder every time.
    # This avoids duplicated rows even if the workflow is run multiple times.
    for i, src_path in enumerate(images, start=1):
        medium_name = make_variant_output_name(
            src_path, i, "m", medium_side, medium_quality, medium_ext
        )
        small_name = make_variant_output_name(
            src_path, i, "s", small_side, small_quality, small_ext
        )
        log(f"[{i}/{len(images)}] {src_path.name}")

        medium_w, medium_h = make_resized_image_if_needed(
            src_path=src_path,
            dst_path=medium_dir / medium_name,
            max_side=medium_side,
            quality=medium_quality,
            output_format="WEBP",
            force=force_rebuild_medium_small,
            log=log,
        )
        small_w, small_h = make_resized_image_if_needed(
            src_path=src_path,
            dst_path=small_dir / small_name,
            max_side=small_side,
            quality=small_quality,
            output_format="WEBP",
            force=force_rebuild_medium_small,
            log=log,
        )

        raw_href = f"{upload_url_base}/raw/{src_path.name}"
        medium_src = f"{upload_url_base}/medium/{medium_name}"
        small_src = f"{upload_url_base}/small/{small_name}"

        manifest["images"].append({
            "index": i,
            "source_filename": src_path.name,

            # 互換性維持：従来キーは残す。
            # large画像は作らないので，large_* は medium と同じ実体を指す。
            "large_filename": medium_name,
            "medium_filename": medium_name,
            "small_filename": small_name,

            # 投稿本文で使うリンク先・表示画像。
            "raw_href": raw_href,
            "medium_src": medium_src,

            # contact sheet / modal 用JavaScriptが使う可能性のあるキー。
            # large_src はリンク切れ防止のため medium_src と同じにする。
            "large_src": medium_src,
            "small_src": small_src,

            "large_width": medium_w,
            "large_height": medium_h,
            "medium_width": medium_w,
            "medium_height": medium_h,
            "small_width": small_w,
            "small_height": small_h,
        })

    with tmp_manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    tmp_manifest_path.replace(manifest_path)

    log("Resize done. medium/small are WebP, same-setting files were skipped, and gallery-manifest.json was rebuilt.")
    return base_dir


# =========================
# Shell helpers
# =========================

def run_process(args, log, cwd=None):
    log(f"$ {' '.join(shlex.quote(str(a)) for a in args)}")

    proc = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd,
    )

    assert proc.stdout is not None
    for line in proc.stdout:
        log(line.rstrip("\n"))

    code = proc.wait()
    if code != 0:
        raise RuntimeError(f"Command failed with exit code {code}: {' '.join(map(str, args))}")


def run_wsl_bash(script: str, log):
    run_process(["wsl", "bash", "-lc", script], log)


def windows_path_to_wsl(path: Path, log) -> str:
    p = str(path.resolve())

    # wslpath can misread backslashes from Windows paths.
    # Use forward slashes before passing the path to WSL.
    p_for_wslpath = p.replace("\\", "/")

    cmd = ["wsl", "wslpath", "-a", p_for_wslpath]
    log(f"$ {' '.join(shlex.quote(str(a)) for a in cmd)}")

    try:
        out = subprocess.check_output(
            cmd,
            text=True,
            encoding="utf-8",
            errors="replace",
            stderr=subprocess.STDOUT,
        )
        return out.strip()
    except subprocess.CalledProcessError as e:
        log("wslpath failed. Output:")
        log((e.output or "").rstrip())

        # Manual fallback for normal drive-letter paths.
        # Example: F:/Taiwan2026/day1 -> /mnt/f/Taiwan2026/day1
        if len(p_for_wslpath) >= 3 and p_for_wslpath[1] == ":" and p_for_wslpath[2] == "/":
            drive = p_for_wslpath[0].lower()
            rest = p_for_wslpath[3:]
            fallback = f"/mnt/{drive}/{rest}"
            log(f"Fallback WSL path: {fallback}")
            return fallback

        raise RuntimeError(f"Could not convert Windows path to WSL path: {p}")


def normalize_subdir(subdir: str) -> str:
    subdir = subdir.strip().replace("\\", "/")
    subdir = subdir.strip("/")
    if not subdir:
        raise ValueError("Subfolder is empty. Example: kyoto2026_04")
    if ".." in subdir.split("/"):
        raise ValueError("Subfolder must not contain '..'")
    return subdir


def shell_quote(s: str) -> str:
    return shlex.quote(s)


def remote_user_from_login(pi_login: str) -> str:
    """Extract the remote user name from a simple SSH login string."""
    login = pi_login.strip()
    if "@" in login:
        return login.split("@", 1)[0].strip()
    return login.split()[0].strip() or "cherry"


def read_jobs_csv(csv_path: Path) -> list[dict]:
    """
    Read upload jobs from a simple CSV file.

    Expected format, without requiring a header:
        raw_dir,subdir
        F:/Trip/day1/raw,taiwan2026_day1

    A header row such as raw_dir,subdir is also accepted.
    Lines starting with # are ignored.
    """
    csv_path = csv_path.resolve()
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file does not exist: {csv_path}")
    if not csv_path.is_file():
        raise FileNotFoundError(f"CSV path is not a file: {csv_path}")

    jobs = []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        for line_no, row in enumerate(reader, start=1):
            if not row:
                continue

            # Remove surrounding spaces but keep spaces inside paths.
            row = [col.strip() for col in row]
            if not row[0] or row[0].startswith("#"):
                continue

            if line_no == 1 and row[0].lower() in {"raw_dir", "raw folder", "raw_folder", "path"}:
                continue

            if len(row) < 2:
                raise ValueError(f"CSV line {line_no}: expected raw_dir,subdir")

            raw_dir = row[0].strip()
            subdir = normalize_subdir(row[1].strip())

            if not raw_dir:
                raise ValueError(f"CSV line {line_no}: raw_dir is empty")
            if not subdir:
                raise ValueError(f"CSV line {line_no}: subdir is empty")

            jobs.append({"raw_dir": raw_dir, "subdir": subdir})

    if not jobs:
        raise ValueError(f"No valid jobs found in CSV: {csv_path}")

    return jobs


# =========================
# Main workflow
# =========================

def run_one_job(common_settings: dict, job: dict, job_index: int, total_jobs: int, log):
    pi_login = common_settings["pi_login"].strip()
    remote_uploads_root = common_settings["remote_uploads_root"].strip().rstrip("/")
    wp_container = common_settings["wp_container"].strip()
    wp_network = common_settings["wp_network"].strip()
    wp_db_host = common_settings["wp_db_host"].strip()
    wp_db_user = common_settings["wp_db_user"].strip()
    wp_db_password = common_settings["wp_db_password"]
    wp_db_name = common_settings["wp_db_name"].strip()

    raw_dir = Path(job["raw_dir"].strip())
    subdir = normalize_subdir(job["subdir"])
    post_title = subdir

    if not pi_login:
        raise ValueError("Raspberry Pi login is empty.")
    if not wp_db_password:
        raise ValueError("WordPress DB password is empty.")

    medium_side = _validate_positive_int(common_settings["medium_side"], "Medium max side")
    small_side = _validate_positive_int(common_settings["small_side"], "Small max side")
    medium_quality = _validate_positive_int(common_settings["medium_quality"], "Medium WebP quality")
    small_quality = _validate_positive_int(common_settings["small_quality"], "Small WebP quality")
    force_rebuild_medium_small = bool(common_settings.get("force_rebuild_medium_small", True))

    remote_target = f"{remote_uploads_root}/{subdir}"
    wp_upload_subdir = f"wp-content/uploads/{subdir}"

    log("")
    log("============================================================")
    log(f"JOB {job_index}/{total_jobs}: {subdir}")
    log("============================================================")

    log("=== 1. Resize images and create gallery-manifest.json ===")
    base_dir = resize_images(
        raw_dir=raw_dir,
        upload_subdir=subdir,
        medium_side=medium_side,
        small_side=small_side,
        medium_quality=medium_quality,
        small_quality=small_quality,
        force_rebuild_medium_small=force_rebuild_medium_small,
        log=log,
    )
    log("")

    log("=== 2. Prepare remote upload directory ===")
    # /mnt/kingston や /mnt/crucial 側が root 所有などで cherry が直接 mkdir できない場合がある。
    # v2では remote shell 内の $TARGET 展開が環境によって空になるケースがあったため，
    # v3では $TARGET 変数を使わず，パスを各コマンドに直接クォートして渡す。
    remote_user = remote_user_from_login(pi_login)
    remote_target_q = shell_quote(remote_target)
    remote_raw_q = shell_quote(f"{remote_target}/raw")
    remote_medium_q = shell_quote(f"{remote_target}/medium")
    remote_small_q = shell_quote(f"{remote_target}/small")
    remote_user_q = shell_quote(remote_user)

    remote_prepare_inner = f"""
set -e

if mkdir -p {remote_target_q} 2>/dev/null && test -w {remote_target_q}; then
  :
else
  sudo -n mkdir -p {remote_target_q}
  sudo -n chown -R {remote_user_q} {remote_target_q}
fi

mkdir -p {remote_raw_q} {remote_medium_q} {remote_small_q}
""".strip()

    mkdir_script = (
        f"ssh -o BatchMode=yes -o ConnectTimeout=10 {shell_quote(pi_login)} "
        f"{shell_quote(remote_prepare_inner)}"
    )
    run_wsl_bash(mkdir_script, log)
    log("")

    log("=== 3. Rsync resized folders and JSON manifest to Raspberry Pi ===")
    base_dir_wsl = windows_path_to_wsl(base_dir, log)
    medium_include = f"medium/*_m{medium_side}_q{medium_quality}.webp"
    small_include = f"small/*_s{small_side}_q{small_quality}.webp"
    rsync_script = (
        f"rsync -avh --progress "
        f"--include='raw/***' "
        f"--include='medium/' "
        f"--include={shell_quote(medium_include)} "
        f"--include='small/' "
        f"--include={shell_quote(small_include)} "
        f"--include='gallery-manifest.json' "
        f"--exclude='*' "
        f"{shell_quote(base_dir_wsl.rstrip('/') + '/')} "
        f"{shell_quote(pi_login + ':' + remote_target.rstrip('/') + '/')}"
    )
    run_wsl_bash(rsync_script, log)
    log("")

    log("=== 4. Register medium images with WordPress CLI ===")
    # Register medium images because the generated post embeds medium images.
    register_ids_path = f"{remote_target}/{subdir}_medium_ids_all.txt"
    register_inner_cmd = (
        f"cd /var/www/html && "
        f"find {wp_upload_subdir}/medium -maxdepth 1 -type f -iname '*.webp' | sort | "
        "xargs -r -I {} wp media import {} --skip-copy --porcelain"
    )

    register_cmd = f"""
cd ~/my-wordpress && docker run --rm \\
  --volumes-from {shell_quote(wp_container)} \\
  --network {shell_quote(wp_network)} \\
  -e WORDPRESS_DB_HOST={shell_quote(wp_db_host)} \\
  -e WORDPRESS_DB_USER={shell_quote(wp_db_user)} \\
  -e WORDPRESS_DB_PASSWORD={shell_quote(wp_db_password)} \\
  -e WORDPRESS_DB_NAME={shell_quote(wp_db_name)} \\
  wordpress:cli \\
  sh -c {shell_quote(register_inner_cmd)} \\
  > {shell_quote(register_ids_path)}
""".strip()
    run_wsl_bash(f"ssh {shell_quote(pi_login)} {shell_quote(register_cmd)}", log)
    log("")

    log("=== 5. Create WordPress draft post ===")
    create_post_inner = f'''
cd /var/www/html

SITE_URL=$(wp --path=/var/www/html option get siteurl)
export SITE_URL

MANIFEST="wp-content/uploads/{subdir}/gallery-manifest.json"
CONTENT_FILE="/tmp/{subdir}_post_content.html"

php <<'PHP'
<?php
$site_url = rtrim(getenv("SITE_URL"), "/");
$manifest_path = "wp-content/uploads/{subdir}/gallery-manifest.json";
$content_file = "/tmp/{subdir}_post_content.html";

$json = file_get_contents($manifest_path);
if ($json === false) {{
    fwrite(STDERR, "Failed to read manifest: " . $manifest_path . PHP_EOL);
    exit(1);
}}

$data = json_decode($json, true);
if (!is_array($data)) {{
    fwrite(STDERR, "Failed to decode JSON manifest: " . $manifest_path . PHP_EOL);
    exit(1);
}}

$images = $data["images"] ?? [];
$manifest_url = $data["manifest_url"] ?? "/wp-content/uploads/{subdir}/gallery-manifest.json";

$out = "";

// contact sheet用ボタン。
// JavaScriptとCSSはテーマ側で読み込む想定。
// data-gallery-json に JSON のURLを入れておく。
$out .= '<!-- wp:html -->' . PHP_EOL;
$out .= '<button class="contact-sheet-button" data-gallery-json="' . htmlspecialchars($manifest_url, ENT_QUOTES) . '">一覧表示</button>' . PHP_EOL;
$out .= '<!-- /wp:html -->' . PHP_EOL . PHP_EOL;

foreach ($images as $item) {{
    $raw_href = $item["raw_href"] ?? "";
    $medium_src = $item["medium_src"] ?? "";
    $source_filename = $item["source_filename"] ?? "";
    $medium_width = intval($item["medium_width"] ?? 0);
    $medium_height = intval($item["medium_height"] ?? 0);

    if ($raw_href === "" || $medium_src === "") {{
        continue;
    }}

    // Gutenberg の wp:image ブロックにすると，attachment ID や保存HTMLの差分で
    // 「想定されていないか無効なコンテンツ」になりやすい。
    // そのため，ここでは明示的に wp:html ブロックとして出力する。
    // URL は siteurl を付けた絶対URLではなく，/wp-content/uploads/... の root-relative のままにする。
    // これにより，管理画面のホスト名と公開URLの違いによる「外部画像」扱いを避けやすい。
    $raw_url = $raw_href;
    $medium_url = $medium_src;

    $alt = pathinfo($source_filename, PATHINFO_FILENAME);
    $alt = htmlspecialchars($alt, ENT_QUOTES);

    $size_attrs = "";
    if ($medium_width > 0 && $medium_height > 0) {{
        $size_attrs = ' width="' . $medium_width . '" height="' . $medium_height . '"';
    }}

    // 表示画像は medium WebP，クリック先は raw original。
    // Gutenberg の画像ブロックとして保存する。
    // ブロック属性にも url / href / alt / caption を入れて，
    // エディタで「対応していないブロック」になりにくくする。
    // デフォルトではキャプションを出さない。
    // 空の <figcaption></figcaption> は Gutenberg の画像ブロック検証で
    // 「想定されていないか無効なコンテンツ」になりやすいため。
    // 後からエディタでキャプションを追加した場合だけ，WordPress が正規の figcaption を保存する。
    // 公開画面での黒背景span化はテーマJS側で行う。
    $block_attrs = [
        "url" => $medium_url,
        "alt" => pathinfo($source_filename, PATHINFO_FILENAME),
        "href" => $raw_url,
        "sizeSlug" => "full",
        "linkDestination" => "custom",
        "className" => "travel-photo-figure",
    ];

    $out .= '<!-- wp:image ' . json_encode($block_attrs, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE) . ' -->' . PHP_EOL;
    $out .= '<figure class="wp-block-image size-full travel-photo-figure">';
    $out .= '<a href="' . htmlspecialchars($raw_url, ENT_QUOTES) . '">';
    $out .= '<img src="' . htmlspecialchars($medium_url, ENT_QUOTES) . '" alt="' . $alt . '" />';
    $out .= '</a>';
    $out .= '</figure>' . PHP_EOL;
    $out .= '<!-- /wp:image -->' . PHP_EOL . PHP_EOL;
}}

file_put_contents($content_file, $out);
PHP

wp --path=/var/www/html post create "$CONTENT_FILE" \\
  --post_type=post \\
  --post_status=draft \\
  --post_title={shell_quote(post_title)}
'''.strip()

    create_post_inner_b64 = base64.b64encode(create_post_inner.encode("utf-8")).decode("ascii")
    create_post_runner = (
        "printf %s "
        + shell_quote(create_post_inner_b64)
        + " | base64 -d > /tmp/create_wp_post.sh && sh /tmp/create_wp_post.sh"
    )

    create_post_cmd = f"""
cd ~/my-wordpress && docker run --rm \\
  --volumes-from {shell_quote(wp_container)} \\
  --network {shell_quote(wp_network)} \\
  -e WORDPRESS_DB_HOST={shell_quote(wp_db_host)} \\
  -e WORDPRESS_DB_USER={shell_quote(wp_db_user)} \\
  -e WORDPRESS_DB_PASSWORD={shell_quote(wp_db_password)} \\
  -e WORDPRESS_DB_NAME={shell_quote(wp_db_name)} \\
  wordpress:cli \\
  sh -c {shell_quote(create_post_runner)}
""".strip()
    run_wsl_bash(f"ssh {shell_quote(pi_login)} {shell_quote(create_post_cmd)}", log)

    log("")
    log(f"JOB DONE: {subdir}")


def run_workflow(settings: dict, log):
    jobs = settings["jobs"]

    if not jobs:
        raise ValueError("No upload jobs. Please add at least one raw folder and subfolder.")

    seen_subdirs = set()
    for i, job in enumerate(jobs, start=1):
        raw_dir = job["raw_dir"].strip()
        subdir = normalize_subdir(job["subdir"])

        if not raw_dir:
            raise ValueError(f"Job {i}: raw folder is empty.")
        if subdir in seen_subdirs:
            raise ValueError(f"Duplicate upload subfolder: {subdir}")
        seen_subdirs.add(subdir)

    total_jobs = len(jobs)

    for i, job in enumerate(jobs, start=1):
        run_one_job(settings, job, i, total_jobs, log)

    log("")
    log("ALL JOBS DONE.")

# =========================
# CustomTkinter tab GUI
# =========================


class UploadJobRow:
    """One upload job row shown inside the uploader tab."""

    def __init__(self, plugin: "UploaderTab", parent, index: int) -> None:
        self.plugin = plugin
        self.parent = parent
        self.index = index

        self.raw_dir = tk.StringVar(master=plugin.app, value="")
        self.subdir = tk.StringVar(master=plugin.app, value="")

        self.frame = ctk.CTkFrame(
            parent,
            corner_radius=10,
            fg_color=("gray94", "gray17"),
        )
        self.frame.grid(
            row=index,
            column=0,
            sticky="ew",
            padx=2,
            pady=4,
        )
        self.frame.grid_columnconfigure(1, weight=5)
        self.frame.grid_columnconfigure(4, weight=2)

        self.index_label = ctk.CTkLabel(
            self.frame,
            text=f"{index + 1:02d}",
            width=36,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=("gray38", "gray68"),
        )
        self.index_label.grid(row=0, column=0, padx=(10, 8), pady=10)

        self.raw_entry = ctk.CTkEntry(
            self.frame,
            textvariable=self.raw_dir,
            height=36,
            placeholder_text=r"F:\Trip\day1\raw",
        )
        self.raw_entry.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(0, 8),
            pady=10,
        )

        self.browse_button = ctk.CTkButton(
            self.frame,
            text="Browse",
            width=78,
            height=36,
            command=self.browse_folder,
        )
        self.browse_button.grid(row=0, column=2, padx=(0, 14), pady=10)

        ctk.CTkLabel(
            self.frame,
            text="→",
            width=20,
            text_color=("gray45", "gray60"),
        ).grid(row=0, column=3, padx=(0, 8))

        self.subdir_entry = ctk.CTkEntry(
            self.frame,
            textvariable=self.subdir,
            height=36,
            placeholder_text="upload-subfolder",
        )
        self.subdir_entry.grid(
            row=0,
            column=4,
            sticky="ew",
            padx=(0, 8),
            pady=10,
        )

        self.remove_button = ctk.CTkButton(
            self.frame,
            text="Remove",
            width=82,
            height=36,
            fg_color="transparent",
            border_width=1,
            text_color=("gray25", "gray82"),
            hover_color=("gray88", "gray24"),
            command=self.remove,
        )
        self.remove_button.grid(row=0, column=5, padx=(0, 10), pady=10)

    def browse_folder(self) -> None:
        folder = filedialog.askdirectory(
            parent=self.plugin.app,
            title="Select raw folder",
        )
        if not folder:
            return

        self.raw_dir.set(folder)

        # If subdir is empty, use the raw folder's parent folder name.
        # Example: F:/trip/day1/raw -> day1
        if not self.subdir.get().strip():
            try:
                p = Path(folder)
                candidate = p.parent.name if p.name.lower() == "raw" else p.name
                self.subdir.set(candidate)
            except Exception:
                pass

    def remove(self) -> None:
        self.plugin._remove_job_row(self)

    def destroy(self) -> None:
        self.frame.destroy()

    def set_index(self, index: int) -> None:
        self.index = index
        self.frame.grid_configure(row=index)
        self.index_label.configure(text=f"{index + 1:02d}")

    def to_dict(self) -> dict:
        return {
            "raw_dir": self.raw_dir.get(),
            "subdir": self.subdir.get(),
        }


class UploaderTab(BaseTabPlugin):
    TAB_TITLE = "uploader"
    ORDER = 80

    def __init__(self, app, tabview) -> None:
        super().__init__(app, tabview)

        self.log_queue: queue.Queue[str] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.job_rows: list[UploadJobRow] = []

        self.vars = {
            "pi_login": tk.StringVar(master=app, value=DEFAULT_PI_LOGIN),
            "remote_uploads_root": tk.StringVar(master=app, value=DEFAULT_REMOTE_UPLOADS_ROOT),
            "medium_side": tk.StringVar(master=app, value=str(DEFAULT_MEDIUM_MAX_SIDE)),
            "medium_quality": tk.StringVar(master=app, value=str(DEFAULT_MEDIUM_WEBP_QUALITY)),
            "small_side": tk.StringVar(master=app, value=str(DEFAULT_SMALL_MAX_SIDE)),
            "small_quality": tk.StringVar(master=app, value=str(DEFAULT_SMALL_WEBP_QUALITY)),
            "force_rebuild_medium_small": tk.BooleanVar(
                master=app,
                value=DEFAULT_FORCE_REBUILD_MEDIUM_SMALL,
            ),
            "find_parent_dir": tk.StringVar(master=app, value=""),
            "wp_container": tk.StringVar(master=app, value=DEFAULT_WP_CONTAINER),
            "wp_network": tk.StringVar(master=app, value=DEFAULT_WP_NETWORK),
            "wp_db_host": tk.StringVar(master=app, value=DEFAULT_WP_DB_HOST),
            "wp_db_user": tk.StringVar(master=app, value=DEFAULT_WP_DB_USER),
            "wp_db_password": tk.StringVar(master=app, value=DEFAULT_WP_DB_PASSWORD),
            "wp_db_name": tk.StringVar(master=app, value=DEFAULT_WP_DB_NAME),
        }

    def create_ui(self) -> None:
        tab = self.tab
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        # Header -----------------------------------------------------
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
            text="WordPress Uploader",
            anchor="w",
            font=ctk.CTkFont(size=23, weight="bold"),
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            title_box,
            text="Resize → transfer → register media → create draft posts",
            anchor="w",
            text_color=("gray40", "gray68"),
            font=ctk.CTkFont(size=12),
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

        self.status_badge = ctk.CTkLabel(
            header,
            text="  Ready  ",
            height=30,
            corner_radius=15,
            fg_color=("gray88", "gray24"),
            text_color=("gray30", "gray78"),
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.status_badge.grid(row=0, column=1, rowspan=2, sticky="e")

        # Whole content scrolls on smaller windows. ------------------
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
        page.grid_columnconfigure(1, weight=1)

        # Connection / image settings -------------------------------
        connection_card = self._card(page, "Connection & image settings")
        connection_card.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(0, 6),
            pady=(0, 10),
        )
        connection_card.grid_columnconfigure(1, weight=1)

        self._labeled_entry(
            connection_card,
            1,
            "Raspberry Pi login",
            "pi_login",
            placeholder="user@host",
        )
        self._labeled_entry(
            connection_card,
            2,
            "Remote uploads root",
            "remote_uploads_root",
            placeholder="/mnt/.../wp-content/uploads",
        )

        image_grid = ctk.CTkFrame(connection_card, fg_color="transparent")
        image_grid.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=14,
            pady=(8, 6),
        )
        for col in range(4):
            image_grid.grid_columnconfigure(col, weight=1)

        self._mini_entry(image_grid, 0, "Medium side", "medium_side")
        self._mini_entry(image_grid, 1, "Medium q", "medium_quality")
        self._mini_entry(image_grid, 2, "Small side", "small_side")
        self._mini_entry(image_grid, 3, "Small q", "small_quality")

        ctk.CTkCheckBox(
            connection_card,
            text="Force rebuild existing same-setting medium/small files",
            variable=self.vars["force_rebuild_medium_small"],
            checkbox_width=19,
            checkbox_height=19,
        ).grid(
            row=4,
            column=0,
            columnspan=2,
            sticky="w",
            padx=14,
            pady=(8, 14),
        )

        # WordPress / Docker settings -------------------------------
        wp_card = self._card(page, "WordPress / Docker settings")
        wp_card.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(6, 0),
            pady=(0, 10),
        )
        wp_card.grid_columnconfigure(1, weight=1)

        self._labeled_entry(wp_card, 1, "WP container", "wp_container")
        self._labeled_entry(wp_card, 2, "Docker network", "wp_network")

        db_grid = ctk.CTkFrame(wp_card, fg_color="transparent")
        db_grid.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=14,
            pady=(8, 6),
        )
        for col in range(2):
            db_grid.grid_columnconfigure(col, weight=1)

        self._mini_entry(db_grid, 0, "DB host", "wp_db_host")
        self._mini_entry(db_grid, 1, "DB user", "wp_db_user")
        self._mini_entry(db_grid, 2, "DB password", "wp_db_password", show="•", row=2)
        self._mini_entry(db_grid, 3, "DB name", "wp_db_name", row=2)

        # Upload jobs -----------------------------------------------
        jobs_card = self._card(page, "Upload jobs")
        jobs_card.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 10),
        )
        jobs_card.grid_columnconfigure(0, weight=1)

        finder = ctk.CTkFrame(jobs_card, fg_color="transparent")
        finder.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=14,
            pady=(2, 10),
        )
        finder.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            finder,
            text="Parent folder",
            width=92,
            anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=(0, 8))

        ctk.CTkEntry(
            finder,
            textvariable=self.vars["find_parent_dir"],
            height=36,
            placeholder_text="Choose a parent folder and scan for raw directories",
        ).grid(row=0, column=1, sticky="ew", padx=(0, 8))

        ctk.CTkButton(
            finder,
            text="Browse",
            width=78,
            height=36,
            command=self._browse_find_parent,
        ).grid(row=0, column=2, padx=(0, 8))

        self.find_button = ctk.CTkButton(
            finder,
            text="Find all raw folders",
            width=145,
            height=36,
            fg_color="transparent",
            border_width=1,
            text_color=("gray20", "gray88"),
            command=self._find_all_raw_folders,
        )
        self.find_button.grid(row=0, column=3)

        # Small column header for the dynamic rows.
        columns = ctk.CTkFrame(jobs_card, fg_color="transparent")
        columns.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 2))
        columns.grid_columnconfigure(1, weight=5)
        columns.grid_columnconfigure(4, weight=2)

        ctk.CTkLabel(columns, text="", width=36).grid(row=0, column=0)
        ctk.CTkLabel(
            columns,
            text="PC raw folder",
            anchor="w",
            text_color=("gray42", "gray65"),
            font=ctk.CTkFont(size=11, weight="bold"),
        ).grid(row=0, column=1, sticky="w")
        ctk.CTkLabel(columns, text="", width=78).grid(row=0, column=2)
        ctk.CTkLabel(columns, text="", width=20).grid(row=0, column=3)
        ctk.CTkLabel(
            columns,
            text="Upload subfolder",
            anchor="w",
            text_color=("gray42", "gray65"),
            font=ctk.CTkFont(size=11, weight="bold"),
        ).grid(row=0, column=4, sticky="w")
        ctk.CTkLabel(columns, text="", width=82).grid(row=0, column=5)

        self.jobs_frame = ctk.CTkScrollableFrame(
            jobs_card,
            height=175,
            corner_radius=10,
            fg_color=("gray97", "gray14"),
        )
        self.jobs_frame.grid(
            row=3,
            column=0,
            sticky="ew",
            padx=14,
            pady=(0, 10),
        )
        self.jobs_frame.grid_columnconfigure(0, weight=1)

        job_actions = ctk.CTkFrame(jobs_card, fg_color="transparent")
        job_actions.grid(
            row=4,
            column=0,
            sticky="ew",
            padx=14,
            pady=(0, 14),
        )
        job_actions.grid_columnconfigure(2, weight=1)

        self.add_job_button = ctk.CTkButton(
            job_actions,
            text="+ Add job",
            width=105,
            height=36,
            command=self._add_job_row,
        )
        self.add_job_button.grid(row=0, column=0, padx=(0, 8))

        self.load_csv_button = ctk.CTkButton(
            job_actions,
            text="Load jobs from CSV",
            width=145,
            height=36,
            fg_color="transparent",
            border_width=1,
            text_color=("gray20", "gray88"),
            command=self._load_jobs_csv,
        )
        self.load_csv_button.grid(row=0, column=1)

        ctk.CTkLabel(
            job_actions,
            text="raw_dir, subdir",
            anchor="e",
            text_color=("gray48", "gray58"),
            font=ctk.CTkFont(size=11),
        ).grid(row=0, column=2, sticky="e")

        # Run controls ----------------------------------------------
        controls = ctk.CTkFrame(page, fg_color="transparent")
        controls.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 10),
        )
        controls.grid_columnconfigure(2, weight=1)

        self.run_button = ctk.CTkButton(
            controls,
            text="Run all",
            width=150,
            height=44,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._start,
        )
        self.run_button.grid(row=0, column=0, padx=(0, 8))

        ctk.CTkButton(
            controls,
            text="Clear log",
            width=100,
            height=44,
            fg_color="transparent",
            border_width=1,
            text_color=("gray20", "gray88"),
            command=self._clear_log,
        ).grid(row=0, column=1)

        self.progress = ctk.CTkProgressBar(
            controls,
            mode="indeterminate",
            height=8,
        )
        self.progress.grid(
            row=0,
            column=2,
            sticky="ew",
            padx=(18, 0),
        )
        self.progress.set(0)

        # Terminal ---------------------------------------------------
        log_card = self._card(page, "Progress / Terminal output")
        log_card.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="nsew",
            pady=(0, 6),
        )
        log_card.grid_columnconfigure(0, weight=1)
        log_card.grid_rowconfigure(1, weight=1)

        self.log_text = ctk.CTkTextbox(
            log_card,
            height=250,
            wrap="word",
            corner_radius=10,
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self.log_text.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=14,
            pady=(2, 14),
        )
        self.log_text.configure(state="disabled")

        self._add_job_row()
        self.app.after(100, self._poll_log_queue)

    # ------------------------------------------------------------------
    # UI helpers
    # ------------------------------------------------------------------
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
            columnspan=4,
            sticky="ew",
            padx=14,
            pady=(12, 8),
        )
        return card

    def _labeled_entry(
        self,
        parent,
        row: int,
        label: str,
        key: str,
        placeholder: str = "",
        show: str | None = None,
    ) -> None:
        ctk.CTkLabel(
            parent,
            text=label,
            width=125,
            anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(
            row=row,
            column=0,
            sticky="w",
            padx=(14, 8),
            pady=6,
        )

        ctk.CTkEntry(
            parent,
            textvariable=self.vars[key],
            height=36,
            placeholder_text=placeholder,
            show=show,
        ).grid(
            row=row,
            column=1,
            sticky="ew",
            padx=(0, 14),
            pady=6,
        )

    def _mini_entry(
        self,
        parent,
        column: int,
        label: str,
        key: str,
        show: str | None = None,
        row: int = 0,
    ) -> None:
        # column can be 0..3. For a 2-column DB grid, callers may pass row=2.
        actual_col = column
        actual_row = row

        if row == 2:
            actual_col = column - 2
            actual_row = 2

        box = ctk.CTkFrame(parent, fg_color="transparent")
        box.grid(
            row=actual_row,
            column=actual_col,
            sticky="ew",
            padx=(0 if actual_col == 0 else 5, 5 if actual_col == 0 else 0),
            pady=(0, 6),
        )
        box.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            box,
            text=label,
            anchor="w",
            text_color=("gray42", "gray68"),
            font=ctk.CTkFont(size=11, weight="bold"),
        ).grid(row=0, column=0, sticky="ew", pady=(0, 3))

        ctk.CTkEntry(
            box,
            textvariable=self.vars[key],
            height=34,
            show=show,
        ).grid(row=1, column=0, sticky="ew")

    # ------------------------------------------------------------------
    # Job actions
    # ------------------------------------------------------------------
    def _browse_find_parent(self) -> None:
        folder = filedialog.askdirectory(
            parent=self.app,
            title="Select parent folder to search raw folders",
        )
        if folder:
            self.vars["find_parent_dir"].set(folder)

    def _find_all_raw_folders(self) -> None:
        parent = self.vars["find_parent_dir"].get().strip()
        if not parent:
            messagebox.showerror(
                "Find raw folders",
                "Please select a parent folder first.",
                parent=self.app,
            )
            return

        try:
            parent_path = Path(parent)
            raw_dirs = find_raw_dirs(parent_path)
            jobs = [
                {
                    "raw_dir": str(raw_dir),
                    "subdir": make_subdir_from_raw_parent(parent_path, raw_dir),
                }
                for raw_dir in raw_dirs
            ]
        except Exception as exc:
            messagebox.showerror(
                "Find raw folders error",
                str(exc),
                parent=self.app,
            )
            return

        if not jobs:
            messagebox.showinfo(
                "Find raw folders",
                "No raw folders with supported images were found.",
                parent=self.app,
            )
            return

        self._set_job_rows(jobs)
        self._append_log(f"Found {len(jobs)} raw folders under: {parent}")
        for job in jobs:
            self._append_log(f"  {job['raw_dir']}  ->  {job['subdir']}")

    def _set_job_rows(self, jobs: list[dict]) -> None:
        for row in list(self.job_rows):
            row.destroy()
        self.job_rows.clear()

        for job in jobs:
            row = UploadJobRow(self, self.jobs_frame, len(self.job_rows))
            row.raw_dir.set(job["raw_dir"])
            row.subdir.set(job["subdir"])
            self.job_rows.append(row)

        if not self.job_rows:
            self._add_job_row()
        else:
            self._refresh_job_rows()

    def _load_jobs_csv(self) -> None:
        csv_file = filedialog.askopenfilename(
            parent=self.app,
            title="Select jobs CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not csv_file:
            return

        try:
            jobs = read_jobs_csv(Path(csv_file))
            self._set_job_rows(jobs)
            self._append_log(f"Loaded {len(jobs)} jobs from CSV: {csv_file}")
        except Exception as exc:
            messagebox.showerror(
                "CSV load error",
                str(exc),
                parent=self.app,
            )

    def _add_job_row(self) -> None:
        row = UploadJobRow(self, self.jobs_frame, len(self.job_rows))
        self.job_rows.append(row)
        self._refresh_job_rows()

    def _remove_job_row(self, row_obj: UploadJobRow) -> None:
        if len(self.job_rows) <= 1:
            messagebox.showinfo(
                "Cannot remove",
                "At least one upload job is required.",
                parent=self.app,
            )
            return

        self.job_rows.remove(row_obj)
        row_obj.destroy()
        self._refresh_job_rows()

    def _refresh_job_rows(self) -> None:
        for index, row in enumerate(self.job_rows):
            row.set_index(index)
            row.remove_button.configure(
                state="disabled" if len(self.job_rows) <= 1 else "normal"
            )

    # ------------------------------------------------------------------
    # Log / worker
    # ------------------------------------------------------------------
    def _append_log(self, text: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _log_from_worker(self, text: str) -> None:
        self.log_queue.put(text)

    def _poll_log_queue(self) -> None:
        try:
            while True:
                text = self.log_queue.get_nowait()
                self._append_log(text)
        except queue.Empty:
            pass

        self.app.after(100, self._poll_log_queue)

    def _clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _collect_settings(self) -> dict:
        settings = {key: var.get() for key, var in self.vars.items()}
        settings["jobs"] = [row.to_dict() for row in self.job_rows]
        return settings

    def _set_running_state(self, running: bool) -> None:
        state = "disabled" if running else "normal"
        self.run_button.configure(state=state)
        self.add_job_button.configure(state=state)
        self.load_csv_button.configure(state=state)
        self.find_button.configure(state=state)

        for row in self.job_rows:
            row.browse_button.configure(state=state)
            if running:
                row.remove_button.configure(state="disabled")
            else:
                row.remove_button.configure(
                    state="disabled" if len(self.job_rows) <= 1 else "normal"
                )

        if running:
            self.status_badge.configure(
                text="  Running  ",
                fg_color=("#dbeafe", "#15355f"),
                text_color=("#1d4ed8", "#93c5fd"),
            )
            self.progress.start()
        else:
            self.status_badge.configure(
                text="  Ready  ",
                fg_color=("gray88", "gray24"),
                text_color=("gray30", "gray78"),
            )
            self.progress.stop()
            self.progress.set(0)

    def _start(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo(
                "Running",
                "Workflow is already running.",
                parent=self.app,
            )
            return

        settings = self._collect_settings()
        self._set_running_state(True)
        self._append_log("START")

        def target() -> None:
            try:
                run_workflow(settings, self._log_from_worker)
                self.log_queue.put("SUCCESS")
            except Exception as exc:
                self.log_queue.put("")
                self.log_queue.put(f"ERROR: {exc}")
            finally:
                self.app.after(0, self._finish)

        self.worker = threading.Thread(target=target, daemon=True)
        self.worker.start()

    def _finish(self) -> None:
        self._set_running_state(False)


TAB_PLUGIN = UploaderTab

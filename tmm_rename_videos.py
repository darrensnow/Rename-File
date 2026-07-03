#!/usr/bin/env python3

"""Rename video files into TinyMediaManager-friendly names.

The script walks a library root, detects folders that contain video files,
guesses whether each folder contains a movie or TV episodes, and prints or
applies the rename plan.

Movie folders:
  Folder Name (2024)/random-file.mkv -> Folder Name (2024).mkv
  Folder Name (2024)/cut-1080p.mkv   -> Folder Name (2024) - 1080p.mkv

TV folders:
  Show Name/S01E02.mkv               -> Show Name - S01E02.mkv
  Show Name/02 - Pilot.mkv           -> Show Name - S01E02 - Pilot.mkv
  Show Name Season 1/EP03.mp4        -> Show Name - S01E03.mp4

By default the script only prints the plan. Add --apply to rename files.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


VIDEO_EXTENSIONS = {
    ".3gp",
    ".asf",
    ".avi",
    ".flv",
    ".iso",
    ".m2ts",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp4",
    ".mpeg",
    ".mpg",
    ".mts",
    ".rm",
    ".rmvb",
    ".ts",
    ".vob",
    ".webm",
    ".wmv",
}

SKIP_DIR_NAMES = {
    ".git",
    "@eadir",
    "extrafanart",
    "extras",
    "sample",
    "samples",
}

SEASON_NUMBER_PATTERN = "(?:\\d{1,2}|[\u96f6\u3007\u4e00\u4e8c\u4e24\u5169\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341]{1,3})"

SEASON_ONLY_PATTERNS = [
    re.compile(r"(?i)^season[ ._-]*(?P<season>\d{1,2})$"),
    re.compile(r"(?i)^s(?P<season>\d{1,2})$"),
    re.compile(f"^\u7b2c\\s*(?P<season>{SEASON_NUMBER_PATTERN})\\s*\u5b63$"),
]

SEASON_HINT_PATTERNS = [
    re.compile(r"(?i)\bseason[ ._-]*(?P<season>\d{1,2})\b"),
    re.compile(r"(?i)\bs(?P<season>\d{1,2})\b"),
    re.compile(f"\u7b2c\\s*(?P<season>{SEASON_NUMBER_PATTERN})\\s*\u5b63"),
]

EPISODE_PATTERNS = [
    re.compile(r"(?i)\bs(?P<season>\d{1,2})[ ._-]*e(?P<episode>\d{1,3})\b"),
    re.compile(r"(?i)\b(?P<season>\d{1,2})x(?P<episode>\d{1,3})\b"),
    re.compile(r"(?i)\bepisode[ ._-]*(?P<episode>\d{1,3})\b"),
    re.compile(r"(?i)\bep?[ ._-]*(?P<episode>\d{1,3})\b"),
    re.compile(r"第\s*(?P<episode>\d{1,3})\s*[集话話]"),
]

LEADING_EPISODE_PATTERN = re.compile(r"^\s*(?P<episode>\d{1,3})(?:\b|[ ._-]+)")

TECHNICAL_TOKEN_PATTERN = re.compile(
    r"(?i)\b("
    r"480p|576p|720p|1080p|1440p|2160p|4k|8k|"
    r"x264|x265|h[\s._-]?26[45]|hevc|av1|"
    r"aac|ac3|eac3|dd|dts(?:[\s._-]?hd)?|truehd|atmos|flac|fla|"
    r"web[\s._-]*dl|webrip|web|bluray|bdrip|brrip|remux|dvdrip|"
    r"hdr(?:10)?|dolby[\s._-]?vision|dv|proper|repack|10bit|8bit|"
    r"amzn|nf|dsnp|hmax|ddp(?:[\s._-]?\d(?:\.\d)?)?|"
    r"\d{2,3}fps"
    r")\b"
)


CHANNEL_TOKEN_PATTERN = re.compile(r"(?i)\b(?:[257]\s*[._-]?\s*1|2\s*[._-]?\s*0)\b")
EXTRA_PATTERNS = [
    ("behindthescenes", re.compile(r"(?i)behind[ ._-]*the[ ._-]*scenes")),
    ("deleted", re.compile(r"(?i)deleted[ ._-]*scenes?")),
    ("featurette", re.compile(r"(?i)featurette")),
    ("interview", re.compile(r"(?i)interview")),
    ("scene", re.compile(r"(?i)scene")),
    ("short", re.compile(r"(?i)short")),
    ("trailer", re.compile(r"(?i)trailer")),
    ("sample", re.compile(r"(?i)sample")),
    ("extras", re.compile(r"(?i)extra")),
]

ILLEGAL_CHAR_PATTERN = re.compile(r"[<>:\"/\\|?*\x00-\x1f]")
MULTI_SPACE_PATTERN = re.compile(r"\s+")
SEPARATOR_EDGE_PATTERN = re.compile(r"^[\s._\-]+|[\s._\-]+$")
YEAR_PATTERN = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
TITLE_TRAILING_TRIM_PATTERN = re.compile(r"[\s\-._\(\[\)\]]+$")


@dataclass(frozen=True)
class RenamePlan:
    source: Path
    target: Path


@dataclass(frozen=True)
class EpisodeInfo:
    season: int
    episode: int
    title_hint: str


@dataclass(frozen=True)
class ScanItem:
    source: Path
    target: Path
    mode: str
    status: str
    detail: str


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rename media files into TinyMediaManager-friendly names."
    )
    parser.add_argument(
        "root",
        nargs="?",
        type=Path,
        help="Library root to scan. Omit to open the GUI.",
    )
    parser.add_argument(
        "--mode",
        choices=("auto", "movie", "tv"),
        default="auto",
        help="Rename mode. Default: auto.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply renames. Without this flag the script only prints a dry-run plan.",
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="Only scan the root folder itself and its direct child folders.",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Open the graphical interface.",
    )
    return parser.parse_args(argv)


def is_video_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS


def normalize_whitespace(value: str) -> str:
    return MULTI_SPACE_PATTERN.sub(" ", value).strip()


def normalize_component(value: str) -> str:
    value = value.replace("(", " (").replace(")", ") ")
    value = value.replace("_", " ").replace(".", " ")
    value = ILLEGAL_CHAR_PATTERN.sub(" ", value)
    value = normalize_whitespace(value)
    value = re.sub(r"\s*-\s*", " - ", value)
    value = normalize_whitespace(value)
    return SEPARATOR_EDGE_PATTERN.sub("", value)


def simplify_for_match(value: str) -> str:
    value = value.replace("_", " ").replace(".", " ")
    value = re.sub(r"[^\w]+", " ", value, flags=re.UNICODE)
    return normalize_whitespace(value).lower()


def build_match_variants(value: str) -> list[str]:
    variants = {normalize_component(value), simplify_for_match(value)}
    return sorted((variant for variant in variants if variant), key=len, reverse=True)


def strip_first_case_insensitive(text: str, token: str) -> str:
    pattern = re.compile(re.escape(token), re.IGNORECASE)
    return pattern.sub(" ", text, count=1)


def remove_folder_title(text: str, folder_title: str) -> str:
    updated = text
    for variant in build_match_variants(folder_title):
        lowered_text = updated.lower()
        lowered_variant = variant.lower()
        if lowered_text.startswith(lowered_variant + " "):
            updated = updated[len(variant) :]
            break
        if lowered_text == lowered_variant:
            return ""
        if lowered_variant in lowered_text:
            updated = strip_first_case_insensitive(updated, variant)
            break
    return normalize_component(updated)


CHINESE_DIGITS = {
    "\u96f6": 0,
    "\u3007": 0,
    "\u4e00": 1,
    "\u4e8c": 2,
    "\u4e24": 2,
    "\u5169": 2,
    "\u4e09": 3,
    "\u56db": 4,
    "\u4e94": 5,
    "\u516d": 6,
    "\u4e03": 7,
    "\u516b": 8,
    "\u4e5d": 9,
}


def parse_chinese_number(value: str) -> int | None:
    value = value.strip()
    if not value:
        return None
    ten = "\u5341"
    if any(char != ten and char not in CHINESE_DIGITS for char in value):
        return None
    if ten not in value:
        if len(value) == 1:
            return CHINESE_DIGITS.get(value)
        return None
    if value.count(ten) != 1:
        return None

    tens_text, ones_text = value.split(ten, 1)
    tens = 1 if not tens_text else CHINESE_DIGITS.get(tens_text)
    ones = 0 if not ones_text else CHINESE_DIGITS.get(ones_text)
    if tens is None or ones is None:
        return None
    return tens * 10 + ones


def parse_number_token(value: str) -> int | None:
    value = value.strip()
    if value.isdigit():
        return int(value)
    return parse_chinese_number(value)


def extract_season_hint(name: str) -> int | None:
    for pattern in SEASON_HINT_PATTERNS:
        match = pattern.search(name)
        if match:
            season = parse_number_token(match.group("season"))
            if season is not None:
                return season
    return None


def parse_season_only_folder(name: str) -> int | None:
    normalized_name = normalize_component(name)
    for pattern in SEASON_ONLY_PATTERNS:
        match = pattern.fullmatch(normalized_name)
        if match:
            season = parse_number_token(match.group("season"))
            if season is not None:
                return season
    return None


def strip_season_marker(name: str) -> str:
    updated = normalize_component(name)
    for pattern in SEASON_HINT_PATTERNS:
        updated = pattern.sub(" ", updated)
    return normalize_component(updated)


def cleanup_season_folder_title(name: str) -> str:
    title = strip_season_marker(name)
    title = TECHNICAL_TOKEN_PATTERN.sub(" ", title)
    title = CHANNEL_TOKEN_PATTERN.sub(" ", title)
    return normalize_component(title)

def season_marker_starts_name(name: str) -> bool:
    normalized_name = normalize_component(name)
    for pattern in SEASON_HINT_PATTERNS:
        match = pattern.search(normalized_name)
        if match and match.start() == 0:
            return True
    return False


def remove_year_from_title(title: str) -> str:
    title = normalize_component(title)
    title = re.sub(r"[\s._-]*[\(\[]\s*(?:19|20)\d{2}\s*[\)\]][\s._-]*", " ", title)
    title = YEAR_PATTERN.sub(" ", title)
    return normalize_component(title)

def derive_show_context(directory: Path) -> tuple[str, int | None]:
    folder_name = normalize_component(directory.name)
    season_only = parse_season_only_folder(folder_name)
    if season_only is not None:
        parent_title = remove_year_from_title(directory.parent.name)
        return parent_title or folder_name, season_only

    season_hint = extract_season_hint(folder_name)
    if season_hint is not None:
        if season_marker_starts_name(folder_name):
            parent_title = remove_year_from_title(directory.parent.name)
            return parent_title or folder_name, season_hint
        show_title = cleanup_season_folder_title(folder_name)
        if show_title:
            return remove_year_from_title(show_title), season_hint
        parent_title = remove_year_from_title(directory.parent.name)
        return parent_title or folder_name, season_hint

    return normalize_movie_folder_title(directory.name), None


def cleanup_episode_title(title: str, show_title: str) -> str:
    # Remove show title first to keep the operation idempotent on repeated scans.
    title = remove_folder_title(normalize_component(title), show_title)
    title = re.sub(r"\[[^\]]+\]", " ", title)
    title = TECHNICAL_TOKEN_PATTERN.sub(" ", title)
    title = re.sub(r"(?<!\d)(?:19|20)\d{2}(?!\d)", " ", title)
    title = normalize_component(title)
    title = remove_folder_title(title, show_title)
    return title


def normalize_movie_folder_title(folder_name: str) -> str:
    name = normalize_component(folder_name)
    match = YEAR_PATTERN.search(name)
    if not match:
        return name

    title_part = name[: match.start()]
    title_part = TITLE_TRAILING_TRIM_PATTERN.sub("", title_part)
    title_part = TECHNICAL_TOKEN_PATTERN.sub(" ", title_part)
    title_part = normalize_component(title_part)
    if not title_part:
        return name
    return f"{title_part} ({match.group(1)})"


def parse_episode_info(
    file_stem: str,
    show_title: str,
    fallback_season: int | None,
    allow_leading_number: bool,
) -> EpisodeInfo | None:
    raw_text = file_stem.replace("_", " ")
    for pattern in EPISODE_PATTERNS:
        match = pattern.search(raw_text)
        if not match:
            continue

        season_group = match.groupdict().get("season")
        season = int(season_group) if season_group else (fallback_season or 1)
        episode = int(match.group("episode"))
        title_hint = cleanup_episode_title(
            raw_text[: match.start()] + " " + raw_text[match.end() :],
            show_title,
        )
        return EpisodeInfo(season=season, episode=episode, title_hint=title_hint)

    if allow_leading_number:
        candidate = normalize_component(file_stem)
        match = LEADING_EPISODE_PATTERN.match(candidate)
        if match:
            episode = int(match.group("episode"))
            title_hint = cleanup_episode_title(candidate[match.end() :], show_title)
            return EpisodeInfo(
                season=fallback_season or 1,
                episode=episode,
                title_hint=title_hint,
            )

    return None


def detect_extra_type(file_stem: str) -> str | None:
    for extra_name, pattern in EXTRA_PATTERNS:
        if pattern.search(file_stem):
            return extra_name
    return None


def looks_like_numbered_episode_batch(video_files: list[Path]) -> bool:
    if len(video_files) < 2:
        return False

    numbered_files = sum(
        1
        for video_file in video_files
        if LEADING_EPISODE_PATTERN.match(normalize_component(video_file.stem))
    )
    return numbered_files >= 2 and numbered_files >= len(video_files) / 2


def derive_version_label(file_stem: str, folder_title: str, index: int) -> str:
    label = normalize_component(file_stem)
    label = remove_folder_title(label, folder_title)
    label = normalize_component(label)
    if not label:
        return f"version {index}"
    return label


def ensure_unique_name(
    filename: str,
    used_targets: set[str],
    reserved_names: set[str],
) -> str:
    candidate = filename
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    counter = 2
    while candidate.lower() in used_targets or candidate.lower() in reserved_names:
        candidate = f"{stem} ({counter}){suffix}"
        counter += 1
    return candidate


def plan_tv_renames(directory: Path, video_files: list[Path]) -> list[RenamePlan]:
    show_title, season_hint = derive_show_context(directory)
    allow_leading_number = (
        season_hint is not None
        or parse_season_only_folder(directory.parent.name) is not None
        or looks_like_numbered_episode_batch(video_files)
    )

    reserved_names = {
        child.name.lower()
        for child in directory.iterdir()
        if child.is_file() and child not in video_files
    }
    used_targets: set[str] = set()
    plans: list[RenamePlan] = []

    for video_file in sorted(video_files, key=lambda path: path.name.lower()):
        episode_info = parse_episode_info(
            file_stem=video_file.stem,
            show_title=show_title,
            fallback_season=season_hint,
            allow_leading_number=allow_leading_number,
        )

        if episode_info is None:
            extra_type = detect_extra_type(video_file.stem)
            if extra_type:
                target_base = f"{show_title}-{extra_type}"
            else:
                target_base = f"{show_title} - {normalize_component(video_file.stem)}"
        else:
            target_base = f"{show_title} - S{episode_info.season:02d}E{episode_info.episode:02d}"
            if episode_info.title_hint:
                target_base += f" - {episode_info.title_hint}"

        target_name = ensure_unique_name(
            f"{target_base}{video_file.suffix.lower()}",
            used_targets,
            reserved_names,
        )
        used_targets.add(target_name.lower())
        plans.append(RenamePlan(source=video_file, target=video_file.with_name(target_name)))

    return plans


def plan_movie_renames(directory: Path, video_files: list[Path]) -> list[RenamePlan]:
    folder_title = normalize_movie_folder_title(directory.name)
    reserved_names = {
        child.name.lower()
        for child in directory.iterdir()
        if child.is_file() and child not in video_files
    }
    used_targets: set[str] = set()
    plans: list[RenamePlan] = []

    for index, video_file in enumerate(sorted(video_files, key=lambda path: path.name.lower()), start=1):
        extra_type = detect_extra_type(video_file.stem)
        if extra_type:
            target_base = f"{folder_title}-{extra_type}"
        elif len(video_files) == 1:
            target_base = folder_title
        else:
            version_label = derive_version_label(video_file.stem, folder_title, index)
            target_base = f"{folder_title} - {version_label}"

        target_name = ensure_unique_name(
            f"{target_base}{video_file.suffix.lower()}",
            used_targets,
            reserved_names,
        )
        used_targets.add(target_name.lower())
        plans.append(RenamePlan(source=video_file, target=video_file.with_name(target_name)))

    return plans


def detect_mode(directory: Path, video_files: list[Path], selected_mode: str) -> str:
    if selected_mode != "auto":
        return selected_mode

    show_title, season_hint = derive_show_context(directory)
    allow_leading_number = season_hint is not None or looks_like_numbered_episode_batch(video_files)

    for video_file in video_files:
        if parse_episode_info(video_file.stem, show_title, season_hint, allow_leading_number):
            return "tv"

    if season_hint is not None and len(video_files) > 1:
        return "tv"

    return "movie"


def iter_media_folders(root: Path, recursive: bool) -> Iterable[tuple[Path, list[Path]]]:
    if recursive:
        for current_root, dir_names, file_names in os.walk(root):
            dir_names[:] = [
                dir_name
                for dir_name in dir_names
                if dir_name.lower() not in SKIP_DIR_NAMES and not dir_name.startswith(".")
            ]
            current_path = Path(current_root)
            video_files = [current_path / name for name in file_names if is_video_file(current_path / name)]
            if video_files:
                yield current_path, video_files
        return

    direct_targets = [root]
    direct_targets.extend(
        child for child in root.iterdir() if child.is_dir() and child.name.lower() not in SKIP_DIR_NAMES
    )
    for directory in direct_targets:
        video_files = [child for child in directory.iterdir() if is_video_file(child)]
        if video_files:
            yield directory, video_files


def execute_plans(plans: list[RenamePlan]) -> None:
    staged_moves: list[tuple[Path, Path, Path]] = []
    try:
        for plan in plans:
            if plan.source == plan.target:
                continue
            temp_name = f".__tmm_tmp__{uuid.uuid4().hex}{plan.source.suffix.lower()}"
            temp_path = plan.source.with_name(temp_name)
            plan.source.rename(temp_path)
            staged_moves.append((temp_path, plan.source, plan.target))

        for temp_path, _original_path, target_path in staged_moves:
            temp_path.rename(target_path)
    except Exception:
        for temp_path, original_path, _target_path in reversed(staged_moves):
            if temp_path.exists() and not original_path.exists():
                temp_path.rename(original_path)
        raise


def scan_library(root: Path, mode: str, recursive: bool) -> tuple[list[ScanItem], int]:
    raw_plans: list[tuple[RenamePlan, str]] = []
    processed_folders = 0

    for directory, video_files in iter_media_folders(root, recursive=recursive):
        processed_folders += 1
        active_mode = detect_mode(directory, video_files, mode)
        plans = (
            plan_tv_renames(directory, video_files)
            if active_mode == "tv"
            else plan_movie_renames(directory, video_files)
        )
        for plan in plans:
            raw_plans.append((plan, active_mode))

    moving_source_keys = {
        str(plan.source).lower() for plan, _ in raw_plans if plan.source != plan.target
    }
    target_counts: dict[str, int] = {}
    for plan, _ in raw_plans:
        if plan.source == plan.target:
            continue
        target_counts[str(plan.target).lower()] = target_counts.get(str(plan.target).lower(), 0) + 1

    items: list[ScanItem] = []
    for plan, active_mode in raw_plans:
        if plan.source == plan.target:
            items.append(ScanItem(plan.source, plan.target, active_mode, "SKIP", "已经是规范命名"))
            continue
        target_key = str(plan.target).lower()
        target_taken = plan.target.exists() and target_key not in moving_source_keys
        duplicate = target_counts.get(target_key, 0) > 1
        if target_taken:
            items.append(ScanItem(plan.source, plan.target, active_mode, "CONFLICT", "目标已存在"))
        elif duplicate:
            items.append(ScanItem(plan.source, plan.target, active_mode, "CONFLICT", "多个文件映射到同一目标"))
        else:
            items.append(ScanItem(plan.source, plan.target, active_mode, "RENAME", "待重命名"))

    return items, processed_folders


def launch_gui(initial_root: Path | None = None, initial_mode: str = "auto") -> int:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    filter_choices = ("全部", "仅待重命名", "仅冲突", "仅跳过")
    mode_choices = ("auto", "movie", "tv")
    status_labels = {"RENAME": "重命名", "SKIP": "跳过", "CONFLICT": "冲突"}
    mode_labels = {"movie": "电影", "tv": "剧集", "auto": "自动"}
    filter_to_status = {"仅待重命名": "RENAME", "仅冲突": "CONFLICT", "仅跳过": "SKIP"}

    class App:
        def __init__(self, window: tk.Tk) -> None:
            self.window = window
            self.items: list[ScanItem] = []
            self.processed_folders = 0
            self.current_root: Path | None = None
            self.path_var = tk.StringVar(value=str(initial_root) if initial_root else "")
            self.recursive_var = tk.BooleanVar(value=True)
            self.mode_var = tk.StringVar(value=initial_mode if initial_mode in mode_choices else "auto")
            self.filter_var = tk.StringVar(value=filter_choices[0])
            self.summary_var = tk.StringVar(value='请选择目录后点击"预览"。')
            self._build_widgets()

        def _build_widgets(self) -> None:
            self.window.title("TinyMediaManager 视频重命名")
            self.window.geometry("1280x780")
            self.window.minsize(1000, 600)

            container = ttk.Frame(self.window, padding=12)
            container.pack(fill="both", expand=True)
            container.columnconfigure(1, weight=1)
            container.rowconfigure(3, weight=1)

            ttk.Label(container, text="目录").grid(row=0, column=0, sticky="w", padx=(0, 8))
            entry = ttk.Entry(container, textvariable=self.path_var)
            entry.grid(row=0, column=1, sticky="ew")
            entry.focus_set()
            ttk.Button(container, text="浏览...", command=self.browse).grid(row=0, column=2, padx=(8, 0))

            action_row = ttk.Frame(container)
            action_row.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(10, 0))
            ttk.Checkbutton(action_row, text="递归扫描", variable=self.recursive_var).pack(side="left")
            ttk.Label(action_row, text="模式").pack(side="left", padx=(16, 4))
            ttk.Combobox(
                action_row,
                textvariable=self.mode_var,
                values=mode_choices,
                state="readonly",
                width=8,
            ).pack(side="left")
            ttk.Button(action_row, text="预览", command=self.preview).pack(side="left", padx=(8, 0))
            self.apply_button = ttk.Button(
                action_row, text="执行重命名", command=self.apply_changes, state="disabled"
            )
            self.apply_button.pack(side="left", padx=(8, 0))
            ttk.Label(action_row, text="筛选").pack(side="left", padx=(16, 4))
            filter_box = ttk.Combobox(
                action_row,
                textvariable=self.filter_var,
                values=filter_choices,
                state="readonly",
                width=12,
            )
            filter_box.pack(side="left")
            filter_box.bind("<<ComboboxSelected>>", lambda _event: self.refresh_view())

            ttk.Label(container, textvariable=self.summary_var, anchor="w").grid(
                row=2, column=0, columnspan=3, sticky="ew", pady=(12, 10)
            )

            tree_frame = ttk.Frame(container)
            tree_frame.grid(row=3, column=0, columnspan=3, sticky="nsew")
            tree_frame.columnconfigure(0, weight=1)
            tree_frame.rowconfigure(0, weight=1)

            columns = ("status", "mode", "source", "target", "detail")
            self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings")
            for column, label, width, anchor in (
                ("status", "状态", 80, "center"),
                ("mode", "类型", 80, "center"),
                ("source", "原路径", 420, "w"),
                ("target", "目标路径", 420, "w"),
                ("detail", "说明", 220, "w"),
            ):
                self.tree.heading(column, text=label)
                self.tree.column(column, width=width, anchor=anchor)
            self.tree.grid(row=0, column=0, sticky="nsew")

            vertical_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
            vertical_scroll.grid(row=0, column=1, sticky="ns")
            horizontal_scroll = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
            horizontal_scroll.grid(row=1, column=0, sticky="ew")
            self.tree.configure(yscrollcommand=vertical_scroll.set, xscrollcommand=horizontal_scroll.set)
            self.tree.tag_configure("rename", background="#ecfdf3", foreground="#027a48")
            self.tree.tag_configure("conflict", background="#fef3f2", foreground="#b42318")
            self.tree.tag_configure("skip", background="#f8f9fc", foreground="#667085")

            self.window.bind("<Return>", lambda _event: self.preview())

        def browse(self) -> None:
            chosen = filedialog.askdirectory(initialdir=self.path_var.get() or None)
            if chosen:
                self.path_var.set(chosen)

        def _format_path(self, path: Path) -> str:
            if self.current_root is None:
                return str(path)
            try:
                return str(path.relative_to(self.current_root))
            except ValueError:
                return str(path)

        def _resolve_root(self) -> Path:
            raw_value = self.path_var.get().strip()
            if not raw_value:
                raise ValueError("请先选择目录。")
            resolved = Path(raw_value).expanduser().resolve()
            if not resolved.exists() or not resolved.is_dir():
                raise FileNotFoundError(f"目录不存在或不是文件夹：{resolved}")
            self.path_var.set(str(resolved))
            return resolved

        def preview(self) -> None:
            try:
                root = self._resolve_root()
                items, processed = scan_library(
                    root,
                    self.mode_var.get(),
                    recursive=self.recursive_var.get(),
                )
            except (FileNotFoundError, ValueError) as error:
                messagebox.showerror("预览失败", str(error), parent=self.window)
                return
            except Exception as error:
                messagebox.showerror("预览失败", str(error), parent=self.window)
                return

            self.items = items
            self.processed_folders = processed
            self.current_root = root
            self.refresh_view()

        def refresh_view(self) -> None:
            self.tree.delete(*self.tree.get_children())
            wanted_status = filter_to_status.get(self.filter_var.get())
            visible = 0
            for item in self.items:
                if wanted_status is not None and item.status != wanted_status:
                    continue
                visible += 1
                self.tree.insert(
                    "",
                    "end",
                    values=(
                        status_labels.get(item.status, item.status),
                        mode_labels.get(item.mode, item.mode),
                        self._format_path(item.source),
                        self._format_path(item.target),
                        item.detail,
                    ),
                    tags=(item.status.lower(),),
                )

            rename_count = sum(1 for item in self.items if item.status == "RENAME")
            conflict_count = sum(1 for item in self.items if item.status == "CONFLICT")
            skip_count = sum(1 for item in self.items if item.status == "SKIP")
            self.summary_var.set(
                " | ".join(
                    [
                        f"已扫描文件夹: {self.processed_folders}",
                        f"视频: {len(self.items)}",
                        f"待重命名: {rename_count}",
                        f"冲突: {conflict_count}",
                        f"跳过: {skip_count}",
                        f"当前显示: {visible}",
                    ]
                )
            )
            self.apply_button.configure(
                state="normal" if rename_count and not conflict_count else "disabled"
            )

        def apply_changes(self) -> None:
            rename_items = [item for item in self.items if item.status == "RENAME"]
            conflict_items = [item for item in self.items if item.status == "CONFLICT"]
            if conflict_items:
                messagebox.showerror("无法执行", "存在冲突，请先解决后再执行。", parent=self.window)
                return
            if not rename_items:
                messagebox.showinfo("无需处理", "没有需要重命名的项目。", parent=self.window)
                return
            if not messagebox.askyesno(
                "确认", f"确定执行 {len(rename_items)} 个重命名操作吗？", parent=self.window
            ):
                return

            try:
                execute_plans([RenamePlan(source=item.source, target=item.target) for item in rename_items])
            except Exception as error:
                messagebox.showerror("执行失败", str(error), parent=self.window)
                return

            messagebox.showinfo("完成", f"已执行 {len(rename_items)} 个重命名。", parent=self.window)
            self.preview()

    window = tk.Tk()
    App(window)
    window.mainloop()
    return 0


def run_cli(args: argparse.Namespace) -> int:
    root = args.root.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        print(f"Root folder not found or not a directory: {root}", file=sys.stderr)
        return 1

    items, processed_folders = scan_library(root, args.mode, recursive=not args.no_recursive)

    for item in items:
        if item.status == "SKIP":
            print(f"[SKIP    ] {item.source}")
        elif item.status == "CONFLICT":
            print(f"[CONFLICT] {item.source} -> {item.target} :: {item.detail}")
        else:
            print(f"[RENAME  ] {item.source} -> {item.target}")

    rename_items = [item for item in items if item.status == "RENAME"]
    conflict_items = [item for item in items if item.status == "CONFLICT"]
    print()
    print(f"Scanned folders: {processed_folders}")
    print(f"Video files: {len(items)}")
    print(f"Renames needed: {len(rename_items)}")
    print(f"Conflicts: {len(conflict_items)}")

    if not args.apply:
        print("Dry-run only. Add --apply to rename files.")
        return 0

    if conflict_items:
        print("Conflicts detected; aborting. Resolve them and try again.", file=sys.stderr)
        return 1

    execute_plans([RenamePlan(source=item.source, target=item.target) for item in rename_items])
    print(f"Applied renames: {len(rename_items)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.gui or args.root is None:
        initial_root = args.root.expanduser() if args.root is not None else None
        return launch_gui(initial_root, initial_mode=args.mode)
    return run_cli(args)


if __name__ == "__main__":
    raise SystemExit(main())

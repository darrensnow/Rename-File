#!/usr/bin/env python3

"""Normalize video and folder names based on AV code patterns.

The script scans video files under a root path and derives a normalized code
from the file name first, then from the parent folder name. It also normalizes
folder names when the folder name itself contains an AV code.

Supported examples:
  WAAA-338       -> WAAA-338
  WAAA-338-C     -> WAAA-338-C
  waaa-338       -> WAAA-338
  WAAA-338ch     -> WAAA-338-C
  WAAA-338-UC    -> WAAA-338-C
  waaa-338ch     -> WAAA-338-C
  XXXXX@WAAA-338-C -> WAAA-338-C
  WAAA-338-U     -> WAAA-338
  MVSD-551-GC    -> MVSD-551
  MVSD-523-C_X1080X -> MVSD-523-C

Run without arguments to open the GUI. Pass a root path to use the CLI.
"""

from __future__ import annotations

import argparse
import re
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path


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
    "__pycache__",
}

CODE_PATTERN = re.compile(
    r"(?i)(?<![a-z0-9])"
    r"(?P<prefix>[a-z]{2,10})"
    r"\s*[-_ ]?\s*"
    r"(?P<number>\d{3,5})"
    r"(?:\s*[-_ ]?\s*(?P<suffix>uc|ch|c|u))?"
    r"(?![a-z0-9])"
)


@dataclass(frozen=True)
class RenamePlan:
    kind: str
    source: Path
    target: Path
    status: str
    detail: str


@dataclass(frozen=True)
class ScanResult:
    root: Path
    recursive: bool
    directories: list[Path]
    video_files: list[Path]
    file_plans: list[RenamePlan]
    directory_plans: list[RenamePlan]
    plans: list[RenamePlan]
    rename_plans: list[RenamePlan]
    conflict_plans: list[RenamePlan]
    file_rename_plans: list[RenamePlan]
    directory_rename_plans: list[RenamePlan]


def is_same_name(source: Path, target: Path) -> bool:
    return source.parent == target.parent and source.name == target.name


def normalize_root(root: Path) -> Path:
    resolved = root.expanduser().resolve()
    if not resolved.exists() or not resolved.is_dir():
        raise FileNotFoundError(f"Root folder not found or not a directory: {resolved}")
    return resolved


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rename video files into normalized AV code names."
    )
    parser.add_argument(
        "root",
        nargs="?",
        type=Path,
        help="Root folder to scan. If omitted, the GUI opens.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply renames. Without this flag the script only prints the plan.",
    )
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="Only scan the root folder and its direct child folders.",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Open the graphical interface.",
    )
    return parser.parse_args(argv)


def is_video_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS


def is_skipped_directory(path: Path) -> bool:
    return any(part.lower() in SKIP_DIR_NAMES for part in path.parts)


def iter_video_files(root: Path, recursive: bool) -> list[Path]:
    if recursive:
        files: list[Path] = []
        for candidate in root.rglob("*"):
            if not candidate.is_file():
                continue
            if is_skipped_directory(candidate):
                continue
            if is_video_file(candidate):
                files.append(candidate)
        return sorted(files, key=lambda path: str(path).lower())

    files = [child for child in root.iterdir() if is_video_file(child)]
    for child in root.iterdir():
        if child.is_dir() and child.name.lower() not in SKIP_DIR_NAMES:
            files.extend(grandchild for grandchild in child.iterdir() if is_video_file(grandchild))
    return sorted(files, key=lambda path: str(path).lower())


def iter_candidate_directories(root: Path, recursive: bool) -> list[Path]:
    if recursive:
        directories = [
            candidate
            for candidate in root.rglob("*")
            if candidate.is_dir() and not is_skipped_directory(candidate)
        ]
    else:
        directories = [
            child for child in root.iterdir() if child.is_dir() and child.name.lower() not in SKIP_DIR_NAMES
        ]

    return sorted(
        [directory for directory in directories if extract_code(directory.name)],
        key=lambda path: str(path).lower(),
    )


def build_text_candidates(value: str) -> list[str]:
    candidates: list[str] = []
    stripped = value.strip()
    if stripped:
        if "@" in stripped:
            after_at = stripped.rsplit("@", 1)[-1].strip()
            if after_at:
                candidates.append(after_at)
        candidates.append(stripped)
    return candidates


def normalize_match(match: re.Match[str]) -> str:
    prefix = match.group("prefix").upper()
    number = match.group("number")
    suffix = (match.group("suffix") or "").upper()

    normalized = f"{prefix}-{number}"
    if suffix in {"UC", "CH", "C"}:
        normalized += "-C"
    return normalized


def extract_code(value: str) -> str | None:
    for candidate in build_text_candidates(value):
        matches = list(CODE_PATTERN.finditer(candidate))
        if matches:
            return normalize_match(matches[-1])
    return None


def choose_code(video_file: Path) -> tuple[str | None, str]:
    file_code = extract_code(video_file.stem)
    if file_code:
        return file_code, "file"

    folder_code = extract_code(video_file.parent.name)
    if folder_code:
        return folder_code, "folder"

    return None, ""


def build_file_plan(video_file: Path) -> RenamePlan:
    normalized_code, source_kind = choose_code(video_file)
    if normalized_code is None:
        return RenamePlan(
            kind="file",
            source=video_file,
            target=video_file,
            status="SKIP",
            detail="No code found in file name or parent folder name.",
        )

    target = video_file.with_name(f"{normalized_code}{video_file.suffix}")
    if is_same_name(video_file, target):
        return RenamePlan(
            kind="file",
            source=video_file,
            target=target,
            status="SKIP",
            detail=f"Already normalized from {source_kind} name.",
        )

    return RenamePlan(
        kind="file",
        source=video_file,
        target=target,
        status="RENAME",
        detail=f"Matched from {source_kind} name.",
    )


def build_directory_plan(directory: Path) -> RenamePlan:
    normalized_code = extract_code(directory.name)
    if normalized_code is None:
        return RenamePlan(
            kind="folder",
            source=directory,
            target=directory,
            status="SKIP",
            detail="No code found in folder name.",
        )

    target = directory.with_name(normalized_code)
    if is_same_name(directory, target):
        return RenamePlan(
            kind="folder",
            source=directory,
            target=target,
            status="SKIP",
            detail="Already normalized from folder name.",
        )

    return RenamePlan(
        kind="folder",
        source=directory,
        target=target,
        status="RENAME",
        detail="Matched from folder name.",
    )


def mark_conflicts(plans: list[RenamePlan]) -> list[RenamePlan]:
    grouped: dict[str, list[RenamePlan]] = {}
    moving_sources = {
        str(plan.source).lower()
        for plan in plans
        if plan.status == "RENAME" and not is_same_name(plan.source, plan.target)
    }

    for plan in plans:
        if is_same_name(plan.source, plan.target):
            continue
        grouped.setdefault(str(plan.target).lower(), []).append(plan)

    updated: list[RenamePlan] = []
    for plan in plans:
        if is_same_name(plan.source, plan.target):
            updated.append(plan)
            continue

        target_key = str(plan.target).lower()
        target_taken = plan.target.exists() and target_key not in moving_sources
        duplicate_target = len(grouped[target_key]) > 1
        if target_taken or duplicate_target:
            reason = "Target already exists." if target_taken else "Multiple files map to the same target."
            updated.append(
                RenamePlan(
                    kind=plan.kind,
                    source=plan.source,
                    target=plan.target,
                    status="CONFLICT",
                    detail=reason,
                )
            )
            continue

        updated.append(plan)

    return updated


def execute_file_plans(plans: list[RenamePlan]) -> None:
    staged_moves: list[tuple[Path, Path, Path]] = []
    try:
        for plan in plans:
            if is_same_name(plan.source, plan.target):
                continue
            temp_name = f".__rename_tmp__{uuid.uuid4().hex}{plan.source.suffix}"
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


def execute_directory_plans(plans: list[RenamePlan]) -> None:
    for plan in sorted(plans, key=lambda item: len(item.source.parts), reverse=True):
        if is_same_name(plan.source, plan.target):
            continue

        case_only_rename = (
            plan.source.parent == plan.target.parent and plan.source.name.lower() == plan.target.name.lower()
        )
        if case_only_rename:
            temp_path = plan.source.with_name(f".__rename_tmp__{uuid.uuid4().hex}")
            plan.source.rename(temp_path)
            temp_path.rename(plan.target)
            continue

        plan.source.rename(plan.target)


def scan_library(root: Path, recursive: bool) -> ScanResult:
    video_files = iter_video_files(root, recursive=recursive)
    directories = iter_candidate_directories(root, recursive=recursive)

    file_plans = mark_conflicts([build_file_plan(video_file) for video_file in video_files])
    directory_plans = mark_conflicts([build_directory_plan(directory) for directory in directories])
    plans = sorted(file_plans + directory_plans, key=lambda plan: (plan.kind, str(plan.source).lower()))

    rename_plans = [plan for plan in plans if plan.status == "RENAME"]
    conflict_plans = [plan for plan in plans if plan.status == "CONFLICT"]
    file_rename_plans = [plan for plan in file_plans if plan.status == "RENAME"]
    directory_rename_plans = [plan for plan in directory_plans if plan.status == "RENAME"]

    return ScanResult(
        root=root,
        recursive=recursive,
        directories=directories,
        video_files=video_files,
        file_plans=file_plans,
        directory_plans=directory_plans,
        plans=plans,
        rename_plans=rename_plans,
        conflict_plans=conflict_plans,
        file_rename_plans=file_rename_plans,
        directory_rename_plans=directory_rename_plans,
    )


def print_scan_result(result: ScanResult) -> None:
    for plan in result.plans:
        label = f"{plan.kind.upper():<6}"
        if plan.status == "SKIP":
            print(f"[SKIP    ] [{label}] {plan.source} :: {plan.detail}")
        elif plan.status == "CONFLICT":
            print(f"[CONFLICT] [{label}] {plan.source} -> {plan.target} :: {plan.detail}")
        else:
            print(f"[RENAME  ] [{label}] {plan.source} -> {plan.target} :: {plan.detail}")

    print()
    print(f"Folders checked: {len(result.directories)}")
    print(f"Video files: {len(result.video_files)}")
    print(f"Folder renames needed: {len(result.directory_rename_plans)}")
    print(f"File renames needed: {len(result.file_rename_plans)}")
    print(f"Renames needed: {len(result.rename_plans)}")
    print(f"Conflicts: {len(result.conflict_plans)}")


def apply_scan_result(result: ScanResult) -> None:
    execute_file_plans(result.file_rename_plans)
    execute_directory_plans(result.directory_rename_plans)


def translate_plan_status(status: str) -> str:
    return {
        "SKIP": "跳过",
        "CONFLICT": "冲突",
        "RENAME": "重命名",
    }.get(status, status)


def translate_plan_kind(kind: str) -> str:
    return {
        "file": "文件",
        "folder": "文件夹",
    }.get(kind, kind)


def translate_plan_detail(detail: str) -> str:
    return {
        "No code found in file name or parent folder name.": "文件名和父文件夹名中都没有识别到编号。",
        "Already normalized from file name.": "文件名已经是规范格式。",
        "Already normalized from folder name.": "文件夹名已经是规范格式。",
        "Matched from file name.": "从文件名中识别到编号。",
        "Matched from folder name.": "从文件夹名中识别到编号。",
        "No code found in folder name.": "文件夹名中没有识别到编号。",
        "Target already exists.": "目标名称已存在。",
        "Multiple files map to the same target.": "多个项目映射到了同一个目标名称。",
    }.get(detail, detail)


FILTER_CHOICES = ("全部", "仅待重命名", "仅冲突", "仅跳过")


def plan_matches_filter(plan: RenamePlan, filter_choice: str) -> bool:
    status = {
        "仅待重命名": "RENAME",
        "仅冲突": "CONFLICT",
        "仅跳过": "SKIP",
    }.get(filter_choice)
    return True if status is None else plan.status == status


def plan_tag_name(plan: RenamePlan) -> str:
    return {
        "RENAME": "rename",
        "CONFLICT": "conflict",
        "SKIP": "skip",
    }.get(plan.status, "default")


def create_gui_app(initial_root: Path | None = None):
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    class RenameGuiApp:
        def __init__(self, window: tk.Tk) -> None:
            self.window = window
            self.current_result: ScanResult | None = None
            self.path_var = tk.StringVar(value=str(initial_root) if initial_root else "")
            self.recursive_var = tk.BooleanVar(value=True)
            self.filter_var = tk.StringVar(value=FILTER_CHOICES[0])
            self.summary_var = tk.StringVar(value="请选择目录，然后点击“预览”。")
            self._build_widgets()
            if initial_root is not None:
                self.window.after(100, self.preview)

        def _build_widgets(self) -> None:
            self.window.title("JAV 视频重命名")
            self.window.geometry("1420x820")
            self.window.minsize(1100, 620)

            container = ttk.Frame(self.window, padding=12)
            container.pack(fill="both", expand=True)
            container.columnconfigure(1, weight=1)
            container.rowconfigure(3, weight=1)

            ttk.Label(container, text="目录").grid(row=0, column=0, sticky="w", padx=(0, 8))
            path_entry = ttk.Entry(container, textvariable=self.path_var)
            path_entry.grid(row=0, column=1, sticky="ew")
            path_entry.focus_set()
            ttk.Button(container, text="浏览...", command=self.browse).grid(row=0, column=2, padx=(8, 0))

            action_row = ttk.Frame(container)
            action_row.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(10, 0))
            ttk.Checkbutton(action_row, text="递归扫描", variable=self.recursive_var).pack(side="left")
            ttk.Button(action_row, text="预览", command=self.preview).pack(side="left", padx=(8, 0))
            self.apply_button = ttk.Button(action_row, text="执行重命名", command=self.apply_changes)
            self.apply_button.pack(side="left", padx=(8, 0))
            self.apply_button.configure(state="disabled")
            ttk.Label(action_row, text="筛选").pack(side="left", padx=(16, 4))
            filter_box = ttk.Combobox(
                action_row,
                textvariable=self.filter_var,
                values=FILTER_CHOICES,
                state="readonly",
                width=12,
            )
            filter_box.pack(side="left")
            filter_box.bind("<<ComboboxSelected>>", lambda _event: self.refresh_view())
            ttk.Label(
                action_row,
                text="Windows 可双击 jav_rename_videos_gui.pyw 启动；Linux 请用 python3 jav_rename_videos.py --gui。",
            ).pack(side="right")

            ttk.Label(container, textvariable=self.summary_var, anchor="w").grid(
                row=2,
                column=0,
                columnspan=3,
                sticky="ew",
                pady=(12, 10),
            )

            tree_frame = ttk.Frame(container)
            tree_frame.grid(row=3, column=0, columnspan=3, sticky="nsew")
            tree_frame.columnconfigure(0, weight=1)
            tree_frame.rowconfigure(0, weight=1)

            columns = ("status", "kind", "source", "target", "detail")
            self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings")
            self.tree.heading("status", text="状态")
            self.tree.heading("kind", text="类型")
            self.tree.heading("source", text="原路径")
            self.tree.heading("target", text="目标路径")
            self.tree.heading("detail", text="说明")
            self.tree.column("status", width=90, anchor="center", stretch=False)
            self.tree.column("kind", width=90, anchor="center", stretch=False)
            self.tree.column("source", width=420, anchor="w")
            self.tree.column("target", width=420, anchor="w")
            self.tree.column("detail", width=300, anchor="w")
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
            selected = filedialog.askdirectory(initialdir=self.path_var.get() or None)
            if selected:
                self.path_var.set(selected)

        def format_path(self, path: Path, root: Path) -> str:
            try:
                return str(path.relative_to(root))
            except ValueError:
                return str(path)

        def set_apply_state(self, result: ScanResult) -> None:
            if result.rename_plans and not result.conflict_plans:
                self.apply_button.configure(state="normal")
            else:
                self.apply_button.configure(state="disabled")

        def refresh_view(self) -> None:
            if self.current_result is not None:
                self.render_result(self.current_result)

        def render_result(self, result: ScanResult) -> None:
            filtered_plans = [
                plan for plan in result.plans if plan_matches_filter(plan, self.filter_var.get())
            ]
            self.tree.delete(*self.tree.get_children())
            for plan in filtered_plans:
                source_text = self.format_path(plan.source, result.root)
                target_text = self.format_path(plan.target, result.root)
                self.tree.insert(
                    "",
                    "end",
                    values=(
                        translate_plan_status(plan.status),
                        translate_plan_kind(plan.kind),
                        source_text,
                        target_text,
                        translate_plan_detail(plan.detail),
                    ),
                    tags=(plan_tag_name(plan),),
                )

            self.summary_var.set(
                " | ".join(
                    [
                        f"已检查文件夹: {len(result.directories)}",
                        f"视频文件: {len(result.video_files)}",
                        f"待重命名文件夹: {len(result.directory_rename_plans)}",
                        f"待重命名文件: {len(result.file_rename_plans)}",
                        f"冲突: {len(result.conflict_plans)}",
                        f"当前显示: {len(filtered_plans)}",
                        f"筛选: {self.filter_var.get()}",
                    ]
                )
            )
            self.set_apply_state(result)

        def load_result(self) -> ScanResult:
            raw_path = self.path_var.get().strip()
            if not raw_path:
                raise ValueError("请先选择目录。")

            root_path = normalize_root(Path(raw_path))
            self.path_var.set(str(root_path))
            return scan_library(root_path, recursive=self.recursive_var.get())

        def preview(self) -> None:
            try:
                result = self.load_result()
            except (FileNotFoundError, ValueError) as error:
                messagebox.showerror("预览失败", str(error), parent=self.window)
                return
            except Exception as error:
                messagebox.showerror("预览失败", str(error), parent=self.window)
                return

            self.current_result = result
            self.render_result(result)

        def apply_changes(self) -> None:
            try:
                result = self.load_result()
            except (FileNotFoundError, ValueError) as error:
                messagebox.showerror("执行失败", str(error), parent=self.window)
                return
            except Exception as error:
                messagebox.showerror("执行失败", str(error), parent=self.window)
                return

            self.current_result = result
            self.render_result(result)

            if result.conflict_plans:
                messagebox.showerror(
                    "无法执行",
                    "预览结果中存在冲突，请先处理后再执行。",
                    parent=self.window,
                )
                return

            if not result.rename_plans:
                messagebox.showinfo("无需处理", "没有需要重命名的项目。", parent=self.window)
                return

            confirmed = messagebox.askyesno(
                "确认执行",
                f"确定执行 {len(result.rename_plans)} 个重命名操作吗？",
                parent=self.window,
            )
            if not confirmed:
                return

            try:
                apply_scan_result(result)
                refreshed = scan_library(result.root, recursive=result.recursive)
            except Exception as error:
                messagebox.showerror("执行失败", str(error), parent=self.window)
                return

            self.current_result = refreshed
            self.render_result(refreshed)
            messagebox.showinfo(
                "完成",
                f"已执行 {len(result.rename_plans)} 个重命名操作。",
                parent=self.window,
            )

    root_window = tk.Tk()
    RenameGuiApp(root_window)
    return root_window


def launch_gui(initial_root: Path | None = None) -> int:
    root_window = create_gui_app(initial_root)
    root_window.mainloop()
    return 0


def run_cli(args: argparse.Namespace) -> int:
    if args.root is None:
        print("Root folder is required in CLI mode.", file=sys.stderr)
        return 1

    try:
        root = normalize_root(args.root)
    except FileNotFoundError as error:
        print(str(error), file=sys.stderr)
        return 1

    result = scan_library(root, recursive=not args.no_recursive)
    print_scan_result(result)

    if not args.apply:
        print("Dry-run only. Add --apply to rename files.")
        return 0

    if result.conflict_plans:
        print("Found conflicts. Resolve them first or rerun after adjusting the files.", file=sys.stderr)
        return 1

    apply_scan_result(result)
    print(f"Applied renames: {len(result.rename_plans)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.gui or args.root is None:
        initial_root = None if args.root is None else args.root.expanduser()
        return launch_gui(initial_root)
    return run_cli(args)


if __name__ == "__main__":
    raise SystemExit(main())
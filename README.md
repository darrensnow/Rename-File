# 视频重命名工具集

这是一个用于整理视频文件名和文件夹名的 Python 工具集，重点面向 JAV / 番号类资源的批量规范化处理。

当前仓库内提供了两套可直接使用的重命名脚本：

- `jav_rename_videos.py`
- `tmm_rename_videos.py`

这两个脚本都支持：

- 命令行预览
- 命令行实际执行重命名
- 图形界面预览
- 图形界面执行重命名
- Windows 双击启动
- Linux 图形桌面启动

脚本默认先预览，不会直接改名。只有点击界面中的 `执行重命名`，或者命令行加上 `--apply` 参数时，才会真正修改文件名。

## 功能特点

- 自动识别视频文件名中的番号
- 自动识别父文件夹名中的番号
- 同时重命名视频文件和文件夹
- 自动统一大小写，例如 `waaa-338` -> `WAAA-338`
- 自动处理常见后缀变体，例如 `ch`、`uc`、`u`
- 自动处理带前缀的网址或垃圾字符，例如 `xxxxx@WAAA-338-C`
- 支持预览结果、冲突检测、颜色区分、状态筛选

GUI 界面中：

- 绿色表示 `重命名`
- 红色表示 `冲突`
- 灰色表示 `跳过`

筛选框支持：

- `全部`
- `仅待重命名`
- `仅冲突`
- `仅跳过`

## 已支持的常见规则

示例：

- `WAAA-338` -> `WAAA-338`
- `WAAA-338-C` -> `WAAA-338-C`
- `waaa-338` -> `WAAA-338`
- `WAAA-338ch` -> `WAAA-338-C`
- `WAAA-338-UC` -> `WAAA-338-C`
- `WAAA-338-U` -> `WAAA-338`
- `XXXXX@WAAA-338-C` -> `WAAA-338-C`
- `MVSD-551-GC` -> `MVSD-551`
- `MVSD-523-C_X1080X` -> `MVSD-523-C`

## 文件说明

核心脚本：

- `jav_rename_videos.py`：JAV 视频重命名主脚本
- `tmm_rename_videos.py`：TMM 风格视频重命名主脚本

Windows 双击启动文件：

- `jav_rename_videos_gui.pyw`
- `tmm_rename_videos_gui.pyw`

Linux 桌面启动模板：

- `jav_rename_videos.desktop`
- `tmm_rename_videos.desktop`

详细中文说明文档：

- `jav_rename_videos.md`
- `tmm_rename_videos.md`

## 运行环境

- Python 3.10 及以上更稳妥
- Windows 或 Linux
- 图形界面依赖 `tkinter`

Linux 如果没有安装 `tkinter`，在 Debian / Ubuntu 上通常执行：

```bash
sudo apt install python3-tk
```

## 快速开始

### Windows 图形界面

直接双击：

```text
jav_rename_videos_gui.pyw
```

或：

```text
tmm_rename_videos_gui.pyw
```

### Windows 命令行

预览：

```powershell
py -3 jav_rename_videos.py "D:\Videos"
```

执行：

```powershell
py -3 jav_rename_videos.py "D:\Videos" --apply
```

预览：

```powershell
py -3 tmm_rename_videos.py "D:\Videos"
```

执行：

```powershell
py -3 tmm_rename_videos.py "D:\Videos" --apply
```

### Linux 图形界面

```bash
python3 jav_rename_videos.py --gui
```

```bash
python3 tmm_rename_videos.py --gui
```

### Linux 命令行

```bash
python3 jav_rename_videos.py "/data/videos" --apply
```

```bash
python3 tmm_rename_videos.py "/data/videos" --apply
```

## Linux 桌面启动方式

仓库中已经附带 `.desktop` 模板文件。

使用方式：

1. 打开对应的 `.desktop` 文件
2. 将里面的 `Exec` 和 `Path` 改成你自己的实际路径
3. 复制到桌面，或者复制到 `~/.local/share/applications/`
4. 增加执行权限

例如：

```bash
chmod +x jav_rename_videos.desktop
chmod +x tmm_rename_videos.desktop
```

## 使用建议

- 第一次处理目录时，先预览再执行
- 如果目录较大，建议先在测试目录试跑一遍
- 如果出现 `冲突`，请先手工处理冲突项，再重新预览
- 如果只想专门处理异常项，建议用 GUI 的筛选框先查看 `仅冲突`

## 注意事项

- 本工具会直接修改文件名和文件夹名
- 建议在大批量操作前先备份
- 如果你的系统是纯命令行环境，没有桌面图形界面，则只能使用命令行模式

## 文档入口

如果你需要更细的使用说明，可以继续查看：

- `jav_rename_videos.md`
- `tmm_rename_videos.md`
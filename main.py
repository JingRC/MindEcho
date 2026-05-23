#!/usr/bin/env python3
"""MindEcho 统一启动入口。"""

import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
SRC_ROOT = PROJECT_ROOT / "src"
GUI_ROOT = SRC_ROOT / "gui"


def configure_console() -> None:
    """Avoid crashes when the Windows console cannot encode emoji or symbols."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                try:
                    stream.reconfigure(errors="replace")
                except Exception:
                    pass


def bootstrap_paths() -> None:
    for path in (PROJECT_ROOT, SRC_ROOT, GUI_ROOT):
        path_str = str(path)
        if path.exists() and path_str not in sys.path:
            sys.path.insert(0, path_str)

    ffmpeg_bin = PROJECT_ROOT / "tools" / "ffmpeg" / "bin"
    ffmpeg_bin_str = str(ffmpeg_bin)
    if ffmpeg_bin.exists() and ffmpeg_bin_str not in os.environ.get("PATH", ""):
        os.environ["PATH"] = ffmpeg_bin_str + os.pathsep + os.environ.get("PATH", "")


def check_and_install_deps() -> bool:
    required_packages = {
        "numpy": "numpy",
        "scipy": "scipy",
        "sounddevice": "sounddevice",
        "matplotlib": "matplotlib",
        "PyQt6": "PyQt6.QtWidgets",
    }

    print("检查依赖包...")
    missing = []
    for package_name, import_name in required_packages.items():
        try:
            __import__(import_name)
            print(f"  已就绪: {package_name}")
        except ImportError:
            print(f"  缺失: {package_name}")
            missing.append(package_name)

    if not missing:
        return True

    print("\n开始安装缺失依赖...")
    for package_name in missing:
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
            print(f"  安装成功: {package_name}")
        except subprocess.CalledProcessError:
            print(f"  安装失败: {package_name}")
            return False

    return True


def launch_gui() -> int:
    try:
        from src.gui.integrated_recording_interface import main as integrated_main
    except ImportError as exc:
        print(f"无法导入主界面: {exc}")
        return 1

    integrated_main()
    return 0


def main() -> int:
    configure_console()
    bootstrap_paths()

    print("MindEcho 统一启动器")
    print(f"Python: {sys.executable} ({sys.version.split()[0]})")
    print("=" * 32)

    if not check_and_install_deps():
        print("依赖安装失败，请手动处理后重试。")
        return 1

    print("\n正在启动主界面...")
    return launch_gui()


if __name__ == "__main__":
    raise SystemExit(main())

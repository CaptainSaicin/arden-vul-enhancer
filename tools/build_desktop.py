#!/usr/bin/env python3
"""Build a native desktop app on the current OS and make a release ZIP.

Run from any directory after installing requirements-build.txt. PyInstaller
must run separately on Windows, macOS, and Linux; the workflow handles that.
No owner PDF is read, required, or included in the build.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
NAME = "Arden-Vul-Enhancer"
VERSION = re.search(r'^version\s*=\s*"([^"]+)"', (ROOT / "pyproject.toml").read_text(), re.M).group(1)
SOURCE_NAMES = {
    "arden_vul_enhancer", "docs", "tools", "tests", ".github", ".gitignore",
    "README.md", "LICENSE", "THIRD_PARTY_NOTICES.md", "CONTRIBUTING.md",
    "requirements.txt", "requirements-build.txt", "pyproject.toml",
    "Start-Windows.bat", "Start-macOS.command", "Start-Linux.sh",
}
EXCLUDE_PARTS = {"__pycache__", ".venv", ".git", "build", "dist", "release", ".pytest_cache"}


def run(command):
    print("Running:", " ".join(str(arg) for arg in command), flush=True)
    subprocess.run([str(arg) for arg in command], check=True, cwd=ROOT)


def safe_source_files():
    for name in sorted(SOURCE_NAMES):
        path = ROOT / name
        if not path.exists():
            continue
        candidates = [path] if path.is_file() else sorted(path.rglob("*"))
        for item in candidates:
            relative = item.relative_to(ROOT)
            if not item.is_file() or any(part in EXCLUDE_PARTS for part in relative.parts):
                continue
            if item.suffix.lower() in {".pdf", ".pyc", ".pyo", ".log"}:
                continue
            yield item, relative


def source_archive(destination):
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for item, relative in safe_source_files():
            archive.write(item, Path("arden-vul-enhancer") / relative)


def zip_tree(folder, destination):
    """Preserve executable flags and POSIX symlinks in the desktop package."""
    if sys.platform == "darwin":
        run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", folder, destination])
        return
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(folder.rglob("*")):
            relative = path.relative_to(folder.parent).as_posix()
            if path.is_symlink():
                info = zipfile.ZipInfo(relative)
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(info, os.readlink(path))
            elif path.is_file():
                archive.write(path, relative)


def dependency_notices(destination):
    """Keep the dependency notices provided with installed distributions."""
    target = destination / "dependency-notices"
    target.mkdir()
    for package in ("PyMuPDF", "pyinstaller"):
        distribution = importlib.metadata.distribution(package)
        for relative in distribution.files or []:
            name = str(relative)
            if ".dist-info/" in name and any(word in relative.name.lower() for word in ("license", "copying", "notice")):
                source = Path(distribution.locate_file(relative))
                if source.is_file():
                    shutil.copy2(source, target / f"{package}-{relative.name}")
    # Python's standard distributions usually place the interpreter license here.
    for path in (Path(sys.base_prefix) / "LICENSE.txt", Path(sys.base_prefix) / "LICENSE"):
        if path.is_file():
            shutil.copy2(path, target / "Python-LICENSE.txt")
            break


def build(platform_label=None):
    if platform_label is None:
        os_label = {"win32": "Windows", "darwin": "macOS"}.get(sys.platform, "Linux")
        platform_label = f"{os_label}-{platform.machine()}"
    if not re.fullmatch(r"[A-Za-z0-9_-]+", platform_label):
        raise SystemExit("The platform label may contain only letters, numbers, dashes, and underscores.")
    patch = ROOT / "arden_vul_enhancer" / "data" / "patch.json.gz"
    if not patch.is_file():
        raise SystemExit("Missing patch.json.gz. Use the complete source download, including its data folder.")

    build_dir = ROOT / "build" / "desktop"
    dist_dir = ROOT / "dist" / "desktop"
    build_dir.mkdir(parents=True, exist_ok=True)
    dist_dir.mkdir(parents=True, exist_ok=True)
    entry = build_dir / "desktop_entry.py"
    entry.write_text('from arden_vul_enhancer.__main__ import main\nraise SystemExit(main())\n')

    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--onedir", "--windowed", "--name", NAME,
        "--distpath", str(dist_dir), "--workpath", str(build_dir / "work"),
        "--specpath", str(build_dir), "--paths", str(ROOT),
        "--collect-all", "pymupdf", "--copy-metadata", "PyMuPDF",
        "--add-data", str(patch) + os.pathsep + "arden_vul_enhancer/data",
        "--add-data", str(ROOT / "LICENSE") + os.pathsep + ".",
        str(entry),
    ]
    # Some portable CPython distributions carry Tcl/Tk beside libpython,
    # outside the system dynamic-linker cache. Include those libraries too.
    if sys.platform.startswith("linux"):
        local_gui_libraries = set()
        for pattern in ("libtcl*.so*", "libtk*.so*"):
            local_gui_libraries.update((Path(sys.base_prefix) / "lib").glob(pattern))
        for library in sorted(local_gui_libraries):
            if library.is_file() and not library.is_symlink():
                command[-1:-1] = ["--add-binary", str(library) + os.pathsep + "."]
    if sys.platform == "darwin":
        command[command.index(str(entry)):command.index(str(entry))] = [
            "--osx-bundle-identifier", "org.ardenvul.enhancer",
        ]
    run(command)

    executable = dist_dir / NAME / (NAME + (".exe" if sys.platform == "win32" else ""))
    if sys.platform == "darwin":
        executable = dist_dir / (NAME + ".app") / "Contents" / "MacOS" / NAME
    run([executable, "--self-check"])

    stage = build_dir / "package" / NAME
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    source_app = dist_dir / (NAME + ".app") if sys.platform == "darwin" else dist_dir / NAME
    if sys.platform == "darwin":
        shutil.copytree(source_app, stage / source_app.name, symlinks=True)
    else:
        shutil.copytree(source_app, stage, dirs_exist_ok=True, symlinks=True)
    for filename in ("LICENSE", "THIRD_PARTY_NOTICES.md", "README.md"):
        shutil.copy2(ROOT / filename, stage / filename)
    shutil.copy2(ROOT / "docs" / "USER_GUIDE.md", stage / "USER_GUIDE.md")
    dependency_notices(stage)
    source_archive(stage / "Arden-Vul-Enhancer-source.zip")

    version_info = {"app_version": VERSION, "platform": platform_label,
                    "python": platform.python_version(),
                    "pymupdf": importlib.metadata.version("PyMuPDF"),
                    "pyinstaller": importlib.metadata.version("pyinstaller")}
    (stage / "BUILD-INFO.json").write_text(json.dumps(version_info, indent=2) + "\n")
    release = ROOT / "release"
    release.mkdir(exist_ok=True)
    output = release / f"{NAME}-v{VERSION}-{platform_label}.zip"
    if output.exists():
        output.unlink()
    zip_tree(stage, output)
    print(f"\nDesktop download ready: {output}\nSize: {output.stat().st_size / (1024 * 1024):.1f} MiB")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform-label", help="Friendly platform label for the downloadable ZIP")
    arguments = parser.parse_args()
    build(arguments.platform_label)

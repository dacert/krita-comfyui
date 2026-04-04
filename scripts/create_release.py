"""
Script to generate the release package for the Krita ComfyUI plugin.
"""

import os
import sys
import tarfile
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

TEMP_EXTENSIONS = frozenset((
    ".pyc",
    ".pyo",
    ".pyd",
    ".so",
    ".dist-info",
    ".egg-info",
    ".config",
    ".log",
))


def _should_exclude(path: Path) -> bool:
    """Check if a file or directory should be excluded."""
    return "__pycache__" in path.parts or path.suffix in TEMP_EXTENSIONS


def _add_directory_to_zip(
    zip_file: ZipFile, source_dir: Path, archive_prefix: Path, exclude_dir: str = ""
) -> None:
    """Add filtered directory contents to ZIP."""
    for root, dirs, files in os.walk(source_dir):
        file_path = Path(root)

        # Prune excluded directories
        if exclude_dir and file_path.name == exclude_dir:
            dirs[:] = []
            continue

        rel_path = file_path.relative_to(source_dir)
        if rel_path != Path(".") and "__pycache__" not in rel_path.parts:
            arcname = (archive_prefix / rel_path).as_posix()
            zip_file.writestr(f"{arcname}/", "")

        for file in files:
            full_path = file_path / file
            if _should_exclude(full_path):
                continue
            arcname = (archive_prefix / rel_path / file).as_posix()
            zip_file.write(full_path, arcname)


def find_websockets(krita_comfyui_dir: Path) -> Path:
    """Find the websockets tarball for inclusion in the release package."""
    websockets_dir = krita_comfyui_dir / "websockets"
    matches = list(websockets_dir.glob("dist/websockets-*.tar.gz"))
    if not matches:
        raise FileNotFoundError(
            f"No websockets tarball found in {websockets_dir}/dist/, execute: BUILD_EXTENSION=no python -m build krita_comfyui/websockets"
        )
    return matches[0]


def _extract_tarball(tarball_path: Path, dest_dir: Path) -> Path:
    """Extract tarball and return the internal root directory name."""
    with tarfile.open(tarball_path, "r:gz") as tar:
        internal_dir = next(
            (m.name.split("/")[0] for m in tar.getmembers() if "/" in m.name),
            None,
        )
        if internal_dir is None:
            raise ValueError(f"Invalid tarball structure: {tarball_path}")
        tar.extractall(dest_dir)
    return dest_dir / internal_dir


def create_release(zip_name: str) -> Path:
    """Create the release package for the Krita ComfyUI plugin."""
    project_root = Path(__file__).resolve().parent.parent
    krita_comfyui_dir = project_root / "krita_comfyui"
    desktop_file = project_root / "krita_comfyui.desktop"
    license_file = project_root / "LICENSE"

    missing_files = [d for d in (krita_comfyui_dir, desktop_file, license_file) if not d.exists()]
    if missing_files:
        raise FileNotFoundError(
            f"Required files not found: {', '.join(str(f) for f in missing_files)}"
        )

    dist_path = project_root / "dist"
    dist_path.mkdir(parents=True, exist_ok=True)

    output_path = dist_path / zip_name

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        with ZipFile(output_path, "w", compression=ZIP_DEFLATED, compresslevel=9) as zip_file:
            zip_file.writestr("krita_comfyui/", "")
            zip_file.write(license_file, "krita_comfyui/LICENSE")
            zip_file.write(desktop_file, "krita_comfyui.desktop")
            _add_directory_to_zip(
                zip_file, krita_comfyui_dir, Path("krita_comfyui"), exclude_dir="websockets"
            )

            tarball_path = find_websockets(krita_comfyui_dir)
            extracted = _extract_tarball(tarball_path, temp_path)
            _add_directory_to_zip(zip_file, extracted, Path("krita_comfyui/websockets"))

    return output_path


def main():
    sys.path.insert(0, str(Path(__file__).parent.parent))
    import krita_comfyui

    version = krita_comfyui.__version__
    zip_name = f"krita_comfyui-{version}.zip"

    try:
        result = create_release(zip_name)
        print(f"\nSuccess! Package created at: {result}")
    except Exception as e:
        print(f"\nError: {e}")
        raise


if __name__ == "__main__":
    main()

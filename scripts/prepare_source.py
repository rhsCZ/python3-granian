#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import shutil
import stat
import tarfile
import tempfile
import urllib.request
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path


PACKAGE_NAME = "python3-granian"
MAINTAINER = "PPA Builder <builder@example.com>"


def read_series_ubuntu_version(config_path: Path, series_name: str) -> str:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    for item in config["series"]:
        if item["name"] == series_name:
            return item["ubuntu_version"]
    raise ValueError(f"Unknown series '{series_name}' in {config_path}")


def read_upload_revision(state_path: Path, version: str, series_name: str) -> int:
    if not state_path.exists():
        return 1

    state = json.loads(state_path.read_text(encoding="utf-8"))
    uploads = state.get("uploads", {})
    series_uploads = uploads.get(version, {})
    return int(series_uploads.get(series_name, 0)) + 1


def build_package_version(version: str, ubuntu_version: str, revision: int) -> str:
    return f"{version}-{ubuntu_version}+0ubuntu{revision}"


def download_file(url: str, destination: Path) -> None:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "python3-granian-launchpad-packaging"},
    )
    with urllib.request.urlopen(request) as response, destination.open("wb") as handle:
        shutil.copyfileobj(response, handle)


def extract_tarball(archive_path: Path, destination: Path) -> Path:
    with tarfile.open(archive_path, "r:*") as archive:
        try:
            archive.extractall(destination, filter="data")
        except TypeError:
            archive.extractall(destination)

    extracted = [path for path in destination.iterdir() if path.is_dir()]
    if len(extracted) != 1:
        raise RuntimeError(f"Expected one extracted directory in {destination}, found {len(extracted)}")
    return extracted[0]


def write_changelog(path: Path, version: str, series: str, tag: str) -> None:
    timestamp = format_datetime(datetime.now(timezone.utc))
    content = (
        f"{PACKAGE_NAME} ({version}) {series}; urgency=medium\n\n"
        f"  * Package upstream Granian release {tag}.\n\n"
        f" -- {MAINTAINER}  {timestamp}\n"
    )
    path.write_text(content, encoding="utf-8", newline="\n")


def ensure_executable(path: Path) -> None:
    if not path.exists():
        return

    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def ensure_non_executable(path: Path) -> None:
    if not path.exists():
        return

    path.chmod(path.stat().st_mode & ~(stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))


def normalize_debian_permissions(debian_dir: Path) -> None:
    executable_files = {"rules"}

    for path in debian_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.name in executable_files:
            ensure_executable(path)
        else:
            ensure_non_executable(path)


def write_metadata(path: Path, *, version: str, tag: str, series: str, source_dir: Path, revision: int) -> None:
    metadata = {
        "package_name": PACKAGE_NAME,
        "package_version": version,
        "series": series,
        "tag": tag,
        "revision": revision,
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "source_dir": str(source_dir),
    }
    path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--series", required=True)
    parser.add_argument("--config", default="config/series.json")
    parser.add_argument("--template-dir", default="debian-template")
    parser.add_argument("--output-dir", default="work/prepared")
    parser.add_argument("--upload-state", default="versions/uploads.json")
    parser.add_argument("--tarball-url")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    template_dir = Path(args.template_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    upload_state_path = Path(args.upload_state).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    ubuntu_version = read_series_ubuntu_version(config_path, args.series)
    revision = read_upload_revision(upload_state_path, args.version, args.series)
    package_version = build_package_version(args.version, ubuntu_version, revision)
    source_dir = output_dir / f"{PACKAGE_NAME}-{package_version}"

    if source_dir.exists():
        shutil.rmtree(source_dir)

    tarball_url = args.tarball_url or f"https://github.com/emmett-framework/granian/archive/refs/tags/{args.tag}.tar.gz"

    with tempfile.TemporaryDirectory() as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        archive_path = temp_dir / f"{args.tag}.tar.gz"
        download_file(tarball_url, archive_path)
        extracted_root = extract_tarball(archive_path, temp_dir / "src")
        shutil.copytree(extracted_root, source_dir)

    debian_dir = source_dir / "debian"
    if debian_dir.exists():
        shutil.rmtree(debian_dir)
    shutil.copytree(template_dir, debian_dir)
    normalize_debian_permissions(debian_dir)
    write_changelog(debian_dir / "changelog", package_version, args.series, args.tag)
    write_metadata(
        debian_dir / ".packaging-info.json",
        version=package_version,
        tag=args.tag,
        series=args.series,
        source_dir=source_dir,
        revision=revision,
    )

    print(source_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path


RUSTFLAGS_BLOCK = """[build]
rustflags = ["--cfg", "pyo3_disable_reference_pool"]
"""


def run(*args: str, cwd: Path) -> str:
    result = subprocess.run(args, cwd=cwd, check=True, text=True, capture_output=True)
    return result.stdout


def resolve_cargo_binary() -> str:
    preferred = os.environ.get("CARGO_BIN")
    if preferred:
        return preferred

    for candidate in ("cargo-1.96", "cargo"):
        path = shutil.which(candidate)
        if path:
            return path

    raise FileNotFoundError("Neither cargo-1.96 nor cargo was found in PATH")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", required=True)
    args = parser.parse_args()

    source_dir = Path(args.source_dir).resolve()
    vendor_dir = source_dir / "vendor"
    cargo_dir = source_dir / ".cargo"
    config_path = cargo_dir / "config.toml"
    cargo_bin = resolve_cargo_binary()

    if vendor_dir.exists():
        shutil.rmtree(vendor_dir)
    cargo_dir.mkdir(parents=True, exist_ok=True)

    vendor_config = run(cargo_bin, "vendor", "--locked", "--versioned-dirs", "vendor", cwd=source_dir).strip()
    config_path.write_text(RUSTFLAGS_BLOCK + "\n" + vendor_config + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

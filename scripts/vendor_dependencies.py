#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path


RUSTFLAGS_BLOCK = """[build]
rustflags = ["--cfg", "pyo3_disable_reference_pool"]
"""

def run(*args: str, cwd: Path) -> str:
    result = subprocess.run(args, cwd=cwd, check=True, text=True, capture_output=True)
    return result.stdout


def sha256_hex(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def update_cargo_checksum(crate_dir: Path, relative_paths: list[str]) -> None:
    checksum_path = crate_dir / ".cargo-checksum.json"
    if not checksum_path.exists():
        return

    checksum_data = json.loads(checksum_path.read_text(encoding="utf-8"))
    files = checksum_data.setdefault("files", {})
    for relative_path in relative_paths:
        files[relative_path] = sha256_hex(crate_dir / relative_path)
    checksum_path.write_text(
        json.dumps(checksum_data, separators=(",", ":")),
        encoding="utf-8",
        newline="\n",
    )


def apply_replacements(path: Path, replacements: list[tuple[str, str]]) -> bool:
    original = path.read_text(encoding="utf-8")
    updated = original
    changed = False
    for before, after in replacements:
        if before not in updated:
            continue
        updated = updated.replace(before, after, 1)
        changed = True

    if not changed or updated == original:
        return False

    path.write_text(updated, encoding="utf-8", newline="\n")
    return True


def resolve_cargo_binary() -> str:
    preferred = os.environ.get("CARGO_BIN")
    if preferred:
        return preferred

    for candidate in ("cargo-1.96", "cargo"):
        path = shutil.which(candidate)
        if path:
            return path

    raise FileNotFoundError("Neither cargo-1.96 nor cargo was found in PATH")


def patch_target_lexicon_riscv64a23(crate_dir: Path) -> None:
    targets_path = crate_dir / "src" / "targets.rs"
    if not targets_path.exists():
        return

    original = targets_path.read_text(encoding="utf-8")
    if 'Riscv64a23 => Cow::Borrowed("riscv64a23")' in original:
        return

    updated = original
    replacements = [
        (
            "pub enum Riscv64Architecture {\n"
            "    Riscv64,\n"
            "    Riscv64gc,\n"
            "    Riscv64imac,\n"
            "}\n",
            "pub enum Riscv64Architecture {\n"
            "    Riscv64,\n"
            "    Riscv64gc,\n"
            "    Riscv64imac,\n"
            "    Riscv64a23,\n"
            "}\n",
        ),
        (
            '            Riscv64gc => Cow::Borrowed("riscv64gc"),\n'
            '            Riscv64imac => Cow::Borrowed("riscv64imac"),\n',
            '            Riscv64gc => Cow::Borrowed("riscv64gc"),\n'
            '            Riscv64imac => Cow::Borrowed("riscv64imac"),\n'
            '            Riscv64a23 => Cow::Borrowed("riscv64a23"),\n',
        ),
        (
            '            "riscv64gc" => Riscv64gc,\n'
            '            "riscv64imac" => Riscv64imac,\n',
            '            "riscv64gc" => Riscv64gc,\n'
            '            "riscv64imac" => Riscv64imac,\n'
            '            "riscv64a23" => Riscv64a23,\n',
        ),
        (
            '            "riscv64gc-unknown-linux-gnu",\n'
            '            "riscv64gc-unknown-linux-musl",\n',
            '            "riscv64gc-unknown-linux-gnu",\n'
            '            "riscv64a23-unknown-linux-gnu",\n'
            '            "riscv64gc-unknown-linux-musl",\n',
        ),
    ]

    for before, after in replacements:
        if before not in updated:
            raise RuntimeError(f"Unable to patch {targets_path}: expected snippet not found")
        updated = updated.replace(before, after, 1)

    if updated == original:
        return

    targets_path.write_text(updated, encoding="utf-8", newline="\n")
    update_cargo_checksum(crate_dir, ["src/targets.rs"])


def patch_cc_riscv64a23(crate_dir: Path) -> None:
    updated_paths: list[str] = []
    replacements = {
        "src/lib.rs": [
            (
                '                    "riscv64gc-unknown-linux-gnu" => Some("riscv64-linux-gnu"),\n',
                '                    "riscv64gc-unknown-linux-gnu" => Some("riscv64-linux-gnu"),\n'
                '                    "riscv64a23-unknown-linux-gnu" => Some("riscv64-linux-gnu"),\n',
            ),
        ],
        "src/target/generated.rs": [
            (
                '    ("riscv64gc-unknown-freebsd", "riscv64-unknown-freebsd"),\n',
                '    ("riscv64a23-unknown-linux-gnu", "riscv64-unknown-linux-gnu"),\n'
                '    ("riscv64gc-unknown-freebsd", "riscv64-unknown-freebsd"),\n',
            ),
        ],
        "src/target_info.rs": [
            (
                '    ("riscv64gc", "riscv64"),\n',
                '    ("riscv64gc", "riscv64"),\n'
                '    ("riscv64a23", "riscv64"),\n',
            ),
        ],
    }

    for relative_path, file_replacements in replacements.items():
        path = crate_dir / relative_path
        if not path.exists():
            continue

        original = path.read_text(encoding="utf-8")
        if "riscv64a23" in original:
            continue

        updated = original
        changed = False
        for before, after in file_replacements:
            if before in updated:
                updated = updated.replace(before, after, 1)
                changed = True

        if not changed or updated == original:
            continue

        path.write_text(updated, encoding="utf-8", newline="\n")
        updated_paths.append(relative_path)

    if updated_paths:
        update_cargo_checksum(crate_dir, updated_paths)


def patch_ahash_riscv64a23(crate_dir: Path) -> None:
    build_rs = crate_dir / "build.rs"
    if not build_rs.exists():
        return
    if 'arch.eq_ignore_ascii_case("riscv64a23")' in build_rs.read_text(encoding="utf-8"):
        return

    if apply_replacements(
        build_rs,
        [
            (
                '        || arch.eq_ignore_ascii_case("riscv64gc")\n',
                '        || arch.eq_ignore_ascii_case("riscv64gc")\n'
                '        || arch.eq_ignore_ascii_case("riscv64a23")\n',
            ),
        ],
    ):
        update_cargo_checksum(crate_dir, ["build.rs"])


def patch_cargo_zigbuild_riscv64a23(crate_dir: Path) -> None:
    zig_rs = crate_dir / "src" / "zig.rs"
    if not zig_rs.exists():
        return
    if '"riscv64a23"' in zig_rs.read_text(encoding="utf-8"):
        return

    if apply_replacements(
        zig_rs,
        [
            (
                '                "riscv64gc" => "generic_rv64+m+a+f+d+c",\n',
                '                "riscv64gc" => "generic_rv64+m+a+f+d+c",\n'
                '                "riscv64a23" => "generic_rv64+m+a+f+d+c",\n',
            ),
            (
                '                "riscv64gc" => "riscv64",\n',
                '                "riscv64gc" => "riscv64",\n'
                '                "riscv64a23" => "riscv64",\n',
            ),
        ],
    ):
        update_cargo_checksum(crate_dir, ["src/zig.rs"])


def patch_libc_riscv64a23(crate_dir: Path) -> None:
    cargo_toml = crate_dir / "Cargo.toml"
    if not cargo_toml.exists():
        return
    if '"riscv64a23-unknown-linux-gnu"' in cargo_toml.read_text(encoding="utf-8"):
        return

    if apply_replacements(
        cargo_toml,
        [
            (
                '    "riscv64gc-unknown-linux-gnu",\n',
                '    "riscv64gc-unknown-linux-gnu",\n'
                '    "riscv64a23-unknown-linux-gnu",\n',
            ),
        ],
    ):
        update_cargo_checksum(crate_dir, ["Cargo.toml"])


def patch_vendored_target_lexicons(vendor_dir: Path) -> None:
    for crate_dir in sorted(vendor_dir.glob("target-lexicon-*")):
        if crate_dir.is_dir():
            patch_target_lexicon_riscv64a23(crate_dir)


def patch_vendored_cc_crates(vendor_dir: Path) -> None:
    for crate_dir in sorted(vendor_dir.glob("cc-*")):
        if crate_dir.is_dir():
            patch_cc_riscv64a23(crate_dir)


def patch_vendored_ahash_crates(vendor_dir: Path) -> None:
    for crate_dir in sorted(vendor_dir.glob("ahash-*")):
        if crate_dir.is_dir():
            patch_ahash_riscv64a23(crate_dir)


def patch_vendored_cargo_zigbuild_crates(vendor_dir: Path) -> None:
    for crate_dir in sorted(vendor_dir.glob("cargo-zigbuild-*")):
        if crate_dir.is_dir():
            patch_cargo_zigbuild_riscv64a23(crate_dir)


def patch_vendored_libc_crates(vendor_dir: Path) -> None:
    for crate_dir in sorted(vendor_dir.glob("libc-*")):
        if crate_dir.is_dir():
            patch_libc_riscv64a23(crate_dir)


def sanitize_rust_source_for_audit(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    lines = text.splitlines()
    sanitized: list[str] = []
    pending_test = False
    skipping_test = False
    brace_depth = 0

    for line in lines:
        stripped = line.strip()
        if skipping_test:
            brace_depth += line.count("{") - line.count("}")
            if brace_depth <= 0:
                skipping_test = False
            continue

        if stripped.startswith("#[test") or stripped.startswith("#[tokio::test"):
            pending_test = True
            continue
        if pending_test and stripped.startswith("#["):
            continue
        if pending_test and "fn " in stripped:
            skipping_test = True
            brace_depth = line.count("{") - line.count("}")
            pending_test = False
            if brace_depth <= 0:
                skipping_test = False
            continue
        if pending_test and stripped and not stripped.startswith("#["):
            pending_test = False

        sanitized.append(re.sub(r"//.*", "", line))

    return "\n".join(sanitized)


def sanitize_text_for_audit(path: Path, text: str) -> str:
    if path.suffix == ".rs":
        return sanitize_rust_source_for_audit(text)
    if path.suffix in {".toml", ".lock"}:
        return re.sub(r"#.*", "", text)
    return text


def audit_vendored_riscv_aliases(vendor_dir: Path, report_path: Path) -> None:
    ignored_suffixes = {
        ".a",
        ".bin",
        ".gif",
        ".jpg",
        ".jpeg",
        ".json",
        ".lock",
        ".pdf",
        ".png",
        ".svg",
        ".toml.orig",
    }
    ignored_names = {
        ".cargo-checksum.json",
        "CHANGELOG.md",
        "README.md",
    }
    ignored_parts = {
        ".github",
        "examples",
        "tests",
    }

    offenders: dict[str, list[str]] = {}
    for path in sorted(vendor_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.name in ignored_names:
            continue
        if any(part in ignored_parts for part in path.parts):
            continue
        if any(path.name.endswith(suffix) for suffix in ignored_suffixes):
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        text = sanitize_text_for_audit(path, text)
        if "riscv64gc" not in text or "riscv64a23" in text:
            continue

        relative_path = path.relative_to(vendor_dir)
        crate_name = relative_path.parts[0]
        offenders.setdefault(crate_name, []).append(relative_path.as_posix())

    report_path.write_text(
        json.dumps(
            {
                "missing_riscv64a23_alias": [
                    {"crate": crate_name, "files": files}
                    for crate_name, files in sorted(offenders.items())
                ]
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


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
    patch_vendored_ahash_crates(vendor_dir)
    patch_vendored_cargo_zigbuild_crates(vendor_dir)
    patch_vendored_cc_crates(vendor_dir)
    patch_vendored_libc_crates(vendor_dir)
    patch_vendored_target_lexicons(vendor_dir)
    audit_vendored_riscv_aliases(vendor_dir, source_dir / "vendor" / "riscv64a23-audit.json")
    config_path.write_text(RUSTFLAGS_BLOCK + "\n" + vendor_config + "\n", encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

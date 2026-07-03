# python3-granian Launchpad Packaging

This repository tracks upstream releases from `emmett-framework/granian`,
prepares a native Debian source package for `python3-granian`, and uploads the
signed source package to a Launchpad PPA.

## Workflow

1. A scheduled GitHub Actions workflow checks the latest upstream release.
2. For each configured Ubuntu series, the workflow prepares a source tree with:
   - upstream Granian source
   - `debian/` packaging from `debian-template/`
   - vendored Cargo dependencies
3. GitHub builds a signed native source package.
4. The source package is uploaded to the configured Launchpad PPA.
5. Launchpad builds binary packages for the architectures available in that PPA.

## Repository layout

- `debian-template/` Debian packaging template copied into each prepared source tree
- `config/series.json` target Ubuntu series and version suffix prefixes
- `scripts/` release detection, source preparation, source build, vendoring, and upload helpers
- `.github/workflows/` scheduled and manual GitHub Actions workflows
- `versions/state.json` last successfully uploaded upstream release
- `versions/uploads.json` upload counters used to increment suffixes such as `noble1`, `noble2`, ...

## Packaging model

- The generated source package format is `3.0 (native)`.
- Package versions follow the PPA revision style used by the existing package, for example `2.7.8-1~ppa1~noble2`.
- The resulting source package contains a single `.tar.xz` payload.
- Cargo dependencies are vendored into the prepared source tree so Launchpad builds remain offline-capable.

## Required GitHub secrets

- `LAUNCHPAD_GPG_PRIVATE_KEY` ASCII-armored private key used to sign source uploads
- `LAUNCHPAD_GPG_PASSPHRASE` passphrase for the private key
- `LAUNCHPAD_GPG_KEY_ID` signing key identifier used by `dpkg-buildpackage`
- `LAUNCHPAD_PPA` target upload shortcut, for example `ppa:example/ubuntu/python3-granian`

## Required Launchpad setup

1. Import the public GPG key into the Launchpad account that owns or can upload to the PPA.
2. Ensure the PPA exposes the required build dependencies for each target series.
3. Upload auxiliary toolchain packages such as `rustc-1.96` and `cargo-1.96` before uploading Granian.

#!/usr/bin/env bash

set -euo pipefail

SOURCE_DIR="$(realpath "${1:?source dir is required}")"
GPG_KEY_ID="${2:?gpg key id or fingerprint is required}"
OUTPUT_DIR="${3:-dist}"

mkdir -p "${OUTPUT_DIR}"

pushd "${SOURCE_DIR}" >/dev/null

SOURCE_NAME="$(dpkg-parsechangelog -S Source)"
SOURCE_VERSION="$(dpkg-parsechangelog -S Version)"
PARENT_DIR="$(dirname "${SOURCE_DIR}")"

if [ -f "debian/rules" ]; then
    chmod +x debian/rules
fi

export DEB_SIGN_KEYID="${GPG_KEY_ID}"
dpkg-buildpackage -d -S -sa -k"${GPG_KEY_ID}"

popd >/dev/null

shopt -s nullglob
for artifact in \
    "${PARENT_DIR}/${SOURCE_NAME}_${SOURCE_VERSION}.tar."* \
    "${PARENT_DIR}/${SOURCE_NAME}_${SOURCE_VERSION}.dsc" \
    "${PARENT_DIR}/${SOURCE_NAME}_${SOURCE_VERSION}_source.buildinfo" \
    "${PARENT_DIR}/${SOURCE_NAME}_${SOURCE_VERSION}_source.changes"
do
    mv "${artifact}" "${OUTPUT_DIR}/"
done

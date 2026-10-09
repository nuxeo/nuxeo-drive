#!/usr/bin/env bash
#
# Build the universal (arm64 + x86_64) `check_open` helper and install it into
# the application data directory so PyInstaller ships it.
#
# Run from anywhere:
#     ./tools/osx/utilities/build_check_open.sh
#
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${HERE}/../../.." && pwd)"

SOURCE="${HERE}/check_open.swift"
OUTPUT_DIR="${REPO_ROOT}/nxdrive/drive/data/utilities"
OUTPUT="${OUTPUT_DIR}/check_open"

# Oldest macOS the application supports. Both slices target the same version so
# the binary runs everywhere the app does.
DEPLOYMENT_TARGET="11.0"

BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "${BUILD_DIR}"' EXIT

echo "Building arm64 slice..."
swiftc -O \
    -target "arm64-apple-macos${DEPLOYMENT_TARGET}" \
    -o "${BUILD_DIR}/check_open-arm64" \
    "${SOURCE}"

echo "Building x86_64 slice..."
swiftc -O \
    -target "x86_64-apple-macos${DEPLOYMENT_TARGET}" \
    -o "${BUILD_DIR}/check_open-x86_64" \
    "${SOURCE}"

echo "Creating universal binary..."
mkdir -p "${OUTPUT_DIR}"
lipo -create \
    "${BUILD_DIR}/check_open-arm64" \
    "${BUILD_DIR}/check_open-x86_64" \
    -output "${OUTPUT}"

chmod +x "${OUTPUT}"

echo
echo "Built ${OUTPUT}"
lipo -info "${OUTPUT}"

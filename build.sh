#!/bin/sh
set -eu

PROJECT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
OUTPUT_DIR="${1:-$PROJECT_DIR/dist}"
CONTROL_FILE="$PROJECT_DIR/DEBIAN/control"
BUILD_DIR="$PROJECT_DIR/.build"

PACKAGE_NAME="$(sed -n 's/^Package:[[:space:]]*//p' "$CONTROL_FILE" | head -n 1)"
PACKAGE_VERSION="$(sed -n 's/^Version:[[:space:]]*//p' "$CONTROL_FILE" | head -n 1)"
PACKAGE_ARCH="$(sed -n 's/^Architecture:[[:space:]]*//p' "$CONTROL_FILE" | head -n 1)"

for command_name in dpkg-deb chmod mkdir cp find; do
    command -v "$command_name" >/dev/null 2>&1 || {
        echo "$command_name is required." >&2
        exit 1
    }
done

rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"
STAGING="$BUILD_DIR/package"
trap 'rm -rf "$BUILD_DIR"' EXIT

mkdir -p "$STAGING"
cp -a "$PROJECT_DIR/DEBIAN" "$STAGING/"
cp -a "$PROJECT_DIR/usr" "$STAGING/"
find "$STAGING/usr" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
find "$STAGING/usr" -type d -name '__pycache__' -empty -delete

chmod 755 "$STAGING/DEBIAN/postinst"
chmod 755 "$STAGING/DEBIAN/prerm"

mkdir -p "$OUTPUT_DIR"
OUTPUT_DIR="$(CDPATH= cd -- "$OUTPUT_DIR" && pwd)"
PACKAGE="$OUTPUT_DIR/${PACKAGE_NAME}_${PACKAGE_VERSION}_${PACKAGE_ARCH}.deb"

dpkg-deb --build --root-owner-group -Zgzip -z9 "$STAGING" "$PACKAGE"
echo "$PACKAGE"

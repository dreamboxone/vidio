#!/bin/sh
set -eu

PROJECT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
OUTPUT_DIR="${1:-$PROJECT_DIR/dist}"
CONTROL_FILE="$PROJECT_DIR/IPK/control"
BUILD_DIR="$PROJECT_DIR/.build-ipk"

PACKAGE_NAME="$(sed -n 's/^Package:[[:space:]]*//p' "$CONTROL_FILE" | head -n 1)"
PACKAGE_VERSION="$(sed -n 's/^Version:[[:space:]]*//p' "$CONTROL_FILE" | head -n 1)"
PACKAGE_ARCH="$(sed -n 's/^Architecture:[[:space:]]*//p' "$CONTROL_FILE" | head -n 1)"

for command_name in ar chmod cp find mkdir sed tar; do
    command -v "$command_name" >/dev/null 2>&1 || {
        echo "$command_name is required." >&2
        exit 1
    }
done

rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR/package/CONTROL" "$BUILD_DIR/archive"
trap 'rm -rf "$BUILD_DIR"' EXIT

cp -a "$PROJECT_DIR/usr" "$BUILD_DIR/package/"
cp "$PROJECT_DIR/IPK/control" "$BUILD_DIR/package/CONTROL/control"
cp "$PROJECT_DIR/IPK/preinst" "$BUILD_DIR/package/CONTROL/preinst"
cp "$PROJECT_DIR/IPK/postinst" "$BUILD_DIR/package/CONTROL/postinst"
cp "$PROJECT_DIR/IPK/prerm" "$BUILD_DIR/package/CONTROL/prerm"
find "$BUILD_DIR/package/usr" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
find "$BUILD_DIR/package/usr" -type d -name '__pycache__' -empty -delete
chmod 755 "$BUILD_DIR/package/CONTROL/preinst" "$BUILD_DIR/package/CONTROL/postinst" "$BUILD_DIR/package/CONTROL/prerm"

tar -czf "$BUILD_DIR/archive/control.tar.gz" --owner=0 --group=0 -C "$BUILD_DIR/package/CONTROL" .
tar -czf "$BUILD_DIR/archive/data.tar.gz" --owner=0 --group=0 -C "$BUILD_DIR/package" --exclude=./CONTROL .
printf '2.0\n' > "$BUILD_DIR/archive/debian-binary"

mkdir -p "$OUTPUT_DIR"
OUTPUT_DIR="$(CDPATH= cd -- "$OUTPUT_DIR" && pwd)"
PACKAGE="$OUTPUT_DIR/${PACKAGE_NAME}_${PACKAGE_VERSION}_${PACKAGE_ARCH}.ipk"

rm -f "$PACKAGE"
cd "$BUILD_DIR/archive"
ar -cr "$PACKAGE" debian-binary control.tar.gz data.tar.gz
echo "$PACKAGE"

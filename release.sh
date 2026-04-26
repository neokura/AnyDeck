#!/bin/bash

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PLUGIN_SLUG="anydeck"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RELEASE_DIR="$SCRIPT_DIR/release"

cleanup() {
    if [ -n "${STAGING_DIR:-}" ] && [ -d "$STAGING_DIR" ]; then
        rm -rf "$STAGING_DIR"
    fi
}
trap cleanup EXIT

cd "$SCRIPT_DIR"

echo -e "${GREEN}=== AnyDeck Release Script ===${NC}"
echo ""

PACKAGE_VERSION=""
if [ -f package.json ] && command -v node >/dev/null 2>&1; then
    PACKAGE_VERSION="$(node -p "require('./package.json').version")"
fi

VERSION="${1:-$PACKAGE_VERSION}"
if [ -z "$VERSION" ]; then
    echo -e "${RED}Error: Could not determine the release version from package.json.${NC}"
    exit 1
fi

if [[ ! $VERSION =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$ ]]; then
    echo -e "${RED}Error: Invalid version format. Use semantic versioning (for example 0.2.0-alpha.0).${NC}"
    exit 1
fi

if [ -n "$PACKAGE_VERSION" ] && [ "$PACKAGE_VERSION" != "$VERSION" ]; then
    echo -e "${RED}Error: package.json version is ${PACKAGE_VERSION}, but the requested release version is ${VERSION}.${NC}"
    echo -e "${YELLOW}Update package.json first, then rerun this script.${NC}"
    exit 1
fi

echo -e "${YELLOW}Building project...${NC}"
pnpm run build
echo -e "${GREEN}✓ Build complete${NC}"

STAGING_DIR="$(mktemp -d)"
PACKAGE_ROOT="$STAGING_DIR/$PLUGIN_SLUG"
mkdir -p "$PACKAGE_ROOT"
mkdir -p "$RELEASE_DIR"

cp -R dist "$PACKAGE_ROOT/"
cp main.py plugin.json package.json LICENSE README.md "$PACKAGE_ROOT/"
cp -R icons "$PACKAGE_ROOT/"
rm -f "$PACKAGE_ROOT"/dist/*.map

ZIP_NAME="${PLUGIN_SLUG}-v${VERSION}.zip"
ZIP_PATH="$RELEASE_DIR/$ZIP_NAME"
rm -f "$ZIP_PATH"

echo -e "${YELLOW}Creating release zip: ${ZIP_NAME}${NC}"
(
    cd "$STAGING_DIR"
    zip -rq "$ZIP_PATH" "$PLUGIN_SLUG" -x "*.DS_Store" "*/.DS_Store"
)
echo -e "${GREEN}✓ Release zip created${NC}"

echo ""
echo -e "${YELLOW}Zip contents:${NC}"
unzip -l "$ZIP_PATH"

echo ""
echo -e "${GREEN}=== Release v${VERSION} ready! ===${NC}"
echo -e "File: ${ZIP_PATH}"

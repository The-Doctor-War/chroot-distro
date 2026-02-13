#!/bin/bash

# Enable strict mode
set -euo pipefail

if ! command -v npm &>/dev/null; then
	echo "Error: npm is not installed or not in PATH."
	exit 1
fi

echo "✅ npm found."

echo "Building WebUI..."
cd webui
npm ci
npm run build
cd ..
echo "✅ Built WebUI to webroot/"

echo "Creating chroot-distro.zip..."
mkdir -p data
rm -f chroot-distro.zip

zip -r chroot-distro.zip . \
	-x "README.md" \
	-x "CHANGELOG.md" \
	-x ".git/*" \
	-x ".github/*" \
	-x ".agent/*" \
	-x ".editorconfig" \
	-x "*.zip" \
	-x "webui/*" \
	-x "webui" \
	-x "build.sh" \
	-x "tools/*"

ls -lh chroot-distro.zip
echo "✅ Created chroot-distro.zip"

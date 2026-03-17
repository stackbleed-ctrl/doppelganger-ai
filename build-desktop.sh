#!/usr/bin/env bash
# build-desktop.sh
# Builds the Doppelganger desktop app (no Docker required)
# Prerequisites: Rust, Node.js 18+, Python 3.11+

set -e

echo "🧬 Building Doppelganger Desktop..."

# Check prerequisites
command -v rustc >/dev/null 2>&1 || { echo "❌ Rust not found. Install: https://rustup.rs"; exit 1; }
command -v node  >/dev/null 2>&1 || { echo "❌ Node.js not found. Install: https://nodejs.org"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "❌ Python 3 not found. Install from python.org"; exit 1; }

# Install Tauri CLI if not present
if ! command -v cargo-tauri >/dev/null 2>&1; then
  echo "Installing Tauri CLI..."
  cargo install tauri-cli --version "^1.6"
fi

# Install frontend deps
echo "Installing frontend dependencies..."
cd frontend && npm ci --silent && cd ..

# Build the app
echo "Building desktop app..."
cargo tauri build

echo ""
echo "✅ Build complete!"
echo ""
echo "Installers are in: src-tauri/target/release/bundle/"
echo ""
echo "  macOS:   .dmg in bundle/dmg/"
echo "  Windows: .msi + .exe in bundle/msi/ and bundle/nsis/"
echo "  Linux:   .deb + .AppImage in bundle/deb/ and bundle/appimage/"

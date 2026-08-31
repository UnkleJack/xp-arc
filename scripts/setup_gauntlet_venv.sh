#!/usr/bin/env bash
# Gauntlet Clean Venv Setup
# Creates an isolated venv with compatible cryptography/cffi for gauntlet runs

set -euo pipefail

GAUNTLET_VENV="${GAUNTLET_VENV:-/tmp/xp-arc-gauntlet-venv}"

echo "╔═════════════════════════════════════════════╗"
echo "║      GAUNTLET CLEAN VENV SETUP             ║"
echo "╚═════════════════════════════════════════════╝"
echo

# Clean up any existing
rm -rf "$GAUNTLET_VENV"

echo "Creating venv at $GAUNTLET_VENV..."
python3 -m venv "$GAUNTLET_VENV"
source "$GAUNTLET_VENV/bin/activate"

# Upgrade pip
pip install --upgrade pip setuptools wheel

# Install cryptography with compatible cffi
# Python 3.13 needs cffi >= 1.16.0, cryptography >= 42.0.0
echo "Installing compatible cffi and cryptography..."
pip install "cffi>=1.16.0"
pip install "cryptography>=42.0.0"

# Verify
python3 -c "from cryptography.fernet import Fernet; print('✓ cryptography OK')"

# Install xp-arc with gauntlet extra in editable mode
echo "Installing xp-arc[gauntlet]..."
pip install -e /Users/jadeddragon/xp-arc[gauntlet]

# Verify gauntlet imports
python3 -c "
from gauntlet_pkg import Gauntlet
print('✓ Gauntlet imports OK')
"

echo
echo "╔═════════════════════════════════════════════╗"
echo "║         VENV READY FOR GAUNTLET            ║"
echo "╚═════════════════════════════════════════════╝"
echo
echo "To run gauntlet:"
echo "  source $GAUNTLET_VENV/bin/activate"
echo "  python3 -m gauntlet_pkg --db gauntlet"
echo
echo "To run specific phase:"
echo "  python3 -m gauntlet_pkg --db gauntlet --phase 1"
echo
echo "Venv location: $GAUNTLET_VENV"
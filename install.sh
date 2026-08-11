#!/usr/bin/env bash
# XP-Arc Installation Script
# Usage: ./install.sh [core|asset-engine|competitive-intel|all|gauntlet]

set -euo pipefail

EXTRAS="${1:-core}"

echo "╔═════════════════════════════════════════════╗"
echo "║          XP-ARC INSTALLER v0.3.0          ║"
echo "╚═════════════════════════════════════════════╝"
echo

# Validate Python version
PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d'.' -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d'.' -f2)

if [[ $PYTHON_MAJOR -lt 3 ]] || [[ $PYTHON_MAJOR -eq 3 && $PYTHON_MINOR -lt 10 ]]; then
    echo "ERROR: Python 3.10+ required. Found: $PYTHON_VERSION"
    exit 1
fi
echo "✓ Python $PYTHON_VERSION detected"

# Install with extras
case "$EXTRAS" in
    core)
        echo "Installing core orchestration..."
        pip install -e .
        ;;
    asset-engine)
        echo "Installing Asset Engine..."
        pip install -e .[asset-engine]
        ;;
    competitive-intel)
        echo "Installing Competitive Intelligence..."
        pip install -e .[competitive-intel]
        ;;
    all)
        echo "Installing everything..."
        pip install -e .[all]
        ;;
    gauntlet)
        echo "Installing Gauntlet testing framework..."
        pip install -e .[gauntlet]
        ;;
    *)
        echo "ERROR: Unknown extra: $EXTRAS"
        echo "Valid options: core, asset-engine, competitive-intel, all, gauntlet"
        exit 1
        ;;
esac

echo
echo "╔═════════════════════════════════════════════╗"
echo "║         INSTALLATION COMPLETE             ║"
echo "╚═════════════════════════════════════════════╝"
echo
echo "Quick start:"
echo "  python run_kitchen.py                    # One-shot run"
echo "  python run_persistent.py --port 8089     # Persistent daemon + API"
echo "  python -m gauntlet_pkg --db gauntlet     # Adversarial testing"
echo
echo "Environment variables (optional):"
echo "  export XP_ARC_ABOYEUR_KEY='your-signing-key'"
echo "  export XP_ARC_MASTER_KEY='your-master-key'"
echo "  export XP_ARC_API_KEY='your-api-key'"
echo "  export XP_ARC_CISO_TOKEN='your-ciso-token'"
echo "  export XP_ARC_GEMINI_API_KEY='your-gemini-key'"
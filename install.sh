#!/bin/bash
# ═══════════════════════════════════════════════════════════
#  XP-Arc Installation Script for Zo.Computer
#  Installs the XP-Arc protocol engine and DRAGON dashboard
# ═══════════════════════════════════════════════════════════

set -e

# ─── Configuration ───
INSTALL_DIR="${XP_ARC_HOME:-$HOME/xp-arc}"
DB_PATH="${XP_ARC_DB:-$INSTALL_DIR/xp_arc.db}"
API_PORT="${XP_ARC_PORT:-8089}"
DRAGON_DIR="$INSTALL_DIR/dragon"

echo "╔══════════════════════════════════════════════╗"
echo "║       XP-ARC INSTALLER — Zo.Computer        ║"
echo "╠══════════════════════════════════════════════╣"
echo "║  Install dir:  $INSTALL_DIR"
echo "║  DB path:      $DB_PATH"
echo "║  API port:     $API_PORT"
echo "╚══════════════════════════════════════════════╝"
echo ""

# ─── Check Python ───
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python 3 not found. XP-Arc requires Python 3.10+"
    exit 1
fi

PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "[✓] Python $PY_VERSION detected"

# ─── Create install directory ───
if [ -d "$INSTALL_DIR" ]; then
    echo "[!] Existing installation found at $INSTALL_DIR"
    echo "    Backing up database..."
    if [ -f "$DB_PATH" ]; then
        cp "$DB_PATH" "${DB_PATH}.backup.$(date +%Y%m%d_%H%M%S)"
        echo "    [✓] Database backed up"
    fi
fi

mkdir -p "$INSTALL_DIR"
echo "[✓] Install directory ready"

# ─── Copy files ───
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "[...] Copying XP-Arc files..."
cp -r "$SCRIPT_DIR/xp_arc" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/run_kitchen.py" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/run_persistent.py" "$INSTALL_DIR/"
cp -r "$SCRIPT_DIR/dragon" "$INSTALL_DIR/"

# Copy docs
cp "$SCRIPT_DIR/WHITEPAPER.md" "$INSTALL_DIR/" 2>/dev/null || true
cp "$SCRIPT_DIR/CONSTITUTION.MD" "$INSTALL_DIR/" 2>/dev/null || true
cp "$SCRIPT_DIR/LEGAL.md" "$INSTALL_DIR/" 2>/dev/null || true
cp "$SCRIPT_DIR/LICENSE" "$INSTALL_DIR/" 2>/dev/null || true
cp "$SCRIPT_DIR/README.md" "$INSTALL_DIR/" 2>/dev/null || true

echo "[✓] Files copied"

# ─── Create systemd service file (optional) ───
SERVICE_FILE="$INSTALL_DIR/xp-arc.service"
cat > "$SERVICE_FILE" << SERVICEEOF
[Unit]
Description=XP-Arc Persistent Kitchen — Multi-Agent Intelligence Pipeline
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$INSTALL_DIR
Environment=XP_ARC_DB=$DB_PATH
Environment=XP_ARC_PORT=$API_PORT
Environment=XP_ARC_POLL=3
ExecStart=/usr/bin/python3 $INSTALL_DIR/run_persistent.py --db $DB_PATH --port $API_PORT
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SERVICEEOF

echo "[✓] Systemd service file created at $SERVICE_FILE"

# ─── Create convenience scripts ───

# Start script
cat > "$INSTALL_DIR/start.sh" << 'STARTEOF'
#!/bin/bash
cd "$(dirname "$0")"
DB="${XP_ARC_DB:-./xp_arc.db}"
PORT="${XP_ARC_PORT:-8089}"
echo "Starting XP-Arc persistent kitchen..."
echo "  DB: $DB"
echo "  API: http://localhost:$PORT/api/dragon"
python3 run_persistent.py --db "$DB" --port "$PORT" "$@"
STARTEOF
chmod +x "$INSTALL_DIR/start.sh"

# Run-once script
cat > "$INSTALL_DIR/run_once.sh" << 'RUNEOF'
#!/bin/bash
cd "$(dirname "$0")"
DB="${XP_ARC_DB:-./xp_arc.db}"
python3 run_kitchen.py --db "$DB" "$@"
RUNEOF
chmod +x "$INSTALL_DIR/run_once.sh"

# Seed script
cat > "$INSTALL_DIR/seed.sh" << 'SEEDEOF'
#!/bin/bash
PORT="${XP_ARC_PORT:-8089}"
if [ -z "$1" ]; then
    echo "Usage: ./seed.sh <url>"
    echo "  Seeds a URL into the running XP-Arc pipeline"
    exit 1
fi
curl -s -X POST "http://localhost:$PORT/api/seed" \
    -H "Content-Type: application/json" \
    -d "{\"url\": \"$1\"}" | python3 -m json.tool
SEEDEOF
chmod +x "$INSTALL_DIR/seed.sh"

echo "[✓] Convenience scripts created (start.sh, run_once.sh, seed.sh)"

# ─── Verify installation ───
echo ""
echo "[...] Verifying installation..."
cd "$INSTALL_DIR"
python3 -c "
from xp_arc.core.pool import IntelligencePool
from xp_arc.core.executive import ExecutiveChef
from xp_arc.core.aboyeur import Aboyeur
from xp_arc.stations.forager import TheForager
from xp_arc.stations.analyst import TheAnalyst
from xp_arc.stations.sentinel import TheSentinel
from xp_arc.stations.plongeur import ThePlongeur
from xp_arc.monitoring.zorans_law import ZoransLaw
from xp_arc.monitoring.spazzmatic import SpaZzMatiC
print('[✓] All modules import successfully')
"

echo ""
echo "═══════════════════════════════════════════════"
echo "  INSTALLATION COMPLETE"
echo "═══════════════════════════════════════════════"
echo ""
echo "  Quick start:"
echo "    cd $INSTALL_DIR"
echo ""
echo "    # One-shot run with default targets:"
echo "    ./run_once.sh"
echo ""
echo "    # Persistent daemon with API:"
echo "    ./start.sh"
echo ""
echo "    # Seed a URL into running daemon:"
echo "    ./seed.sh https://example.com"
echo ""
echo "    # Install as systemd service:"
echo "    sudo cp xp-arc.service /etc/systemd/system/"
echo "    sudo systemctl enable xp-arc"
echo "    sudo systemctl start xp-arc"
echo ""
echo "  DRAGON dashboard:"
echo "    API:    http://localhost:$API_PORT/api/dragon"
echo "    Static: open dragon/index.html in browser"
echo ""
echo "  Zo.Computer integration:"
echo "    See DEPLOY.md for Hono/Bun route setup"
echo "═══════════════════════════════════════════════"

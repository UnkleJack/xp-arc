import sqlite3
import sys
from datetime import datetime

sys.path.insert(0, '/Users/jadeddragon/xp-arc')

from xp_arc.core.sanitization import sanitize_markdown

DB_PATH = "/home/workspace/TheKitchen/intelligence_pool.db"

def build_dossier():
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        # Check if tables exist
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='entities'")
        if not cur.fetchone():
            return "Intelligence Pool is empty or uninitialized."

        cur.execute("SELECT id, type, value, status, timestamp FROM entities ORDER BY timestamp DESC")
        entities = cur.fetchall()

        cur.execute("SELECT source, relationship, target FROM edges")
        edges = cur.fetchall()

        if not entities:
            return "No entities found in Intelligence Pool."

        md = "# DRAGON XP-Arc Dossier\n\n"
        md += f"**Timestamp:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
        md += "**Clearance:** Operator Only\n\n"
        md += "---\n\n"

        md += "## Target Telemetry (Entities)\n\n"
        for e in entities:
            # e[3] is status — sanitize entity values before rendering
            # (WHITEPAPER 5.5.5: output injection defense)
            safe_value = sanitize_markdown(e[2])
            status_icon = "[OK]" if e[3] == "mapped" else ("[FAIL]" if e[3] == "failed" else "[WAIT]")
            md += f"- {status_icon} **[{e[1].upper()}]** `{safe_value}` *(Status: {e[3]})*\n"

        md += "\n## Network Graph (Edges)\n\n"
        for edge in edges:
            safe_source = sanitize_markdown(edge[0])
            safe_rel   = sanitize_markdown(edge[1])
            safe_tgt   = sanitize_markdown(edge[2])
            md += f"- `{safe_source}` --({safe_rel})--> `{safe_tgt}`\n"

        md += "\n---\n*XP-Arc Intelligence Pool. Automated Delivery via Zo Substrate.*"
        return md

    except Exception as e:
        return f"Error generating dossier: {e}"

if __name__ == "__main__":
    print(build_dossier())

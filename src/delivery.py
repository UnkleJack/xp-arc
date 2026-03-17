import sqlite3
import sys
from datetime import datetime

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
            
        md = "# 🐉 XP-Arc DRAGON Dossier\n\n"
        md += f"**Timestamp:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
        md += "**Clearance:** Operator Only\n\n"
        md += "---\n\n"
        
        md += "## 🎯 Target Telemetry (Entities)\n\n"
        for e in entities:
            # e[3] is status
            status_icon = "🟢" if e[3] == "mapped" else ("🔴" if e[3] == "failed" else "🟡")
            md += f"- {status_icon} **[{e[1].upper()}]** `{e[2]}` *(Status: {e[3]})*\n"
            
        md += "\n## 🕸️ Network Graph (Edges)\n\n"
        for edge in edges:
            md += f"- `{edge[0]}` ──(**{edge[1]}**)──▶ `{edge[2]}`\n"
            
        md += "\n---\n*XP-Arc Intelligence Pool. Automated Delivery via Zo Substrate.*"
        return md
        
    except Exception as e:
        return f"Error generating dossier: {e}"

if __name__ == "__main__":
    print(build_dossier())

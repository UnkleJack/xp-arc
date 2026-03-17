import sqlite3

class IntelligencePool:
    def __init__(self, db_path=":memory:"):
        self.conn = sqlite3.connect(db_path)
        self.setup()

    def setup(self):
        with self.conn:
            self.conn.execute("CREATE TABLE IF NOT EXISTS entities (id INTEGER PRIMARY KEY, type TEXT, value TEXT UNIQUE, status TEXT)")
            self.conn.execute("CREATE TABLE IF NOT EXISTS edges (source TEXT, relationship TEXT, target TEXT)")

    def add_entity(self, ent_type, value):
        try:
            with self.conn:
                self.conn.execute("INSERT INTO entities (type, value, status) VALUES (?, ?, 'raw')", (ent_type, value))
                print(f"[POOL] + Added new {ent_type}: {value}")
        except sqlite3.IntegrityError:
            pass

    def add_edge(self, source, rel, target):
        with self.conn:
            self.conn.execute("INSERT INTO edges (source, relationship, target) VALUES (?, ?, ?)", (source, rel, target))

    def get_next_raw(self):
        cur = self.conn.execute("SELECT id, type, value FROM entities WHERE status = 'raw' LIMIT 1")
        return cur.fetchone()

    def mark_status(self, entity_id, status):
        with self.conn:
            self.conn.execute("UPDATE entities SET status = ? WHERE id = ?", (status, entity_id))

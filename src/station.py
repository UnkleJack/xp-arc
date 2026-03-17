class StationChef:
    def __init__(self, pool, name, handles_types):
        self.pool = pool
        self.name = name
        self.handles_types = handles_types

    def can_handle(self, ent_type):
        return ent_type in self.handles_types

    def process(self, entity_type, entity_value):
        raise NotImplementedError

    def log(self, msg):
        print(f"[{self.name}] {msg}")

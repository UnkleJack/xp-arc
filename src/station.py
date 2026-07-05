class StationChef:
    def __init__(self, pool, name, handles_types):
        """Create a station.

        Parameters
        ----------
        pool: IntelligencePool
            The shared pool that stations read/write to.
        name: str
            Human‑readable identifier for logging.
        handles_types: list[str]
            A list of entity types this station can process.
        """
        self.pool = pool
        self.name = name
        self.handles_types = handles_types

    def handled_types(self):
        """Return the list of entity types this station can handle.

        The executive uses this for graceful‑degradation fallback chains.
        """
        return self.handles_types

    def can_handle(self, ent_type):
        return ent_type in self.handles_types

    def process(self, entity_type, entity_value):
        """Process an entity.

        Concrete subclasses must implement the actual logic. The base class
        raises ``NotImplementedError`` to make the contract explicit.
        """
        raise NotImplementedError

    def log(self, msg):
        print(f"[{self.name}] {msg}")

class ExecutiveChef:
    def __init__(self, pool):
        self.pool = pool
        self.stations = []

    def register_station(self, station):
        self.stations.append(station)

    def run_service(self):
        while True:
            raw = self.pool.get_next_raw()
            if not raw:
                break
            ent_id, ent_type, ent_value = raw
            print(f"\n[EXECUTIVE] Raw ingredient on the pass: [{ent_type}] {ent_value}")
            
            handled = False
            for station in self.stations:
                if station.can_handle(ent_type):
                    try:
                        station.process(ent_type, ent_value)
                        handled = True
                    except Exception as e:
                        print(f"  [!] {station.name} dropped the pan: {e}")
            
            if not handled:
                print(f"  [!] No station available for [{ent_type}] yet.")
            
            self.pool.mark_status(ent_id, 'mapped' if handled else 'unhandled')

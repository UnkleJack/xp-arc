import re
import urllib.request
from orchestrator.station import StationChef

class TheForager(StationChef):
    def __init__(self, pool):
        super().__init__(pool, name="The Forager", handles_types=['url'])

    def process(self, entity_type, entity_value):
        self.log(f"Scraping target DOM: {entity_value}")
        try:
            req = urllib.request.Request(entity_value, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
            html = urllib.request.urlopen(req, timeout=5).read().decode('utf-8', errors='ignore')
            
            # Extract domains from links
            domains = set(re.findall(r'href="https?://([^/"]+)', html))
            
            # Limit to 3 external domains per site so the PoC terminal output doesn't scroll for 10 pages
            count = 0
            for d in domains:
                if d not in entity_value and count < 3:
                    self.pool.add_entity('domain', d)
                    self.pool.add_edge(entity_value, 'links_to', d)
                    self.log(f"+ Extracted Domain: {d}")
                    count += 1
        except Exception as e:
            self.log(f"Failed to forage {entity_value}: {e}")

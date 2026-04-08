"""
The Cartographer — Rôtisseur.

Graph intelligence. Discovers hidden connections, identifies
bridge nodes, detects clusters, and maps the topology of
the Intelligence Pool's entity graph.

The Cartographer sees patterns the other stations can't.
It reads the same edges everyone else wrote and finds
the story they didn't know they were telling.
"""

from collections import defaultdict, deque
from ..core.station import StationChef


class TheCartographer(StationChef):
    """
    Performs graph analysis on the Intelligence Pool's edge network.

    Discovers:
    - Clusters (connected components)
    - Bridge nodes (entities connecting otherwise separate groups)
    - Hub nodes (highest edge count)
    - Shortest paths between entities
    - 2nd and 3rd degree inferred relationships
    """

    station_id = "cartographer"
    name = "The Cartographer"
    handles_types = ['_cartography_request']
    sla_seconds = 180
    is_primary = True

    def map_topology(self) -> dict:
        """
        Full topological analysis of the entity graph.
        Writes discovered relationships as new edges.
        Returns analysis report.
        """
        self.log("Mapping Intelligence Pool topology...")

        edges = self.pool.get_all_edges()
        entities = self.pool.get_all_entities()

        # Build undirected adjacency list
        adj = defaultdict(set)
        directed = defaultdict(list)  # For path tracing
        edge_count = defaultdict(int)

        for edge in edges:
            src, tgt = edge['source'], edge['target']
            adj[src].add(tgt)
            adj[tgt].add(src)
            directed[src].append(tgt)
            edge_count[src] += 1
            edge_count[tgt] += 1

        # All known entity values
        all_values = set(e['value'] for e in entities)
        for e in edges:
            all_values.add(e['source'])
            all_values.add(e['target'])

        # ─── Cluster Detection (Connected Components) ───
        clusters = self._find_clusters(all_values, adj)
        self.log(f"  Found {len(clusters)} clusters")

        # ─── Hub Detection ───
        hubs = sorted(edge_count.items(), key=lambda x: -x[1])[:20]
        self.log(f"  Top hub: {hubs[0][0]} ({hubs[0][1]} edges)" if hubs else "  No hubs")

        # ─── Bridge Node Detection ───
        bridges = self._find_bridge_nodes(all_values, adj, clusters)
        self.log(f"  Found {len(bridges)} bridge nodes")

        # ─── Infer 2nd-Degree Relationships ───
        inferred = self._infer_relationships(directed, all_values)
        self.log(f"  Inferred {len(inferred)} hidden connections")

        # Write inferred edges
        new_edges = 0
        for inf in inferred:
            self.pool.add_edge(inf['source'], inf['relationship'], inf['target'])
            new_edges += 1

        # Write bridge findings
        for bridge in bridges:
            self.pool.add_finding(
                'info', self.station_id,
                f"Bridge node: {bridge['node']} connects {bridge['clusters_connected']} clusters",
                f"Edges: {bridge['edge_count']}"
            )

        # ─── Build Report ───
        cluster_summary = []
        for i, cluster in enumerate(clusters[:15]):
            cluster_summary.append({
                'cluster_id': i,
                'size': len(cluster),
                'members': sorted(list(cluster))[:10],
                'has_seed': any(
                    e['type'] == 'url' for e in entities
                    if e['value'] in cluster
                ),
            })

        report = {
            'total_nodes': len(all_values),
            'total_edges': len(edges),
            'new_inferred_edges': new_edges,
            'clusters': {
                'count': len(clusters),
                'largest': len(clusters[0]) if clusters else 0,
                'smallest': len(clusters[-1]) if clusters else 0,
                'isolated_nodes': sum(1 for c in clusters if len(c) == 1),
                'details': cluster_summary,
            },
            'hubs': [{'node': h[0], 'edges': h[1]} for h in hubs[:10]],
            'bridges': bridges[:10],
            'inferred_connections': inferred[:20],
        }

        self.pool._log_event('cartography_complete', self.station_id,
                             f"Mapped {len(all_values)} nodes, {len(edges)} edges, "
                             f"{len(clusters)} clusters, {new_edges} inferred connections")

        return report

    def _find_clusters(self, nodes: set, adj: dict) -> list:
        """Find connected components using BFS."""
        visited = set()
        clusters = []

        for node in nodes:
            if node in visited:
                continue
            cluster = set()
            queue = deque([node])
            while queue:
                current = queue.popleft()
                if current in visited:
                    continue
                visited.add(current)
                cluster.add(current)
                for neighbor in adj.get(current, set()):
                    if neighbor not in visited:
                        queue.append(neighbor)
            clusters.append(cluster)

        # Sort by size descending
        clusters.sort(key=len, reverse=True)
        return clusters

    def _find_bridge_nodes(self, nodes: set, adj: dict, clusters: list) -> list:
        """
        Find nodes that, if removed, would increase the number
        of connected components. These are structurally critical.
        """
        bridges = []

        # Only check nodes with 2+ connections (potential bridges)
        candidates = [n for n in nodes if len(adj.get(n, set())) >= 2]

        for node in candidates[:100]:  # Limit for performance
            neighbors = adj.get(node, set())
            if len(neighbors) < 2:
                continue

            # Check if removing this node disconnects its neighbors
            remaining = nodes - {node}
            remaining_adj = defaultdict(set)
            for n in remaining:
                remaining_adj[n] = adj.get(n, set()) - {node}

            # BFS from first neighbor
            start = list(neighbors)[0]
            if start not in remaining:
                continue

            reachable = set()
            queue = deque([start])
            while queue:
                current = queue.popleft()
                if current in reachable:
                    continue
                reachable.add(current)
                for nb in remaining_adj.get(current, set()):
                    if nb not in reachable:
                        queue.append(nb)

            # If not all neighbors are reachable, this is a bridge
            unreachable = neighbors - reachable - {node}
            if unreachable:
                # Determine which clusters this node connects
                node_clusters = set()
                for i, cluster in enumerate(clusters):
                    if node in cluster:
                        node_clusters.add(i)
                    for nb in neighbors:
                        if nb in cluster:
                            node_clusters.add(i)

                bridges.append({
                    'node': node,
                    'edge_count': len(neighbors),
                    'clusters_connected': len(node_clusters),
                    'separates': list(unreachable)[:5],
                })

        bridges.sort(key=lambda x: -x['edge_count'])
        return bridges

    def _infer_relationships(self, directed: dict, all_values: set) -> list:
        """
        Discover 2nd-degree connections that imply relationships.

        If A links_to B and B subdomain_of C, then A has_indirect_connection to C.
        """
        inferred = []
        seen_pairs = set()

        for source, first_hops in directed.items():
            for mid in first_hops:
                for target in directed.get(mid, []):
                    if target == source:
                        continue
                    pair = (source, target)
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)

                    # Only add if both endpoints are real entities
                    if source in all_values and target in all_values:
                        inferred.append({
                            'source': source,
                            'target': target,
                            'relationship': 'indirect_connection',
                            'via': mid,
                            'path': f"{source} → {mid} → {target}",
                        })

        return inferred

    def process(self, entity_id, entity_type, entity_value):
        report = self.map_topology()
        return {
            'entity_type': '_cartography_request',
            'entity_value': 'topology_map',
            'relationships': [],
            'confidence': 1.0,
            'notes': f"Mapped {report['total_nodes']} nodes, "
                     f"{report['clusters']['count']} clusters, "
                     f"{report['new_inferred_edges']} inferred edges",
        }

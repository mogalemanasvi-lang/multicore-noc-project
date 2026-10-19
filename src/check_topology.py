"""check_topology.py - verifies the cluster topology file and compares it with a 4x4 mesh.
Usage (from booksim2/src):  python3 check_topology.py cluster16.txt
Compare 'avg hops (BookSim)' = analytical avg distance (incl. self pairs) + 1 router."""
import sys, itertools, networkx as nx

def load(fn):
    G = nx.Graph(); nodes = {}
    for line in open(fn):
        t = line.split()
        if not t: continue
        r = int(t[1]); G.add_node(r); i = 2
        while i < len(t):
            if t[i] == "router":
                j = int(t[i+1]); G.add_edge(r, j); i += 2
            elif t[i] == "node":
                nodes[int(t[i+1])] = r; i += 2
            else:
                i += 1          # a link-latency number
    return G, nodes

def min_bisection(G):
    V = sorted(G.nodes()); n = len(V); best = 10**9
    for comb in itertools.combinations(V[1:], n//2 - 1):
        S = set((V[0],) + comb)
        cut = sum(1 for u, v in G.edges() if (u in S) != (v in S))
        best = min(best, cut)
    return best

def metrics(G):
    n = G.number_of_nodes()
    d = dict(nx.all_pairs_shortest_path_length(G))
    tot = sum(d[u][v] for u in G for v in G)          # self pairs add 0
    avg_incl_self = tot / (n * n)
    return dict(routers=n, links=G.number_of_edges(), connected=nx.is_connected(G),
                diameter=nx.diameter(G), avg_hops_uniform=round(avg_incl_self, 3),
                avg_hops_booksim_style=round(avg_incl_self + 1, 3),
                max_router_degree=max(dict(G.degree()).values()),
                bisection_links=min_bisection(G))

if __name__ == "__main__":
    fn = sys.argv[1] if len(sys.argv) > 1 else "cluster16.txt"
    G, nodes = load(fn)
    assert len(nodes) == G.number_of_nodes(), "every router should have one node here"
    M = nx.grid_2d_graph(4, 4)
    M = nx.convert_node_labels_to_integers(M)
    a, b = metrics(G), metrics(M)
    print(f"{'metric':26s}{'cluster':>12s}{'4x4 mesh':>12s}")
    for k in a: print(f"{k:26s}{str(a[k]):>12s}{str(b[k]):>12s}")
    print("isomorphic to mesh?", nx.is_isomorphic(G, M))

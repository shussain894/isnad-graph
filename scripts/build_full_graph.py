"""Stage 1: the full Sahih al-Bukhari transmission graph.

Nodes  : every transmitter named in any isnad, all generations.
Edges  : teacher -> student, taken from adjacent positions in a chain;
         weight = number of hadiths in which that hand-off occurs.
Metrics: directed betweenness (bridge role) and PageRank on the reversed
         graph (how much transmission traces back through a narrator).
Output : output/full_graph.json, output/centrality.csv, output/full_summary.txt

Identity is string-based at this stage: one normalised Arabic name = one
node. That is known to be imperfect (a bare "Sufyan" may be two men); the
imperfection is measured and reported rather than guessed away. Entity
resolution against a rijal database is Stage 2.
"""

import csv
import json
import time
from collections import Counter, defaultdict
from pathlib import Path

import networkx as nx
import pandas as pd

from isnad_parse import parse_chains, resolve_relatives

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "bukhari"
OUT = ROOT / "output"

SEED = 42
TOP_COMMUNITIES = 4       # matches the validated 4-colour palette
LABEL_MIN_CHAINS = 40     # nodes labelled directly in the viewer


def community_layout(und, comm_of, communities) -> dict:
    """Two-level layout: place the clusters, then lay out each one inside its
    own patch. A single flat force layout of ~4k nodes collapses into one
    disc and hides the cluster structure the graph actually has.
    """
    giant = max(nx.connected_components(und), key=len)
    main = [i for i, c in enumerate(communities) if c & giant]
    islands = [i for i, c in enumerate(communities) if not (c & giant)]

    meta = nx.Graph()
    meta.add_nodes_from(main)
    for u, v, d in und.edges(data=True):
        cu, cv = comm_of[u], comm_of[v]
        if cu != cv:
            if meta.has_edge(cu, cv):
                meta[cu][cv]["weight"] += d["weight"]
            else:
                meta.add_edge(cu, cv, weight=d["weight"])
    raw = nx.spring_layout(meta, seed=SEED, weight="weight", iterations=300)

    # The spring result has the right *ordering* but terrible spacing: a few
    # loosely-linked clusters shoot to the margins and compress everything else
    # into a blob. Replace each coordinate with its rank along that axis, which
    # keeps who-is-near-whom while giving every cluster equal room. The x axis
    # is stretched to match the landscape viewport.
    def spread(values: dict, lo: float, hi: float) -> dict:
        order = sorted(values, key=lambda i: values[i])
        n = len(order) - 1 or 1
        return {i: lo + (hi - lo) * k / n for k, i in enumerate(order)}

    xs = spread({i: p[0] for i, p in raw.items()}, -1.45, 1.45)
    ys = spread({i: p[1] for i, p in raw.items()}, -0.85, 0.85)
    centres = {i: (xs[i], ys[i]) for i in raw}

    # A handful of narrators sit in tiny disconnected components. Park them in a
    # row beneath the main mass rather than letting them drive the extents.
    for k, i in enumerate(islands):
        centres[i] = (-1.3 + 0.32 * k, -1.25)

    biggest = max(len(c) for c in communities)
    pos: dict = {}
    for i, comm in enumerate(communities):
        # Rebuilt in sorted order rather than used as a subgraph view: the
        # spring layout seeds its starting positions in node order, so a stable
        # order is what makes the coordinates reproducible.
        members = sorted(comm)
        sub = nx.Graph()
        sub.add_nodes_from(members)
        sub.add_edges_from(
            (u, v, d) for u, v, d in und.subgraph(comm).edges(data=True)
        )
        if sub.number_of_nodes() == 1:
            local = {next(iter(sub)): (0.0, 0.0)}
        else:
            local = nx.spring_layout(sub, seed=SEED, weight="weight", iterations=80)
        radius = 0.05 + 0.13 * (len(comm) / biggest) ** 0.5
        cx, cy = centres[i]
        for n, (x, y) in local.items():
            pos[n] = (cx + x * radius, cy + y * radius)
    return pos


def build() -> None:
    frames = [pd.read_csv(p) for p in sorted(DATA.glob("Chapter*.csv"))]
    df = pd.concat(frames, ignore_index=True)

    edge_w: Counter[tuple[str, str]] = Counter()
    chains_per_node: Counter[str] = Counter()
    unresolved: set[str] = set()

    rows_total = len(df)
    rows_no_isnad = 0        # no Arabic isnad text at all
    rows_no_chain = 0        # isnad text present but nothing parsable
    rows_single = 0          # only one transmitter found -> no edge
    rows_used = 0
    chains_seen = 0
    tahwil_rows = 0

    for isnad in df["Arabic_Isnad"]:
        if not isinstance(isnad, str) or not isnad.strip():
            rows_no_isnad += 1
            continue
        chains = parse_chains(isnad)
        if not chains:
            rows_no_chain += 1
            continue
        if len(chains) > 1:
            tahwil_rows += 1

        row_nodes: set[str] = set()
        row_has_edge = False
        for levels in chains:
            chains_seen += 1
            resolved = resolve_relatives(levels)
            for names, flag in resolved:
                row_nodes.update(names)
                if flag:
                    unresolved.update(n for n in names if "⟨" in n)
            # Text order is student-first, so level i+1 taught level i.
            for i in range(len(resolved) - 1):
                students, _ = resolved[i]
                teachers, _ = resolved[i + 1]
                for t in teachers:
                    for s in students:
                        if t != s:
                            edge_w[(t, s)] += 1
                            row_has_edge = True

        # Sorted, not raw set order: node insertion order decides the order
        # Louvain visits nodes, and Python randomises set iteration per process.
        # Without this the community assignment changes between identical runs.
        for n in sorted(row_nodes):
            chains_per_node[n] += 1
        if row_has_edge:
            rows_used += 1
        else:
            rows_single += 1

    G = nx.DiGraph()
    for n, c in chains_per_node.items():
        G.add_node(n, chains=c, unresolved=n in unresolved)
    for (t, s), w in edge_w.items():
        G.add_edge(t, s, weight=w)

    print(f"nodes {G.number_of_nodes()}  edges {G.number_of_edges()}")

    # ---------------------------------------------------------- centrality
    t0 = time.time()
    betw = nx.betweenness_centrality(G, weight=None, seed=SEED)
    print(f"betweenness in {time.time() - t0:.0f}s")
    # Reversed graph: mass flows from collectors back towards the sources, so a
    # high score means "much of the corpus traces back through this narrator".
    pr_source = nx.pagerank(G.reverse(copy=True), weight="weight")
    pr_collect = nx.pagerank(G, weight="weight")

    # -------------------------------------------------------- communities
    und = nx.Graph()
    und.add_nodes_from(G.nodes())
    for t, s, d in G.edges(data=True):
        if und.has_edge(t, s):
            und[t][s]["weight"] += d["weight"]
        else:
            und.add_edge(t, s, weight=d["weight"])
    communities = nx.community.louvain_communities(und, weight="weight", seed=SEED)
    # Tie-break on a name so equal-sized communities keep a stable index.
    communities = sorted(communities, key=lambda c: (-len(c), min(c)))
    comm_of = {n: i for i, c in enumerate(communities) for n in c}

    # ------------------------------------------------------------- layout
    t0 = time.time()
    pos = community_layout(und, comm_of, communities)
    print(f"layout in {time.time() - t0:.0f}s")

    # ---------------------------------------------------------- ambiguity
    mononyms = {n: c for n, c in chains_per_node.items() if len(n.split()) == 1}
    kunya_only = {
        n: c for n, c in chains_per_node.items()
        if len(n.split()) == 2 and n.split()[0] in {"ابو", "ابي", "ابا", "ابن", "ام"}
    }

    OUT.mkdir(exist_ok=True)

    # ------------------------------------------------------------ outputs
    nodes_json = []
    for n in G.nodes():
        nodes_json.append({
            "id": n,
            "chains": chains_per_node[n],
            "in": G.in_degree(n),
            "out": G.out_degree(n),
            "betweenness": round(betw[n], 6),
            "pagerank": round(pr_source[n], 7),
            "community": comm_of[n],
            "unresolved": bool(G.nodes[n]["unresolved"]),
            "x": round(float(pos[n][0]), 4),
            "y": round(float(pos[n][1]), 4),
        })
    nodes_json.sort(key=lambda d: -d["chains"])

    graph_json = {
        "meta": {
            "source": "Sahih al-Bukhari (LK Hadith Corpus)",
            "stage": 1,
            "identity": "string-based (normalised Arabic name); not entity-resolved",
            "edge_definition": "teacher -> student, adjacent positions in a chain",
            "rows_total": rows_total,
            "rows_used": rows_used,
            "nodes": G.number_of_nodes(),
            "edges": G.number_of_edges(),
            "unresolved_nodes": len(unresolved),
            "top_communities": TOP_COMMUNITIES,
            "label_min_chains": LABEL_MIN_CHAINS,
        },
        "nodes": nodes_json,
        "edges": [
            {"s": t, "t": s, "w": d["weight"]} for t, s, d in G.edges(data=True)
        ],
    }
    (OUT / "full_graph.json").write_text(
        json.dumps(graph_json, ensure_ascii=False, separators=(",", ":"))
    )

    ranked = sorted(G.nodes(), key=lambda n: -betw[n])
    with (OUT / "centrality.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow([
            "rank", "narrator", "chains", "in_degree", "out_degree",
            "betweenness", "pagerank_source", "pagerank_collector",
            "community", "unresolved",
        ])
        for i, n in enumerate(ranked, 1):
            w.writerow([
                i, n, chains_per_node[n], G.in_degree(n), G.out_degree(n),
                f"{betw[n]:.6f}", f"{pr_source[n]:.7f}", f"{pr_collect[n]:.7f}",
                comm_of[n], int(bool(G.nodes[n]["unresolved"])),
            ])

    # ------------------------------------------------------------ summary
    parsed_pct = 100 * rows_used / rows_total
    L = [
        "STAGE 1 — full Bukhari transmission graph",
        "=" * 52,
        "",
        "PARSE",
        f"  hadith rows                 {rows_total}",
        f"  rows yielding >=1 edge      {rows_used}  ({parsed_pct:.1f}%)",
        f"  rows with no Arabic isnad   {rows_no_isnad}",
        f"  rows isnad present, unparsed {rows_no_chain}",
        f"  rows with a single narrator {rows_single}",
        f"  rows with parallel chains (tahwil)  {tahwil_rows}",
        f"  chains parsed               {chains_seen}",
        "",
        "GRAPH",
        f"  nodes (distinct name strings)  {G.number_of_nodes()}",
        f"  edges (teacher -> student)     {G.number_of_edges()}",
        f"  unresolved placeholder nodes   {len(unresolved)}",
        f"  weakly connected components    {nx.number_weakly_connected_components(G)}",
        f"  Louvain communities            {len(communities)} "
        f"(top sizes: {[len(c) for c in communities[:8]]})",
        "",
        "AMBIGUITY (string identity, to be fixed in Stage 2)",
        f"  single-token names   {len(mononyms)} nodes, "
        f"{sum(mononyms.values())} chain appearances",
        f"  kunya/ibn-only names {len(kunya_only)} nodes, "
        f"{sum(kunya_only.values())} chain appearances",
        "  worst hot spots (one string, probably several men):",
    ]
    for n, c in sorted(mononyms.items(), key=lambda kv: -kv[1])[:15]:
        L.append(f"     {c:5d} chains  {n}")
    L += [
        "",
        "TOP 25 BY BETWEENNESS (bridge role in transmission)",
    ]
    for i, n in enumerate(ranked[:25], 1):
        L.append(f"  {i:3d}. {n:38s} betw {betw[n]:.4f}  chains {chains_per_node[n]}")
    L += ["", "TOP 15 BY PAGERANK (transmission tracing back through them)"]
    for i, n in enumerate(sorted(G.nodes(), key=lambda x: -pr_source[x])[:15], 1):
        L.append(f"  {i:3d}. {n:38s} pr {pr_source[n]:.5f}  chains {chains_per_node[n]}")
    summary = "\n".join(L)
    (OUT / "full_summary.txt").write_text(summary)
    print(summary)


if __name__ == "__main__":
    build()

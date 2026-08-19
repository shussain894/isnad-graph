# Companions transmission network — Sahih al-Bukhari

Interactive graph of the top 100 first narrators (Companions) in Sahih
al-Bukhari, clustered with Louvain community detection.

- **Nodes** — Companions, sized by number of hadiths they narrate.
- **Edges** — two Companions are linked when the same student (the second
  narrator in the isnad) transmitted from both; weight = number of distinct
  shared students.
- **Color** — Louvain communities (weighted). The four largest are colored;
  smaller fragments fold into gray "Other".

## Layout

```
data/bukhari/          97 chapter CSVs from the LK Hadith Corpus
scripts/build_graph.py parse -> graph -> Louvain -> output/
output/graph.json      nodes, edges, communities (input to the web viewer)
output/summary.txt     human-readable community breakdown
web/index.html         Cytoscape.js viewer (light + dark)
```

## Run

```sh
.venv/bin/python scripts/build_graph.py   # rebuild output/
python3 -m http.server                    # from the project root
# open http://localhost:8000/web/
```

## Method notes & known limitations

- The Companion is taken from the English isnad ("Narrated X:"), the student
  from the second-to-last transmitter of the Arabic isnad (split on
  transmission verbs after normalization).
- Name disambiguation is heuristic: an alias map merges common translation
  variants, and a curated list drops well-known Successors (Tabi'un) whom the
  translator listed as first narrator. Both lists live at the top of
  `scripts/build_graph.py`. Rare variants in the long tail may still split or
  mislabel a narrator — a proper fix needs a rijal database (phase 2).
- Chains whose second narrator is a relative reference ("from his father")
  are counted for hadith totals but skipped for edges.
- Data source: [LK Hadith Corpus](https://github.com/ShathaTm/LK-Hadith-Corpus)
  (Bukhari, 7,345 hadith rows; 6,617 with a resolvable Companion).

## Ideas for phase 2

- Link narrators to a rijal database (e.g. muslimscholars.info) for real
  disambiguation, generation tags, and cities.
- Betweenness centrality on the full narrator graph (all generations).
- node2vec + UMAP map colored by these Louvain communities.

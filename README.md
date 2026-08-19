# Isnad graph — Sahih al-Bukhari

Interactive graphs of hadith transmission in Sahih al-Bukhari, clustered with
Louvain community detection. Two views ship today:

| View | Page | Scope |
|---|---|---|
| Companions | `web/index.html` | top 100 first narrators, undirected co-transmission |
| Full network | `web/full.html` | all 3,809 named transmitters, directed teacher → student |

### Companions view (Stage 0)

- **Nodes** — Companions, sized by number of hadiths they narrate.
- **Edges** — two Companions are linked when the same student (the second
  narrator in the isnad) transmitted from both; weight = number of distinct
  shared students.
- **Color** — Louvain communities (weighted). The four largest are colored;
  smaller fragments fold into gray "Other".

### Full network view (Stage 1)

- **Nodes** — every transmitter named anywhere in an isnad, all generations,
  sized by how many hadiths they appear in.
- **Edges** — directed teacher → student, taken from adjacent positions in a
  chain; weight = number of hadiths carrying that hand-off.
- **Color** — the four largest Louvain communities; everything else gray.
  Unresolved placeholders (see below) are drawn faded and can be hidden.
- **Layout** — two-level: the communities are placed relative to one another,
  then each is laid out inside its own patch. A single flat force layout of
  ~3,800 nodes collapses into one disc and hides the cluster structure.

## Layout

```
data/bukhari/               97 chapter CSVs from the LK Hadith Corpus
scripts/isnad_parse.py      shared Arabic normalization + chain parsing
scripts/build_graph.py      Stage 0: Companions -> Louvain -> output/
scripts/build_full_graph.py Stage 1: full chains -> centrality -> output/
output/graph.json           Stage 0 nodes, edges, communities
output/summary.txt          Stage 0 community breakdown
output/full_graph.json      Stage 1 nodes (with layout), edges, metrics
output/centrality.csv       Stage 1 ranking: betweenness, PageRank, degrees
output/full_summary.txt     Stage 1 parse, ambiguity and centrality report
web/index.html              Cytoscape.js viewer (light + dark)
web/full.html               sigma.js/WebGL viewer (light + dark)
```

Both scripts are deterministic: identical inputs give byte-identical outputs.
That needs care, because Python randomizes set iteration order per process and
Louvain's result depends on the order it visits nodes — so anything feeding
node insertion order is sorted first.

## Run

```sh
.venv/bin/python scripts/build_graph.py       # rebuild Stage 0 output/
.venv/bin/python scripts/build_full_graph.py  # rebuild Stage 1 output/ (~15s)
python3 -m http.server                        # from the project root
# open http://localhost:8000/web/  and  http://localhost:8000/web/full.html
```

## Stage 1 results

**Parse rate.** 7,312 of 7,345 hadith rows (99.6%) yield at least one
teacher → student edge. Of the 33 that do not: 2 rows carry no Arabic isnad at
all, 3 have isnad text that produces no usable segment, and 28 name only a
single transmitter, which is a chain with nothing to link. 7,396 chains are
parsed in total — more than one per row because 56 rows contain a taḥwīl
marker (`ح`, a switch to a parallel chain) and are split in two.

**Graph.** 3,809 nodes, 9,712 directed edges, 9 weakly connected components
(the giant one holds 3,796 nodes, 99.7%), 28 Louvain communities.

**Ambiguity.** Identity at this stage is the normalized name string, so one
man written two ways is two nodes and two men written the same way are one
node. The scale of the problem, to be fixed in Stage 2:

| Measure | Nodes | Chain appearances |
|---|---|---|
| Single-token names (`شعبة`, `سفيان`) | 408 | 14,086 |
| Kunya/ibn-only names (`ابو اسامة`) | 299 | 6,351 |
| Unresolved relative placeholders | 317 | — |

The largest hot spots are `شعبة` (760 chains), `سفيان` (681), `عايشة` (641),
`مالك` (606) and `الزهري` (598). The splitting is visible too: `الزهري` (598)
and `ابن شهاب` (625) are the same man, as are `انس` (351) and `انس بن مالك`
(342). Nothing is merged on a guess — the counts are reported as they are.

**Sanity benchmark** (the roadmap's parse check): by betweenness, سفيان ranks
2nd, شعبة 3rd, الزهري 5th, ابي هريرة 6th, ابن عباس 7th, ابن شهاب 8th,
عايشة 9th and مالك 17th. That is the expected shape, so the chain direction
and segmentation are behaving.

`النبي` ranks 1st on only 43 chains. That is real structure rather than a bug:
he is the source every chain points back to, so the few chains that name him
explicitly bridge otherwise separate Companion subtrees.

## Method notes & known limitations

- The Companion is taken from the English isnad ("Narrated X:"), the student
  from the second-to-last transmitter of the Arabic isnad (split on
  transmission verbs after normalization).
- Name disambiguation is heuristic: an alias map merges common translation
  variants, and a curated list drops well-known Successors (Tabi'un) whom the
  translator listed as first narrator. Both lists live at the top of
  `scripts/build_graph.py`. Rare variants in the long tail may still split or
  mislabel a narrator — a proper fix needs a rijal database (phase 2).
- An isnad is written student-first: segment 0 is al-Bukhari's own shaykh and
  the last segment is the Companion, so transmission runs from the *end* of the
  parsed list toward the start. Both scripts rely on this.
- Relative references ("from his father") cannot be resolved to a name without
  a rijal database. Stage 0 skips them for edges; Stage 1 keeps the chain
  intact with a contextual placeholder — `ابيه ⟨هشام⟩` is "the father of
  Hisham", which is what the text actually says. Placeholders are flagged
  unresolved, drawn faded, and never merged onto one shared "father" node.
  They land where they should: `ابيه ⟨هشام⟩` sits beside ʿUrwa, who genuinely
  is Hisham's father.
- Taḥwīl (`ح`) marks a switch to a parallel chain inside one isnad. Treating it
  as an ordinary token would silently weld two chains together and invent an
  edge that no source states, so the parser splits there instead. The known
  cost is that the first chain loses the shared tail after the marker; that
  under-counts some edges, which is preferred to inventing them.
- Data source: [LK Hadith Corpus](https://github.com/ShathaTm/LK-Hadith-Corpus)
  (Bukhari, 7,345 hadith rows; 6,617 with a resolvable Companion).

## Roadmap

Work happens in stages. **Each stage is a self-contained work order**: build
only what its scope says, respect the guardrails, hit the done-when criteria,
then stop and regroup before starting the next. Never mix stages in one PR.

### Global guardrails (apply to every stage)

1. **No invented data.** A narrator, edge, or attribute appears only if it is
   traceable to a source row/record. Unresolved or ambiguous entities are kept
   and *flagged* (gray "unresolved" state), never guessed or dropped silently.
2. **No ML-generated reliability judgments — ever.** Classical jarh wa ta'dil
   grades (Ibn Hajar, al-Dhahabi, ...) may be displayed verbatim with
   attribution. No model output may grade, score, or rank a narrator's
   trustworthiness. This is a hard line, not a style preference.
3. **Reproducible pipeline.** `data/` holds immutable inputs; everything in
   `output/` is regenerated by scripts. Any manual correction lives in a
   versioned override file (e.g. `data/overrides/*.csv`), never edited into
   outputs.
4. **The viewer stays a static site** (no build step, no backend) until a
   stage's done-when criteria are impossible without one.
5. **Check dataset licenses before committing data.** Itqan code is MIT, but
   verify redistribution terms of each dataset it bundles; muslimscholars.info
   scrape terms must be checked before any redistribution.
6. **Performance budget:** the graph view must stay interactive (~60fps pan)
   at each stage's node count. Past ~2,000 rendered nodes, switch the renderer
   (e.g. sigma.js/WebGL) rather than degrade.

### Stage 0 — Companions of Bukhari ✅ (done)

Top-100 Companion graph, shared-student edges, Louvain, Cytoscape viewer.

### Stage 1 — Full Bukhari transmission graph ✅ (done)

Results and measured rates are in [Stage 1 results](#stage-1-results) above.

**Goal:** every transmitter in every isnad of Bukhari, all generations, as a
directed graph (teacher → student along each chain, weight = co-occurrence
count).

- Parse full Arabic isnads into ordered transmitter sequences (extend the
  existing splitter; keep the relative-reference skip rule).
- Identity is still string-based (normalized Arabic name = one node). Accept
  the resulting imperfection; **measure it**: report the count of distinct
  name strings and the estimated ambiguity hot spots (e.g. bare "Sufyan").
- Compute betweenness/PageRank; sanity benchmark: az-Zuhri, Malik, and the
  major Companion students must rank near the top, or the parse is wrong.
- Viewer: renderer upgrade as needed (expect 2–5k nodes), generation-agnostic
  force layout is fine at this stage.

**Done when:** the full graph renders interactively; centrality table exists
in `output/`; parse-failure and ambiguity rates are reported in the README.
**Explicitly out of scope:** biographical data, entity resolution, other
collections.

### Stage 2 — Entity resolution against a rijal database

**Goal:** replace string identities with real narrator IDs.

- Primary source: [Itqan](https://github.com/R3GENESI5/Itqan) (115k profiles,
  name variants, teacher/student links). Fallback/cross-check:
  [Kaggle hadith-narrators](https://www.kaggle.com/datasets/fahd09/hadith-narrators) (~24k, pre-linked teacher/student indices).
- Match on normalized name variants first, then disambiguate collisions using
  chain context (who they narrate from/to vs. the database's teacher/student
  lists) — the approach in [arXiv:2607.05424](https://arxiv.org/html/2607.05424).
- Ship a versioned resolution table (`output/resolution.csv`: name string →
  narrator ID, confidence, method) plus a manual override file that wins over
  automatic matches.
- **Guardrail:** downstream stages may only use resolved IDs; unresolved
  nodes stay in the graph flagged gray. No fuzzy match below the confidence
  threshold gets an ID.

**Done when:** ≥80% of chain positions resolve to an ID; the top-100
Companions from Stage 0 resolve at 100% (hand-verified); resolution rate is
in the README.

### Stage 3 — Biographical enrichment

**Goal:** attach generation (tabaqa), city, death year, and classical grades
to resolved narrators; make the viewer filterable.

- Node attributes from Itqan; grades always displayed with their classical
  source named (guardrail 2).
- Viewer: filter by generation / city / grade; a timeline scrubber over death
  years; a **geographic view** (arc map of transmission between cities —
  deck.gl or similar) as a second tab.
- Layout upgrade: offer a "generations" layout — a layered top-down DAG
  (Prophet ﷺ → Companions → Tabi'un → ...) alongside the force layout. This
  is the readable answer to "show the structure in depth" (see 3D note).

**Done when:** attribute coverage is reported per field; both views ship;
filters compose (e.g. "Kufan narrators, 2nd generation").

### Stage 4 — Embeddings (node2vec)

**Goal:** a 2D embedding map as an alternative lens, not a replacement.

- node2vec on the full resolved graph → UMAP → 2D scatter, colored by the
  Louvain communities, side by side with the force view.
- Evaluate: do embedding clusters agree with Louvain and with known regional
  schools? Report the agreement, including where they disagree.
- **GNNs stay out of scope** until a legitimate prediction task exists.
  Candidate future tasks: link prediction for entity resolution assistance,
  missing-attribute imputation (clearly labeled as inferred). Reliability
  prediction is permanently excluded (guardrail 2).

**Done when:** the map ships with an honest written assessment of what it
adds over Stages 1–3. If the answer is "nothing," say so and remove it.

### Stage 5 (optional, gated) — Beyond Bukhari / advanced views

Only planned after a regroup on Stages 1–4. Candidates: extend to the other
five collections via [Sanadset 650K](https://www.sciencedirect.com/science/article/pii/S2352340922007478); hadith-level chain explorer (pick a
hadith, watch its chains converge); 3D.

**3D decision gate:** a 3D force graph is *not* on the roadmap by default —
occlusion and navigation costs usually exceed the insight. The third axis is
better spent on generation layering (Stage 3), time, or geography. Revisit 3D
only if the layered DAG demonstrably fails to communicate depth-of-chain, and
prototype it as a throwaway branch first.

"""Build a Companion co-transmission graph from Sahih al-Bukhari.

Nodes  : first narrators (Companions), from the English isnad "Narrated X:".
Edges  : two Companions share an edge when the same student (2nd narrator in
         the Arabic isnad) transmitted from both; weight = # distinct shared
         students.
Then   : keep the top 100 Companions by hadith count, run Louvain.
Output : output/graph.json (nodes + edges + communities), output/summary.txt
"""

import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import networkx as nx
import pandas as pd

from isnad_parse import is_relative, parse_chains

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "bukhari"
OUT = ROOT / "output"

TOP_N = 100
SEED = 42

# ---------------------------------------------------------------- English side

# Canonical names for common translation variants. Keys are normalized forms
# (apostrophes removed, ibn -> bin, hyphens -> spaces, lowercase).
ALIASES = {
    "aisha": "'Aisha",
    "aishah": "'Aisha",
    "abu huraira": "Abu Huraira",
    "abu hurairah": "Abu Huraira",
    "bin abbas": "Ibn 'Abbas",
    "abdullah bin abbas": "Ibn 'Abbas",
    "bin umar": "Ibn 'Umar",
    "abdullah bin umar": "Ibn 'Umar",
    "salims father": "Ibn 'Umar",  # Salim bin 'Abdullah's father
    "anas": "Anas bin Malik",
    "anas bin malik": "Anas bin Malik",
    "umar": "'Umar bin Al-Khattab",
    "umar bin al khattab": "'Umar bin Al-Khattab",
    "ali": "'Ali bin Abi Talib",
    "ali bin abi talib": "'Ali bin Abi Talib",
    "jabir": "Jabir bin 'Abdullah",
    "jabir bin abdullah": "Jabir bin 'Abdullah",
    "abu said al khudri": "Abu Sa'id Al-Khudri",
    "abu said": "Abu Sa'id Al-Khudri",
    "abu musa": "Abu Musa Al-Ash'ari",
    "abu musa al ashari": "Abu Musa Al-Ash'ari",
    # Bukhari's translators use bare "'Abdullah" for Ibn Mas'ud by convention.
    "abdullah": "'Abdullah bin Mas'ud",
    "abdullah bin masud": "'Abdullah bin Mas'ud",
    "bin masud": "'Abdullah bin Mas'ud",
    "abu bakr": "Abu Bakr As-Siddiq",
    "sahl": "Sahl bin Sa'd",
    "sahl bin sad": "Sahl bin Sa'd",
    "ubada bin as samit": "'Ubada bin As-Samit",
    "al mughira": "Al-Mughira bin Shu'ba",
    "al mughira bin shuba": "Al-Mughira bin Shu'ba",
    "abdullah bin amr": "'Abdullah bin 'Amr",
    "abdullah bin amr bin al as": "'Abdullah bin 'Amr",
    "al bara": "Al-Bara' bin 'Azib",
    "al bara bin azib": "Al-Bara' bin 'Azib",
    "sahl bin sad as saidi": "Sahl bin Sa'd",
    "asma": "Asma' bint Abu Bakr",
    "asma bint abu bakr": "Asma' bint Abu Bakr",
    "asma bint abi bakr": "Asma' bint Abu Bakr",
    "salama": "Salama bin Al-Akwa'",
    "salama bin al akwa": "Salama bin Al-Akwa'",
    "sad": "Sa'd bin Abi Waqqas",
    "sad bin abi waqqas": "Sa'd bin Abi Waqqas",
}

# Well-known Successors (Tabi'un) that appear as "Narrated X" in the English
# translation. They are not Companions, so rows attributed to them are dropped.
TABIUN = {
    "nafi", "az zuhri", "urwa", "urwa bin az zubair", "hishams father",
    "qatada", "abu wail", "said bin jubair", "abu burda", "qais", "ikrima",
    "mujahid", "al hasan", "ash shabi", "tawus", "ata", "ata bin abi rabah",
    "abu salama", "al araj", "muhammad bin sirin", "bin sirin", "humaid",
    "thabit", "abu hazim", "salim", "masruq", "abu ishaq", "al amash",
    "ibrahim", "alqama", "abu qilaba", "abu uthman", "ash shabi", "amr",
    "abu salama bin abdur rahman", "abu al minhal", "abdur rahman bin abi laila",
    "bin abi mulaika", "bin abu mulaika", "al aswad", "said bin al musaiyab",
    "bin juraij", "aiyub", "amr bin maimun", "abdur rahman bin yazid",
    "abu jamra", "abu is haq", "zaid bin wahb", "ata bin yasar", "abu salih",
    "hammam", "hammam bin munabbih", "al qasim", "abu raja", "warrad",
}

NARRATED_RE = re.compile(r"^\s*narrated\s+", re.IGNORECASE)

# Registry of display names per normalized key, so every variant of a name
# collapses onto one node even when it has no alias entry.
_display: dict[str, str] = {}


def norm_english(name: str) -> str:
    """Normalized key: drop apostrophe-like marks, unify ibn/b. -> bin."""
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c))
    for ch in ("'", "`", "ʿ", "‘", "’"):
        s = s.replace(ch, "")
    s = s.lower().replace("-", " ")
    s = re.sub(r"\b(ibn|b\.)\b", "bin", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def extract_companion(english_isnad) -> str | None:
    if not isinstance(english_isnad, str):
        return None
    s = english_isnad.strip()
    if not NARRATED_RE.match(s):
        return None
    s = NARRATED_RE.sub("", s)
    s = s.split(":")[0]
    s = re.sub(r"\(.*?\)", "", s).strip().rstrip(":,")
    if not s or len(s) > 60:
        return None
    key = norm_english(s)
    if key in TABIUN:
        return None
    if key in ALIASES:
        return ALIASES[key]
    return _display.setdefault(key, s)


# ----------------------------------------------------------------- Arabic side
# Normalization and chain parsing live in isnad_parse.py, shared with Stage 1.


def extract_students(arabic_isnad) -> list[str]:
    """The Companion's direct students = transmitters at the second-to-last
    level of the first chain. Relative references ("from his father") are
    skipped here: Stage 0 identifies students by name only."""
    chains = parse_chains(arabic_isnad)
    if not chains or len(chains[0]) < 2:
        return []
    return [
        name for name in chains[0][-2]
        if not is_relative(name) and len(name) >= 3
    ]


# ---------------------------------------------------------------------- build

def main() -> None:
    frames = [pd.read_csv(p) for p in sorted(DATA.glob("Chapter*.csv"))]
    df = pd.concat(frames, ignore_index=True)

    hadith_counts: Counter[str] = Counter()
    students: dict[str, set[str]] = defaultdict(set)
    parsed = 0

    for _, row in df.iterrows():
        companion = extract_companion(row["English_Isnad"])
        if companion is None:
            continue
        hadith_counts[companion] += 1
        parsed += 1
        students[companion].update(extract_students(row["Arabic_Isnad"]))

    top = [name for name, _ in hadith_counts.most_common(TOP_N)]

    # Invert: student -> companions (restricted to top 100) they narrate from.
    # Iteration is over sorted names, not raw sets: insertion order decides the
    # order Louvain visits nodes, and Python randomises set order per process,
    # so unsorted iteration makes the communities differ between identical runs.
    teachers_of: dict[str, set[str]] = defaultdict(set)
    for companion in top:
        for s in sorted(students[companion]):
            teachers_of[s].add(companion)

    shared: Counter[tuple[str, str]] = Counter()
    for s, comps in sorted(teachers_of.items()):
        comps = sorted(comps)
        for i in range(len(comps)):
            for j in range(i + 1, len(comps)):
                shared[(comps[i], comps[j])] += 1

    G = nx.Graph()
    for name in top:
        G.add_node(name, hadith_count=hadith_counts[name])
    for (a, b), w in shared.items():
        G.add_edge(a, b, weight=w)

    communities = nx.community.louvain_communities(G, weight="weight", seed=SEED)
    communities = sorted(communities, key=lambda c: (-len(c), min(c)))
    comm_of = {n: i for i, c in enumerate(communities) for n in c}

    OUT.mkdir(exist_ok=True)
    graph_json = {
        "meta": {
            "source": "Sahih al-Bukhari (LK Hadith Corpus)",
            "hadiths_total": len(df),
            "hadiths_parsed": parsed,
            "edge_definition": "shared direct students (2nd narrator in isnad)",
            "n_communities": len(communities),
        },
        "nodes": [
            {
                "id": n,
                "hadith_count": G.nodes[n]["hadith_count"],
                "n_students": len(students[n]),
                "community": comm_of[n],
            }
            for n in top
        ],
        "edges": [
            {"source": a, "target": b, "weight": d["weight"]}
            for a, b, d in G.edges(data=True)
        ],
    }
    (OUT / "graph.json").write_text(json.dumps(graph_json, ensure_ascii=False, indent=1))

    lines = [
        f"Hadiths in corpus: {len(df)}, with parsable companion: {parsed}",
        f"Distinct companions: {len(hadith_counts)}; kept top {len(top)}",
        f"Edges among top {len(top)}: {G.number_of_edges()}",
        f"Louvain communities: {len(communities)} "
        f"(sizes: {[len(c) for c in communities]})",
        "",
    ]
    for i, comm in enumerate(communities):
        members = sorted(comm, key=lambda n: -hadith_counts[n])
        lines.append(f"--- Community {i} ({len(members)} members) ---")
        for m in members[:12]:
            lines.append(f"  {m:45s} {hadith_counts[m]:5d} hadiths, {len(students[m]):3d} students")
        if len(members) > 12:
            lines.append(f"  ... and {len(members) - 12} more")
        lines.append("")
    summary = "\n".join(lines)
    (OUT / "summary.txt").write_text(summary)
    print(summary)


if __name__ == "__main__":
    main()

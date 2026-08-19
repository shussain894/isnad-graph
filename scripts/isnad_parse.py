"""Shared Arabic isnad parsing: normalisation, segmentation, full chains.

Both `build_graph.py` (Stage 0) and `build_full_graph.py` (Stage 1) import
from here so there is exactly one implementation of the Arabic-side logic.

Text order convention: an isnad is written student-first. Segment 0 is
al-Bukhari's own shaykh; the last segment is the Companion, closest to the
Prophet (peace be upon him). Transmission therefore flows from the END of the
list towards the START.
"""

import re

AR_DIACRITICS = re.compile(r"[ً-ٰٟـ]")
AR_HONORIFICS = re.compile(
    r"(رضي الله عنهما|رضي الله عنها|رضي الله عنهم|رضي الله عنه"
    r"|صلي الله عليه وسلم|عليه السلام)"
)

# Verbs/particles that separate one transmitter from the next in an isnad.
# Waw-prefixed forms are listed explicitly: after normalisation the waw is
# glued to the following word, so "وحدثنا" is a single token.
SPLITTERS = {
    "حدثنا", "حدثني", "حدثتنا", "حدثتني", "حدثه", "حدثهم", "حدثته",
    "اخبرنا", "اخبرني", "اخبرته", "اخبره", "اخبرهم",
    "انبانا", "انباني", "سمعت", "سمعته", "سمعنا", "سمع",
    "عن", "ان", "انه", "انها", "اني",
    "قال", "قالت", "قالا", "قالوا", "يقول", "تقول",
    "يحدث", "يحدثه", "سالت", "زعم", "بلغني", "بلغه", "رفعه",
    "نا", "ثنا", "كتب", "الي", "اليه", "تابعه", "به",
    "و",
    # waw-prefixed variants
    "وحدثنا", "وحدثني", "واخبرنا", "واخبرني", "وسمعت", "وعن", "وان",
    "وقال", "وقالت", "وحدثه", "وزادني", "وتابعه",
}

# Narrative words that mark the end of a name inside a segment. A segment is
# truncated at the first of these; they are never part of a narrator's name.
JUNK = {
    "المنبر", "نحوه", "مثله", "بهذا", "الحديث", "هذا", "ذلك", "فقال",
    "فقالت", "قوله", "بعض", "حين", "فلم", "لكني", "جالس", "محدثك",
    "فقراته", "فاذا", "فيه", "علي المنبر", "يعني", "او",
}

# Relative references that cannot be resolved without a rijal database.
RELATIVE = {
    "ابيه", "ابيها", "امه", "امها", "جده", "جدته", "عمه", "عمته",
    "اخيه", "اختها", "مولاه", "مولاها", "زوجها", "ابنه", "ابنته",
}

# First-person relatives ("my father"). Only a relative reference when the
# segment is exactly this word — "ابي هريرة" is Abu Hurairah, not "my father".
SOLO_RELATIVE = {"ابي", "امي", "جدي", "عمي", "اخي", "ابن اخي", "ابن عمي"}


def is_relative(name: str) -> bool:
    toks = name.split()
    if toks and toks[0] in RELATIVE:
        return True
    return name in SOLO_RELATIVE

# Tokens after which a waw-initial word is part of a genealogical construct
# (e.g. "علقمة بن وقاص"), not a new co-narrator.
_NAME_GLUE = {"بن", "ابن", "ابي", "ابو", "ابا", "عبد", "ام", "بنت", "مولي", "ال"}

# Narrators whose names genuinely begin with waw — never split these.
_WAW_NAMES = {
    "وهب", "وكيع", "وايل", "ورقاء", "وراد", "وحشي", "واثلة", "واقد",
    "وبرة", "وليد", "الوليد", "وردان",
}

TAHWIL = "ح"  # marks a switch to a parallel chain within one isnad


def norm_arabic(text: str) -> str:
    """Strip diacritics, unify alef/ya/hamza forms, drop honorifics."""
    s = AR_DIACRITICS.sub("", text)
    s = s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    s = s.replace("ى", "ي").replace("ئ", "ي").replace("ؤ", "و")
    s = AR_HONORIFICS.sub(" ", s)
    s = re.sub(r"[،,.:()\[\]~ـ‏‎\"'؟!]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _truncate_junk(tokens: list[str]) -> list[str]:
    for i, tok in enumerate(tokens):
        if tok in JUNK:
            return tokens[:i]
    return tokens


def split_conarrators(tokens: list[str]) -> list[list[str]]:
    """Split one segment into co-narrators listed with waw ("A and B").

    A waw-initial token starts a new co-narrator unless it continues a
    genealogical construct or is a name that really begins with waw.
    """
    groups: list[list[str]] = [[]]
    for i, tok in enumerate(tokens):
        starts_new = (
            tok.startswith("و")
            and len(tok) > 2
            and tok not in _WAW_NAMES
            and tok[1:] not in _NAME_GLUE
            and groups[-1]                      # never lead with a waw split
            and (i == 0 or tokens[i - 1] not in _NAME_GLUE)
        )
        if starts_new:
            groups.append([tok[1:]])
        else:
            groups[-1].append(tok)
    return [g for g in groups if g]


def isnad_segments(arabic_isnad) -> list[str]:
    """Split one chain into transmitter-name segments, in text order.

    Kept for Stage 0 (which only needs the flat segment list); co-narrators
    are not separated here.
    """
    chains = parse_chains(arabic_isnad)
    if not chains:
        return []
    return [" / ".join(level) for level in chains[0]]


def parse_chains(arabic_isnad) -> list[list[list[str]]]:
    """Parse an isnad into chains -> levels -> co-narrator names.

    Returns one entry per parallel chain (split at the tahwil marker). Each
    chain is a list of levels in text order (shaykh first, Companion last);
    each level holds one or more names transmitting at that position.
    """
    if not isinstance(arabic_isnad, str):
        return []
    tokens = norm_arabic(arabic_isnad).split()

    # Break into parallel chains at the tahwil marker.
    blocks: list[list[str]] = [[]]
    for tok in tokens:
        if tok == TAHWIL:
            blocks.append([])
        else:
            blocks[-1].append(tok)

    chains: list[list[list[str]]] = []
    for block in blocks:
        levels: list[list[str]] = []
        current: list[str] = []

        def flush() -> None:
            toks = _truncate_junk(current)
            if not toks:
                return
            names = [" ".join(g) for g in split_conarrators(toks)]
            names = [n for n in names if len(n) >= 3]
            if names:
                levels.append(names)

        for tok in block:
            if tok in SPLITTERS:
                flush()
                current = []
            else:
                current.append(tok)
        flush()

        if levels:
            chains.append(levels)
    return chains


def resolve_relatives(levels: list[list[str]]) -> list[tuple[list[str], bool]]:
    """Turn relative references into contextual placeholders.

    "X, from his father" cannot be resolved to a name, but the father *is*
    identifiable in context as "the father of X". Keeping a placeholder
    preserves chain continuity without inventing an identity, and without
    collapsing every unnamed father onto one node. Placeholders are flagged
    so downstream stages can show them as unresolved.

    Returns one (names, unresolved) pair per level.
    """
    out: list[tuple[list[str], bool]] = []
    for i, names in enumerate(levels):
        resolved: list[str] = []
        unresolved = False
        for name in names:
            if is_relative(name):
                head = name.split()[0]
                # The referrer is the preceding level (one step towards
                # al-Bukhari), i.e. the person who said "from his father".
                owner = " + ".join(levels[i - 1]) if i > 0 else "?"
                resolved.append(f"{head} ⟨{owner}⟩")
                unresolved = True
            else:
                resolved.append(name)
        out.append((resolved, unresolved))
    return out

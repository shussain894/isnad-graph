# isnad-graph — instructions for Claude

Interactive transmission network of hadith narrators from Sahih al-Bukhari.

## The one rule that matters most

**The README's Roadmap section is the authoritative plan.** Work on exactly
one stage at a time, only when asked, respecting its scope, guardrails, and
done-when criteria. Never mix stages in one PR. If a task seems to require
breaking a global guardrail (especially: no invented data; no ML-generated
reliability judgements), stop and ask instead of working around it.

## Practical setup

- Python env: `.venv/bin/python` (pandas, networkx installed). No global pip.
- Rebuild outputs: `.venv/bin/python scripts/build_graph.py`
- View: `python3 -m http.server` from project root → http://localhost:8000/web/
- `data/` is immutable input; `output/` is always regenerable; manual
  corrections go in versioned override files, never edited into outputs.

## Conventions

- Name normalisation, alias map, and Tabi'un exclusion list live at the top
  of `scripts/build_graph.py` — extend them there, don't fork the logic.
- The viewer (`web/index.html`) is a static page, no build step. Its 4-colour
  categorical palette was validated for colour-blind safety (all-pairs, light +
  dark) with the dataviz skill's validator — do not add or change series
  colours without re-running that validation. More than 4 coloured communities
  will not pass; fold extras into grey "Other".
- Sensitive-domain tone: classical scholars are the authority on narrator
  reliability. Grades are displayed verbatim with their source named.

## Git

- Remote uses the `github-personal` SSH alias (personal account shussain894).
  Commits must be authored as shussain894 <shahhussain1@me.com> — this is
  automatic via gitconfig includeIf, but verify with `git config user.email`
  if anything about the environment looks off. The user's work email must
  never appear in commits.
- No Co-Authored-By lines in commit messages.

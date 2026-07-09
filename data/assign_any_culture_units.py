#!/usr/bin/env python3
"""
assign_any_culture_units.py

Rome: Total War EDU + EDB helper.

Purpose:
- Add a target faction to a limited number of units from ANY culture input.
- Preserve comments, loc notes, whitespace, and all other data as much as possible.
- Only ADD the faction. Never remove or rewrite unrelated data.
- Hard safety rule: only assigns entries that already contain `slave` or `all`.
- Works with any culture keywords, examples:
    --culture greek
    --culture eastern
    --culture barbarian
    --culture greek,sogdian
    --culture "greek hoplite cavalry"
    --culture scythian
    --culture carthaginian
    --culture egyptian
    --culture roman

It searches unit type, dictionary, soldier, officer, ownership, category, and class text.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


TYPE_RE = re.compile(r"^type\s+(.+?)\s*$", re.MULTILINE)
OWNERSHIP_RE = re.compile(r"^(ownership\s+)(.+?)(\s*)$", re.MULTILINE)
CATEGORY_RE = re.compile(r"^category\s+(.+?)\s*$", re.MULTILINE)
CLASS_RE = re.compile(r"^class\s+(.+?)\s*$", re.MULTILINE)

RECRUIT_RE = re.compile(
    r'^(?P<prefix>\s*recruit\s+"(?P<unit>[^"]+)"\s+\d+\s+requires\s+factions\s+\{)'
    r'(?P<factions>[^}]*)'
    r'(?P<suffix>\}.*)$',
    re.MULTILINE,
)


CULTURE_SYNONYMS = {
    "greek": ["greek", "hellenic", "macedon", "seleucid", "hoplite", "pikemen", "phalanx", "thureophoroi", "thorakitai"],
    "hellenic": ["greek", "hellenic", "macedon", "seleucid", "hoplite", "pikemen", "phalanx"],
    "eastern": ["east", "eastern", "persian", "parth", "armen", "pontic", "iranian", "cataphract", "horse archer"],
    "east": ["east", "eastern", "persian", "parth", "armen", "pontic", "iranian", "cataphract", "horse archer"],
    "sogdian": ["sogd", "sogdian", "east", "eastern", "iranian", "horse archer", "cataphract", "scyth"],
    "barbarian": ["barb", "barbarian", "warband", "gaul", "german", "dacian", "briton", "scythian"],
    "barb": ["barb", "barbarian", "warband", "gaul", "german", "dacian", "briton", "scythian"],
    "scythian": ["scyth", "scythian", "sarmatian", "horse archer", "steppe"],
    "carthaginian": ["carthaginian", "carthage", "numidian", "libyan", "iberian", "poeni"],
    "carthage": ["carthaginian", "carthage", "numidian", "libyan", "iberian", "poeni"],
    "egyptian": ["egyptian", "egypt", "nubian", "nile", "machimoi", "cleruch"],
    "egypt": ["egyptian", "egypt", "nubian", "nile", "machimoi", "cleruch"],
    "roman": ["roman", "legionary", "auxillia", "auxilia", "hastati", "triarii", "praetorian"],
}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def split_blocks(text: str) -> list[tuple[str, int, int, str]]:
    matches = list(TYPE_RE.finditer(text))
    out = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out.append((m.group(1).strip(), start, end, text[start:end]))
    return out


def split_factions(raw: str) -> list[str]:
    return [x.strip() for x in raw.replace("\n", " ").split(",") if x.strip()]


def ownerships(block: str) -> list[str]:
    m = OWNERSHIP_RE.search(block)
    return split_factions(m.group(2)) if m else []


def allowed_by_slave_or_all(block: str) -> bool:
    owners = {x.lower() for x in ownerships(block)}
    return "slave" in owners or "all" in owners


def already_has_faction_in_ownership(block: str, faction: str) -> bool:
    return faction.lower() in {x.lower() for x in ownerships(block)}


def field(block: str, regex: re.Pattern[str]) -> str:
    m = regex.search(block)
    return m.group(1).strip().lower() if m else ""


def expand_culture_input(culture: str) -> list[str]:
    raw = []
    for part in re.split(r"[,;|]+|\s+", culture.strip()):
        part = part.strip().lower()
        if part:
            raw.append(part)

    expanded = []
    for term in raw:
        expanded.append(term)
        expanded.extend(CULTURE_SYNONYMS.get(term, []))

    # Preserve order, dedupe
    seen = set()
    result = []
    for x in expanded:
        xl = x.lower()
        if xl not in seen:
            seen.add(xl)
            result.append(x)
    return result


def score_unit(unit_type: str, block: str, culture_terms: list[str], want_general: bool) -> int:
    text = (unit_type + "\n" + block).lower()
    is_general = "general_unit" in text

    if want_general and not is_general:
        return -10**9
    if not want_general and is_general:
        return -10**9

    score = 0

    # Strong exact culture/name matching.
    for term in culture_terms:
        term_l = term.lower()
        if term_l in text:
            score += 20 if " " in term_l else 10

    # If no culture match, reject. This makes arbitrary cultures safe.
    if score <= 0:
        return -10**9

    category = field(block, CATEGORY_RE)
    klass = field(block, CLASS_RE)

    if category in {"infantry", "cavalry"}:
        score += 5
    if category in {"siege", "handler"}:
        score -= 8

    if klass in {"spearmen", "missile", "light", "heavy"}:
        score += 2

    # Prefer non-mercenary regular units unless merc is part of requested culture.
    if "mercenary_unit" in text and not any("merc" in t.lower() for t in culture_terms):
        score -= 5

    # Slightly prefer units with slave/all ownership exactly because they are safe to clone.
    owners = {x.lower() for x in ownerships(block)}
    if "slave" in owners:
        score += 4
    if "all" in owners:
        score += 4

    return score


def add_faction_to_ownership(block: str, faction: str) -> str:
    def repl(m: re.Match[str]) -> str:
        raw = m.group(2)
        current = split_factions(raw)
        if faction.lower() in {x.lower() for x in current}:
            return m.group(0)

        stripped = raw.rstrip()
        if stripped and not stripped.endswith(","):
            stripped += ","
        if stripped and not stripped.endswith(" "):
            stripped += " "
        stripped += faction + ","

        return f"{m.group(1)}{stripped}{m.group(3)}"

    return OWNERSHIP_RE.sub(repl, block, count=1)


def select_and_patch_edu(
    edu_text: str,
    faction: str,
    culture: str,
    amount: int,
    generals: int,
    categories: set[str] | None,
) -> tuple[str, list[str], list[str]]:
    terms = expand_culture_input(culture)

    unit_candidates = []
    general_candidates = []

    for unit_type, start, end, block in split_blocks(edu_text):
        if not allowed_by_slave_or_all(block):
            continue
        if already_has_faction_in_ownership(block, faction):
            continue

        cat = field(block, CATEGORY_RE)
        if categories and cat not in categories:
            continue

        s = score_unit(unit_type, block, terms, want_general=False)
        if s > -10**9:
            unit_candidates.append((s, unit_type))

        gs = score_unit(unit_type, block, terms, want_general=True)
        if gs > -10**9:
            general_candidates.append((gs, unit_type))

    unit_candidates.sort(key=lambda x: (-x[0], x[1]))
    general_candidates.sort(key=lambda x: (-x[0], x[1]))

    chosen_units = [u for _, u in unit_candidates[:amount]]
    chosen_generals = [u for _, u in general_candidates[:generals]]
    chosen = set(chosen_units + chosen_generals)

    pieces = []
    last = 0
    for unit_type, start, end, block in split_blocks(edu_text):
        pieces.append(edu_text[last:start])
        if unit_type in chosen:
            block = add_faction_to_ownership(block, faction)
        pieces.append(block)
        last = end
    pieces.append(edu_text[last:])

    return "".join(pieces), chosen_units, chosen_generals


def recruit_line_allowed(raw_factions: str) -> bool:
    factions = {x.lower() for x in split_factions(raw_factions)}
    return "slave" in factions or "all" in factions


def recruit_line_has(raw_factions: str, faction: str) -> bool:
    return faction.lower() in {x.lower() for x in split_factions(raw_factions)}


def patch_edb(edb_text: str, chosen: set[str], faction: str) -> str:
    def repl(m: re.Match[str]) -> str:
        unit = m.group("unit")
        raw = m.group("factions")

        if unit not in chosen:
            return m.group(0)

        # User rule: only all/slave factions allowed to assign.
        if not recruit_line_allowed(raw):
            return m.group(0)

        if recruit_line_has(raw, faction):
            return m.group(0)

        stripped = raw.rstrip()
        if stripped and not stripped.endswith(","):
            stripped += ","
        if stripped and not stripped.endswith(" "):
            stripped += " "
        stripped += faction + ","

        return f'{m.group("prefix")}{stripped}{m.group("suffix")}'

    return RECRUIT_RE.sub(repl, edb_text)


def write_unit_list(path: Path, units: list[str], generals: list[str], culture: str, faction: str) -> None:
    text = []
    text.append(f"Faction: {faction}")
    text.append(f"Culture input: {culture}")
    text.append("")
    text.append(f"Units ({len(units)})")
    text.extend(units)
    text.append("")
    text.append(f"Generals ({len(generals)})")
    text.extend(generals)
    write_text(path, "\n".join(text) + "\n")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("edu", type=Path, help="export_descr_unit.txt")
    p.add_argument("edb", type=Path, help="export_descr_buildings.txt")
    p.add_argument("--faction", required=True, help="Faction to add, e.g. tayuan")
    p.add_argument("--culture", required=True, help='Any culture/name keywords, e.g. "greek", "eastern", "greek,sogdian"')
    p.add_argument("--amount", type=int, default=34, help="Non-general units to add")
    p.add_argument("--generals", type=int, default=1, help="General units to add")
    p.add_argument("--categories", default="infantry,cavalry", help='Comma list, or "" for all categories')
    p.add_argument("--out-edu", type=Path)
    p.add_argument("--out-edb", type=Path)
    p.add_argument("--list", type=Path)
    args = p.parse_args()

    categories = {x.strip().lower() for x in args.categories.split(",") if x.strip()}
    if not categories:
        categories = None

    edu_text = read_text(args.edu)
    edb_text = read_text(args.edb)

    new_edu, units, generals = select_and_patch_edu(
        edu_text=edu_text,
        faction=args.faction,
        culture=args.culture,
        amount=args.amount,
        generals=args.generals,
        categories=categories,
    )

    chosen = set(units + generals)
    new_edb = patch_edb(edb_text, chosen, args.faction)

    safe_culture = re.sub(r"[^A-Za-z0-9_-]+", "_", args.culture.strip()).strip("_") or "culture"
    out_edu = args.out_edu or args.edu.with_name(f"{args.edu.stem}_{args.faction}_{safe_culture}_{args.amount}.txt")
    out_edb = args.out_edb or args.edb.with_name(f"{args.edb.stem}_{args.faction}_{safe_culture}_{args.amount}.txt")
    out_list = args.list or args.edu.with_name(f"{args.faction}_{safe_culture}_{args.amount}_unit_list.txt")

    write_text(out_edu, new_edu)
    write_text(out_edb, new_edb)
    write_unit_list(out_list, units, generals, args.culture, args.faction)

    print(f"Selected {len(units)} units + {len(generals)} generals.")
    print("Safety rule enforced: only ownership/recruitment entries with slave or all were assigned.")
    print(f"Wrote {out_edu}")
    print(f"Wrote {out_edb}")
    print(f"Wrote {out_list}")


if __name__ == "__main__":
    main()

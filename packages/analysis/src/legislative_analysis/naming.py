"""Display names that identify exactly one person.

Eight surnames in this Assembly stand for more than one member: 13 of the
70 askers are "… Sangma", 8 are "… Lyngdoh". A chart that labels a bubble
"Sangma (230, 24)" therefore names a *family*, not a legislator — and a
reader cannot tell which Sangma the figure is about, or whether two
"… Sangma" bubbles are the same person counted twice.

`member_labels()` returns, for each member, the shortest label that still
identifies that person uniquely across the whole corpus:

1. the surname alone, when exactly one member carries it ("Kharpran");
2. otherwise the given name plus the surname ("Mukul Sangma",
   "Zenith Sangma" for *Zenith M. Sangma*);
3. the full name, when the two-token form would still collide.

Uniqueness is judged over *every* member in the corpus, never over the
subset a figure happens to display: a chart of the top 20 askers must not
print "Nongrum" when a second Nongrum also asks questions, simply because
that member fell outside the top 20.

The labels are deterministic functions of the name set, so figures rebuild
identically and two figures built from the same corpus label the same
person the same way.
"""

from __future__ import annotations

import re
from collections import defaultdict

__all__ = ["member_labels", "shared_surnames", "surname_counts"]


def _clean(name: str) -> str:
    return re.sub(r"\s+", " ", str(name or "").strip()).strip(" ,.;:")


def _first(name: str) -> str:
    parts = _clean(name).split()
    return parts[0] if parts else ""


def _surname(name: str) -> str:
    parts = _clean(name).split()
    return parts[-1] if parts else ""


def _key(name: str) -> str:
    """Punctuation/space-insensitive key, so "M. Sangma" == "M Sangma"."""
    return re.sub(r"[^a-z]", "", str(name or "").lower())


def surname_counts(names) -> dict[str, int]:
    """How many distinct people carry each surname."""
    groups: dict[str, set[str]] = defaultdict(set)
    for name in names:
        clean = _clean(name)
        if _surname(clean):
            groups[_surname(clean)].add(_key(clean))
    return {surname: len(people) for surname, people in groups.items()}


def shared_surnames(names) -> set[str]:
    """Surnames carried by more than one member."""
    return {s for s, n in surname_counts(names).items() if n > 1}


def member_labels(names) -> dict[str, str]:
    """Map each member's full name to its shortest unambiguous label."""
    clean_names = {_clean(n) for n in names if _clean(n)}

    # Spellings of one member ("Zenith M. Sangma" / "Zenith M Sangma") are
    # one person, not two: collapse them before deciding uniqueness, or a
    # duplicated spelling would look like a name collision.
    canonical: dict[str, str] = {}
    for name in sorted(clean_names):
        canonical.setdefault(_key(name), name)

    people = sorted(set(canonical.values()))
    unique_surnames = {s for s, n in surname_counts(people).items() if n == 1}
    # a given name is usable as a qualifier only within its own surname
    first_names: dict[tuple[str, str], set[str]] = defaultdict(set)
    for name in people:
        first_names[(_first(name), _surname(name))].add(_key(name))

    labels: dict[str, str] = {}
    for name in people:
        surname = _surname(name)
        if surname in unique_surnames:
            labels[name] = surname
        elif len(first_names[(_first(name), surname)]) == 1:
            labels[name] = f"{_first(name)} {surname}"
        else:
            labels[name] = name          # given name shared too: full name

    # final guard: if two members ended up with the same label, neither is
    # identified by it, so both fall back to their full names
    seen: dict[str, list[str]] = defaultdict(list)
    for name, label in labels.items():
        seen[label].append(name)
    for label, owners in seen.items():
        if len(owners) > 1:
            for name in owners:
                labels[name] = name

    return {name: labels[canonical[_key(name)]] for name in clean_names}

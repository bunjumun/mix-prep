"""The mixprep naming convention: NN_CAT_Descriptor[_Variant] (SPEC section 8).

Imports from `model` only; no file I/O, no third-party imports.
"""

import re
from typing import Any, Dict, List, Optional

from . import model

# Built from the canonical category list -- single source of truth.
_CATEGORY_ALTERNATION = "|".join(re.escape(code) for code in model.CATEGORIES)
NAME_RE = re.compile(
    r"^\d{2}_(" + _CATEGORY_ALTERNATION + r")_[A-Za-z0-9]+(_[A-Za-z0-9]+)*$"
)

_SPLIT_RE = re.compile(r"[^A-Za-z0-9]+")
_ALNUM_RE = re.compile(r"^[A-Za-z0-9]+$")

# Ordered keyword -> category table.  FIRST match wins; matching is a
# case-folded substring test against the original name.  Order is load-bearing:
#   * drum-specific compounds precede 'bass' so "Bass Drum" lands in DR;
#   * backing-vocal terms precede lead-vocal terms;
#   * 'lead synth' style hints precede the bare 'lead';
#   * loose two/three-letter tokens ('amp', 'oh', 'bs') sit at the tail so they
#     cannot shadow more specific words.
KEYWORD_TABLE = (
    # --- drum compounds that would otherwise be swallowed by another category
    ("bass drum", "DR"),
    ("bassdrum", "DR"),
    ("bass-drum", "DR"),
    ("kick drum", "DR"),
    ("drum kit", "DR"),
    # --- backing vocals BEFORE lead vocals
    ("bgv", "BV"),
    ("backing vox", "BV"),
    ("backing vocal", "BV"),
    ("backing", "BV"),
    ("bck vox", "BV"),
    ("harmony", "BV"),
    ("harms", "BV"),
    ("harm", "BV"),
    ("stack", "BV"),
    ("choir", "BV"),
    ("gang vox", "BV"),
    ("double vox", "BV"),
    # --- 'lead synth' style hints BEFORE the bare 'lead'
    ("lead synth", "SYN"),
    ("synth lead", "SYN"),
    ("lead syn", "SYN"),
    ("syn lead", "SYN"),
    ("lead gtr", "GTR"),
    ("gtr lead", "GTR"),
    ("lead guitar", "GTR"),
    ("guitar lead", "GTR"),
    # --- drums
    ("kick", "DR"),
    ("snare", "DR"),
    ("snr", "DR"),
    ("rimshot", "DR"),
    ("hihat", "DR"),
    ("hi-hat", "DR"),
    ("hi hat", "DR"),
    ("hat", "DR"),
    ("hh", "DR"),
    ("tom", "DR"),
    ("ride", "DR"),
    ("crash", "DR"),
    ("cymbal", "DR"),
    ("overhead", "DR"),
    ("room", "DR"),
    ("drum", "DR"),
    ("kit", "DR"),
    # --- percussion
    ("shaker", "PRC"),
    ("tamb", "PRC"),
    ("conga", "PRC"),
    ("bongo", "PRC"),
    ("cowbell", "PRC"),
    ("handclap", "PRC"),
    ("hand clap", "PRC"),
    ("clap", "PRC"),
    ("triangle", "PRC"),
    ("woodblock", "PRC"),
    ("castanet", "PRC"),
    ("perc", "PRC"),
    # --- bass
    ("bass", "BS"),
    ("808", "BS"),
    ("upright", "BS"),
    ("sub", "BS"),
    # --- guitar
    ("gtr", "GTR"),
    ("guit", "GTR"),
    ("acoustic", "GTR"),
    ("acous", "GTR"),
    ("strat", "GTR"),
    ("tele", "GTR"),
    ("les paul", "GTR"),
    ("banjo", "GTR"),
    ("mando", "GTR"),
    ("ukulele", "GTR"),
    # --- keys
    ("piano", "KEY"),
    ("rhodes", "KEY"),
    ("wurli", "KEY"),
    ("wurlitzer", "KEY"),
    ("clav", "KEY"),
    ("organ", "KEY"),
    ("hammond", "KEY"),
    ("keys", "KEY"),
    ("key", "KEY"),
    # --- synths
    ("synth", "SYN"),
    ("syn", "SYN"),
    ("pad", "SYN"),
    ("pluck", "SYN"),
    ("arp", "SYN"),
    ("saw", "SYN"),
    ("poly", "SYN"),
    ("moog", "SYN"),
    ("juno", "SYN"),
    ("prophet", "SYN"),
    # --- lead vocals
    ("vox", "VOX"),
    ("vocal", "VOX"),
    ("adlib", "VOX"),
    ("ad-lib", "VOX"),
    ("ad lib", "VOX"),
    ("verse", "VOX"),
    ("chorus vox", "VOX"),
    ("lead", "VOX"),
    ("sing", "VOX"),
    # --- backing vocals, loose token
    ("bv", "BV"),
    # --- effects / ear candy
    ("riser", "FX"),
    ("impact", "FX"),
    ("swell", "FX"),
    ("whoosh", "FX"),
    ("reverse", "FX"),
    ("downlifter", "FX"),
    ("uplifter", "FX"),
    ("transition", "FX"),
    ("sfx", "FX"),
    ("fx", "FX"),
    ("noise", "FX"),
    # --- misc
    ("click", "MISC"),
    ("talkback", "MISC"),
    ("loop", "MISC"),
    ("count in", "MISC"),
    ("countin", "MISC"),
    ("scratch", "MISC"),
    # --- loose tokens last so they never shadow the specific words above
    ("amp", "GTR"),
    ("oh", "DR"),
    ("bs", "BS"),
)


def is_valid_name(name: Any) -> bool:
    """True if `name` satisfies the convention regex."""
    if not isinstance(name, str):
        return False
    return NAME_RE.match(name) is not None


def parse_name(name: Any) -> Optional[Dict[str, Any]]:
    """Split a convention-valid name into its parts, or None if it is invalid."""
    if not is_valid_name(name):
        return None
    parts = name.split("_")
    return {
        "nn": int(parts[0]),
        "category": parts[1],
        "descriptor": parts[2],
        "variants": parts[3:],
    }


def descriptor_from(original_name: Any) -> str:
    """Messy original name -> a CamelCase descriptor matching [A-Za-z0-9]+."""
    if original_name is None:
        return "Track"
    text = original_name if isinstance(original_name, str) else str(original_name)
    parts = [p for p in _SPLIT_RE.split(text) if p]
    # Capitalise the first letter of each part but preserve interior capitals
    # so 'DI' stays 'DI'.
    descriptor = "".join(p[0].upper() + p[1:] for p in parts)
    if not descriptor or not _ALNUM_RE.match(descriptor):
        return "Track"
    if descriptor.isdigit():
        # A purely numeric descriptor is regex-valid but unreadable next to the
        # NN prefix, so qualify it.
        return "Track" + descriptor
    return descriptor


def suggest_category(original_name: Any) -> str:
    """First KEYWORD_TABLE hit against the case-folded name, else 'MISC'."""
    if original_name is None:
        return "MISC"
    text = original_name if isinstance(original_name, str) else str(original_name)
    haystack = text.casefold()
    for keyword, category in KEYWORD_TABLE:
        if keyword in haystack:
            return category
    return "MISC"


def suggest_name(original_name: Any, category: str, nn: Any) -> str:
    """Build a full convention name from an original name, category and number."""
    try:
        number = int(nn)
    except (TypeError, ValueError):
        raise model.MixprepError("track number must be a whole number, got %r" % (nn,))
    if category not in model.CATEGORIES:
        raise model.MixprepError(
            "unknown category %r (expected one of %s)"
            % (category, ", ".join(model.CATEGORIES))
        )
    return "%02d_%s_%s" % (number, category, descriptor_from(original_name))


def _sort_key(track: Dict[str, Any]) -> Any:
    category = track.get("category")
    index = model.CATEGORY_INDEX.get(category, len(model.CATEGORIES))
    raw_id = track.get("id")
    try:
        track_id = int(raw_id)
    except (TypeError, ValueError):
        track_id = 0
    return (index, track_id)


def renumber_plan(tracks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Plan the NN rewrite for every track, in (category order, id) order."""
    ordered = sorted([t for t in (tracks or []) if isinstance(t, dict)], key=_sort_key)
    plan: List[Dict[str, Any]] = []
    for position, track in enumerate(ordered, start=1):
        old = track.get("new_name")
        entry = {
            "id": track.get("id"),
            "old": old if isinstance(old, str) else None,
            "new": None,
            "nn": position,
            "skipped": False,
            "reason": None,
        }
        if not isinstance(old, str) or old.strip() == "":
            entry["skipped"] = True
            entry["reason"] = "no new_name"
        elif not is_valid_name(old):
            entry["skipped"] = True
            entry["reason"] = "non-conforming name"
        else:
            # Rewrite ONLY the leading NN; never splice the rest of the name.
            entry["new"] = ("%02d" % position) + old[2:]
            if position > 99:
                entry["reason"] = "overflow"
        plan.append(entry)
    return plan

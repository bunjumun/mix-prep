"""Canonical constants and schema helpers for mixprep manifests.

This module is the single source of truth for categories, workflow phases,
enums, YAML key order and the hardware -> real-time table.  It performs **no**
file I/O and imports nothing outside the standard library (SPEC C-1/C-6/C-7).
"""

import datetime
import re
from typing import Any, Dict, List, Optional

SCHEMA_VERSION = 1

# Category order == numbering order (SPEC section 8).
CATEGORIES = ("DR", "PRC", "BS", "GTR", "KEY", "SYN", "VOX", "BV", "FX", "MISC")
CATEGORY_NAMES = {
    "DR": "Drums",
    "PRC": "Percussion",
    "BS": "Bass",
    "GTR": "Guitar",
    "KEY": "Keys",
    "SYN": "Synths",
    "VOX": "Lead vocals",
    "BV": "Backing vocals",
    "FX": "Effects",
    "MISC": "Misc",
}
CATEGORY_INDEX = dict((code, i) for i, code in enumerate(CATEGORIES))

WORKFLOW_PHASES = (
    "copy_made",
    "tracks_inventoried",
    "renamed_in_daw",
    "exported_dry",
    "exported_wet",
    "imported_to_mix",
    "mixing_started",
)

MIX_DAWS = ("ableton", "logic")
TRACK_KINDS = ("audio", "instrument", "bus", "aux")
DECISIONS = ("keep", "cut", "undecided")
EXPORT_STATUSES = ("pending", "done", "n/a")
EXPORT_DIRECTIONS = ("dry", "wet")
HARDWARE_TYPES = ("none", "insert", "external_instrument", "sidechain", "send")
REALTIME_MODES = ("auto", "force", "off")

# (dry_pass_needs_realtime, wet_pass_needs_realtime) per SPEC section 10.
HARDWARE_REALTIME = {
    "none": (False, False),
    # DRY offline OK (insert bypassed), WET must be real time.
    "insert": (False, True),
    "send": (True, True),
    "sidechain": (True, True),
    "external_instrument": (True, True),
}

SLUG_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class MixprepError(Exception):
    """Hard/structural error. CLI catches this, prints to stderr, exits non-zero."""

    exit_code = 1


# --------------------------------------------------------------------------
# Stable YAML key order (SPEC section 7)
# --------------------------------------------------------------------------

ROOT_KEY_ORDER = ("schema_version", "song", "export", "workflow", "notes", "tracks")
SONG_KEY_ORDER = (
    "title",
    "slug",
    "source_project",
    "mixprep_copy",
    "mix_daw",
    "sample_rate",
    "tempo",
)
EXPORT_KEY_ORDER = ("realtime", "hardware_returns")
NOTE_KEY_ORDER = ("ts", "text", "edited")
TRACK_KEY_ORDER = (
    "id",
    "original_name",
    "new_name",
    "category",
    "track_kind",
    "group",
    "decision",
    "hardware",
    "exports",
    "channel_strip_ref",
    "effects_chain",
    "source",
    "notes",
)
HARDWARE_KEY_ORDER = ("type", "io")
EXPORTS_KEY_ORDER = ("dry", "wet")
EXPORT_SLOT_KEY_ORDER = ("status", "path")
FX_KEY_ORDER = ("plugin", "maker", "preset", "bypassed", "settings", "params", "ref")
SOURCE_KEY_ORDER = ("mic", "performer", "recorded", "takes")

# --------------------------------------------------------------------------
# Enum + type maps driving `set` dotted paths and validation
# --------------------------------------------------------------------------

# dotted path (relative to a track dict) -> tuple of allowed values
TRACK_ENUMS = {
    "category": CATEGORIES,
    "track_kind": TRACK_KINDS,
    "decision": DECISIONS,
    "hardware.type": HARDWARE_TYPES,
    "exports.dry.status": EXPORT_STATUSES,
    "exports.wet.status": EXPORT_STATUSES,
}

# dotted path -> "str" | "int" | "bool" | "str_or_null"
TRACK_FIELD_TYPES = {
    "original_name": "str",
    "new_name": "str_or_null",
    "category": "str",
    "track_kind": "str",
    "group": "str_or_null",
    "decision": "str",
    "hardware.type": "str",
    "hardware.io": "str_or_null",
    "exports.dry.status": "str",
    "exports.dry.path": "str_or_null",
    "exports.wet.status": "str",
    "exports.wet.path": "str_or_null",
    "channel_strip_ref": "str_or_null",
    "effects_chain.bypassed": "bool",
    "source.mic": "str_or_null",
    "source.performer": "str_or_null",
    "source.recorded": "str_or_null",
    "source.takes": "int",
}

# Manifest-level (non-track) settable paths, used as a fallback by `coerce`.
MANIFEST_FIELD_TYPES = dict(
    [
        ("schema_version", "int"),
        ("song.title", "str"),
        ("song.slug", "str"),
        ("song.source_project", "str"),
        ("song.mixprep_copy", "str"),
        ("song.mix_daw", "str"),
        ("song.sample_rate", "int"),
        ("song.tempo", "int"),
        ("export.realtime", "str"),
        ("export.hardware_returns", "str"),
    ]
    + [("workflow." + flag, "bool") for flag in WORKFLOW_PHASES]
)

_NULL_STRINGS = ("", "null", "none", "~")
_TRUE_STRINGS = ("true", "yes", "y", "on", "1")
_FALSE_STRINGS = ("false", "no", "n", "off", "0")


# --------------------------------------------------------------------------
# Constructors
# --------------------------------------------------------------------------


def now_ts() -> str:
    """ISO-8601 local time, seconds precision, e.g. '2026-07-28T14:03:11'."""
    return datetime.datetime.now().replace(microsecond=0).isoformat()


def title_from_slug(slug: str) -> str:
    """'ocean-floor' -> 'Ocean Floor'."""
    words = re.split(r"[^A-Za-z0-9]+", str(slug))
    words = [w for w in words if w]
    if not words:
        return str(slug)
    return " ".join(w[0].upper() + w[1:] for w in words)


def new_manifest(
    slug,
    title=None,
    source_project="",
    mixprep_copy="",
    mix_daw="logic",
    sample_rate=48000,
    tempo=120,
) -> Dict[str, Any]:
    """A complete, empty manifest dict for `slug` (SPEC section 7)."""
    if title is None or title == "":
        title = title_from_slug(slug)
    return {
        "schema_version": SCHEMA_VERSION,
        "song": {
            "title": title,
            "slug": slug,
            "source_project": source_project if source_project is not None else "",
            "mixprep_copy": mixprep_copy if mixprep_copy is not None else "",
            "mix_daw": mix_daw,
            "sample_rate": sample_rate,
            "tempo": tempo,
        },
        "export": {"realtime": "auto", "hardware_returns": ""},
        "workflow": dict((flag, False) for flag in WORKFLOW_PHASES),
        "notes": [],
        "tracks": [],
    }


def new_track(
    track_id: int,
    original_name: str,
    category: Optional[str] = None,
    new_name: Optional[str] = None,
) -> Dict[str, Any]:
    """A complete track dict with every key present (SPEC section 7)."""
    return {
        "id": int(track_id),
        "original_name": original_name,
        "new_name": new_name,
        "category": category,
        "track_kind": "audio",
        "group": None,
        "decision": "undecided",
        "hardware": {"type": "none", "io": None},
        "exports": {
            "dry": {"status": "pending", "path": None},
            "wet": {"status": "pending", "path": None},
        },
        "channel_strip_ref": None,
        "effects_chain": [],
        "source": {"mic": None, "performer": None, "recorded": None, "takes": None},
        "notes": [],
    }


# --------------------------------------------------------------------------
# Track lookup
# --------------------------------------------------------------------------


def _tracks_of(manifest: Any) -> List[Dict[str, Any]]:
    if not isinstance(manifest, dict):
        raise MixprepError("manifest is not a mapping")
    tracks = manifest.get("tracks")
    if tracks is None:
        return []
    if not isinstance(tracks, list):
        raise MixprepError("manifest 'tracks' is not a list")
    return [t for t in tracks if isinstance(t, dict)]


def _track_id(track: Dict[str, Any]) -> Optional[int]:
    raw = track.get("id")
    if isinstance(raw, bool) or raw is None:
        return None
    if isinstance(raw, int):
        return raw
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return None


def next_track_id(manifest: Dict[str, Any]) -> int:
    """max(existing ids) + 1, starting at 1. Never reuses ids."""
    ids = [i for i in (_track_id(t) for t in _tracks_of(manifest)) if i is not None]
    if not ids:
        return 1
    return max(ids) + 1


def _describe(track: Dict[str, Any]) -> str:
    return "id=%s (%s)" % (track.get("id"), track.get("new_name") or track.get("original_name") or "")


def get_track(manifest: Dict[str, Any], ref: Any) -> Dict[str, Any]:
    """Find a track by integer id (str or int), exact new_name, or exact original_name."""
    tracks = _tracks_of(manifest)
    if ref is None:
        raise MixprepError("no track reference given")
    numeric: Optional[int] = None
    if isinstance(ref, bool):
        raise MixprepError("invalid track reference: %r" % (ref,))
    if isinstance(ref, int):
        numeric = ref
    elif isinstance(ref, str) and ref.strip().lstrip("+-").isdigit():
        try:
            numeric = int(ref.strip())
        except ValueError:
            numeric = None

    if numeric is not None:
        matches = [t for t in tracks if _track_id(t) == numeric]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise MixprepError(
                "ambiguous track reference %r: %d tracks share id %d"
                % (ref, len(matches), numeric)
            )
        if not isinstance(ref, str):
            raise MixprepError("no track with id %d" % numeric)

    key = str(ref)
    for field in ("new_name", "original_name"):
        matches = [t for t in tracks if t.get(field) == key]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise MixprepError(
                "ambiguous track reference %r: matches %s on %s"
                % (key, ", ".join(_describe(t) for t in matches), field)
            )
    raise MixprepError(
        "no track matching %r (expected a track id, new_name, or original_name)" % (key,)
    )


# --------------------------------------------------------------------------
# Dotted paths
# --------------------------------------------------------------------------


def get_path(obj: Any, dotted: str) -> Any:
    """Value at a dotted path, or None if any segment is absent."""
    cur = obj
    for part in str(dotted).split("."):
        if not isinstance(cur, dict):
            return None
        if part not in cur:
            return None
        cur = cur[part]
    return cur


def set_path(obj: Dict[str, Any], dotted: str, value: Any) -> None:
    """Set a dotted path, creating intermediate dicts as needed."""
    parts = str(dotted).split(".")
    if not parts or parts == [""]:
        raise MixprepError("empty field path")
    cur = obj
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    cur[parts[-1]] = value


def field_type(dotted_path: str) -> Optional[str]:
    """Declared type for a settable dotted path, or None if unknown."""
    key = str(dotted_path)
    if key in TRACK_FIELD_TYPES:
        return TRACK_FIELD_TYPES[key]
    return MANIFEST_FIELD_TYPES.get(key)


def coerce(dotted_path: str, raw_string: Any) -> Any:
    """Coerce a CLI string to the declared type for `dotted_path`.

    '', 'null' and 'none' become None for nullable fields.  Booleans accept
    true/false/yes/no/1/0.  Raises MixprepError on an unknown path or a value
    that cannot be parsed as the declared type.
    """
    kind = field_type(dotted_path)
    if kind is None:
        raise MixprepError("unknown field '%s'" % (dotted_path,))
    if raw_string is None:
        return None
    if not isinstance(raw_string, str):
        raw = str(raw_string)
    else:
        raw = raw_string
    stripped = raw.strip()
    lowered = stripped.lower()

    if kind == "str_or_null":
        if lowered in _NULL_STRINGS:
            return None
        return raw
    if kind == "str":
        return raw
    if kind == "int":
        if lowered in _NULL_STRINGS:
            return None
        try:
            return int(stripped, 10)
        except (TypeError, ValueError):
            raise MixprepError(
                "field '%s' expects a whole number, got %r" % (dotted_path, raw)
            )
    if kind == "bool":
        if lowered in _TRUE_STRINGS:
            return True
        if lowered in _FALSE_STRINGS:
            return False
        raise MixprepError(
            "field '%s' expects a boolean (true/false/yes/no/1/0), got %r"
            % (dotted_path, raw)
        )
    raise MixprepError("field '%s' has an unsupported type %r" % (dotted_path, kind))


# --------------------------------------------------------------------------
# Real-time export derivation (SPEC section 10, FR-26)
# --------------------------------------------------------------------------


def derive_realtime(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Per-pass real-time requirement plus the reasons behind it."""
    export = manifest.get("export") if isinstance(manifest, dict) else None
    if not isinstance(export, dict):
        export = {}
    mode = export.get("realtime")
    if mode not in REALTIME_MODES:
        mode = "auto"

    dry = False
    wet = False
    reasons: List[Dict[str, Any]] = []
    dry_na: List[Any] = []

    for track in _tracks_of(manifest):
        if track.get("decision") == "cut":
            continue
        hardware = track.get("hardware")
        htype = hardware.get("type") if isinstance(hardware, dict) else None
        if htype not in HARDWARE_REALTIME:
            htype = "none"
        needs_dry, needs_wet = HARDWARE_REALTIME[htype]
        if needs_dry or needs_wet:
            passes = []
            if needs_dry:
                passes.append("dry")
            if needs_wet:
                passes.append("wet")
            reasons.append(
                {
                    "scope": "track",
                    "id": track.get("id"),
                    "name": track.get("new_name") or track.get("original_name") or "",
                    "hardware": htype,
                    "passes": passes,
                }
            )
            dry = dry or needs_dry
            wet = wet or needs_wet
        if htype == "external_instrument":
            status = get_path(track, "exports.dry.status")
            if status != "n/a":
                dry_na.append(track.get("id"))

    returns = export.get("hardware_returns")
    if returns is not None and str(returns).strip() != "":
        reasons.append(
            {
                "scope": "song",
                "name": "hardware_returns",
                "detail": str(returns),
                "passes": ["wet"],
            }
        )
        wet = True

    if mode == "force":
        dry = True
        wet = True
    elif mode == "off":
        dry = False
        wet = False

    return {
        "mode": mode,
        "dry": dry,
        "wet": wet,
        "reasons": reasons,
        "dry_na_recommended": dry_na,
    }

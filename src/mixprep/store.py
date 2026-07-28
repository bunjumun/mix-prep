"""Filesystem + YAML persistence for mixprep manifests.

Write scope (SPEC C-1/C-7): this module writes **only** inside
``<root>/songs/<slug>/`` and only from :func:`save`.  Stored pointers
(``source_project``, ``mixprep_copy``, ``ref``, ``channel_strip_ref``) are inert
strings -- they are never opened, resolved or dereferenced here.
"""

import copy
import os
import pathlib
import tempfile
from typing import Any, Dict, List, Optional

import yaml

from . import model
from .model import MixprepError

SONGS_DIRNAME = "songs"
MANIFEST_FILENAME = "song.yaml"
ROOT_ENV_VAR = "MIXPREP_ROOT"

# Slug shape lives in model (single source of truth).
_SLUG_RE = model.SLUG_RE


# --------------------------------------------------------------------------
# Locations
# --------------------------------------------------------------------------


def validate_slug(slug: Any) -> None:
    """Raise MixprepError unless `slug` matches ^[A-Za-z0-9_-]+$."""
    if not isinstance(slug, str) or not _SLUG_RE.match(slug):
        raise MixprepError(
            "invalid slug %r: use only letters, digits, '-' and '_'" % (slug,)
        )


def find_root(start: Optional[Any] = None) -> pathlib.Path:
    """Locate the mixprep repo root.

    ``$MIXPREP_ROOT`` wins if set (and must exist).  Otherwise walk up from
    `start` (default: cwd) looking for a directory containing ``songs/`` or
    ``pyproject.toml``; fall back to the starting directory.
    """
    env_root = os.environ.get(ROOT_ENV_VAR)
    if env_root:
        root = pathlib.Path(env_root).expanduser()
        if not root.is_dir():
            raise MixprepError(
                "%s points at %s, which is not an existing directory"
                % (ROOT_ENV_VAR, root)
            )
        return root.resolve()

    if start is None:
        base = pathlib.Path.cwd()
    else:
        base = pathlib.Path(start)
    base = base.expanduser()
    try:
        base = base.resolve()
    except OSError:
        pass
    if base.is_file():
        base = base.parent

    for candidate in [base] + list(base.parents):
        if (candidate / SONGS_DIRNAME).is_dir() or (candidate / "pyproject.toml").is_file():
            return candidate
    return base


def song_dir(root: Any, slug: str) -> pathlib.Path:
    """<root>/songs/<slug> -- the only directory mixprep ever writes into."""
    validate_slug(slug)
    return pathlib.Path(root) / SONGS_DIRNAME / slug


def manifest_path(root: Any, slug: str) -> pathlib.Path:
    """<root>/songs/<slug>/song.yaml"""
    return song_dir(root, slug) / MANIFEST_FILENAME


def exists(root: Any, slug: str) -> bool:
    """True if the song's manifest file exists."""
    return manifest_path(root, slug).is_file()


def list_slugs(root: Any) -> List[str]:
    """Sorted slugs of every directory under songs/ that holds a manifest."""
    songs = pathlib.Path(root) / SONGS_DIRNAME
    if not songs.is_dir():
        return []
    slugs = []
    for entry in songs.iterdir():
        if entry.is_dir() and (entry / MANIFEST_FILENAME).is_file():
            slugs.append(entry.name)
    return sorted(slugs)


# --------------------------------------------------------------------------
# Load
# --------------------------------------------------------------------------


def load(root: Any, slug: str) -> Dict[str, Any]:
    """Read and parse songs/<slug>/song.yaml."""
    path = manifest_path(root, slug)
    if not path.is_file():
        raise MixprepError("no manifest for '%s' (expected %s)" % (slug, path))
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise MixprepError("cannot read %s: %s" % (path, exc))
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise MixprepError("cannot parse %s: %s" % (path, exc))
    if data is None:
        raise MixprepError("%s is empty" % path)
    if not isinstance(data, dict):
        raise MixprepError("%s does not contain a YAML mapping at the top level" % path)

    raw_version = data.get("schema_version")
    if raw_version is None:
        # Missing schema_version is tolerated: assume the first schema.
        data["schema_version"] = 1
    else:
        try:
            version = int(raw_version)
        except (TypeError, ValueError):
            version = None
        if version is not None and version > model.SCHEMA_VERSION:
            raise MixprepError(
                "%s has schema_version %s but this mixprep supports up to %d -- upgrade mixprep"
                % (path, raw_version, model.SCHEMA_VERSION)
            )
    return data


# --------------------------------------------------------------------------
# Ordering + serialisation
# --------------------------------------------------------------------------


def _ordered(mapping: Dict[str, Any], order: Any) -> Dict[str, Any]:
    """Known keys first in `order`, then unknown keys in their original order."""
    out: Dict[str, Any] = {}
    for key in order:
        if key in mapping:
            out[key] = mapping[key]
    for key in mapping:
        if key not in out:
            out[key] = mapping[key]
    return out


def _order_notes(notes: Any) -> Any:
    if not isinstance(notes, list):
        return notes
    return [
        _ordered(n, model.NOTE_KEY_ORDER) if isinstance(n, dict) else n for n in notes
    ]


def _order_track(track: Any) -> Any:
    if not isinstance(track, dict):
        return track
    out = _ordered(track, model.TRACK_KEY_ORDER)
    if isinstance(out.get("hardware"), dict):
        out["hardware"] = _ordered(out["hardware"], model.HARDWARE_KEY_ORDER)
    if isinstance(out.get("exports"), dict):
        exports = _ordered(out["exports"], model.EXPORTS_KEY_ORDER)
        for direction in list(exports.keys()):
            slot = exports[direction]
            if isinstance(slot, dict):
                exports[direction] = _ordered(slot, model.EXPORT_SLOT_KEY_ORDER)
        out["exports"] = exports
    if isinstance(out.get("effects_chain"), list):
        # List order == signal-chain order; preserve it exactly.
        out["effects_chain"] = [
            _ordered(fx, model.FX_KEY_ORDER) if isinstance(fx, dict) else fx
            for fx in out["effects_chain"]
        ]
    if isinstance(out.get("source"), dict):
        out["source"] = _ordered(out["source"], model.SOURCE_KEY_ORDER)
    if "notes" in out:
        out["notes"] = _order_notes(out["notes"])
    return out


def order_manifest(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Return a deep copy reordered to the canonical key order (SPEC section 7).

    Unknown keys are preserved and appended after the known ones at their own
    level; ``tracks``, ``effects_chain`` and ``notes`` list order is untouched.
    """
    if not isinstance(manifest, dict):
        raise MixprepError("manifest is not a mapping")
    data = copy.deepcopy(manifest)
    out = _ordered(data, model.ROOT_KEY_ORDER)
    if isinstance(out.get("song"), dict):
        out["song"] = _ordered(out["song"], model.SONG_KEY_ORDER)
    if isinstance(out.get("export"), dict):
        out["export"] = _ordered(out["export"], model.EXPORT_KEY_ORDER)
    if isinstance(out.get("workflow"), dict):
        out["workflow"] = _ordered(out["workflow"], model.WORKFLOW_PHASES)
    if "notes" in out:
        out["notes"] = _order_notes(out["notes"])
    if isinstance(out.get("tracks"), list):
        out["tracks"] = [_order_track(t) for t in out["tracks"]]
    return out


def dump_yaml(manifest: Dict[str, Any]) -> str:
    """Serialise a manifest to the canonical, git-friendly YAML text."""
    return yaml.safe_dump(
        order_manifest(manifest),
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=100,
    )


# --------------------------------------------------------------------------
# Save (the ONLY writer in mixprep)
# --------------------------------------------------------------------------


def save(
    root: Any, slug: str, manifest: Dict[str, Any], dry_run: bool = False
) -> pathlib.Path:
    """Atomically write songs/<slug>/song.yaml and return its path.

    With ``dry_run=True`` nothing at all is written (not even the directory);
    the path that *would* have been written is returned.
    """
    path = manifest_path(root, slug)
    if not isinstance(manifest, dict):
        raise MixprepError("manifest is not a mapping")

    if dry_run:
        return path

    if not manifest.get("schema_version"):
        manifest["schema_version"] = model.SCHEMA_VERSION

    text = dump_yaml(manifest)
    directory = path.parent
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise MixprepError("cannot create %s: %s" % (directory, exc))

    tmp_name: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(directory),
            prefix=".song.",
            suffix=".yaml.tmp",
            delete=False,
        ) as handle:
            tmp_name = handle.name
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, str(path))
        tmp_name = None
    except OSError as exc:
        raise MixprepError("cannot write %s: %s" % (path, exc))
    finally:
        if tmp_name is not None and os.path.exists(tmp_name):
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
    return path

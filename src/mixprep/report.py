"""Validation and rendering for mixprep manifests.

Pure functions over manifest dicts: **no** click, **no** file I/O.  Every
``*_data`` helper returns a JSON-serialisable structure; every ``*_text``
helper returns plain text (no ANSI, no rich).

Stored pointers (``source_project``, ``mixprep_copy``, ``ref``,
``channel_strip_ref``, export paths) are treated as inert strings here.  They
are compared and printed, never opened, resolved or stat-ed (SPEC C-1/C-3/C-7).
"""

import os
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import model, naming

# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def render_table(
    headers: Sequence[Any],
    rows: Sequence[Sequence[Any]],
    aligns: Optional[Sequence[str]] = None,
) -> str:
    """Space-padded columns with a ``---`` rule under the header row."""
    head = ["" if h is None else str(h) for h in (headers or [])]
    ncols = len(head)
    body: List[List[str]] = []
    for row in rows or []:
        cells = ["" if c is None else str(c) for c in row]
        if len(cells) < ncols:
            cells = cells + [""] * (ncols - len(cells))
        body.append(cells[:ncols])

    if aligns is None:
        col_aligns = ["l"] * ncols
    else:
        col_aligns = list(aligns)[:ncols] + ["l"] * max(0, ncols - len(aligns))

    widths = [len(h) for h in head]
    for cells in body:
        for i, cell in enumerate(cells):
            if len(cell) > widths[i]:
                widths[i] = len(cell)

    def _fmt(cells: Sequence[str]) -> str:
        out = []
        for i, cell in enumerate(cells):
            if col_aligns[i] == "r":
                out.append(cell.rjust(widths[i]))
            else:
                out.append(cell.ljust(widths[i]))
        return "  ".join(out).rstrip()

    lines = [_fmt(head), "  ".join("-" * w for w in widths).rstrip()]
    for cells in body:
        lines.append(_fmt(cells))
    return "\n".join(lines)


def _tracks(manifest: Any) -> List[Dict[str, Any]]:
    """Every track that is a mapping; tolerant of a junk manifest."""
    if not isinstance(manifest, dict):
        return []
    tracks = manifest.get("tracks")
    if not isinstance(tracks, list):
        return []
    return [t for t in tracks if isinstance(t, dict)]


def _song(manifest: Any) -> Dict[str, Any]:
    if isinstance(manifest, dict) and isinstance(manifest.get("song"), dict):
        return manifest["song"]
    return {}


def _workflow(manifest: Any) -> Dict[str, bool]:
    raw = manifest.get("workflow") if isinstance(manifest, dict) else None
    if not isinstance(raw, dict):
        raw = {}
    return dict((flag, bool(raw.get(flag))) for flag in model.WORKFLOW_PHASES)


def _label(track: Dict[str, Any]) -> str:
    name = track.get("new_name") or track.get("original_name") or ""
    if name:
        return "track %s (%s)" % (track.get("id"), name)
    return "track %s" % (track.get("id"),)


def _pct(part: int, total: int) -> Optional[float]:
    """Percentage, or None when there is nothing to measure."""
    if not total:
        return None
    return round(part * 100.0 / total, 1)


def _pct_text(value: Optional[float]) -> str:
    if value is None:
        return "-"
    return "%g%%" % value


def source_copy_conflict(source_project: Any, mixprep_copy: Any) -> Optional[str]:
    """FR-28/C-9 guard: is ``mixprep_copy`` the same as, or inside, the source?

    Pure string comparison -- the two paths are never opened or stat-ed.
    Returns a human-readable reason, or None when the pair is fine (which
    includes the case where either side is empty).
    """
    source = source_project.strip() if isinstance(source_project, str) else ""
    copy = mixprep_copy.strip() if isinstance(mixprep_copy, str) else ""
    if not source or not copy:
        return None
    src = os.path.normpath(source)
    cpy = os.path.normpath(copy)
    if src == cpy:
        return "mixprep_copy is the same path as source_project (%s)" % source
    prefix = src if src.endswith(os.sep) else src + os.sep
    if cpy.startswith(prefix):
        return "mixprep_copy (%s) is nested inside source_project (%s)" % (copy, source)
    return None


def workflow_order_problems(manifest: Any) -> List[str]:
    """Flags that are true while an earlier pipeline phase is still false."""
    flags = _workflow(manifest)
    problems = []
    first_false = None
    for flag in model.WORKFLOW_PHASES:
        if flags[flag]:
            if first_false is not None:
                problems.append(
                    "workflow.%s is checked but the earlier phase '%s' is not"
                    % (flag, first_false)
                )
        elif first_false is None:
            first_false = flag
    return problems


# --------------------------------------------------------------------------
# Validation (SPEC section 8 severity table)
# --------------------------------------------------------------------------


def validate_manifest(
    manifest: Any, slug: Optional[str] = None
) -> Tuple[List[str], List[str]]:
    """Return ``(errors, warnings)`` per the SPEC section 8 severity table."""
    errors: List[str] = []
    warnings: List[str] = []

    if not isinstance(manifest, dict):
        return (["manifest is not a YAML mapping"], [])

    # --- schema_version ---------------------------------------------------
    raw_version = manifest.get("schema_version")
    if raw_version is None:
        errors.append("missing required field 'schema_version'")
    else:
        try:
            version = int(raw_version)
        except (TypeError, ValueError):
            version = None
        if version is None:
            errors.append("schema_version %r is not a whole number" % (raw_version,))
        elif version > model.SCHEMA_VERSION:
            errors.append(
                "schema_version %d is newer than this mixprep supports (%d)"
                % (version, model.SCHEMA_VERSION)
            )
        elif version < 1:
            errors.append("schema_version %d is not >= 1" % version)

    # --- song -------------------------------------------------------------
    song = manifest.get("song")
    if song is None:
        errors.append("missing required section 'song'")
        song = {}
    elif not isinstance(song, dict):
        errors.append("'song' is not a mapping")
        song = {}

    title = song.get("title")
    if not isinstance(title, str) or not title.strip():
        errors.append("missing required field 'song.title'")

    song_slug = song.get("slug")
    if not isinstance(song_slug, str) or not song_slug.strip():
        errors.append("missing required field 'song.slug'")
    elif not model.SLUG_RE.match(song_slug):
        errors.append(
            "song.slug %r is not filesystem-safe (expected [A-Za-z0-9_-]+)" % song_slug
        )
    elif slug is not None and song_slug != slug:
        warnings.append(
            "song.slug %r does not match the song directory name %r"
            % (song_slug, slug)
        )

    mix_daw = song.get("mix_daw")
    if mix_daw is not None and mix_daw not in model.MIX_DAWS:
        errors.append(
            "song.mix_daw %r is not one of %s" % (mix_daw, ", ".join(model.MIX_DAWS))
        )

    conflict = source_copy_conflict(song.get("source_project"), song.get("mixprep_copy"))
    if conflict:
        warnings.append("%s -- the copy must live outside the original (C-9)" % conflict)

    # --- export -----------------------------------------------------------
    export = manifest.get("export")
    if export is None:
        export = {}
    elif not isinstance(export, dict):
        errors.append("'export' is not a mapping")
        export = {}
    realtime = export.get("realtime")
    if realtime is not None and realtime not in model.REALTIME_MODES:
        errors.append(
            "export.realtime %r is not one of %s"
            % (realtime, ", ".join(model.REALTIME_MODES))
        )

    # --- workflow ---------------------------------------------------------
    raw_workflow = manifest.get("workflow")
    if raw_workflow is not None and not isinstance(raw_workflow, dict):
        errors.append("'workflow' is not a mapping")
    else:
        warnings.extend(workflow_order_problems(manifest))

    # --- notes ------------------------------------------------------------
    raw_notes = manifest.get("notes")
    if raw_notes is not None and not isinstance(raw_notes, list):
        errors.append("'notes' is not a list")

    # --- tracks -----------------------------------------------------------
    raw_tracks = manifest.get("tracks")
    if raw_tracks is None:
        raw_tracks = []
    elif not isinstance(raw_tracks, list):
        errors.append("'tracks' is not a list")
        raw_tracks = []

    seen_ids: Dict[int, str] = {}
    seen_names: Dict[str, str] = {}

    for position, track in enumerate(raw_tracks):
        label = "tracks[%d]" % position
        if not isinstance(track, dict):
            errors.append("%s is not a mapping" % label)
            continue

        raw_id = track.get("id")
        if raw_id is None or isinstance(raw_id, bool):
            errors.append("%s: missing required field 'id'" % label)
        else:
            try:
                track_id = int(raw_id)
            except (TypeError, ValueError):
                errors.append("%s: id %r is not a whole number" % (label, raw_id))
                track_id = None
            if track_id is not None:
                label = "track %d" % track_id
                if track_id in seen_ids:
                    errors.append(
                        "duplicate track id %d (also used by %s)"
                        % (track_id, seen_ids[track_id])
                    )
                else:
                    seen_ids[track_id] = "tracks[%d]" % position

        original = track.get("original_name")
        if original is None:
            errors.append("%s: missing required field 'original_name'" % label)
        elif not isinstance(original, str):
            errors.append("%s: original_name %r is not a string" % (label, original))
        elif not original.strip():
            warnings.append("%s: original_name is empty" % label)

        new_name = track.get("new_name")
        if new_name is None or (isinstance(new_name, str) and not new_name.strip()):
            warnings.append("%s: no new_name yet (run `mixprep suggest`)" % label)
        elif not isinstance(new_name, str):
            warnings.append("%s: new_name %r is not a string" % (label, new_name))
        else:
            if not naming.is_valid_name(new_name):
                warnings.append(
                    "%s: new_name %r does not match the naming convention "
                    "(NN_CAT_Descriptor[_Variant])" % (label, new_name)
                )
            key = new_name.strip()
            if key in seen_names:
                errors.append(
                    "duplicate new_name %r (%s and %s)" % (key, seen_names[key], label)
                )
            else:
                seen_names[key] = label

        category = track.get("category")
        if category is None or category == "":
            warnings.append("%s: no category yet (run `mixprep suggest`)" % label)
        elif category not in model.CATEGORIES:
            errors.append(
                "%s: unknown category %r (expected one of %s)"
                % (label, category, ", ".join(model.CATEGORIES))
            )

        for field, allowed in (
            ("track_kind", model.TRACK_KINDS),
            ("decision", model.DECISIONS),
        ):
            value = track.get(field)
            if value is not None and value not in allowed:
                errors.append(
                    "%s: invalid %s %r (expected one of %s)"
                    % (label, field, value, ", ".join(allowed))
                )

        hardware = track.get("hardware")
        if hardware is not None and not isinstance(hardware, dict):
            errors.append("%s: 'hardware' is not a mapping" % label)
        else:
            hardware_type = model.get_path(track, "hardware.type")
            if hardware_type is not None and hardware_type not in model.HARDWARE_TYPES:
                errors.append(
                    "%s: invalid hardware.type %r (expected one of %s)"
                    % (label, hardware_type, ", ".join(model.HARDWARE_TYPES))
                )

        exports = track.get("exports")
        if exports is not None and not isinstance(exports, dict):
            errors.append("%s: 'exports' is not a mapping" % label)
        else:
            for direction in model.EXPORT_DIRECTIONS:
                status = model.get_path(track, "exports.%s.status" % direction)
                if status is None:
                    continue
                if status not in model.EXPORT_STATUSES:
                    errors.append(
                        "%s: invalid exports.%s.status %r (expected one of %s)"
                        % (label, direction, status, ", ".join(model.EXPORT_STATUSES))
                    )
                elif status == "done":
                    path = model.get_path(track, "exports.%s.path" % direction)
                    if not (isinstance(path, str) and path.strip()):
                        warnings.append(
                            "%s: exports.%s.status is 'done' but no stem path is recorded"
                            % (label, direction)
                        )

        chain = track.get("effects_chain")
        if chain is not None and not isinstance(chain, list):
            errors.append("%s: 'effects_chain' is not a list" % label)
        elif isinstance(chain, list):
            for index, entry in enumerate(chain):
                if not isinstance(entry, dict):
                    warnings.append(
                        "%s: effects_chain[%d] is not a mapping" % (label, index)
                    )
                elif not (
                    isinstance(entry.get("plugin"), str) and entry["plugin"].strip()
                ):
                    warnings.append(
                        "%s: effects_chain[%d] has no 'plugin' name" % (label, index)
                    )

    # --- NN numbering -----------------------------------------------------
    dict_tracks = [t for t in raw_tracks if isinstance(t, dict)]
    plan = naming.renumber_plan(dict_tracks)
    misplaced = []
    overflow = False
    for entry in plan:
        if entry.get("reason") == "overflow":
            overflow = True
        if entry.get("skipped"):
            continue
        parsed = naming.parse_name(entry.get("old"))
        if parsed is not None and parsed["nn"] != entry["nn"]:
            misplaced.append(
                "track %s (%s -> %s)" % (entry.get("id"), entry.get("old"), entry.get("new"))
            )
    if misplaced:
        shown = misplaced[:6]
        if len(misplaced) > len(shown):
            shown.append("... and %d more" % (len(misplaced) - len(shown)))
        warnings.append(
            "NN numbering has gaps or is out of order: %s; run `mixprep renumber`"
            % ", ".join(shown)
        )
    if overflow:
        warnings.append(
            "more than 99 tracks: NN numbering overflows past 99 and no longer sorts"
        )

    # --- groups (FR-24) ---------------------------------------------------
    for name, members in sorted(_group_map(dict_tracks).items()):
        decisions = [m.get("decision") for m in members]
        keeps = decisions.count("keep")
        cuts = decisions.count("cut")
        if keeps and cuts:
            warnings.append(
                "group '%s' has split decisions (%d keep / %d cut) -- confirm that is intended"
                % (name, keeps, cuts)
            )
        elif cuts and not keeps:
            warnings.append(
                "group '%s' has no kept track (%d cut, %d undecided)"
                % (name, cuts, len(members) - cuts)
            )

    return (errors, warnings)


def _group_map(tracks: Sequence[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for track in tracks:
        name = track.get("group")
        if isinstance(name, str) and name.strip():
            groups.setdefault(name.strip(), []).append(track)
    return groups


def validate_text(
    slug: Optional[str], errors: Sequence[str], warnings: Sequence[str]
) -> str:
    """Plain-text validation report for one song."""
    head = "%s: %d error%s, %d warning%s" % (
        slug if slug else "manifest",
        len(errors),
        "" if len(errors) == 1 else "s",
        len(warnings),
        "" if len(warnings) == 1 else "s",
    )
    if not errors and not warnings:
        return head + "  OK"
    lines = [head]
    for message in errors:
        lines.append("  ERROR  %s" % message)
    for message in warnings:
        lines.append("  WARN   %s" % message)
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Status (FR-8, FR-12, FR-26)
# --------------------------------------------------------------------------

_NEXT_STEPS = {
    "copy_made": (
        "Quit Logic, duplicate the project into MixPrep/, lock the original, then "
        "`mixprep check {slug} copy_made`."
    ),
    "tracks_inventoried": (
        "Inventory the tracks: `pbpaste | mixprep add {slug} --bulk`, then "
        "`mixprep check {slug} tracks_inventoried`."
    ),
    "renamed_in_daw": (
        "Name the tracks (`mixprep suggest {slug}` then `mixprep renumber {slug}`), "
        "work through `mixprep sheet {slug}` in the copy, then "
        "`mixprep check {slug} renamed_in_daw`."
    ),
    "exported_dry": (
        "Export the DRY pass (Bypass Effect Plug-ins CHECKED) into Exports/<song>/DRY/, "
        "record each `exports.dry.status`, then `mixprep check {slug} exported_dry`."
    ),
    "exported_wet": (
        "Export the WET pass (Bypass Effect Plug-ins UNCHECKED) into Exports/<song>/WET/, "
        "record each `exports.wet.status`, then `mixprep check {slug} exported_wet`."
    ),
    "imported_to_mix": (
        "Import the stems into the mix project, then `mixprep check {slug} imported_to_mix`."
    ),
    "mixing_started": (
        "Start mixing and record keep/cut decisions with `mixprep set {slug} <track> "
        "decision=keep`, then `mixprep check {slug} mixing_started`."
    ),
}


def realtime_banner(realtime: Dict[str, Any]) -> str:
    """The SPEC section 10 'Export mode' banner phrasing."""
    dry = bool(realtime.get("dry"))
    wet = bool(realtime.get("wet"))
    if dry and wet:
        return "DRY + WET: REAL TIME"
    if wet:
        return "DRY: offline OK / WET: REAL TIME"
    if dry:
        return "DRY: REAL TIME / WET: offline OK"
    return "DRY + WET: offline OK"


def _realtime_reason_text(reason: Dict[str, Any]) -> str:
    passes = "+".join(reason.get("passes") or []) or "-"
    if reason.get("scope") == "song":
        return "song %s: %s -> %s pass real time" % (
            reason.get("name"),
            reason.get("detail"),
            passes.upper(),
        )
    return "track %s %s: hardware %s -> %s pass real time" % (
        reason.get("id"),
        reason.get("name") or "",
        reason.get("hardware"),
        passes.upper(),
    )


def export_rollup(tracks: Sequence[Dict[str, Any]], direction: str) -> Dict[str, Any]:
    """Export progress for one direction over **non-cut** tracks; 'n/a' counts
    as satisfied (FR-8)."""
    active = [t for t in tracks if t.get("decision") != "cut"]
    done = 0
    na = 0
    pending = 0
    for track in active:
        status = model.get_path(track, "exports.%s.status" % direction)
        if status == "done":
            done += 1
        elif status == "n/a":
            na += 1
        else:
            pending += 1
    satisfied = done + na
    return {
        "total": len(active),
        "done": done,
        "na": na,
        "pending": pending,
        "satisfied": satisfied,
        "pct": _pct(satisfied, len(active)),
    }


def current_phase(manifest: Any) -> Optional[str]:
    """The last consecutively-true workflow flag, or None."""
    flags = _workflow(manifest)
    phase = None
    for flag in model.WORKFLOW_PHASES:
        if not flags[flag]:
            break
        phase = flag
    return phase


def next_flag(manifest: Any) -> Optional[str]:
    flags = _workflow(manifest)
    for flag in model.WORKFLOW_PHASES:
        if not flags[flag]:
            return flag
    return None


def _notes_data(container: Any) -> List[Dict[str, Any]]:
    notes = container.get("notes") if isinstance(container, dict) else None
    if not isinstance(notes, list):
        return []
    out = []
    for index, note in enumerate(notes, start=1):
        if isinstance(note, dict):
            out.append(
                {
                    "index": index,
                    "ts": note.get("ts"),
                    "text": note.get("text"),
                    "edited": note.get("edited"),
                }
            )
        else:
            out.append({"index": index, "ts": None, "text": str(note), "edited": None})
    return out


def status_data(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Everything `status` reports, as JSON-serialisable data (FR-12)."""
    song = _song(manifest)
    tracks = _tracks(manifest)
    flags = _workflow(manifest)

    decisions = dict((value, 0) for value in model.DECISIONS)
    decisions["other"] = 0
    categories: Dict[str, int] = {}
    uncategorised = 0
    for track in tracks:
        decision = track.get("decision")
        if decision in decisions:
            decisions[decision] += 1
        else:
            decisions["other"] += 1
        category = track.get("category")
        if category in model.CATEGORY_INDEX:
            categories[category] = categories.get(category, 0) + 1
        else:
            uncategorised += 1

    realtime = model.derive_realtime(manifest)
    realtime_out = dict(realtime)
    realtime_out["banner"] = realtime_banner(realtime)

    groups = []
    for name, members in sorted(_group_map(tracks).items()):
        member_decisions = [m.get("decision") for m in members]
        keeps = member_decisions.count("keep")
        cuts = member_decisions.count("cut")
        groups.append(
            {
                "group": name,
                "tracks": len(members),
                "keep": keeps,
                "cut": cuts,
                "undecided": len(members) - keeps - cuts,
                "split": bool(keeps and cuts),
                "no_keep": bool(cuts and not keeps),
                "ids": [m.get("id") for m in members],
            }
        )

    decided = decisions["keep"] + decisions["cut"]
    nxt = next_flag(manifest)
    return {
        "schema_version": manifest.get("schema_version", model.SCHEMA_VERSION),
        "slug": song.get("slug"),
        "title": song.get("title"),
        "mix_daw": song.get("mix_daw"),
        "sample_rate": song.get("sample_rate"),
        "tempo": song.get("tempo"),
        "source_project": song.get("source_project"),
        "mixprep_copy": song.get("mixprep_copy"),
        "workflow": flags,
        "phase": current_phase(manifest),
        "next_flag": nxt,
        "next_step": (
            _NEXT_STEPS[nxt].format(slug=song.get("slug") or "<slug>")
            if nxt
            else "All workflow phases are complete."
        ),
        "tracks": {
            "total": len(tracks),
            "active": len([t for t in tracks if t.get("decision") != "cut"]),
            "cut": decisions["cut"],
        },
        "decisions": decisions,
        "decided_pct": _pct(decided, len(tracks)),
        "categories": categories,
        "uncategorised": uncategorised,
        "exports": dict(
            (direction, export_rollup(tracks, direction))
            for direction in model.EXPORT_DIRECTIONS
        ),
        "realtime": realtime_out,
        "groups": groups,
        "notes": _notes_data(manifest),
    }


def status_text(manifest: Dict[str, Any]) -> str:
    """The human-readable `status` report, including the real-time banner."""
    data = status_data(manifest)
    lines: List[str] = []

    title = data.get("title") or data.get("slug") or "(untitled)"
    lines.append("%s  [%s]" % (title, data.get("slug")))
    lines.append(
        "DAW: %s   %s Hz   %s BPM   schema v%s"
        % (
            data.get("mix_daw"),
            data.get("sample_rate"),
            data.get("tempo"),
            data.get("schema_version"),
        )
    )
    counts = data["tracks"]
    lines.append(
        "Tracks: %d total, %d non-cut, %d cut"
        % (counts["total"], counts["active"], counts["cut"])
    )

    lines.append("")
    lines.append("Workflow")
    for flag in model.WORKFLOW_PHASES:
        mark = "x" if data["workflow"][flag] else " "
        lines.append("  [%s] %s" % (mark, flag))

    realtime = data["realtime"]
    lines.append("")
    lines.append("Export mode: %s" % realtime["banner"])
    lines.append("  (export.realtime = %s)" % realtime.get("mode"))
    if realtime.get("reasons"):
        for reason in realtime["reasons"]:
            lines.append("  - %s" % _realtime_reason_text(reason))
    else:
        lines.append("  - no hardware in the signal path; both passes can bounce offline")
    if realtime.get("dry_na_recommended"):
        lines.append(
            "  - recommend exports.dry.status=n/a for external-instrument track(s): %s"
            % ", ".join(str(i) for i in realtime["dry_na_recommended"])
        )

    lines.append("")
    lines.append("Exports (non-cut tracks; 'n/a' counts as satisfied)")
    rows = []
    for direction in model.EXPORT_DIRECTIONS:
        roll = data["exports"][direction]
        rows.append(
            [
                direction.upper(),
                "%d/%d" % (roll["satisfied"], roll["total"]),
                _pct_text(roll["pct"]),
                roll["done"],
                roll["na"],
                roll["pending"],
            ]
        )
    lines.append(
        _indent(
            render_table(
                ["PASS", "SATISFIED", "PCT", "DONE", "N/A", "PENDING"],
                rows,
                ["l", "r", "r", "r", "r", "r"],
            ),
            2,
        )
    )

    decisions = data["decisions"]
    lines.append("")
    lines.append(
        "Decisions: keep %d, cut %d, undecided %d  (%s decided)"
        % (
            decisions["keep"],
            decisions["cut"],
            decisions["undecided"],
            _pct_text(data["decided_pct"]),
        )
    )

    if data["categories"] or data["uncategorised"]:
        parts = [
            "%s %d" % (code, data["categories"][code])
            for code in model.CATEGORIES
            if code in data["categories"]
        ]
        if data["uncategorised"]:
            parts.append("(none) %d" % data["uncategorised"])
        lines.append("Categories: " + ", ".join(parts))

    lines.append("")
    if data["groups"]:
        lines.append("Groups")
        rows = []
        for group in data["groups"]:
            note = ""
            if group["split"]:
                note = "split keep/cut"
            elif group["no_keep"]:
                note = "nothing kept"
            rows.append(
                [
                    group["group"],
                    group["tracks"],
                    group["keep"],
                    group["cut"],
                    group["undecided"],
                    note,
                ]
            )
        lines.append(
            _indent(
                render_table(
                    ["GROUP", "TRACKS", "KEEP", "CUT", "UNDEC", "NOTE"],
                    rows,
                    ["l", "r", "r", "r", "r", "l"],
                ),
                2,
            )
        )
    else:
        lines.append("Groups: none")

    notes = data["notes"]
    lines.append("")
    if notes:
        lines.append("Song notes (%d)" % len(notes))
        for note in notes[-5:]:
            lines.append(
                "  %2s. %s  %s%s"
                % (
                    note["index"],
                    note.get("ts") or "",
                    note.get("text") or "",
                    " (edited %s)" % note["edited"] if note.get("edited") else "",
                )
            )
        if len(notes) > 5:
            lines.append("  ... %d earlier note(s)" % (len(notes) - 5))
    else:
        lines.append("Song notes: none")

    lines.append("")
    lines.append("Next: %s" % data["next_step"])
    return "\n".join(lines)


def _indent(text: str, spaces: int) -> str:
    pad = " " * spaces
    return "\n".join((pad + line) if line else line for line in text.split("\n"))


# --------------------------------------------------------------------------
# Rename sheet (FR-13)
# --------------------------------------------------------------------------


def sheet_data(manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The `original -> new` rename sheet rows, in numbering order."""
    tracks = _tracks(manifest)
    ordered = sorted(tracks, key=_numbering_key)
    return [
        {
            "id": track.get("id"),
            "original_name": track.get("original_name"),
            "new_name": track.get("new_name"),
            "category": track.get("category"),
            "decision": track.get("decision"),
        }
        for track in ordered
    ]


def _numbering_key(track: Dict[str, Any]) -> Any:
    category = track.get("category")
    index = model.CATEGORY_INDEX.get(category, len(model.CATEGORIES))
    try:
        track_id = int(track.get("id"))
    except (TypeError, ValueError):
        track_id = 0
    return (index, track_id)


def sheet_text(manifest: Dict[str, Any]) -> str:
    song = _song(manifest)
    rows_data = sheet_data(manifest)
    lines = [
        "Rename sheet -- %s [%s]"
        % (song.get("title") or song.get("slug") or "(untitled)", song.get("slug")),
        "Rename these tracks in the mixprep COPY only -- never the original project.",
        "",
    ]
    rows = []
    for row in rows_data:
        rows.append(
            [
                row["id"],
                row["original_name"] or "",
                "->",
                row["new_name"] or "(no name yet)",
                row["category"] or "-",
                row["decision"] or "-",
            ]
        )
    if not rows:
        lines.append("(no tracks yet -- run `mixprep add <slug> --bulk`)")
        return "\n".join(lines)
    lines.append(
        render_table(
            ["ID", "ORIGINAL", "", "NEW NAME", "CAT", "DECISION"],
            rows,
            ["r", "l", "l", "l", "l", "l"],
        )
    )
    missing = len([r for r in rows_data if not r["new_name"]])
    lines.append("")
    lines.append(
        "%d track(s); %d still without a new_name." % (len(rows_data), missing)
    )
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Track listing (FR-3)
# --------------------------------------------------------------------------


def tracks_data(
    manifest: Dict[str, Any],
    category: Optional[str] = None,
    decision: Optional[str] = None,
    group: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Track rows, filtered and in numbering order."""
    out = []
    for track in sorted(_tracks(manifest), key=_numbering_key):
        if category is not None and (track.get("category") or "") != category:
            continue
        if decision is not None and (track.get("decision") or "") != decision:
            continue
        if group is not None and (track.get("group") or "") != group:
            continue
        chain = track.get("effects_chain")
        notes = track.get("notes")
        out.append(
            {
                "id": track.get("id"),
                "original_name": track.get("original_name"),
                "new_name": track.get("new_name"),
                "category": track.get("category"),
                "track_kind": track.get("track_kind"),
                "group": track.get("group"),
                "decision": track.get("decision"),
                "hardware": {
                    "type": model.get_path(track, "hardware.type"),
                    "io": model.get_path(track, "hardware.io"),
                },
                "exports": {
                    direction: {
                        "status": model.get_path(
                            track, "exports.%s.status" % direction
                        ),
                        "path": model.get_path(track, "exports.%s.path" % direction),
                    }
                    for direction in model.EXPORT_DIRECTIONS
                },
                "channel_strip_ref": track.get("channel_strip_ref"),
                "effects": len(chain) if isinstance(chain, list) else 0,
                "notes": len(notes) if isinstance(notes, list) else 0,
            }
        )
    return out


def tracks_text(manifest: Dict[str, Any], **filters: Any) -> str:
    rows_data = tracks_data(
        manifest,
        category=filters.get("category"),
        decision=filters.get("decision"),
        group=filters.get("group"),
    )
    active = [
        "%s=%s" % (key, filters[key])
        for key in ("category", "decision", "group")
        if filters.get(key) is not None
    ]
    head = "%d track(s)" % len(rows_data)
    if active:
        head += "  [filter: %s]" % ", ".join(active)
    if not rows_data:
        return head + "\n(nothing matched)"
    rows = []
    for row in rows_data:
        rows.append(
            [
                row["id"],
                row["new_name"] or "-",
                row["original_name"] or "",
                row["category"] or "-",
                row["track_kind"] or "-",
                row["group"] or "-",
                row["decision"] or "-",
                row["exports"]["dry"]["status"] or "-",
                row["exports"]["wet"]["status"] or "-",
                (row["hardware"]["type"] or "none"),
                row["effects"],
            ]
        )
    return "\n".join(
        [
            head,
            "",
            render_table(
                [
                    "ID",
                    "NEW NAME",
                    "ORIGINAL",
                    "CAT",
                    "KIND",
                    "GROUP",
                    "DECISION",
                    "DRY",
                    "WET",
                    "HW",
                    "FX",
                ],
                rows,
                ["r", "l", "l", "l", "l", "l", "l", "l", "l", "l", "r"],
            ),
        ]
    )


# --------------------------------------------------------------------------
# Song listing (FR-14)
# --------------------------------------------------------------------------


def list_data(manifests: Sequence[Any]) -> List[Dict[str, Any]]:
    """`manifests` is a sequence of ``(slug, manifest)`` pairs."""
    out = []
    for slug, manifest in manifests or []:
        song = _song(manifest)
        tracks = _tracks(manifest)
        dry = export_rollup(tracks, "dry")
        wet = export_rollup(tracks, "wet")
        total_slots = dry["total"] + wet["total"]
        satisfied = dry["satisfied"] + wet["satisfied"]
        decided = len(
            [t for t in tracks if t.get("decision") in ("keep", "cut")]
        )
        out.append(
            {
                "slug": slug,
                "title": song.get("title"),
                "mix_daw": song.get("mix_daw"),
                "phase": current_phase(manifest),
                "next_flag": next_flag(manifest),
                "tracks": len(tracks),
                "pct_exported": _pct(satisfied, total_slots),
                "pct_decided": _pct(decided, len(tracks)),
                "schema_version": manifest.get("schema_version")
                if isinstance(manifest, dict)
                else None,
            }
        )
    return out


def list_text(manifests: Sequence[Any]) -> str:
    rows_data = list_data(manifests)
    if not rows_data:
        return "No songs yet. Create one with `mixprep new <slug>`."
    rows = []
    for row in rows_data:
        rows.append(
            [
                row["slug"],
                row["title"] or "",
                row["mix_daw"] or "-",
                row["phase"] or "(not started)",
                row["tracks"],
                _pct_text(row["pct_exported"]),
                _pct_text(row["pct_decided"]),
            ]
        )
    return "\n".join(
        [
            render_table(
                ["SLUG", "TITLE", "DAW", "PHASE", "TRACKS", "EXPORTED", "DECIDED"],
                rows,
                ["l", "l", "l", "l", "r", "r", "r"],
            ),
            "",
            "%d song(s)." % len(rows_data),
        ]
    )

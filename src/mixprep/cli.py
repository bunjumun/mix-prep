"""The ``mixprep`` command-line interface (SPEC section 9).

This is the only module that touches click or does console I/O.

Two contracts shape everything here (SPEC section 3): the musician gets
readable plain text, and an LLM agent gets the *same* commands with
``--format json``, ``--auto``/``--yes`` and ``--dry-run``.  There is no
private API for either one.

Output discipline (FR-21): machine-readable data goes to **stdout**;
warnings and human chatter go to **stderr**.  In ``--format json`` mode
stdout is a single JSON document and nothing else.

Exit codes (FR-22): ``0`` on success *including advisory warnings*;
non-zero only for structural errors (a raised :class:`MixprepError`) or
``validate`` finding ERROR-severity problems.
"""

import json
import sys
from typing import Any, Dict, List, Optional, Sequence, Tuple

import click

from . import model, naming, report, store
from .model import MixprepError

_FORMATS = click.Choice(["text", "json"])


# --------------------------------------------------------------------------
# Shared plumbing
# --------------------------------------------------------------------------


class _MixprepGroup(click.Group):
    """Turns a raised MixprepError into a clean stderr message + exit code."""

    def invoke(self, ctx: click.Context) -> Any:
        try:
            return super(_MixprepGroup, self).invoke(ctx)
        except MixprepError as exc:
            click.echo("error: %s" % exc, err=True)
            ctx.exit(getattr(exc, "exit_code", 1))


def _warn(message: str, bucket: Optional[List[str]] = None) -> None:
    """Advisory problem: always to stderr, never fatal (FR-19/C-4)."""
    if bucket is not None:
        bucket.append(message)
    click.echo("warning: %s" % message, err=True)


def _root() -> Any:
    return store.find_root()


def _load(slug: str) -> Tuple[Any, Dict[str, Any]]:
    root = _root()
    return root, store.load(root, slug)


def _emit_json(data: Any, warnings: Sequence[str], ok: bool = True) -> None:
    """Write the {ok, warnings, data} envelope as the sole contents of stdout."""
    click.echo(json.dumps({"ok": ok, "warnings": list(warnings), "data": data}, indent=2))


def _save(
    root: Any, slug: str, manifest: Dict[str, Any], dry_run: bool, what: str
) -> None:
    path = store.save(root, slug, manifest, dry_run=dry_run)
    if dry_run:
        click.echo("dry-run: would %s (%s left unchanged)" % (what, path), err=True)
    else:
        click.echo("%s" % what)


def _require_noninteractive(assume_yes: bool, flag: str, what: str) -> None:
    """Refuse to block on a prompt that can never be answered (FR-20)."""
    if assume_yes:
        return
    if not sys.stdin.isatty():
        raise MixprepError(
            "%s needs confirmation but stdin is not a terminal -- pass %s to run "
            "unattended" % (what, flag)
        )


def dry_run_option(func: Any) -> Any:
    return click.option(
        "--dry-run",
        is_flag=True,
        help="Compute and report the change without writing anything.",
    )(func)


def format_option(func: Any) -> Any:
    return click.option(
        "--format",
        "fmt",
        type=_FORMATS,
        default="text",
        show_default=True,
        help="Output format. 'json' emits the {ok, warnings, data} envelope on stdout.",
    )(func)


def _check_source_copy(manifest: Dict[str, Any], bucket: Optional[List[str]] = None) -> None:
    """FR-28 / C-9: the copy must never be the source, or live inside it."""
    song = manifest.get("song") or {}
    problem = report.source_copy_conflict(
        song.get("source_project"), song.get("mixprep_copy")
    )
    if problem:
        _warn(problem, bucket)


@click.group(cls=_MixprepGroup, context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(package_name="mixprep", prog_name="mixprep")
def cli() -> None:
    """Track and organize the migration of tracking projects into mix sessions.

    mix-prep records state, not audio. It never opens, writes to, or moves a
    DAW project, an audio file, or any referenced asset -- those paths are
    inert text. It writes only its own manifests under songs/<slug>/.
    """


# --------------------------------------------------------------------------
# Inventory
# --------------------------------------------------------------------------


@cli.command()
@click.argument("slug")
@click.option("--title", default=None, help="Human-readable song title.")
@click.option("--source", default="", help="Path to the ORIGINAL project. Never touched.")
@click.option("--copy", "copy_path", default="", help="Path to the mixprep copy.")
@click.option("--daw", type=click.Choice(list(model.MIX_DAWS)), default="logic",
              show_default=True, help="Target mixing DAW.")
@click.option("--sample-rate", type=int, default=48000, show_default=True)
@click.option("--tempo", type=float, default=120.0, show_default=True)
@click.option("--force", is_flag=True, help="Overwrite an existing manifest.")
@dry_run_option
def new(slug, title, source, copy_path, daw, sample_rate, tempo, force, dry_run):
    """Create songs/<slug>/song.yaml for a new song (FR-1)."""
    root = _root()
    store.validate_slug(slug)
    if store.exists(root, slug) and not force:
        raise MixprepError(
            "song '%s' already exists (%s) -- pass --force to overwrite"
            % (slug, store.manifest_path(root, slug))
        )
    tempo_value = int(tempo) if float(tempo).is_integer() else tempo
    manifest = model.new_manifest(
        slug,
        title=title,
        source_project=source,
        mixprep_copy=copy_path,
        mix_daw=daw,
        sample_rate=sample_rate,
        tempo=tempo_value,
    )
    _check_source_copy(manifest)
    _save(root, slug, manifest, dry_run,
          "created %s" % store.manifest_path(root, slug))


@cli.command()
@click.argument("slug")
@click.option("--bulk", is_flag=True,
              help="Read one track name per line from stdin (e.g. pbpaste | mixprep add ...).")
@click.option("--name", "names", multiple=True, help="Add a single track. Repeatable.")
@click.option("--category", type=click.Choice(list(model.CATEGORIES)), default=None,
              help="Category to apply to every track added in this call.")
@dry_run_option
def add(slug, bulk, names, category, dry_run):
    """Add tracks to a song, each with a stable, never-reused id (FR-2/FR-3)."""
    root, manifest = _load(slug)

    incoming: List[str] = []
    if bulk:
        if sys.stdin.isatty():
            raise MixprepError(
                "--bulk reads a track list from stdin, but stdin is a terminal "
                "(try: pbpaste | mixprep add %s --bulk)" % slug
            )
        # read() on an empty or closed stdin returns immediately -- never blocks.
        for line in sys.stdin.read().splitlines():
            line = line.strip()
            if line:
                incoming.append(line)
    incoming.extend(n.strip() for n in names if n.strip())

    if not incoming:
        raise MixprepError("no track names given (use --bulk with piped input, or --name)")

    manifest.setdefault("tracks", [])
    added = []
    for original in incoming:
        track_id = model.next_track_id(manifest)
        track = model.new_track(track_id, original, category=category)
        manifest["tracks"].append(track)
        added.append((track_id, original))

    for track_id, original in added:
        click.echo("  %3d  %s" % (track_id, original), err=True)
    _save(root, slug, manifest, dry_run,
          "added %d track(s) to '%s'" % (len(added), slug))


# --------------------------------------------------------------------------
# Naming
# --------------------------------------------------------------------------


def _provisional_numbering(tracks: Sequence[Dict[str, Any]]) -> Dict[int, int]:
    """Map track id -> NN, in (category order, id) order -- same rule as renumber."""
    ordered = sorted(
        tracks,
        key=lambda t: (
            model.CATEGORY_INDEX.get(t.get("category"), len(model.CATEGORIES)),
            t.get("id") or 0,
        ),
    )
    return {t.get("id"): i for i, t in enumerate(ordered, start=1)}


@cli.command()
@click.argument("slug")
@click.option("--auto", "--yes", "auto", is_flag=True,
              help="Accept every suggestion without prompting (unattended).")
@click.option("--only-unnamed", is_flag=True,
              help="Only propose names for tracks that have no new_name yet.")
@dry_run_option
def suggest(slug, auto, only_unnamed, dry_run):
    """Propose convention-compliant names and categories (FR-4).

    Categories come from a deterministic keyword table; descriptors are
    CamelCased from the original name. Variant segments (_L, _Double) are
    never inferred -- add those with `mixprep set`.
    """
    root, manifest = _load(slug)
    tracks = manifest.get("tracks") or []
    if not tracks:
        raise MixprepError("song '%s' has no tracks yet (see: mixprep add)" % slug)

    targets = [t for t in tracks if not (only_unnamed and t.get("new_name"))]
    if not targets:
        click.echo("nothing to suggest (every track already has a new_name)", err=True)
        return

    _require_noninteractive(auto, "--auto", "suggest")

    # Fill in missing categories first so the numbering below is meaningful.
    for track in targets:
        if not track.get("category"):
            track["category"] = naming.suggest_category(track.get("original_name") or "")
    numbering = _provisional_numbering(tracks)

    changed = 0
    for track in targets:
        original = track.get("original_name") or ""
        proposed = naming.suggest_name(
            original, track["category"], numbering.get(track.get("id"), 1)
        )
        if track.get("new_name") == proposed:
            continue
        if auto:
            track["new_name"] = proposed
            changed += 1
            click.echo("  %-34s -> %s" % (original[:34], proposed), err=True)
            continue

        click.echo("  %s" % original, err=True)
        answer = click.prompt(
            "    name [enter=accept, s=skip]", default=proposed, show_default=True
        ).strip()
        if answer.lower() == "s":
            continue
        if not naming.is_valid_name(answer):
            _warn("'%s' does not match the naming convention -- saved anyway" % answer)
        track["new_name"] = answer
        changed += 1

    if not changed:
        click.echo("no changes", err=True)
        return
    _save(root, slug, manifest, dry_run, "named %d track(s) in '%s'" % (changed, slug))


@cli.command()
@click.argument("slug")
@dry_run_option
def renumber(slug, dry_run):
    """Recompute every NN so alphabetical DAW sort equals mix order (FR-5)."""
    root, manifest = _load(slug)
    tracks = manifest.get("tracks") or []
    if not tracks:
        raise MixprepError("song '%s' has no tracks yet" % slug)

    if (manifest.get("workflow") or {}).get("renamed_in_daw"):
        _warn(
            "renamed_in_daw is already checked -- renumbering now will desync the "
            "manifest from the names already typed into the DAW"
        )

    by_id = {t.get("id"): t for t in tracks}
    changed = 0
    for entry in naming.renumber_plan(tracks):
        track = by_id.get(entry["id"])
        if track is None:
            continue
        if entry.get("skipped"):
            _warn("track %s skipped: %s" % (entry["id"], entry.get("reason")))
            continue
        if entry.get("reason") == "overflow":
            _warn(
                "track %s numbered %s -- more than 99 tracks breaks two-digit sorting"
                % (entry["id"], entry.get("nn"))
            )
        if entry.get("new") and entry["new"] != entry.get("old"):
            track["new_name"] = entry["new"]
            changed += 1
            click.echo("  %-28s -> %s" % (entry.get("old"), entry["new"]), err=True)

    if not changed:
        click.echo("numbering already correct", err=True)
        return
    _save(root, slug, manifest, dry_run, "renumbered %d track(s) in '%s'" % (changed, slug))


# --------------------------------------------------------------------------
# Editing
# --------------------------------------------------------------------------


_SONG_SCOPE = "song"


@cli.command("set")
@click.argument("slug")
@click.argument("target")
@click.argument("assignments", nargs=-1, required=True)
@dry_run_option
def set_cmd(slug, target, assignments, dry_run):
    """Set fields on a track, or on the song itself (FR-16).

    TARGET is a track id, an exact new_name, or an exact original_name --
    or the literal word `song` to edit song-level fields. If a real track is
    somehow named "song", the song scope wins; address it by id instead.

    \b
    mixprep set ocean-floor 21 decision=keep exports.wet.status=done
    mixprep set ocean-floor song export.realtime=force
    """
    root, manifest = _load(slug)

    song_scope = target == _SONG_SCOPE
    if song_scope:
        container: Dict[str, Any] = manifest
        allowed = model.MANIFEST_FIELD_TYPES
        scope_label = "song '%s'" % slug
    else:
        container = model.get_track(manifest, target)
        allowed = model.TRACK_FIELD_TYPES
        scope_label = "track %s" % container.get("id")

    touched_paths = []
    for assignment in assignments:
        if "=" not in assignment:
            raise MixprepError("expected key=value, got '%s'" % assignment)
        path, raw = assignment.split("=", 1)
        path = path.strip()

        if path == "id":
            raise MixprepError(
                "track ids are permanent and never reused -- they cannot be set"
            )
        if path.startswith("effects_chain"):
            raise MixprepError(
                "edit the effects chain with `mixprep fx`, not `set`"
            )
        if path not in allowed:
            scope_hint = "song-level" if song_scope else "track-level"
            raise MixprepError(
                "'%s' is not a settable %s field (known: %s)"
                % (path, scope_hint, ", ".join(sorted(allowed)))
            )

        value = model.coerce(path, raw)
        model.set_path(container, path, value)
        touched_paths.append(path)
        click.echo("  %s = %r" % (path, value), err=True)

    if song_scope and any(
        p in ("song.source_project", "song.mixprep_copy") for p in touched_paths
    ):
        _check_source_copy(manifest)
    if not song_scope:
        new_name = container.get("new_name")
        if new_name and not naming.is_valid_name(new_name):
            _warn(
                "'%s' does not match the naming convention (see: mixprep validate %s)"
                % (new_name, slug)
            )

    _save(root, slug, manifest, dry_run,
          "updated %d field(s) on %s" % (len(touched_paths), scope_label))


@cli.command()
@click.argument("slug")
@click.option("--track", "track_ref", default=None,
              help="Attach the note to a track instead of the song.")
@click.option("--text", default=None, help="Note body.")
@click.option("--edit", "edit_index", type=int, default=None,
              help="Edit note N (1-based) instead of appending. Keeps the original ts.")
@dry_run_option
def note(slug, track_ref, text, edit_index, dry_run):
    """Append or edit a timestamped note on a song or a track (FR-10)."""
    root, manifest = _load(slug)

    if track_ref is None:
        container: Dict[str, Any] = manifest
        where = "song '%s'" % slug
    else:
        container = model.get_track(manifest, track_ref)
        where = "track %s" % container.get("id")

    if text is None:
        if not sys.stdin.isatty():
            raise MixprepError("--text is required when stdin is not a terminal")
        text = click.prompt("note")
    text = text.strip()
    if not text:
        raise MixprepError("refusing to store an empty note")

    notes = container.setdefault("notes", [])
    if not isinstance(notes, list):
        raise MixprepError("notes on %s is not a list" % where)

    if edit_index is not None:
        if edit_index < 1 or edit_index > len(notes):
            raise MixprepError(
                "no note %d on %s (it has %d)" % (edit_index, where, len(notes))
            )
        entry = notes[edit_index - 1]
        if not isinstance(entry, dict):
            raise MixprepError("note %d on %s is malformed" % (edit_index, where))
        entry["text"] = text
        entry["edited"] = model.now_ts()  # original ts is deliberately preserved
        action = "edited note %d on %s" % (edit_index, where)
    else:
        notes.append({"ts": model.now_ts(), "text": text})
        action = "added note %d to %s" % (len(notes), where)

    _save(root, slug, manifest, dry_run, action)


@cli.command()
@click.argument("slug")
@click.argument("track_ref")
@click.option("--add", "plugin", default=None, help="Append a plugin to the chain.")
@click.option("--maker", default=None, help="Vendor (matters when rebuilding in Ableton).")
@click.option("--preset", default=None, help="Preset name.")
@click.option("--bypassed", is_flag=True, help="Mark the added plugin bypassed.")
@click.option("--settings", default=None, help="Free-text note of the values that matter.")
@click.option("--param", "params", multiple=True, metavar="NAME=VALUE",
              help="Structured parameter value. Repeatable.")
@click.option("--ref", default=None,
              help="Pointer to a saved preset/screenshot. Stored as text; never read.")
@click.option("--strip-ref", default=None,
              help="Pointer to a Logic .cst channel-strip setting for the whole chain.")
@click.option("--bypass", "bypass_index", type=int, default=None,
              help="Mark chain entry N (1-based) bypassed.")
@click.option("--clear", is_flag=True, help="Remove every entry from the chain.")
@dry_run_option
def fx(slug, track_ref, plugin, maker, preset, bypassed, settings, params, ref,
       strip_ref, bypass_index, clear, dry_run):
    """Record a track's effects chain for recall in the mix session (FR-11).

    Every path stored here (--ref, --strip-ref) is a pointer only: mix-prep
    never opens, copies, or validates the file it points at (C-3/C-7).
    """
    root, manifest = _load(slug)
    track = model.get_track(manifest, track_ref)
    chain = track.setdefault("effects_chain", [])
    if not isinstance(chain, list):
        raise MixprepError("effects_chain on track %s is not a list" % track.get("id"))

    actions = []

    if clear:
        removed = len(chain)
        del chain[:]
        actions.append("cleared %d entry(ies)" % removed)

    if strip_ref is not None:
        track["channel_strip_ref"] = model.coerce("channel_strip_ref", strip_ref)
        actions.append("set channel_strip_ref")

    if bypass_index is not None:
        if bypass_index < 1 or bypass_index > len(chain):
            raise MixprepError(
                "no chain entry %d on track %s (it has %d)"
                % (bypass_index, track.get("id"), len(chain))
            )
        chain[bypass_index - 1]["bypassed"] = True
        actions.append("bypassed entry %d" % bypass_index)

    if plugin:
        entry: Dict[str, Any] = {"plugin": plugin}
        if maker:
            entry["maker"] = maker
        if preset:
            entry["preset"] = preset
        if bypassed:
            entry["bypassed"] = True
        if settings:
            entry["settings"] = settings
        if params:
            collected: Dict[str, str] = {}
            for pair in params:
                if "=" not in pair:
                    raise MixprepError("expected --param NAME=VALUE, got '%s'" % pair)
                key, value = pair.split("=", 1)
                key = key.strip()
                if not key:
                    raise MixprepError("--param needs a name before '='")
                collected[key] = value.strip()
            entry["params"] = collected
        if ref:
            entry["ref"] = ref
        chain.append(entry)
        actions.append("added '%s' as entry %d" % (plugin, len(chain)))
    elif ref is not None and not plugin:
        raise MixprepError("--ref applies to a plugin; pass it alongside --add")

    if not actions:
        raise MixprepError(
            "nothing to do (use --add, --bypass, --clear or --strip-ref)"
        )

    _save(root, slug, manifest, dry_run,
          "track %s: %s" % (track.get("id"), "; ".join(actions)))


# --------------------------------------------------------------------------
# Workflow
# --------------------------------------------------------------------------


def _set_flag(slug: str, flag: str, value: bool, dry_run: bool) -> None:
    if flag not in model.WORKFLOW_PHASES:
        raise MixprepError(
            "unknown workflow flag '%s' (known: %s)"
            % (flag, ", ".join(model.WORKFLOW_PHASES))
        )
    root, manifest = _load(slug)
    manifest.setdefault("workflow", {})[flag] = value
    # Order is advisory: warn, then do it anyway (FR-19).
    for problem in report.workflow_order_problems(manifest):
        _warn(problem)
    _save(root, slug, manifest, dry_run,
          "%s %s on '%s'" % ("checked" if value else "unchecked", flag, slug))


@cli.command()
@click.argument("slug")
@click.argument("flag")
@dry_run_option
def check(slug, flag, dry_run):
    """Mark a workflow phase done (FR-15). Out-of-order warns but is allowed."""
    _set_flag(slug, flag, True, dry_run)


@cli.command()
@click.argument("slug")
@click.argument("flag")
@dry_run_option
def uncheck(slug, flag, dry_run):
    """Mark a workflow phase not done (FR-15)."""
    _set_flag(slug, flag, False, dry_run)


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


def _schema_of(manifest: Dict[str, Any]) -> Any:
    return manifest.get("schema_version", model.SCHEMA_VERSION)


@cli.command()
@click.argument("slug")
@format_option
def status(slug, fmt):
    """Workflow, export progress, decisions, and the real-time export banner (FR-12)."""
    _, manifest = _load(slug)
    if fmt == "json":
        data = {"schema_version": _schema_of(manifest), "slug": slug}
        data.update(report.status_data(manifest))
        _emit_json(data, [])
    else:
        click.echo(report.status_text(manifest))


@cli.command()
@click.argument("slug")
@format_option
def sheet(slug, fmt):
    """Print the original -> new rename sheet to work through in the DAW (FR-13)."""
    _, manifest = _load(slug)
    if fmt == "json":
        _emit_json(
            {
                "schema_version": _schema_of(manifest),
                "slug": slug,
                "tracks": report.sheet_data(manifest),
            },
            [],
        )
    else:
        click.echo(report.sheet_text(manifest))


@cli.command()
@click.argument("slug")
@click.option("--category", type=click.Choice(list(model.CATEGORIES)), default=None)
@click.option("--decision", type=click.Choice(list(model.DECISIONS)), default=None)
@click.option("--group", default=None)
@format_option
def tracks(slug, category, decision, group, fmt):
    """List a song's tracks as a table, optionally filtered (FR-3)."""
    _, manifest = _load(slug)
    if fmt == "json":
        _emit_json(
            {
                "schema_version": _schema_of(manifest),
                "slug": slug,
                "tracks": report.tracks_data(
                    manifest, category=category, decision=decision, group=group
                ),
            },
            [],
        )
    else:
        click.echo(
            report.tracks_text(
                manifest, category=category, decision=decision, group=group
            )
        )


@cli.command("list")
@format_option
def list_cmd(fmt):
    """List every song in the repo with its phase and progress (FR-14)."""
    root = _root()
    pairs = []
    problems: List[str] = []
    for slug in store.list_slugs(root):
        try:
            pairs.append((slug, store.load(root, slug)))
        except MixprepError as exc:
            # One broken manifest must not hide the rest of the catalogue.
            problems.append("%s: %s" % (slug, exc))

    if fmt == "json":
        _emit_json(
            {"schema_version": model.SCHEMA_VERSION, "songs": report.list_data(pairs)},
            problems,
        )
    else:
        for problem in problems:
            _warn(problem)
        click.echo(report.list_text(pairs))


@cli.command()
@click.argument("slug", required=False)
@click.option("--all", "check_all", is_flag=True, help="Validate every song in the repo.")
@format_option
def validate(slug, check_all, fmt):
    """Validate manifests (FR-6).

    Structural errors exit non-zero; style warnings exit 0 (SPEC section 8).
    """
    root = _root()
    if check_all:
        slugs = store.list_slugs(root)
    elif slug:
        slugs = [slug]
    else:
        raise MixprepError("give a slug, or --all")
    if not slugs:
        raise MixprepError("no songs found in %s" % (store.song_dir(root, "x").parent,))

    results = []
    any_errors = False
    for one in slugs:
        try:
            manifest = store.load(root, one)
        except MixprepError as exc:
            # A manifest that will not load is itself an ERROR, not a crash.
            any_errors = True
            results.append({"slug": one, "errors": [str(exc)], "warnings": [], "ok": False})
            continue
        errors, warnings = report.validate_manifest(manifest, one)
        any_errors = any_errors or bool(errors)
        results.append(
            {"slug": one, "errors": errors, "warnings": warnings, "ok": not errors}
        )

    if fmt == "json":
        flat = ["%s: %s" % (r["slug"], w) for r in results for w in r["warnings"]]
        _emit_json(
            {"schema_version": model.SCHEMA_VERSION, "songs": results, "ok": not any_errors},
            flat,
            ok=not any_errors,
        )
    else:
        for result in results:
            click.echo(
                report.validate_text(result["slug"], result["errors"], result["warnings"])
            )

    if any_errors:
        raise MixprepError("validation failed")


@cli.command()
@click.argument("slug")
@click.option("--dir", "want_dir", is_flag=True,
              help="Print the song directory instead of the manifest file.")
@format_option
def path(slug, want_dir, fmt):
    """Print a manifest's absolute path, undecorated (FR-27).

    \b
    $EDITOR "$(mixprep path ocean-floor)"
    """
    root = _root()
    manifest_file = store.manifest_path(root, slug)
    directory = store.song_dir(root, slug)
    if not manifest_file.is_file():
        raise MixprepError("no manifest for '%s' (expected %s)" % (slug, manifest_file))
    if fmt == "json":
        _emit_json(
            {
                "schema_version": model.SCHEMA_VERSION,
                "slug": slug,
                "path": str(manifest_file),
                "dir": str(directory),
            },
            [],
        )
    else:
        click.echo(str(directory if want_dir else manifest_file))


def main() -> Any:
    return cli()


if __name__ == "__main__":  # pragma: no cover
    main()

"""End-to-end tests driving the real `mixprep` CLI as a subprocess.

Subprocess rather than click's CliRunner on purpose: the acceptance criteria
are about the *process* boundary -- stdout/stderr separation (FR-21) and exit
codes (FR-22) -- and only a real process proves those.
"""

import hashlib
import json
import os
import subprocess
import sys

import pytest
import yaml

from mixprep import model, store

SONG = "ocean-floor"


# --------------------------------------------------------------------------
# Harness
# --------------------------------------------------------------------------


@pytest.fixture()
def repo(tmp_path):
    """An isolated mixprep root. Nothing here touches the developer's songs."""
    (tmp_path / "songs").mkdir()
    return tmp_path


def run(repo, *args, **kwargs):
    """Invoke the CLI in `repo`, returning CompletedProcess with text streams."""
    env = dict(os.environ)
    env["MIXPREP_ROOT"] = str(repo)
    env["PYTHONPATH"] = os.pathsep.join(
        [os.path.join(os.path.dirname(os.path.dirname(__file__)), "src")]
        + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
    )
    return subprocess.run(
        [sys.executable, "-m", "mixprep.cli"] + [str(a) for a in args],
        env=env,
        input=kwargs.get("stdin", ""),
        capture_output=True,
        text=True,
        timeout=30,
    )


def manifest_text(repo, slug=SONG):
    return (repo / "songs" / slug / "song.yaml").read_text()


def make_song(repo, **kwargs):
    args = ["new", SONG, "--title", "Ocean Floor", "--daw", "ableton"]
    for key, value in kwargs.items():
        args += ["--" + key.replace("_", "-"), value]
    result = run(repo, *args)
    assert result.returncode == 0, result.stderr
    return result


TRACK_LIST = "\n".join(
    [
        "Kick In",
        "Snare Top",
        "Bass DI",
        "gtr-acoustic_L",
        "gtr-acoustic_R",
        "Vox Lead comp",
        "demo background vocals",
        "Audio 7",
    ]
)


# --------------------------------------------------------------------------
# A-2: the core pipeline
# --------------------------------------------------------------------------


def test_full_pipeline(repo):
    make_song(repo)
    assert run(repo, "add", SONG, "--bulk", stdin=TRACK_LIST).returncode == 0
    assert run(repo, "suggest", SONG, "--auto").returncode == 0
    assert run(repo, "renumber", SONG).returncode == 0

    validated = run(repo, "validate", SONG)
    assert validated.returncode == 0, validated.stdout + validated.stderr

    manifest = yaml.safe_load(manifest_text(repo))
    names = [t["new_name"] for t in manifest["tracks"]]
    assert all(names), "every track should have been named"
    # Alphabetical sort of the names must equal intended mix order (drums first).
    assert sorted(names)[0].endswith("_DR_KickIn")
    assert [t["id"] for t in manifest["tracks"]] == list(range(1, 9))

    for command in ("sheet", "status", "tracks"):
        result = run(repo, command, SONG)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip()
    assert run(repo, "list").returncode == 0


def test_ids_are_never_reused(repo):
    make_song(repo)
    run(repo, "add", SONG, "--bulk", stdin="One\nTwo\nThree")
    path = repo / "songs" / SONG / "song.yaml"
    manifest = yaml.safe_load(path.read_text())
    del manifest["tracks"][1]                       # remove id 2 by hand
    path.write_text(yaml.safe_dump(manifest, sort_keys=False))

    run(repo, "add", SONG, "--name", "Four")
    ids = [t["id"] for t in yaml.safe_load(path.read_text())["tracks"]]
    assert ids == [1, 3, 4], "a removed id must never be handed out again"


# --------------------------------------------------------------------------
# A-7: mix-prep never touches a DAW project, audio file, or asset
# --------------------------------------------------------------------------


def _tree_checksum(root):
    digest = hashlib.sha256()
    for dirpath, dirnames, filenames in sorted(os.walk(root)):
        dirnames.sort()
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            digest.update(os.path.relpath(full, root).encode())
            with open(full, "rb") as handle:
                digest.update(handle.read())
    return digest.hexdigest()


def test_referenced_project_is_never_modified(repo, tmp_path):
    """A-7: a checksummed sentinel 'project' must survive the whole workflow."""
    project = tmp_path / "Ocean Floor.logicx"
    (project / "Alternatives" / "000").mkdir(parents=True)
    (project / "Alternatives" / "000" / "ProjectData").write_bytes(b"\x00binary\x01")
    (project / "Alternatives" / "000" / "MetaData.plist").write_text("<plist/>")
    preset = tmp_path / "leadvox.aupreset"
    preset.write_text("preset payload")
    stem = tmp_path / "01_DR_KickIn.wav"
    stem.write_bytes(b"RIFF....WAVE")

    before = _tree_checksum(project)
    before_preset = preset.read_text()
    before_stem = stem.read_bytes()

    make_song(repo, source=str(project), copy=str(tmp_path / "copy.logicx"))
    run(repo, "add", SONG, "--bulk", stdin=TRACK_LIST)
    run(repo, "suggest", SONG, "--auto")
    run(repo, "renumber", SONG)
    run(repo, "set", SONG, "1", "exports.dry.status=done",
        "exports.dry.path=%s" % stem)
    run(repo, "set", SONG, "1", "channel_strip_ref=%s" % preset)
    run(repo, "fx", SONG, "1", "--add", "Pro-C 2", "--maker", "FabFilter",
        "--ref", str(preset), "--param", "Ratio=3:1")
    run(repo, "note", SONG, "--track", "1", "--text", "checked")
    run(repo, "check", SONG, "copy_made")
    run(repo, "status", SONG)
    run(repo, "validate", SONG)

    assert _tree_checksum(project) == before, "the source project was modified"
    assert preset.read_text() == before_preset, "a referenced asset was modified"
    assert stem.read_bytes() == before_stem, "a stem file was modified"
    # And the pointers were stored verbatim, not resolved or rewritten.
    manifest = yaml.safe_load(manifest_text(repo))
    assert manifest["song"]["source_project"] == str(project)
    assert manifest["tracks"][0]["channel_strip_ref"] == str(preset)


def test_writes_stay_inside_the_songs_directory(repo):
    make_song(repo)
    run(repo, "add", SONG, "--bulk", stdin=TRACK_LIST)
    entries = {p.name for p in repo.iterdir()}
    assert entries == {"songs"}, "mix-prep wrote outside songs/: %s" % entries


@pytest.mark.parametrize("slug", ["../escape", "a/b", "", "has space"])
def test_slug_traversal_is_refused(repo, slug):
    assert run(repo, "new", slug).returncode != 0


# --------------------------------------------------------------------------
# A-5: agent-operability
# --------------------------------------------------------------------------


JSON_COMMANDS = ["status", "sheet", "tracks", "validate", "path"]


@pytest.mark.parametrize("command", JSON_COMMANDS)
def test_json_envelope_on_stdout_only(repo, command):
    make_song(repo)
    run(repo, "add", SONG, "--bulk", stdin=TRACK_LIST)
    run(repo, "suggest", SONG, "--auto")

    result = run(repo, command, SONG, "--format", "json")
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)          # stdout must parse ALONE
    assert set(payload) == {"ok", "warnings", "data"}
    assert payload["ok"] is True
    assert isinstance(payload["warnings"], list)


def test_list_json_envelope(repo):
    make_song(repo)
    payload = json.loads(run(repo, "list", "--format", "json").stdout)
    assert payload["data"]["schema_version"] == model.SCHEMA_VERSION
    assert payload["data"]["songs"][0]["slug"] == SONG


def test_json_data_carries_schema_version(repo):
    make_song(repo)
    for command in JSON_COMMANDS:
        payload = json.loads(run(repo, command, SONG, "--format", "json").stdout)
        assert "schema_version" in payload["data"], command


def test_warnings_go_to_stderr_not_stdout(repo):
    make_song(repo, source="/Music/Song.logicx", copy="/Music/Song.logicx/inside")
    result = run(repo, "check", SONG, "exported_dry")
    assert result.returncode == 0, "a warning must never be fatal (FR-19)"
    assert "warning:" in result.stderr
    assert "warning:" not in result.stdout


def test_bulk_does_not_hang_on_empty_stdin(repo):
    make_song(repo)
    result = run(repo, "add", SONG, "--bulk", stdin="")   # timeout=30 guards a hang
    assert result.returncode != 0
    assert "no track names" in result.stderr


def test_suggest_refuses_rather_than_blocking_without_a_tty(repo):
    make_song(repo)
    run(repo, "add", SONG, "--bulk", stdin=TRACK_LIST)
    result = run(repo, "suggest", SONG)                   # no --auto, no TTY
    assert result.returncode != 0
    assert "--auto" in result.stderr


def test_path_is_bare_and_composable(repo):
    make_song(repo)
    result = run(repo, "path", SONG)
    assert result.returncode == 0
    assert result.stdout.strip() == str(store.manifest_path(repo, SONG))
    assert result.stdout.count("\n") == 1


# --------------------------------------------------------------------------
# A-5: --dry-run writes nothing
# --------------------------------------------------------------------------


def test_dry_run_never_writes(repo):
    make_song(repo)
    run(repo, "add", SONG, "--bulk", stdin=TRACK_LIST)
    run(repo, "suggest", SONG, "--auto")
    before = manifest_text(repo)

    mutations = [
        ("add", SONG, "--name", "Ghost Track"),
        ("suggest", SONG, "--auto"),
        ("renumber", SONG),
        ("set", SONG, "1", "decision=cut"),
        ("note", SONG, "--text", "should not persist"),
        ("fx", SONG, "1", "--add", "Ghost Plugin"),
        ("check", SONG, "copy_made"),
        ("uncheck", SONG, "copy_made"),
    ]
    for args in mutations:
        result = run(repo, *(list(args) + ["--dry-run"]))
        assert result.returncode == 0, "%s: %s" % (args[0], result.stderr)
        assert manifest_text(repo) == before, "%s wrote during --dry-run" % args[0]


def test_dry_run_new_creates_nothing(repo):
    assert run(repo, "new", "phantom", "--dry-run").returncode == 0
    assert not (repo / "songs" / "phantom").exists()


# --------------------------------------------------------------------------
# A-6: round-trip stability and unknown-key preservation
# --------------------------------------------------------------------------


def test_manifest_round_trips_byte_stably(repo):
    make_song(repo)
    run(repo, "add", SONG, "--bulk", stdin=TRACK_LIST)
    run(repo, "suggest", SONG, "--auto")
    first = manifest_text(repo)
    run(repo, "renumber", SONG)              # idempotent: nothing should change
    assert manifest_text(repo) == first


def test_unknown_keys_survive(repo):
    make_song(repo)
    run(repo, "add", SONG, "--name", "Kick In")
    path = repo / "songs" / SONG / "song.yaml"
    manifest = yaml.safe_load(path.read_text())
    manifest["my_own_key"] = "keep me"
    manifest["song"]["engineer"] = "Sam"
    manifest["tracks"][0]["console_channel"] = 14
    path.write_text(yaml.safe_dump(manifest, sort_keys=False))

    run(repo, "set", SONG, "1", "decision=keep")
    reloaded = yaml.safe_load(path.read_text())
    assert reloaded["my_own_key"] == "keep me"
    assert reloaded["song"]["engineer"] == "Sam"
    assert reloaded["tracks"][0]["console_channel"] == 14
    assert reloaded["tracks"][0]["decision"] == "keep"


def test_every_manifest_is_stamped(repo):
    make_song(repo)
    assert yaml.safe_load(manifest_text(repo))["schema_version"] == model.SCHEMA_VERSION


def test_refuses_a_manifest_from_the_future(repo):
    make_song(repo)
    path = repo / "songs" / SONG / "song.yaml"
    manifest = yaml.safe_load(path.read_text())
    manifest["schema_version"] = model.SCHEMA_VERSION + 5
    path.write_text(yaml.safe_dump(manifest, sort_keys=False))
    result = run(repo, "status", SONG)
    assert result.returncode != 0
    assert "schema_version" in result.stderr


# --------------------------------------------------------------------------
# A-8: validation severity and exit codes (SPEC section 8)
# --------------------------------------------------------------------------


def _write_manifest(repo, tracks, **song_overrides):
    song = {
        "title": "Broken",
        "slug": SONG,
        "source_project": "/Music/Broken.logicx",
        "mixprep_copy": "/Music/MixPrep/Broken.logicx",
        "mix_daw": "logic",
        "sample_rate": 48000,
        "tempo": 90,
    }
    song.update(song_overrides)
    manifest = {
        "schema_version": 1,
        "song": song,
        "export": {"realtime": "auto", "hardware_returns": ""},
        "workflow": {flag: False for flag in model.WORKFLOW_PHASES},
        "notes": [],
        "tracks": tracks,
    }
    directory = repo / "songs" / SONG
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "song.yaml").write_text(yaml.safe_dump(manifest, sort_keys=False))


def _track(track_id, **kwargs):
    track = {
        "id": track_id,
        "original_name": "Track %d" % track_id,
        "new_name": "%02d_DR_T%d" % (track_id, track_id),
        "category": "DR",
        "track_kind": "audio",
        "decision": "keep",
    }
    track.update(kwargs)
    return track


@pytest.mark.parametrize(
    "tracks,song",
    [
        ([_track(1), _track(1)], {}),                            # duplicate id
        ([_track(1, decision="maybe")], {}),                     # bad enum
        ([_track(1, category="DRUMS")], {}),                     # unknown category
        ([_track(1, track_kind="midi")], {}),                    # bad track_kind
        ([_track(1), _track(2, new_name="01_DR_T1")], {}),       # duplicate new_name
        ([_track(1)], {"mix_daw": "protools"}),                  # unsupported DAW
    ],
)
def test_structural_errors_exit_non_zero(repo, tracks, song):
    _write_manifest(repo, tracks, **song)
    result = run(repo, "validate", SONG)
    assert result.returncode != 0
    assert "ERROR" in result.stdout


@pytest.mark.parametrize(
    "tracks,song",
    [
        ([_track(1, new_name="kick track")], {}),                # fails the regex
        ([_track(1, new_name=None)], {}),                        # missing new_name
        ([_track(1, original_name="")], {}),                     # empty original
        ([_track(1, exports={"dry": {"status": "done", "path": None},
                             "wet": {"status": "pending", "path": None}})], {}),
        ([_track(1, group="G", decision="keep"),
          _track(2, group="G", decision="cut")], {}),            # split group
        ([_track(1)], {"mixprep_copy": "/Music/Broken.logicx"}),  # copy == source
    ],
)
def test_style_warnings_exit_zero(repo, tracks, song):
    _write_manifest(repo, tracks, **song)
    result = run(repo, "validate", SONG)
    assert result.returncode == 0, result.stdout
    assert "WARN" in result.stdout


def test_validate_all(repo):
    make_song(repo)
    result = run(repo, "validate", "--all")
    assert result.returncode == 0


def test_validate_json_reports_not_ok_on_errors(repo):
    _write_manifest(repo, [_track(1), _track(1)])
    result = run(repo, "validate", SONG, "--format", "json")
    assert result.returncode != 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["data"]["songs"][0]["errors"]


# --------------------------------------------------------------------------
# A-9: the real-time export banner (SPEC section 10)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "hardware_type,expected",
    [
        ("none", "DRY + WET: offline OK"),
        ("insert", "DRY: offline OK / WET: REAL TIME"),
        ("send", "DRY + WET: REAL TIME"),
        ("sidechain", "DRY + WET: REAL TIME"),
        ("external_instrument", "DRY + WET: REAL TIME"),
    ],
)
def test_realtime_banner(repo, hardware_type, expected):
    make_song(repo)
    run(repo, "add", SONG, "--name", "Vox Lead")
    run(repo, "set", SONG, "1", "hardware.type=%s" % hardware_type)
    assert expected in run(repo, "status", SONG).stdout


def test_cut_tracks_do_not_force_realtime(repo):
    make_song(repo)
    run(repo, "add", SONG, "--name", "Hardware Synth")
    run(repo, "set", SONG, "1", "hardware.type=external_instrument", "decision=cut")
    assert "DRY + WET: offline OK" in run(repo, "status", SONG).stdout


def test_realtime_can_be_forced_and_suppressed(repo):
    make_song(repo)
    run(repo, "add", SONG, "--name", "Vox Lead")
    run(repo, "set", SONG, "song", "export.realtime=force")
    assert "DRY + WET: REAL TIME" in run(repo, "status", SONG).stdout
    run(repo, "set", SONG, "song", "export.realtime=off")
    assert "DRY + WET: offline OK" in run(repo, "status", SONG).stdout


def test_hardware_returns_forces_a_realtime_wet_pass(repo):
    make_song(repo)
    run(repo, "add", SONG, "--name", "Vox Lead")
    run(repo, "set", SONG, "song",
        "export.hardware_returns=Bus 8 -> Distressor -> Bus 9")
    assert "WET: REAL TIME" in run(repo, "status", SONG).stdout


# --------------------------------------------------------------------------
# Editing: set / fx / note / check
# --------------------------------------------------------------------------


def test_set_supports_dotted_paths_and_song_scope(repo):
    make_song(repo)
    run(repo, "add", SONG, "--name", "Vox Lead")
    run(repo, "set", SONG, "1", "exports.wet.status=done",
        "exports.wet.path=/Exports/WET/01.wav", "hardware.type=insert",
        "source.takes=3", "group=LeadVox")
    run(repo, "set", SONG, "song", "song.tempo=92", "song.mix_daw=logic")

    manifest = yaml.safe_load(manifest_text(repo))
    track = manifest["tracks"][0]
    assert track["exports"]["wet"] == {"status": "done", "path": "/Exports/WET/01.wav"}
    assert track["hardware"]["type"] == "insert"
    assert track["source"]["takes"] == 3          # coerced to int, not "3"
    assert manifest["song"]["tempo"] == 92
    assert manifest["song"]["mix_daw"] == "logic"


def test_set_rejects_unknown_and_protected_fields(repo):
    make_song(repo)
    run(repo, "add", SONG, "--name", "Vox Lead")
    assert run(repo, "set", SONG, "1", "id=99").returncode != 0
    assert run(repo, "set", SONG, "1", "nonsense=1").returncode != 0
    assert run(repo, "set", SONG, "1", "effects_chain.bypassed=true").returncode != 0
    # Song-level paths must not be settable on a track, and vice versa.
    assert run(repo, "set", SONG, "1", "song.tempo=100").returncode != 0
    assert run(repo, "set", SONG, "song", "decision=keep").returncode != 0


def test_set_resolves_a_track_by_name(repo):
    make_song(repo)
    run(repo, "add", SONG, "--name", "Vox Lead comp")
    assert run(repo, "set", SONG, "Vox Lead comp", "decision=keep").returncode == 0
    assert run(repo, "set", SONG, "No Such Track", "decision=keep").returncode != 0


def test_fx_records_an_ordered_chain_with_pointers(repo):
    make_song(repo)
    run(repo, "add", SONG, "--name", "Vox Lead")
    run(repo, "fx", SONG, "1", "--add", "Channel EQ", "--maker", "Logic",
        "--settings", "HPF 90Hz")
    run(repo, "fx", SONG, "1", "--add", "Pro-C 2", "--maker", "FabFilter",
        "--preset", "Vocal Smooth", "--param", "Ratio=3:1",
        "--param", "Threshold=-22 dB", "--ref", "/presets/proc2.aupreset")
    run(repo, "fx", SONG, "1", "--strip-ref", "/presets/leadvox.cst")

    chain = yaml.safe_load(manifest_text(repo))["tracks"][0]
    assert [e["plugin"] for e in chain["effects_chain"]] == ["Channel EQ", "Pro-C 2"]
    assert chain["effects_chain"][1]["params"] == {"Ratio": "3:1", "Threshold": "-22 dB"}
    assert chain["effects_chain"][1]["ref"] == "/presets/proc2.aupreset"
    assert chain["channel_strip_ref"] == "/presets/leadvox.cst"

    run(repo, "fx", SONG, "1", "--bypass", "1")
    assert yaml.safe_load(manifest_text(repo))["tracks"][0]["effects_chain"][0]["bypassed"]
    run(repo, "fx", SONG, "1", "--clear")
    assert yaml.safe_load(manifest_text(repo))["tracks"][0]["effects_chain"] == []


def test_note_edit_preserves_the_original_timestamp(repo):
    make_song(repo)
    run(repo, "note", SONG, "--text", "first")
    original_ts = yaml.safe_load(manifest_text(repo))["notes"][0]["ts"]
    run(repo, "note", SONG, "--text", "revised", "--edit", "1")

    note = yaml.safe_load(manifest_text(repo))["notes"][0]
    assert note["text"] == "revised"
    assert note["ts"] == original_ts
    assert note["edited"]


def test_check_warns_out_of_order_but_still_applies(repo):
    make_song(repo)
    result = run(repo, "check", SONG, "mixing_started")
    assert result.returncode == 0
    assert "warning:" in result.stderr
    assert yaml.safe_load(manifest_text(repo))["workflow"]["mixing_started"] is True
    run(repo, "uncheck", SONG, "mixing_started")
    assert yaml.safe_load(manifest_text(repo))["workflow"]["mixing_started"] is False


def test_unknown_workflow_flag_is_rejected(repo):
    make_song(repo)
    assert run(repo, "check", SONG, "not_a_phase").returncode != 0


def test_export_rollup_ignores_cut_tracks_and_counts_na(repo):
    make_song(repo)
    run(repo, "add", SONG, "--bulk", stdin="One\nTwo\nThree")
    run(repo, "set", SONG, "1", "decision=cut")
    run(repo, "set", SONG, "2", "exports.dry.status=done",
        "exports.dry.path=/Exports/DRY/2.wav")
    run(repo, "set", SONG, "3", "exports.dry.status=n/a")

    payload = json.loads(run(repo, "status", SONG, "--format", "json").stdout)
    dry = payload["data"]["exports"]["dry"]
    assert dry["satisfied"] == 2 and dry["total"] == 2, dry


def test_missing_song_is_a_clean_error(repo):
    result = run(repo, "status", "no-such-song")
    assert result.returncode != 0
    assert "no manifest" in result.stderr
    assert result.stdout == ""

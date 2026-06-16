# mix-prep (`mixprep`) — Specification Sheet

> Document: `docs/SPEC.md`
> Status: Accepted — Phase 1 scope approved for build
> Version: 0.1.0
> Last updated: 2026-06-16

## 1. Summary

**mix-prep** (CLI command: `mixprep`) is a lightweight, text-based organization system for a musician who tracks ("records") songs across many sessions in **Logic Pro**, then migrates each song into a mixing-optimized project in **Ableton Live** or **Logic**. It maintains one YAML **manifest** per song that records every track, a consistent naming convention, dual (dry/wet) stem-export status, keep/cut decisions, effects chains, and timestamped notes. mix-prep tracks **state, not audio**: no audio files are ever stored in the repository, and the original Logic projects are never touched. The system is intentionally designed to be **agent-operable** so that a future Claude / local-LLM harness can drive the same CLI to assist project migration end to end.

## 2. Goals and Non-Goals

### Goals

- Give every song a single source-of-truth **manifest** describing its tracks, naming, export status, and mix decisions.
- Establish and enforce a **consistent track-naming convention** as the first migration step.
- Track **two exported versions per track** — a **dry** stem (effects bypassed) and a **wet** stem (tracking effects intact).
- Capture **keep/cut decisions** as layers are whittled down in the mix session.
- Produce **printable / scannable reports** (rename sheets, status, track listings).
- **Protect** the original Logic projects absolutely; operate only on verified copies.
- Be **git-friendly** (plain text, stable ordering, minimal diffs) and **agent-operable** (non-interactive flags, clean stdin/stdout, structured output).

### Non-Goals

- mix-prep is **not a DAW** and does not open, render, or play projects.
- mix-prep is **not an audio processor** — it does not bounce, convert, or modify audio.
- mix-prep **does not store audio** in the repo. Stems live on the filesystem (or external drives); the repo tracks only their status.
- mix-prep **never modifies the original Logic projects.** (Phase 1 performs no filesystem mutations of DAW projects at all; even Phase 2 automation operates exclusively on verified copies.)
- mix-prep is **not a backup tool** and does not guarantee storage of stems or projects.

## 3. Personas / Usage Context

| Persona | Description | Needs |
|---|---|---|
| **The Musician** (primary) | Records songs in Logic Pro across many sessions on macOS. Not primarily a developer. Mixes in Ableton or Logic. | Simple commands, readable tables, clear next-step guidance, strong safety guarantees for original projects. |
| **The LLM Agent Operator** (future, Phase 3) | A Claude or local-LLM harness that drives `mixprep` programmatically and reads/writes manifests to help migrate projects. | Non-interactive flags, deterministic exit codes, clean stdin/stdout, structured (machine-readable) output, no required interactive prompts. |

Both personas share the **same CLI and the same manifests.** The agent does not get a private API; it uses what the human uses. This is a core design constraint, not an afterthought.

## 4. Glossary

| Term | Meaning |
|---|---|
| **Tracking session** | A Logic Pro recording session that produces raw recorded tracks for a song. A song spans many tracking sessions. |
| **Mix session** | A separate, mixing-optimized project (Ableton or Logic) where stems are imported, layers are kept/cut, and the song is mixed. |
| **Track** | A single recorded element/lane in the DAW (e.g. "Kick In", "Lead Vocal"). |
| **Layer** | One of several alternative or stacked tracks for the same musical role; layers get whittled down (keep/cut) during mixing. |
| **Stem** | An exported audio file for a single track (or grouped tracks), used in the mix session. |
| **Dry stem** | Stem exported with **effect plug-ins bypassed** — clean signal, so effects can be re-created in the focused mix environment. |
| **Wet stem** | Stem exported **with tracking effects intact** — kept for A/B reference and comparison. |
| **Manifest** | The per-song YAML file (`songs/<slug>/song.yaml`) that is mix-prep's source of truth for that song. |
| **DAW** | Digital Audio Workstation (here: Logic Pro for tracking; Ableton Live or Logic for mixing). |
| **Source project** | The original Logic project. **Never touched.** |
| **mixprep copy** | A manually-made (Phase 1) or verified scripted (Phase 2+) copy of the Logic project; the only one ever opened/edited. |
| **Slug** | Filesystem-safe short identifier for a song, used as its directory name. |
| **Mix template** | (Phase 3) A pre-built Ableton/Logic project with category buses/groups and routing, into which stems are imported. |

## 5. Phased Roadmap

| Phase | Name | Scope | Status |
|---|---|---|---|
| **1** | Organization system | The `mixprep` CLI + per-song YAML manifests. Pure state tracking; no automation of the DAW or filesystem. | **Build now** |
| **2** | Automation | Scripted safe copies + watching for export status. | Planned |
| **3** | Mix template + LLM harness | Generate the mix template and let an agent drive migration. | Planned |

### Phase 1 — Organization System (build now)

The `mixprep` CLI and YAML manifests defined in this document. The human runs commands; mix-prep records and reports state. mix-prep performs **no** mutation of DAW projects or audio. Copies and exports are done **manually** by the human (Section 10), with mix-prep tracking the workflow flags. This phase exists to (a) impose a naming convention, (b) inventory every track, (c) track dual exports and keep/cut decisions, and (d) lay structured-data foundations for later automation.

### Phase 2 — Automation

- **Scripted safe copies with checksum verification.** A command duplicates a `.logicx` into a `MixPrep` folder and verifies the copy (e.g. file-tree + per-file checksums) before recording `copy_made`. Operates only on a copy destination; never writes into the source path.
- **Export-folder watching.** Watch `Exports/<song>/DRY/` and `Exports/<song>/WET/` to auto-update `dry_export` / `wet_export` statuses (and `exported_dry` / `exported_wet` workflow flags) as files appear, matching files to tracks by name.
- **Ableton `.als` parsing.** Ableton projects are gzipped XML. Parse them for **auto-inventory** (discover tracks) and **rename verification** (confirm tracks were renamed to convention in the DAW).
- **Logic automation limits noted.** Logic project files are not a documented open format; Logic automation is limited to **UI scripting** (e.g. AppleScript / accessibility) and is explicitly out of scope for reliable parsing.

### Phase 3 — Mix Template Generation + LLM Harness

- **Mix template generation.** Produce a pre-built mix project (Ableton `.als` and/or Logic) containing **category buses/groups** (per the category codes in Section 8) with routing pre-wired, then import and route the song's stems into the correct groups. This is the "import the stems into a ready-made mixing project" capability the user requested.
- **Claude / local-LLM harness.** An agent drives the `mixprep` CLI and reads/writes manifests to assist migration end to end — proposing names via `suggest`, recording decisions, checking off workflow steps, and generating the mix template.

**Why Phase 1 is the foundation for Phase 3:** the agent needs (1) a **stable, structured data model** it can read and write deterministically (the YAML manifest), and (2) a **complete, non-interactive CLI** it can invoke without a human in the loop. Phase 1 delivers both. The mix template generator (Phase 3) consumes the same manifest — category codes drive bus creation, the `tracks` list drives stem routing, and `decision` filters out cut layers. No new data plumbing is required; Phase 3 is additive.

## 6. Functional Requirements

Requirements are numbered for traceability. Phase tag in brackets.

**Inventory**
- **FR-1** [P1] Create a new song manifest with `mixprep new`, capturing title, slug, source-project path, mixprep-copy path, mix DAW, sample rate, and tempo.
- **FR-2** [P1] Bulk-add tracks by pasting a Logic track list on stdin (`add --bulk`); each line becomes a track with its `original_name` populated.
- **FR-3** [P1] Add/inspect/list individual tracks (`tracks`, `list`).

**Naming**
- **FR-4** [P1] Suggest convention-compliant `new_name`s from messy `original_name`s via a keyword→category table (`suggest`), interactively by default and non-interactively with `--auto`/`--yes`.
- **FR-5** [P1] Assign/repair the leading sort number on every track so alphabetical DAW sort equals mix order, grouped by category order (`renumber`).
- **FR-6** [P1] Validate names against the convention regex (`validate`, `validate --all`).

**Dual export tracking**
- **FR-7** [P1] Track a **dry** and a **wet** export status per track, each one of `pending | done | n/a`.
- **FR-8** [P1] Roll per-track export status up into song workflow flags (`exported_dry`, `exported_wet`) and report progress.

**Decisions**
- **FR-9** [P1] Record a keep/cut decision per track (`keep | cut | undecided`) and report counts.

**Notes & effects**
- **FR-10** [P1] Append timestamped notes at song level and track level; notes are appendable and editable (`note`).
- **FR-11** [P1] Record a track's effects chain as an ordered list of `{plugin, settings}` entries (`fx`).

**Reporting**
- **FR-12** [P1] Print a per-song **status** summary including workflow flags, export progress, and decision counts (`status`).
- **FR-13** [P1] Print a **rename sheet** mapping `original_name → new_name` per track, suitable for working through in the DAW (`sheet`).
- **FR-14** [P1] List all songs in the repo (`list`).

**Workflow**
- **FR-15** [P1] Check/uncheck ordered workflow pipeline flags (`check`/`uncheck`).
- **FR-16** [P1] Edit arbitrary track fields via `set <song> <track> key=value...`.

**Safety**
- **FR-17** [P1] Never write to, move, or delete any DAW project or audio file. mix-prep writes only its own manifests under `songs/<slug>/`.
- **FR-18** [P1] Treat `source_project` as read-only metadata; never dereference it for writes.
- **FR-19** [P1] **Warn, never block:** guardrail violations (bad names, out-of-order workflow checks, missing copy) produce warnings and non-zero advisory signals where useful, but do not prevent the operation.

**Agent-operability (cross-cutting)**
- **FR-20** [P1] Every command that can prompt must offer a non-interactive mode (`--yes`/`--auto`) and must read piped stdin cleanly.
- **FR-21** [P1] Commands that output data support a structured/machine-readable output option for agent consumption.
- **FR-22** [P1] Exit codes are deterministic: `0` success, non-zero for hard errors (not for advisory warnings).

## 7. Data Model Specification

One manifest per song at `songs/<slug>/song.yaml`. Audio is never embedded; only paths and statuses.

### Annotated YAML example

```yaml
song:
  title: "Ocean Floor"                 # human-readable song title
  slug: "ocean-floor"                  # filesystem-safe id; == directory name
  source_project: "/Volumes/Music/Logic/Ocean Floor.logicx"  # ORIGINAL — never touched
  mixprep_copy: "/Volumes/Music/MixPrep/Ocean Floor.logicx"   # the only copy ever opened
  mix_daw: ableton                     # ableton | logic
  sample_rate: 48000                   # Hz
  tempo: 92                            # BPM

workflow:                              # ordered pipeline; booleans, advisory order
  copy_made: true
  tracks_inventoried: true
  renamed_in_daw: false
  exported_dry: false
  exported_wet: false
  imported_to_mix: false
  mixing_started: false

notes:                                 # song-level, timestamped, appendable+editable
  - { ts: "2026-06-16T10:02:00", text: "Verse 2 has a doubled vocal to resolve." }

tracks:
  - id: 1
    original_name: "Audio 7 kick"      # as it appeared in the tracking session
    new_name: "01_DR_KickIn"           # convention-compliant; NN assigned by CLI
    category: DR                       # one of the category codes
    dry_export: pending                # pending | done | n/a
    wet_export: pending                # pending | done | n/a
    decision: undecided                # keep | cut | undecided
    effects_chain:                     # ordered list of plugin entries
      - { plugin: "Channel EQ", settings: "HPF 40Hz, +3dB @ 4kHz" }
      - { plugin: "Compressor",  settings: "ratio 4:1, -6dB GR" }
    source:                            # provenance of the recording
      mic: "Beta 91A"
      performer: "Sam"
      recorded: "2026-05-30"
      takes: 3
    notes:
      - { ts: "2026-06-16T10:05:00", text: "Best take is comp of 1+3." }
```

### Field-by-field table

| Path | Type | Allowed values | Meaning |
|---|---|---|---|
| `song.title` | string | any | Human-readable song title. |
| `song.slug` | string | `[A-Za-z0-9_-]+` | Filesystem-safe id; equals the song directory name. |
| `song.source_project` | string (path) | filesystem path | Original Logic project. **Read-only; never touched.** |
| `song.mixprep_copy` | string (path) | filesystem path | Verified copy; the only project ever opened/edited. |
| `song.mix_daw` | enum | `ableton`, `logic` | Target mixing DAW. |
| `song.sample_rate` | int | e.g. 44100, 48000, 96000 | Project sample rate in Hz. |
| `song.tempo` | number | > 0 | Tempo in BPM. |
| `workflow.copy_made` | bool | true/false | A verified copy exists. |
| `workflow.tracks_inventoried` | bool | true/false | All tracks captured in manifest. |
| `workflow.renamed_in_daw` | bool | true/false | Tracks renamed to convention in the DAW. |
| `workflow.exported_dry` | bool | true/false | All required dry stems exported. |
| `workflow.exported_wet` | bool | true/false | All required wet stems exported. |
| `workflow.imported_to_mix` | bool | true/false | Stems imported into the mix project. |
| `workflow.mixing_started` | bool | true/false | Mixing has begun. |
| `notes[]` | list | — | Song-level timestamped notes. |
| `notes[].ts` | string | ISO-8601 datetime | Timestamp when note was added. |
| `notes[].text` | string | any | Note body. |
| `tracks[]` | list | — | All tracks for the song. |
| `tracks[].id` | int | unique, ≥ 1 | Stable internal track id (distinct from the `NN` sort number in the name). |
| `tracks[].original_name` | string | any | Name as it appeared in the tracking session. |
| `tracks[].new_name` | string | matches naming regex | Convention-compliant name. |
| `tracks[].category` | enum | `DR PRC BS GTR KEY SYN VOX BV FX MISC` | Category code (drives numbering and Phase 3 bus routing). |
| `tracks[].dry_export` | enum | `pending`, `done`, `n/a` | Dry stem export status. |
| `tracks[].wet_export` | enum | `pending`, `done`, `n/a` | Wet stem export status. |
| `tracks[].decision` | enum | `keep`, `cut`, `undecided` | Keep/cut mix decision. |
| `tracks[].effects_chain[]` | list | — | Ordered tracking effects. |
| `tracks[].effects_chain[].plugin` | string | any | Plugin name. |
| `tracks[].effects_chain[].settings` | string | any | Free-text settings summary. |
| `tracks[].source.mic` | string | any | Microphone used (nullable). |
| `tracks[].source.performer` | string | any | Performer (nullable). |
| `tracks[].source.recorded` | string | date | Recording date (nullable). |
| `tracks[].source.takes` | int | ≥ 0 | Number of takes (nullable). |
| `tracks[].notes[]` | list | — | Track-level timestamped notes (appendable + editable). |

> **Ordering / git-friendliness:** the store writes keys in a stable order and preserves track order, so diffs stay minimal and reviewable.

## 8. Naming Convention Specification

### Format

```
NN_CAT_Descriptor[_Variant]
```

- **`NN`** — two-digit, CLI-assigned sort number. Chosen so that **alphabetical sort in any DAW = intended mix order.** Numbering follows category order (below), then track order within a category.
- **`CAT`** — one of the fixed category codes.
- **`Descriptor`** — CamelCase, `[A-Za-z0-9]+`.
- **`_Variant`** — optional, repeatable (e.g. `_L`, `_R`, `_Double`); each segment `[A-Za-z0-9]+`.
- Allowed character set overall: `[A-Za-z0-9_]` only (filesystem-safe).
- **Dry/wet is NOT encoded in the name.** It is handled by export destination folders: `Exports/<song>/DRY/` and `Exports/<song>/WET/`.

Examples: `01_DR_KickIn`, `07_GTR_AcousticRhythm_L`, `21_VOX_Lead`.

### Category code table

| Order | Code | Name | Examples |
|---|---|---|---|
| 1 | `DR` | Drums | `KickIn`, `Snare`, `OHL` |
| 2 | `PRC` | Percussion | `Shaker`, `Tambourine` |
| 3 | `BS` | Bass | `DI`, `Amp` |
| 4 | `GTR` | Guitar | `AcousticRhythm_L`, `Lead` |
| 5 | `KEY` | Keys / acoustic-electric keyboards | `Piano`, `Rhodes` |
| 6 | `SYN` | Synths | `Pad`, `Pluck` |
| 7 | `VOX` | Lead vocals | `Lead`, `Adlib` |
| 8 | `BV` | Backing vocals | `HarmHigh`, `Stack` |
| 9 | `FX` | Effects / ear candy / risers | `Riser`, `Impact` |
| 10 | `MISC` | Uncategorized / other | `Talkback`, `Click` |

Category order = numbering order. The number block for each category is assigned in this sequence.

### Validation regex

```
^\d{2}_(DR|PRC|BS|GTR|KEY|SYN|VOX|BV|FX|MISC)_[A-Za-z0-9]+(_[A-Za-z0-9]+)*$
```

### How the commands use the convention

- **`suggest`** maps each messy `original_name` to a `category` and a CamelCase `Descriptor` via a keyword table (e.g. "kick"→`DR/KickIn`, "ac gtr"→`GTR/Acoustic`). Proposes a full `new_name`; human confirms (or `--auto` accepts all).
- **`renumber`** recomputes every `NN` from category order + intra-category order, rewriting the leading digits of `new_name` so the manifest stays internally consistent and DAW-sortable.
- **`validate`** checks each `new_name` against the regex and the category enum, reporting offenders. With `--all`, validates every song. Warnings, not hard failures (FR-19), unless invoked in a strict/hard-error context.

## 9. CLI Command Specification

Global conventions:
- First positional argument is usually the song **slug**.
- `--song <slug>` may substitute where a positional is ambiguous.
- Prompting commands accept `--yes`/`--auto` for non-interactive use (FR-20).
- Data-listing commands accept a structured output option for agents (FR-21).
- Guardrails **warn, never block** (FR-19). Exit `0` on success incl. warnings; non-zero only on hard errors (FR-22).

| Command | Arguments | Key flags | Behavior | Example |
|---|---|---|---|---|
| `new` | `<slug>` | `--title`, `--source`, `--copy`, `--daw`, `--sample-rate`, `--tempo` | Create `songs/<slug>/song.yaml` from `templates/song.yaml`. | `mixprep new ocean-floor --title "Ocean Floor" --daw ableton` |
| `add` | `<slug>` | `--bulk` (reads stdin), `--name`, `--category` | Add tracks. `--bulk` ingests a pasted Logic track list (one per line) into `original_name`. | `pbpaste \| mixprep add ocean-floor --bulk` |
| `suggest` | `<slug>` | `--auto`/`--yes`, `--only-unnamed` | Propose convention names from originals via keyword table; interactive confirm or auto-accept. | `mixprep suggest ocean-floor --auto` |
| `renumber` | `<slug>` | — | Recompute every `NN` from category + intra-category order. | `mixprep renumber ocean-floor` |
| `set` | `<song> <track> key=value...` | — | Edit arbitrary track fields (e.g. `category=GTR decision=keep`). | `mixprep set ocean-floor 7 decision=cut` |
| `note` | `<slug>` | `--track <id>`, `--text`, `--edit <note-idx>` | Append (or edit) a timestamped note at song or track level. | `mixprep note ocean-floor --track 1 --text "comp 1+3"` |
| `fx` | `<song> <track>` | `--add "plugin"`, `--settings "..."`, `--clear` | Append/clear effects-chain entries. | `mixprep fx ocean-floor 1 --add "Compressor" --settings "4:1"` |
| `check` | `<slug> <flag>` | — | Set a workflow flag true (warns if out of pipeline order). | `mixprep check ocean-floor exported_dry` |
| `uncheck` | `<slug> <flag>` | — | Set a workflow flag false. | `mixprep uncheck ocean-floor mixing_started` |
| `sheet` | `<slug>` | `--format` | Print a printable `original → new` rename sheet. | `mixprep sheet ocean-floor` |
| `status` | `<slug>` | `--format` | Print workflow flags, dry/wet export progress, keep/cut counts. | `mixprep status ocean-floor` |
| `tracks` | `<slug>` | `--format`, `--category`, `--decision` | List tracks as a table (filterable). | `mixprep tracks ocean-floor --category VOX` |
| `validate` | `[<slug>]` | `--all` | Validate names against the regex + category enum. | `mixprep validate --all` |
| `list` | — | `--format` | List all songs in the repo. | `mixprep list` |
| `edit` | `<slug>` | — | Open the manifest for manual editing (advisory; respects safety scope). | `mixprep edit ocean-floor` |

**Agent-operability requirements (call-out):**
- `suggest` must run fully unattended under `--auto`.
- `add --bulk` must accept piped stdin with no TTY.
- `status`, `tracks`, `list`, `sheet`, `validate` must offer a structured `--format` (e.g. JSON) for the agent to parse, in addition to the default plain-text table.
- No command may require interactive input to complete its primary function when a non-interactive flag is supplied.

## 10. Workflow Pipeline (per song)

Ordered phases. Each maps to a `workflow` flag (Section 7). Order is **advisory** — checking out of order warns but is allowed (FR-19).

| Step | Flag | Entry criteria | Exit criteria | Owner (P1) |
|---|---|---|---|---|
| 1. Make safe copy | `copy_made` | Logic closed; original located. | A copy exists in `MixPrep/`; original locked. | Human (manual) |
| 2. Inventory tracks | `tracks_inventoried` | `copy_made`. | All tracks in manifest with `original_name`. | Human via `add --bulk` |
| 3. Rename in DAW | `renamed_in_daw` | All tracks have valid `new_name` (via `suggest`+`renumber`, passes `validate`). | Tracks renamed in the copy to match `new_name`. | Human, guided by `sheet` |
| 4. Export dry stems | `exported_dry` | `renamed_in_daw`. | Each kept track's `dry_export` = `done` (or `n/a`). | Human (manual export) |
| 5. Export wet stems | `exported_wet` | `renamed_in_daw`. | Each kept track's `wet_export` = `done` (or `n/a`). | Human (manual export) |
| 6. Import to mix | `imported_to_mix` | Required stems exported. | Stems imported into the mix project (Phase 3: into the mix template). | Human |
| 7. Mixing started | `mixing_started` | `imported_to_mix`. | Mix in progress; keep/cut `decision`s being recorded. | Human |

### Manual safety + export procedure (Phase 1, macOS)

1. **Quit Logic Pro** so the project is not in use.
2. In **Finder**, select the `.logicx`, press **Cmd+D** to duplicate, move the duplicate into a `MixPrep` folder.
3. **Lock the original** via Finder → Get Info → "Locked".
4. **Only ever open the copy.** Record `copy_made`.
5. **Dry export:** in the copy, `File → Export → All Tracks as Audio Files`, with **"Bypass Effect Plug-ins" CHECKED**, into `Exports/<song>/DRY/`.
6. **Wet export:** repeat with **"Bypass Effect Plug-ins" UNCHECKED**, into `Exports/<song>/WET/`.

(Phase 2 automates steps 2–3 with checksum-verified copies and watches the `DRY/`/`WET/` folders to update statuses automatically.)

## 11. Constraints & Safety Requirements

- **C-1 Original protection.** mix-prep must never write to, move, rename, or delete a `source_project`. It is treated as read-only metadata. (Phase 1 makes no DAW/audio filesystem mutations whatsoever.)
- **C-2 Copy-only operation.** Any future automation (Phase 2+) operates exclusively on a **verified** `mixprep_copy`, never on the source. A copy is "verified" only after checksum/file-tree verification.
- **C-3 No audio in repo.** The repository tracks **state, not stems.** Audio files are excluded via `.gitignore`; manifests store only paths and statuses.
- **C-4 Warn, never block.** Guardrails (invalid names, out-of-order workflow, missing copy) emit warnings but do not prevent the action. Hard errors are reserved for impossible/destructive states.
- **C-5 Git-friendliness.** Plain-text YAML, stable key ordering, preserved track order — minimal, reviewable diffs.
- **C-6 Minimal dependencies.** Runtime deps limited to **PyYAML** and **click**; Python **3.9+**. Plain-text table output (no rich text rendering library). Installed via `pipx install --editable .` to provide the global `mixprep` command.
- **C-7 Write scope.** mix-prep writes only within the repo, under `songs/<slug>/` (and its own docs/templates). It never writes outside the repo.
- **C-8 Agent parity.** The agent operator uses the same CLI and manifests as the human; no separate privileged interface.

## 12. Success Criteria / Acceptance (Phase 1)

Phase 1 is accepted when:

- **A-1** `pipx install --editable .` yields a working global `mixprep` command.
- **A-2** A user can `new` a song, `add --bulk` a pasted Logic track list, `suggest` + `renumber` valid convention names, and `validate` with no errors.
- **A-3** Each track tracks independent `dry_export` and `wet_export` statuses; `status` reports dry/wet progress and keep/cut counts.
- **A-4** `sheet` prints a correct `original → new` rename sheet; `tracks`, `status`, and `list` print scannable plain-text tables.
- **A-5** All listed data/reporting commands offer a structured `--format` output; `suggest --auto` and `add --bulk` run fully non-interactively. (Agent-operability.)
- **A-6** Manifests round-trip through the store with stable ordering (clean git diffs).
- **A-7** mix-prep performs **zero** mutations to any DAW project or audio file; verified by the end-to-end test (`tests/test_e2e.py`).
- **A-8** Guardrails warn but never block; exit codes are deterministic.
- **A-9** Repository layout matches the accepted structure: `pyproject.toml`, `README.md`, `.gitignore`, `docs/naming-convention.md`, `docs/phase2-roadmap.md`, `templates/song.yaml`, `src/mixprep/{cli,model,store,naming,report}.py`, `songs/<slug>/song.yaml`, `tests/test_e2e.py`.

## 13. Open Questions / Decisions to Revisit

- **Mix template structure (Phase 3).** Exact bus/group topology, naming of category buses, default routing and sends, and whether to ship Ableton-only first or both DAWs. How closely should template groups mirror the 10 category codes vs. a coarser bus set?
- **Pro Tools (and other DAWs) support.** Should the model later support Pro Tools / other DAWs as tracking or mix targets? Current enum is `ableton | logic` only.
- **Local-LLM choice for the harness (Phase 3).** Which local model (and runtime) to support alongside Claude, and how the harness authenticates / sandboxes filesystem access while respecting C-1/C-2.
- **Logic project parsing.** Logic's project format is not openly documented; auto-inventory/verify for Logic may be limited to UI scripting. Is UI scripting acceptable, or is Ableton-only auto-parsing sufficient for Phase 2?
- **Stem-to-track matching.** For export-folder watching (Phase 2), how strictly must exported filenames match `new_name`, and how to handle multi-file (e.g. `_L`/`_R`) or grouped exports.
- **Structured output format.** Confirm JSON as the `--format` machine-readable target (vs. NDJSON/YAML) for agent consumption, and whether a stable schema version field is needed.
- **Note editing semantics.** Whether editing a note should preserve the original `ts` or stamp an `edited` time.

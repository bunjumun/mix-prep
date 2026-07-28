# mix-prep (`mixprep`) — Specification Sheet

> Document: `docs/SPEC.md`
> Status: Accepted — Phase 1 scope approved for build
> Version: 0.2.0
> Last updated: 2026-06-16

> **Changelog (0.2.0):** Folded in multi-agent review outcomes — added `schema_version`, `track_kind`, `group`, an `exports` sub-object (status + stem path), hardware/real-time export awareness, a richer plugin-settings log, a JSON output envelope, a global `--dry-run`, and a `source ≠ copy` safety guard. Replaced the interactive `edit` command with `path`. Replaced the undefined `validate --strict` mode with a structural-error vs style-warning exit-code split. `set` now accepts dotted paths.

## 1. Summary

**mix-prep** (CLI command: `mixprep`) is a lightweight, text-based organization system for a musician who tracks ("records") songs across many sessions in **Logic Pro**, then migrates each song into a mixing-optimized project in **Ableton Live** or **Logic**. It maintains one YAML **manifest** per song that records every track, a consistent naming convention, dual (dry/wet) stem-export status, keep/cut decisions, effects chains, and timestamped notes. mix-prep tracks **state, not audio**: no audio files are ever stored in the repository, and the original Logic projects are never touched. The system is intentionally designed to be **agent-operable** so that a future Claude / local-LLM harness can drive the same CLI to assist project migration end to end.

## 2. Goals and Non-Goals

### Goals

- Give every song a single source-of-truth **manifest** describing its tracks, naming, export status, and mix decisions.
- Establish and enforce a **consistent track-naming convention** as the first migration step.
- Track **two exported versions per track** — a **dry** stem (effects bypassed) and a **wet** stem (tracking effects intact).
- Capture **keep/cut decisions** as layers are whittled down in the mix session.
- Capture enough **plugin/effects recall** information to recreate a track's chain in the mix DAW.
- Surface **hardware / real-time export requirements** so outboard-gear tracks are exported correctly.
- Produce **printable / scannable reports** (rename sheets, status, track listings).
- **Protect** the original Logic projects absolutely; operate only on verified copies.
- Be **git-friendly** (plain text, stable ordering, minimal diffs) and **agent-operable** (non-interactive flags, clean stdin/stdout, structured output, deterministic exit codes).

### Non-Goals

- mix-prep is **not a DAW** and does not open, render, or play projects.
- mix-prep is **not an audio processor** — it does not bounce, convert, or modify audio.
- mix-prep **does not store audio** in the repo. Stems live on the filesystem (or external drives); the repo tracks only their status and paths.
- mix-prep **does not read, copy, or embed** referenced asset files (plugin presets, screenshots, `.cst` channel-strip settings). It stores only **pointers** to them.
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
| **Track** | A single recorded element/lane in the DAW (e.g. "Kick In", "Lead Vocal"). Buses/aux returns are also represented as tracks (`track_kind: bus|aux`). |
| **Layer** | One of several alternative or stacked tracks for the same musical role; layers get whittled down (keep/cut) during mixing. Linked via the `group` field. |
| **Stem** | An exported audio file for a single track (or grouped tracks), used in the mix session. |
| **Dry stem** | Stem exported with **effect plug-ins bypassed** — clean signal, so effects can be re-created in the focused mix environment. |
| **Wet stem** | Stem exported **with tracking effects intact** — kept for A/B reference and comparison. |
| **Real-time bounce** | A Logic export performed at playback speed so audio physically passes through external hardware (outboard gear, hardware instruments). Required when a track's signal path leaves the computer. |
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

The `mixprep` CLI and YAML manifests defined in this document. The human runs commands; mix-prep records and reports state. mix-prep performs **no** mutation of DAW projects or audio. Copies and exports are done **manually** by the human (Section 10), with mix-prep tracking the workflow flags. This phase exists to (a) impose a naming convention, (b) inventory every track, (c) track dual exports, hardware/real-time needs, plugin recall, and keep/cut decisions, and (d) lay structured-data foundations for later automation.

### Phase 2 — Automation

- **Scripted safe copies with checksum verification.** A command duplicates a `.logicx` into a `MixPrep` folder and verifies the copy (file-tree + per-file checksums) before recording `copy_made`. Operates only on a copy destination; never writes into the source path. The Phase 1 `source ≠ copy` invariant (C-9) becomes a hard pre-flight refusal here.
- **Export-folder watching.** Watch `Exports/<song>/DRY/` and `Exports/<song>/WET/` to auto-update each track's `exports.<dir>.status` (and the `exported_dry`/`exported_wet` workflow flags), matching files to tracks by name and recording the resolved `exports.<dir>.path`.
- **Ableton `.als` parsing.** Ableton projects are gzipped XML. Parse them for **auto-inventory** (discover tracks) and **rename verification** (confirm tracks were renamed to convention in the DAW).
- **Plugin-settings capture (`mixprep shots`).** A later command that records each track's plugin chain into easily-recalled artifacts and writes their paths into the manifest's existing `ref` / `channel_strip_ref` pointers (no schema change; assets live outside the repo, C-3). Driven by a feasibility study (2026), the design is **reliability-ordered**, because Logic exposes no real scripting API (only `renderpreview`) and the only programmatic route to open plugin windows is fragile macOS Accessibility/UI scripting (≈4/10; unattended loops ≈3/10 due to macOS Sequoia's recurring Screen-Recording prompts and focus-stealing):
  1. **Native saves first (early Phase 2, high reliability):** Logic **Channel Strip Setting** (`.cst`, whole-chain, Logic→Logic exact recall) and per-plugin **AU preset** (`.aupreset`); for the Logic→**Ableton** path, the portable artifact is the plugin's **own vendor preset** (works in any host that has that plugin). These can even be saved manually with mix-prep just recording the resulting `ref`.
  2. **Screenshots as a visual supplement (late Phase 2 / Phase 3, behind the LLM harness):** open each non-bypassed plugin via UI scripting, resolve its CGWindowID, `screencapture -l -o`, save. Capture-once is reliable (≈8/10); the open-it loop is not — so it runs **attended by default**, reports per-plugin success/failure in the JSON envelope, and falls back to the manual log on misses.
  - **Why screenshots still matter:** they are the only recall for outboard hardware front panels, Logic stock plugins with no Ableton equivalent, and Smart Controls / automation context — things presets can't carry.
  - **Layout:** `Exports/<song>/PluginShots/<new_name>/NN_<plugin>.{png,aupreset}` + `00_ChannelStrip.cst`, mirroring the export tree; NN = effects-chain list index.
  - **Hard safety:** the command must positively confirm Logic's open project resolves to `song.mixprep_copy` and abort otherwise — never act against the source (C-1/C-2/C-9). Requires macOS Screen-Recording + Accessibility consent.
  - **Verdict:** complements, never replaces, the Phase 1 manual settings log (which stays the DAW-independent, searchable, git-friendly source of truth). No Phase-1 hooks needed beyond the `ref`/`channel_strip_ref` fields already present; an optional per-plugin `slot` index (Section 13) would make shot↔chain mapping explicit.
- **Logic automation limits noted.** Logic project files are not a documented open format; Logic automation is limited to **UI scripting** (e.g. AppleScript / accessibility) and is explicitly out of scope for reliable parsing.

### Phase 3 — Mix Template Generation + LLM Harness

- **Mix template generation.** Produce a pre-built mix project (Ableton `.als` and/or Logic) containing **category buses/groups** (per the category codes in Section 8) with routing pre-wired, then import and route the song's stems into the correct groups using each track's `category`, `decision`, and `exports.<dir>.path`. This is the "import the stems into a ready-made mixing project" capability the user requested.
- **Claude / local-LLM harness.** An agent drives the `mixprep` CLI and reads/writes manifests to assist migration end to end — proposing names via `suggest`, recording decisions, checking off workflow steps, and generating the mix template.

**Why Phase 1 is the foundation for Phase 3:** the agent needs (1) a **stable, versioned, structured data model** it can read and write deterministically (the YAML manifest, stamped with `schema_version`), and (2) a **complete, non-interactive CLI** with a machine-readable output envelope and deterministic exit codes. Phase 1 delivers both. The mix template generator (Phase 3) consumes the same manifest — category codes drive bus creation, the `tracks` list + `exports.<dir>.path` drive stem routing, and `decision` filters out cut layers. No new data plumbing is required; Phase 3 is additive.

## 6. Functional Requirements

Requirements are numbered for traceability. Phase tag in brackets.

**Inventory**
- **FR-1** [P1] Create a new song manifest with `mixprep new`, capturing title, slug, source-project path, mixprep-copy path, mix DAW, sample rate, and tempo. Stamp `schema_version`.
- **FR-2** [P1] Bulk-add tracks by pasting a Logic track list on stdin (`add --bulk`); each line becomes a track with its `original_name` populated and a stable, never-reused `id`.
- **FR-3** [P1] Add/inspect/list individual tracks (`tracks`, `list`).

**Naming**
- **FR-4** [P1] Suggest convention-compliant `new_name`s and `category` from messy `original_name`s via a keyword→category table (`suggest`), interactively by default and non-interactively with `--auto`/`--yes`.
- **FR-5** [P1] Assign/repair the leading sort number on every track so alphabetical DAW sort equals mix order, grouped by category order (`renumber`). Warn if `renamed_in_daw` is already true (renumbering desyncs the manifest from names already typed in the DAW).
- **FR-6** [P1] Validate names against the convention regex (`validate`, `validate --all`).

**Track classification**
- **FR-23** [P1] Record a `track_kind` per track (`audio | instrument | bus | aux`); reports use it (e.g. an instrument track has no meaningful dry stem; buses/aux carry their own `effects_chain`).
- **FR-24** [P1] Record an optional `group` label per track linking alternative layers / stereo pairs; reports roll up keep/cut by group and warn on split or empty-keep groups.

**Dual export tracking**
- **FR-7** [P1] Track a **dry** and a **wet** export per track via an `exports` sub-object — each direction has a `status` (`pending | done | n/a`) and a resolved stem `path`.
- **FR-8** [P1] Roll per-track export status up into song workflow flags (`exported_dry`, `exported_wet`) and report progress. Rollup considers **only non-cut tracks**; `n/a` counts as satisfied.

**Hardware / real-time export**
- **FR-25** [P1] Record per-track hardware dependency (`hardware.type` ∈ `none|insert|external_instrument|sidechain|send`, plus free-text `hardware.io`) and a song-level `export.realtime` (`auto|force|off`) with `export.hardware_returns` for parallel hardware on buses.
- **FR-26** [P1] **Derive and surface**, per export pass, whether the DRY and WET passes must be bounced in real time, as a song-level banner in `status` (real-time is a whole-pass setting in Logic, not per track). Recommend `dry_export: n/a` for `external_instrument` tracks.

**Decisions**
- **FR-9** [P1] Record a keep/cut decision per track (`keep | cut | undecided`) and report counts.

**Notes & effects recall**
- **FR-10** [P1] Append timestamped notes at song level and track level; notes are appendable and editable (`note`).
- **FR-11** [P1] Record a track's effects chain as an **ordered** list of plugin entries for recall: `plugin` (required) plus optional `maker`, `preset`, `bypassed`, free-text `settings`, structured `params` (key→value), and `ref` (pointer to a saved preset/screenshot). Support an optional track-level `channel_strip_ref` (pointer to a Logic `.cst`). All asset references are **pointers only** (C-3/C-7).

**Reporting**
- **FR-12** [P1] Print a per-song **status** summary including workflow flags, export progress, decision counts, the real-time export banner, and group rollups (`status`).
- **FR-13** [P1] Print a **rename sheet** mapping `original_name → new_name` per track, suitable for working through in the DAW (`sheet`).
- **FR-14** [P1] List all songs in the repo (`list`).

**Workflow**
- **FR-15** [P1] Check/uncheck ordered workflow pipeline flags (`check`/`uncheck`).
- **FR-16** [P1] Edit track fields via `set <song> <track> key=value...`, supporting **dotted paths** into nested fields (e.g. `exports.wet.status=done`, `hardware.type=insert`).

**Manifest access**
- **FR-27** [P1] `path <slug>` prints the manifest's absolute file path (and `--dir` the song directory) to stdout with no decoration, for composable hand-editing (`$EDITOR "$(mixprep path <slug>)"`) and agent file discovery.

**Safety**
- **FR-17** [P1] Never write to, move, or delete any DAW project, audio file, or referenced asset. mix-prep writes only its own manifests under `songs/<slug>/`.
- **FR-18** [P1] Treat `source_project` (and all `ref`/`io` pointers) as read-only metadata; never dereference for writes.
- **FR-19** [P1] **Warn, never block:** advisory guardrail violations (bad names, out-of-order workflow checks, missing copy) produce warnings but do not prevent the operation.
- **FR-28** [P1] **Source ≠ copy guard:** on `new`/`set`, warn loudly if `mixprep_copy` equals or is nested under `source_project`.

**Agent-operability (cross-cutting)**
- **FR-20** [P1] Every command that can prompt must offer a non-interactive mode (`--yes`/`--auto`) and must read piped stdin cleanly (and not hang on empty/closed stdin).
- **FR-21** [P1] Commands that output data support a structured `--format json` envelope `{ok, warnings, data}` (including `schema_version` in `data` for read commands). Machine output goes to **stdout**; human/warning chatter goes to **stderr**.
- **FR-22** [P1] Exit codes are deterministic: `0` success (including advisory warnings), non-zero only for hard/structural errors (see Section 8 classification).
- **FR-29** [P1] All mutating commands accept a global `--dry-run` that computes and reports the would-be change without writing.

## 7. Data Model Specification

One manifest per song at `songs/<slug>/song.yaml`. Audio and asset files are never embedded; only paths/pointers and statuses.

### Annotated YAML example

```yaml
schema_version: 1                      # manifest schema version (for safe migration)

song:
  title: "Ocean Floor"                 # human-readable song title
  slug: "ocean-floor"                  # filesystem-safe id; == directory name
  source_project: "/Volumes/Music/Logic/Ocean Floor.logicx"  # ORIGINAL — never touched
  mixprep_copy: "/Volumes/Music/MixPrep/Ocean Floor.logicx"   # the only copy ever opened
  mix_daw: ableton                     # ableton | logic
  sample_rate: 48000                   # Hz
  tempo: 92                            # BPM

export:                                # song-level export controls
  realtime: auto                       # auto | force | off  (whole-pass real-time control)
  hardware_returns: ""                 # free-text: parallel hardware on a bus/return (not a track)

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
  - id: 21                             # stable, unique, never reused (NOT the NN in the name)
    original_name: "Vox Lead comp"     # as it appeared in the tracking session
    new_name: "21_VOX_Lead"            # convention-compliant; NN assigned by CLI
    category: VOX                      # one of the category codes
    track_kind: audio                  # audio | instrument | bus | aux
    group: "LeadVox"                   # optional: links alternative layers / stereo pairs
    decision: keep                     # keep | cut | undecided
    hardware:                          # signal-path hardware dependency
      type: insert                     # none | insert | external_instrument | sidechain | send
      io: "out 5/6 -> Distressor -> in 5/6"   # free-text routing note (optional)
    exports:
      dry: { status: pending, path: null }   # DRY offline-OK (insert bypassed)
      wet: { status: pending, path: null }   # WET requires real time (insert in path)
    channel_strip_ref: "/Volumes/Music/MixPrep/presets/OceanFloor_LeadVox.cst"  # pointer only
    effects_chain:                     # ordered = signal chain order
      - plugin: "Channel EQ"
        maker: "Logic"
        settings: "HPF 90Hz, -3dB @ 350, +4dB @ 10k"
      - plugin: "Pro-C 2"
        maker: "FabFilter"
        preset: "Vocal Smooth"
        bypassed: false
        settings: "gentle leveling, ~3dB GR"
        params: { Ratio: "3:1", Threshold: "-22 dB", Attack: "8 ms" }
        ref: "/Volumes/Music/MixPrep/presets/leadvox_proc2.aupreset"
      - plugin: "Distressor"
        maker: "Empirical Labs (hardware)"
        settings: "Dist 3, ~4-6dB GR — OUTBOARD insert, see hardware.io"
        ref: "/Volumes/Music/MixPrep/presets/leadvox_distressor.jpg"
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
| `schema_version` | int | ≥ 1 | Manifest schema version; CLI refuses versions newer than it supports. |
| `song.title` | string | any | Human-readable song title. |
| `song.slug` | string | `[A-Za-z0-9_-]+` | Filesystem-safe id; equals the song directory name. |
| `song.source_project` | string (path) | filesystem path | Original Logic project. **Read-only; never touched.** |
| `song.mixprep_copy` | string (path) | filesystem path | Verified copy; the only project ever opened/edited. Must differ from `source_project` (C-9). |
| `song.mix_daw` | enum | `ableton`, `logic` | Target mixing DAW. |
| `song.sample_rate` | int | e.g. 44100, 48000, 96000 | Project sample rate in Hz. |
| `song.tempo` | number | > 0 | Tempo in BPM. |
| `export.realtime` | enum | `auto`, `force`, `off` | Whole-pass real-time control. `auto` derives from track hardware; `force` = whole run real-time; `off` = suppress. |
| `export.hardware_returns` | string | any | Free-text note for parallel hardware on a bus/return (not represented as a track). |
| `workflow.*` | bool | true/false | Ordered pipeline flags (see Section 10). |
| `notes[]` | list | — | Song-level timestamped notes. |
| `notes[].ts` | string | ISO-8601 datetime | Timestamp when note was added. |
| `notes[].text` | string | any | Note body. |
| `tracks[]` | list | — | All tracks for the song (including buses/aux). |
| `tracks[].id` | int | unique, ≥ 1, never reused | Stable internal track id (distinct from the `NN` sort number in the name). |
| `tracks[].original_name` | string | any | Name as it appeared in the tracking session. |
| `tracks[].new_name` | string | matches naming regex | Convention-compliant name. |
| `tracks[].category` | enum | `DR PRC BS GTR KEY SYN VOX BV FX MISC` | Category code (drives numbering and Phase 3 bus routing). |
| `tracks[].track_kind` | enum | `audio`, `instrument`, `bus`, `aux` | Track type; default `audio`. |
| `tracks[].group` | string | any | Optional label linking alternative layers / stereo pairs. |
| `tracks[].decision` | enum | `keep`, `cut`, `undecided` | Keep/cut mix decision. |
| `tracks[].hardware.type` | enum | `none`,`insert`,`external_instrument`,`sidechain`,`send` | Signal-path hardware dependency; default `none`. |
| `tracks[].hardware.io` | string | any | Free-text routing/gear note (nullable). |
| `tracks[].exports.dry.status` | enum | `pending`, `done`, `n/a` | Dry stem export status. |
| `tracks[].exports.dry.path` | string\|null | path | Resolved dry stem file path (nullable). |
| `tracks[].exports.wet.status` | enum | `pending`, `done`, `n/a` | Wet stem export status. |
| `tracks[].exports.wet.path` | string\|null | path | Resolved wet stem file path (nullable). |
| `tracks[].channel_strip_ref` | string\|null | path/note | Pointer to a Logic `.cst` whole-chain recall artifact. **Pointer only.** |
| `tracks[].effects_chain[]` | list | — | Ordered tracking effects (order = chain order). |
| `tracks[].effects_chain[].plugin` | string | any | **Required.** Plugin name. |
| `tracks[].effects_chain[].maker` | string | any | Optional vendor (e.g. `Logic`, `FabFilter`); matters for Ableton rebuild. |
| `tracks[].effects_chain[].preset` | string | any | Optional preset name. |
| `tracks[].effects_chain[].bypassed` | bool | true/false | Optional; default false. |
| `tracks[].effects_chain[].settings` | string | any | Optional free-text quick note (the few values that matter). |
| `tracks[].effects_chain[].params` | map | string→scalar | Optional structured named parameter values (stored as strings, units preserved). |
| `tracks[].effects_chain[].ref` | string\|null | path/note | Optional pointer to a saved preset/screenshot. **Pointer only.** |
| `tracks[].source.mic` | string | any | Microphone used (nullable). |
| `tracks[].source.performer` | string | any | Performer (nullable). |
| `tracks[].source.recorded` | string | date | Recording date (nullable). |
| `tracks[].source.takes` | int | ≥ 0 | Number of takes (nullable). |
| `tracks[].notes[]` | list | — | Track-level timestamped notes (appendable + editable). |

> **`id` invariant:** `id` is allocated from a per-song monotonic counter, is unique, and is **never reused** even after a track is removed. `renumber` only rewrites the `NN` prefix of `new_name`; it never touches `id`. External references (Phase 2 file→track maps, Phase 3 routing, agent plans) rely on this.

> **Ordering / git-friendliness:** the store writes keys in a stable, documented order and preserves track and effects-chain order, so diffs stay minimal and reviewable. Unknown keys added by hand are preserved (round-tripped), appended after known keys. YAML comments are **not** preserved (a known limitation of the two-dependency constraint, C-6).

## 8. Naming Convention Specification

### Format

```
NN_CAT_Descriptor[_Variant]
```

- **`NN`** — two-digit, CLI-assigned sort number. Chosen so that **alphabetical sort in any DAW = intended mix order.** Numbering follows category order (below), then track order within a category. If a song exceeds 99 tracks, `renumber` warns and continues (the validator flags the overflow).
- **`CAT`** — one of the fixed category codes.
- **`Descriptor`** — CamelCase, `[A-Za-z0-9]+`.
- **`_Variant`** — optional, repeatable (e.g. `_L`, `_R`, `_Double`); each segment `[A-Za-z0-9]+`. Stereo pairs use variants and share a `group`.
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
| 10 | `MISC` | Uncategorized / other / loops | `Talkback`, `Click`, `Loop` |

Category codes are a **stable, additive-only enum**: they are the join key Phase 3 uses to create buses, so codes are never renamed. Category order = numbering order.

### Validation regex

```
^\d{2}_(DR|PRC|BS|GTR|KEY|SYN|VOX|BV|FX|MISC)_[A-Za-z0-9]+(_[A-Za-z0-9]+)*$
```

(The regex is built in code from the canonical category list — single source of truth — not transcribed separately.)

### Validation severity (replaces the old `--strict` mode)

`validate` distinguishes **structural errors** from **style warnings** so exit codes are deterministic (FR-22) without a mode flag:

| Severity | Exit | Conditions |
|---|---|---|
| **ERROR** | non-zero | Unparseable YAML; missing required field; `schema_version` newer than supported; duplicate `tracks[].id`; duplicate `new_name`; unknown `category`; invalid enum value (`decision`, export `status`, `track_kind`, `hardware.type`, `export.realtime`, `mix_daw`). |
| **WARNING** | 0 | `new_name` fails the regex; missing `new_name`; `NN` gaps / out of order; workflow flag checked out of order; `mixprep_copy` equals/nested under `source_project`; `requires_realtime`-style mismatch (e.g. `done` with no stem path); empty `original_name`; group with zero `keep` or split stereo-pair decisions; `NN` overflow past 99. |

### How the commands use the convention

- **`suggest`** maps each messy `original_name` to a `category` and a CamelCase `Descriptor` via a deterministic, case-folded keyword table (first match in an ordered list wins; non-alphanumerics stripped from the descriptor so output is always regex-valid). Proposes a full `new_name`; human confirms (or `--auto` accepts all). It does not infer `_Variant` segments — add those via `set`.
- **`renumber`** recomputes every `NN` from category order + intra-category order (ordered by `(category_index, id)`), rewriting the leading digits of `new_name`. It skips/warns on names that don't already conform rather than string-splicing them, and warns if `renamed_in_daw` is true.
- **`validate`** applies the severity table above; `--all` validates every song.

## 9. CLI Command Specification

Global conventions:
- First positional argument is usually the song **slug**.
- Prompting commands accept `--yes`/`--auto` for non-interactive use (FR-20).
- Data-listing commands accept `--format json` returning the envelope `{ok, warnings, data}`; machine data → stdout, warnings/chatter → stderr (FR-21).
- All mutating commands accept `--dry-run` (FR-29).
- Guardrails **warn, never block** (FR-19). Exit `0` on success incl. warnings; non-zero only on hard/structural errors (FR-22, Section 8).

| Command | Arguments | Key flags | Behavior | Example |
|---|---|---|---|---|
| `new` | `<slug>` | `--title`, `--source`, `--copy`, `--daw`, `--sample-rate`, `--tempo`, `--dry-run` | Create `songs/<slug>/song.yaml` from `templates/song.yaml`; stamp `schema_version`; warn on source==copy. | `mixprep new ocean-floor --title "Ocean Floor" --daw ableton` |
| `add` | `<slug>` | `--bulk` (reads stdin), `--name`, `--category`, `--dry-run` | Add tracks with stable ids. `--bulk` ingests a pasted Logic track list (one per line) into `original_name`. | `pbpaste \| mixprep add ocean-floor --bulk` |
| `suggest` | `<slug>` | `--auto`/`--yes`, `--only-unnamed`, `--dry-run` | Propose convention names + category from originals; interactive confirm or auto-accept. | `mixprep suggest ocean-floor --auto` |
| `renumber` | `<slug>` | `--dry-run` | Recompute every `NN` from category + intra-category order; warn if `renamed_in_daw`. | `mixprep renumber ocean-floor` |
| `set` | `<slug> <track> key=value...` | `--dry-run` | Edit track fields, incl. **dotted paths** (`exports.wet.status=done`, `hardware.type=insert`, `group=LeadVox`). Type-coerced per field; warns on bad `new_name` (never auto-renumbers). | `mixprep set ocean-floor 21 decision=keep exports.wet.status=done` |
| `note` | `<slug>` | `--track <id>`, `--text`, `--edit <idx>`, `--dry-run` | Append (or edit) a timestamped note at song or track level. | `mixprep note ocean-floor --track 21 --text "comp 1+3"` |
| `fx` | `<slug> <track>` | `--add "plugin"`, `--maker`, `--preset`, `--bypassed`, `--settings`, `--param N=V` (repeatable), `--ref`, `--strip-ref`, `--bypass <idx>`, `--clear`, `--dry-run` | Append/clear effects-chain entries and set the track `channel_strip_ref`. `--param` splits on first `=`. | `mixprep fx ocean-floor 21 --add "Pro-C 2" --maker FabFilter --preset "Vocal Smooth" --param Ratio=3:1` |
| `check` | `<slug> <flag>` | `--dry-run` | Set a workflow flag true (warns if out of pipeline order). | `mixprep check ocean-floor exported_dry` |
| `uncheck` | `<slug> <flag>` | `--dry-run` | Set a workflow flag false. | `mixprep uncheck ocean-floor mixing_started` |
| `sheet` | `<slug>` | `--format` | Print a printable `original → new` rename sheet. | `mixprep sheet ocean-floor` |
| `status` | `<slug>` | `--format` | Print workflow flags, dry/wet export progress, keep/cut counts, the **real-time export banner**, and group rollups. | `mixprep status ocean-floor` |
| `tracks` | `<slug>` | `--format`, `--category`, `--decision`, `--group` | List tracks as a table (filterable). | `mixprep tracks ocean-floor --category VOX` |
| `validate` | `[<slug>]` | `--all`, `--format` | Validate per the Section 8 severity table. | `mixprep validate --all` |
| `list` | — | `--format` | List all songs in the repo (current phase, % exported, % decided). | `mixprep list` |
| `path` | `<slug>` | `--dir` | Print the manifest's absolute path (or song dir) to stdout, undecorated. | `$EDITOR "$(mixprep path ocean-floor)"` |

**Agent-operability requirements (call-out):**
- `suggest` must run fully unattended under `--auto`; `add --bulk` must accept piped stdin with no TTY and not hang on empty stdin.
- `status`, `tracks`, `list`, `sheet`, `validate`, `path` must offer the `--format json` envelope for the agent to parse, in addition to the default plain-text output.
- No command may require interactive input to complete its primary function when a non-interactive flag is supplied.
- A command that would need a prompt but has no TTY and no `--auto`/`--yes` must error clearly rather than block.

## 10. Workflow Pipeline (per song)

Ordered phases. Each maps to a `workflow` flag (Section 7). Order is **advisory** — checking out of order warns but is allowed (FR-19).

| Step | Flag | Entry criteria | Exit criteria | Owner (P1) |
|---|---|---|---|---|
| 1. Make safe copy | `copy_made` | Logic closed; original located. | A copy exists in `MixPrep/`; original locked; `mixprep_copy ≠ source_project`. | Human (manual) |
| 2. Inventory tracks | `tracks_inventoried` | `copy_made`. | All tracks in manifest with `original_name`. | Human via `add --bulk` |
| 3. Rename in DAW | `renamed_in_daw` | All tracks have valid `new_name` (via `suggest`+`renumber`, passes `validate`). | Tracks renamed in the copy to match `new_name`. | Human, guided by `sheet` |
| 4. Export dry stems | `exported_dry` | `renamed_in_daw`. | Each **non-cut** track's `exports.dry.status` = `done` (or `n/a`). | Human (manual export) |
| 5. Export wet stems | `exported_wet` | `renamed_in_daw`. | Each **non-cut** track's `exports.wet.status` = `done` (or `n/a`). | Human (manual export) |
| 6. Import to mix | `imported_to_mix` | Required stems exported. | Stems imported into the mix project (Phase 3: into the mix template). | Human |
| 7. Mixing started | `mixing_started` | `imported_to_mix`. | Mix in progress; keep/cut `decision`s being recorded. | Human |

### Manual safety + export procedure (Phase 1, macOS)

1. **Quit Logic Pro** so the project is not in use.
2. In **Finder**, select the `.logicx`, press **Cmd+D** to duplicate, move the duplicate into a `MixPrep` folder.
3. **Lock the original** via Finder → Get Info → "Locked".
4. **Only ever open the copy.** Record `copy_made`.

5. **Before exporting — real-time check.** Run `mixprep status <song>` and read the **Export mode** banner:
   - **"DRY: offline OK / WET: REAL TIME"** — you have hardware *inserts* (outboard comp/EQ). Bounce the DRY pass **Offline** (fast); for the WET pass you **must check "Bounce in Real Time"** or the outboard tracks will record silence/dry signal.
   - **"DRY + WET: REAL TIME"** — you have hardware *instruments*, *sidechains*, or hardware on a *send/return*. **Both** passes must be run with **"Bounce in Real Time" checked**.
   - For hardware *external instruments*, a "dry" stem is meaningless (no in-the-box signal to bypass) — set that track's `exports.dry.status: n/a`.
   - Note: "Export All Tracks as Audio Files" applies real-time to the **entire pass** — you cannot mix offline and real-time tracks in one run, so the whole run is slower; that is expected.

6. **Dry export:** in the copy, `File → Export → All Tracks as Audio Files`, with **"Bypass Effect Plug-ins" CHECKED**, **"Bounce in Real Time"** set per the banner, into `Exports/<song>/DRY/`. Record each track's `exports.dry.status`/`path`.
7. **Wet export:** repeat with **"Bypass Effect Plug-ins" UNCHECKED**, **"Bounce in Real Time" CHECKED if the banner requires it**, into `Exports/<song>/WET/`. Record each track's `exports.wet.status`/`path`.

(Phase 2 automates steps 2–3 with checksum-verified copies and watches the `DRY/`/`WET/` folders to update statuses and paths automatically.)

## 11. Constraints & Safety Requirements

- **C-1 Original protection.** mix-prep must never write to, move, rename, or delete a `source_project`. It is treated as read-only metadata. (Phase 1 makes no DAW/audio filesystem mutations whatsoever.)
- **C-2 Copy-only operation.** Any future automation (Phase 2+) operates exclusively on a **verified** `mixprep_copy`, never on the source. A copy is "verified" only after checksum/file-tree verification.
- **C-3 No audio/assets in repo.** The repository tracks **state, not stems.** Audio and referenced asset files (presets, screenshots, `.cst`) are never embedded or copied; manifests store only paths/pointers.
- **C-4 Warn, never block.** Advisory guardrails emit warnings but do not prevent the action. Non-zero exit is reserved for structural errors (Section 8).
- **C-5 Git-friendliness.** Plain-text YAML, stable key ordering, preserved track/effects order, round-tripped unknown keys — minimal, reviewable diffs.
- **C-6 Minimal dependencies.** Runtime deps limited to **PyYAML** and **click**; Python **3.9+**. Plain-text output (no rich-text rendering library). Installed via `pipx install --editable .` for the global `mixprep` command. (Comment preservation in YAML is therefore out of scope.)
- **C-7 Write scope.** mix-prep writes only within the repo, under `songs/<slug>/` (and its own docs/templates). It never writes outside the repo and never dereferences a stored pointer for writes.
- **C-8 Agent parity.** The agent operator uses the same CLI and manifests as the human; no separate privileged interface.
- **C-9 Source ≠ copy invariant.** `mixprep_copy` must never equal or be nested under `source_project`. Phase 1 warns at write time (FR-28); Phase 2 hard-refuses.

## 12. Success Criteria / Acceptance (Phase 1)

Phase 1 is accepted when:

- **A-1** `pipx install --editable .` yields a working global `mixprep` command.
- **A-2** A user can `new` a song, `add --bulk` a pasted Logic track list, `suggest` + `renumber` valid convention names, and `validate` with no errors.
- **A-3** Each track tracks independent dry/wet export status **and stem path** via the `exports` sub-object; `status` reports dry/wet progress (non-cut, `n/a`-aware), keep/cut counts, and group rollups.
- **A-4** `sheet` prints a correct `original → new` rename sheet; `tracks`, `status`, and `list` print scannable plain-text output.
- **A-5** All listed data/reporting commands offer the `--format json` envelope (machine→stdout, warnings→stderr); `suggest --auto` and `add --bulk` run fully non-interactively; mutators honor `--dry-run`. (Agent-operability.)
- **A-6** Manifests round-trip through the store with stable ordering and preserved unknown keys (clean git diffs); every manifest carries `schema_version`.
- **A-7** mix-prep performs **zero** mutations to any DAW project, audio file, or referenced asset; verified by the end-to-end test (`tests/test_e2e.py`) using a checksummed sentinel.
- **A-8** Guardrails warn but never block; `validate` exit codes follow the Section 8 severity table.
- **A-9** Hardware tracks drive a correct per-pass real-time banner in `status`; the Section 10 procedure reflects it.
- **A-10** The plugin-settings log records ordered chains with `plugin` + optional `maker`/`preset`/`bypassed`/`settings`/`params`/`ref` and a track-level `channel_strip_ref`, all as pointers (no asset files read/copied).
- **A-11** Repository layout matches the accepted structure: `pyproject.toml`, `README.md`, `.gitignore`, `docs/naming-convention.md`, `docs/phase2-roadmap.md`, `templates/song.yaml`, `src/mixprep/{cli,model,store,naming,report}.py`, `songs/<slug>/song.yaml`, `tests/test_e2e.py`.

## 13. Open Questions / Decisions to Revisit

- **Mix template structure (Phase 3).** Exact bus/group topology, naming of category buses, default routing/sends, and whether to ship Ableton-only first or both DAWs. How closely should template groups mirror the 10 category codes vs. a coarser bus set?
- **Pro Tools (and other DAWs) support.** Should the model later support Pro Tools / other DAWs as tracking or mix targets? Current enum is `ableton | logic` only. (Treat unknown `mix_daw` values as unsupported, not crashing.)
- **Local-LLM choice for the harness (Phase 3).** Which local model (and runtime) to support alongside Claude, and how the harness authenticates / sandboxes filesystem access while respecting C-1/C-2.
- **Logic project parsing.** Logic's project format is not openly documented; auto-inventory/verify for Logic may be limited to UI scripting. Is UI scripting acceptable, or is Ableton-only auto-parsing sufficient for Phase 2?
- **Stem-to-track matching.** For export-folder watching (Phase 2), how strictly must exported filenames match `new_name`, and how to handle multi-file (e.g. `_L`/`_R`) or grouped exports. (The `exports.<dir>.path` field captured in Phase 1 is the anchor.)
- **Effects-chain `slot` numbers.** Phase 1 uses list order as the chain order. Revisit whether explicit insert-slot numbers (incl. empty slots) are needed for hardware-mixer recall.
- **Plugin-settings capture (`mixprep shots`) — design largely settled (see Phase 2 roadmap), open items remain:** the precise UI-scripting recipe per Logic version, whether to ship native-format capture (`.cst`/`.aupreset`) as fully manual-with-pointer-recording vs. menu-driven first, and whether to add the optional per-plugin `slot` index to make shot↔chain mapping explicit rather than positional.

### Resolved in 0.2.0
- **Structured output format:** JSON envelope `{ok, warnings, data}` confirmed as the `--format json` target; `schema_version` field added.
- **Note editing semantics:** editing a note preserves the original `ts`; an optional `edited` timestamp may be added by `note --edit` (non-load-bearing).
- **`edit` command:** removed in favor of `path` (agent-operable).
- **`validate --strict`:** removed in favor of the structural-error vs style-warning severity table.

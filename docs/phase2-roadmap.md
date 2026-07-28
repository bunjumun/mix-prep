# Roadmap: Phase 2 (automation) and Phase 3 (mix template + LLM harness)

> Forward plan. The authoritative scope is `docs/SPEC.md` §5; this document is about *how we intend to get there* and *what we already know will be hard*. Nothing here is built yet.

## Where Phase 1 leaves us

Phase 1 gives you a complete, honest notebook. You make the safe copy by hand, you paste in the track list, mix-prep proposes and enforces the names, you bounce the two passes in Logic, and you type in what happened. Every command that could touch a DAW project deliberately doesn't — mix-prep makes **zero** filesystem changes to projects or audio.

The manual steps that survive Phase 1 are the ones Phase 2 targets, in the order they cost you the most time:

1. Duplicating the project in Finder and trusting that the duplicate is complete.
2. Typing `exports.dry.status=done` and a path, once per track, twice per song.
3. Confirming that the names you typed into the DAW actually match the manifest.
4. Writing down plugin settings by hand before you close the tracking project.

## Phase 2 — Automation

### 1. Scripted safe copies, checksum-verified

A command that duplicates a `.logicx` into a `MixPrep` folder and then **proves** the copy is good before recording `copy_made`: walk the source file tree, walk the copy's tree, compare the structure, and compare a checksum for every file. Only on a clean comparison does the manifest get updated. A `.logicx` is a package directory, not a single file — a truncated or partially-copied bundle can open and look fine until the take you needed is missing, so structural equality is not enough on its own.

The direction of travel is strictly one-way: the command writes only into the copy destination and never into the source path, no matter what. The Phase 1 `source ≠ copy` guard (C-9) — which today prints a loud warning and carries on — becomes a **hard pre-flight refusal** the moment a command can write files. Warning is the right behaviour for a notebook; it is the wrong behaviour for something holding a copy operation.

Open question: whether to verify with a full content checksum (slow, certain) or size-plus-mtime with checksums on a sample (fast, probabilistic). Given how rarely you copy a project and how much a bad copy costs, the plan is full checksums with a progress report.

### 2. Export-folder watching

Watch `Exports/<song>/DRY/` and `Exports/<song>/WET/`. As files land, match each one to a track by name and fill in that track's `exports.<dir>.status` and the resolved `exports.<dir>.path`. When every non-cut track in a direction is satisfied, tick the corresponding `exported_dry` / `exported_wet` workflow flag.

This is the single biggest ergonomic win in Phase 2 and it costs nothing structurally, because Phase 1 already stores exactly the two fields the watcher needs to write. It's also the payoff for the naming convention: filename-to-track matching is only reliable because every track has a unique, regex-validated `new_name` and Logic names exported files after tracks.

The known-hard part is matching tolerance — how strictly must a filename equal a `new_name`? Logic appends and substitutes characters in some export modes, stereo pairs may arrive as one interleaved file or two, and grouped exports produce one file for several tracks. The plan is strict matching first with an explicit report of unmatched files, rather than fuzzy matching that quietly attaches the wrong stem to the wrong track.

### 3. Ableton `.als` parsing

Ableton project files are gzipped XML — genuinely readable, no reverse engineering required beyond decompressing and walking the tree. Two features come out of that:

- **Auto-inventory.** Read the tracks out of an existing `.als` and populate the manifest, instead of pasting a list from the clipboard.
- **Rename verification.** Compare the track names in the project against the manifest's `new_name` values and report the differences — so `renamed_in_daw` becomes something mix-prep can confirm rather than something you assert.

Both are read-only operations on a copy, consistent with C-1/C-2.

**Logic gets none of this**, and that asymmetry is worth stating plainly: Logic's project format is not a documented open format, and we are not going to guess at it. Logic automation is limited to UI scripting (AppleScript / Accessibility), which is out of scope for anything claiming to be reliable parsing. For Logic, inventory and rename verification stay manual — `add --bulk` and your own eyes.

### 4. `mixprep shots` — capturing plugin settings

The goal: recall a track's plugin chain in the mix DAW without having had to write every parameter down by hand. The design is deliberately **ordered by reliability**, not by how impressive it sounds, because a capture step that fails silently is worse than no capture step at all.

**The constraint that shapes everything:** Logic Pro exposes no real scripting API. The single documented hook is `renderpreview`. The only programmatic way to open a plugin window and read it is macOS Accessibility / UI scripting, and driving that in a loop across a whole session is fragile — realistically about **4/10**, and about **3/10 unattended**, because macOS Sequoia re-prompts for Screen Recording consent and steals focus in ways a long unattended loop cannot survive. Any design that puts UI scripting on the critical path inherits those odds.

So:

**Tier 1 — native saves first (early Phase 2, high reliability).**

Let the DAW write its own recall artifacts and have mix-prep record where they are:

- **Logic Channel Strip Setting (`.cst`)** — the whole chain in one file, exact recall Logic→Logic. Goes in the track's existing `channel_strip_ref`.
- **Per-plugin AU preset (`.aupreset`)** — per-plugin recall within the Apple/AU world. Goes in that chain entry's `ref`.
- **The plugin's own vendor preset** — for the Logic→**Ableton** path this is the portable artifact, because it loads in any host that has the plugin. This is the one that matters most for the user's actual workflow.

Crucially, tier 1 works even with zero automation: you save the presets from the plugin's own menu, and mix-prep records the pointers. The command can then progress from "record the pointer I give you" to "drive the Save-As menu item for me" without changing anything about the data model.

**Tier 2 — screenshots as a visual supplement (late Phase 2 / Phase 3, behind the LLM harness).**

For each non-bypassed plugin: open its window via UI scripting, resolve the window's CGWindowID, `screencapture -l -o`, save the PNG. The *capture* half is reliable (≈8/10 once the window is open and identified); the *open-it-in-a-loop* half is the 4/10. Therefore it runs **attended by default**, reports per-plugin success and failure in the JSON envelope so nothing fails silently, and falls back to the Phase 1 manual settings log wherever it misses.

**Why screenshots still matter, regardless of how well tier 1 works.** They are the *only* recall for three things a preset file cannot carry:

- **Outboard hardware front panels.** There is no preset for a Distressor. There is a photograph of its knobs.
- **Logic stock plugins with no Ableton equivalent.** A `.cst` full of Logic Channel EQ and Space Designer settings is inert once you're mixing in Ableton. A picture of the curve is not.
- **Smart Controls and automation context** — the mapped macro layer and the surrounding automation, which live outside the individual plugin's saved state.

**Layout.** Artifacts mirror the export tree, so everything for one song lives together:

```
Exports/<song>/PluginShots/<new_name>/00_ChannelStrip.cst
Exports/<song>/PluginShots/<new_name>/NN_<plugin>.png
Exports/<song>/PluginShots/<new_name>/NN_<plugin>.aupreset
```

`NN` here is the plugin's index in the track's `effects_chain` list, so a shot maps back to a chain entry positionally. (Whether to replace that with an explicit per-plugin `slot` field — which would also let the chain represent empty insert slots — is an open question in SPEC §13.)

**Hard safety pre-flight.** Before it does anything at all, `shots` must positively confirm that the project currently open in Logic resolves to that song's `mixprep_copy`. If it can't confirm that, or the answer is the source project, it **aborts**. No prompting, no "are you sure" — abort. This is the same rule as C-1/C-2/C-9, restated for a command that drives the UI of a running DAW. The command also requires macOS Screen Recording and Accessibility consent, which the user grants once per machine.

**Verdict:** `shots` complements the Phase 1 manual settings log; it never replaces it. The hand-written `effects_chain` stays the DAW-independent, searchable, git-friendly source of truth — it is readable in ten years, on any machine, without Logic installed. Screenshots and presets are attachments to it.

### 5. What Phase 2 will not do

- Parse Logic project files.
- Write anything into a source project, under any circumstances.
- Copy audio, presets or screenshots into the repo. Pointers only, forever (C-3).
- Bounce audio. Logic does the bouncing; mix-prep tells you which switches to set and records the result.

## Phase 3 — Mix template generation and the LLM harness

### Mix template generation

Produce a ready-made mixing project — Ableton `.als` first, given the user's target DAW, and Logic after — with the **category buses already created and routed**. The bus topology comes straight from the ten category codes: a drum bus, a percussion bus, a bass bus, and so on, wired up before a single stem is imported.

Then import and route the song's stems automatically, driven entirely by fields Phase 1 already collects:

- `category` decides which bus a stem lands on.
- `decision` filters the import: `cut` tracks never make it into the template, so you open a session containing only the layers that survived.
- `exports.<dir>.path` says which file to import — and because it's per-direction, the generator can build a dry-stem session, a wet-stem session, or both.
- `group` keeps stereo pairs and layer stacks together.

Open question (SPEC §13): whether the template's groups should mirror all ten category codes one-for-one, or collapse into a coarser bus set that's more like how you'd actually build a mix by hand.

### The Claude / local-LLM harness

An agent that drives the same `mixprep` CLI a human drives — no private API, no privileged interface (C-8). Realistic jobs for it:

- Running `suggest` over a messy inventory and proposing better descriptors than a keyword table can, using musical context.
- Reading `status` and `validate` output and telling you what to do next in a sentence, rather than a table.
- Recording keep/cut decisions and notes as you say them out loud during a mix.
- Ticking off workflow steps and catching when you've skipped one.
- Driving the template generator and, eventually, the attended `shots` runs.

The open items are which local model and runtime to support alongside Claude, and how the harness authenticates and sandboxes its filesystem access — because an agent with write access to your drives is exactly the thing C-1 and C-2 exist to constrain. The harness must be unable to reach a `source_project`, structurally, not by good intentions.

## Why none of this needs new data plumbing

Phase 1 was designed backwards from this roadmap. Every hook the later phases need is already in the manifest and the CLI:

- **`schema_version`** — stamped on every manifest, and the store refuses to read a version it doesn't understand. Phase 2 can evolve the schema without a Phase 2 tool silently mis-reading a Phase 1 file, or vice versa.
- **Never-reused track `id`s** — a permanent handle for every track, independent of naming and renumbering. The Phase 2 file→track map, the Phase 3 routing table and any agent plan can all point at an `id` and be certain it still means the same track next month.
- **`exports.<dir>.path`** — already a per-direction, per-track field. The export watcher fills it in; the template generator reads it back out. Neither needs a new field.
- **`ref` and `channel_strip_ref`** — already present on every chain entry and every track, already documented as pointers. `shots` writes paths into them and the schema doesn't change at all.
- **The JSON envelope** — `{ok, warnings, data}` on stdout with warnings on stderr, on every reporting command. The harness parses that; it never has to scrape a human-readable table.
- **`--dry-run` on every mutator** — an agent (or a cautious human) can compute the full consequence of a command before committing to it. For anything that eventually touches the filesystem, that's the difference between a plan and an accident.

Phase 3 is additive. The manifest you're writing today is the one it will read.

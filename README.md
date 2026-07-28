# mix-prep

**A text-based organisation system for getting a song out of Logic Pro and into a mix session — without ever touching the original project.**

You track songs in Logic across many sessions. Then, months later, you want to mix — in Ableton or in a clean Logic project. That means: figuring out what all these tracks actually are, giving them names that sort themselves, bouncing a **dry** stem (effects bypassed) and a **wet** stem (tracking effects intact) of each one, remembering which plugins were on what, and keeping track of which of your six vocal layers survived.

mix-prep is the notebook for all of that. One plain-text file per song (`songs/<slug>/song.yaml`), and one command — `mixprep` — to read and write it.

## What mix-prep is not

This matters as much as what it is:

- **It is not a DAW.** It never opens, plays, or renders a project.
- **It does not bounce audio.** You do the exports in Logic, by hand. mix-prep tells you *what* to export and *how* (offline or real-time), then records that you did it.
- **It stores no audio.** Not one sample lives in this repo. Stems live wherever you keep them — internal drive, external drive, wherever. The manifest stores their *paths*, not their contents.
- **It does not copy or embed your presets and screenshots either.** A `.cst` channel-strip setting or an `.aupreset` is stored as a path — a pointer. mix-prep never opens it.
- **It never, ever touches your original Logic projects.** In Phase 1 mix-prep performs *zero* filesystem changes to any DAW project or audio file. The only files it writes are its own manifests under `songs/`.
- **It is not a backup tool.** It does not protect your stems or projects from loss. Keep backing up as you already do.

## Install

You need Python 3.9 or newer (macOS ships with a usable Python 3; `python3 --version` will tell you). The only two libraries mix-prep uses are `click` and `PyYAML`, and they install automatically.

```bash
brew install pipx          # once, if you don't have pipx
pipx ensurepath            # once — puts pipx's commands on your PATH

cd /path/to/mix-prep
pipx install --editable .
```

That gives you a global `mixprep` command you can run from any folder. `--editable` means the install points back at this repo, so if the code here is updated you get it immediately without reinstalling.

Check it worked:

```bash
mixprep --help
mixprep list
```

---

# Walkthrough: one song, start to finish

This is the whole thing, end to end, for a song called **Ocean Floor** — 20 tracks recorded across half a dozen Logic sessions, being moved into Ableton to mix. Every command below is copy-pasteable; change the slug and paths to match your song.

### Step 0 — Make the safe copy (you do this in Finder, not in mix-prep)

1. **Quit Logic Pro.** The project must not be in use.
2. In Finder, select `Ocean Floor.logicx`, press **Cmd+D** to duplicate it, and move the duplicate into a folder called `MixPrep`.
3. Select the **original** → **Cmd+I** (Get Info) → tick **Locked**.
4. From now on, **only ever open the copy.**

Locking the original is the point of the whole exercise. mix-prep is a notebook — it cannot physically stop Logic from writing to a file. The Finder lock can. If you ever open the wrong project by accident, Logic will refuse to save and tell you so, instead of quietly overwriting six months of tracking.

### Step 1 — Create the manifest

```bash
mixprep new ocean-floor \
  --title "Ocean Floor" \
  --source "/Volumes/Music/Logic/Ocean Floor.logicx" \
  --copy   "/Volumes/Music/MixPrep/Ocean Floor.logicx" \
  --daw ableton \
  --sample-rate 48000 \
  --tempo 92
```

This writes `songs/ocean-floor/song.yaml`. `--source` is the original (recorded as read-only metadata and never followed), `--copy` is the duplicate you just made. If those two paths are the same — or the copy is sitting *inside* the original — mix-prep warns loudly. It will still create the manifest (mix-prep warns, it doesn't block), but fix it before you go further.

Now tick off the copy step:

```bash
mixprep check ocean-floor copy_made
```

### Step 2 — Inventory the tracks

Open the **copy** in Logic, select all tracks in the track list, and copy the names (or type them out). Then paste them straight into mix-prep from the clipboard:

```bash
pbpaste | mixprep add ocean-floor --bulk
```

One line becomes one track. Each track gets its messy Logic name stored as `original_name`, plus a permanent numeric `id` that is never reused for anything else, ever. For Ocean Floor the paste looked like this — tracks in the order they happened to accumulate over the sessions:

```
Vox Lead comp
Ac Gtr rhythm L
Ac Gtr rhythm R
Kick In
Kick Out
Snare Top
Snare Btm
OH L
OH R
Bass DI
Bass Amp
Rhodes
Vox double
BGV high
BGV low
Shaker
Riser fx
Room mic
Pad synth
Elec gtr lead
```

```bash
mixprep check ocean-floor tracks_inventoried
```

You can also add tracks one at a time when you remember one you missed:

```bash
mixprep add ocean-floor --name "Tambourine overdub" --category PRC
```

### Step 3 — Let mix-prep propose names

```bash
mixprep suggest ocean-floor
```

It walks the list, proposes a category and a tidy name for each track, and waits for you to accept or correct. To take every suggestion without being asked:

```bash
mixprep suggest ocean-floor --auto
```

Suggestions come from a keyword table: `kick`/`snare`/`OH` → `DR`, `bgv`/`harm` → `BV`, `riser` → `FX`, and so on. It is deterministic, not clever — it will get most things right and a few things comically wrong, which is why the interactive mode exists. The full table is in [`docs/naming-convention.md`](docs/naming-convention.md).

### Step 4 — Renumber so the tracks sort themselves

```bash
mixprep renumber ocean-floor
```

This is the moment the naming convention earns its keep. `renumber` sorts every track by category (drums, percussion, bass, guitar, keys, synths, lead vox, backing vox, FX, misc) and rewrites the two-digit prefix on each name. The result: **alphabetical sort in any DAW = your intended mix order.** Import the stems anywhere, sort by name, and the drums are at the top and the ear candy is at the bottom.

Notice that the track ids and the `NN` prefixes are *not* the same number. The lead vocal was the first track pasted (`id: 1`) but sorts to `16_VOX_...`. The id is a permanent handle for commands; the `NN` is a sorting device that `renumber` is free to rewrite whenever the track list changes.

Now tidy up the names `suggest` got clumsy about, using `set`. `suggest` deliberately never invents `_Variant` suffixes, so a stereo pair arrives as two unrelated descriptors — fix them into a proper pair with a shared `group`:

```bash
mixprep set ocean-floor 1  new_name=16_VOX_Lead
mixprep set ocean-floor 10 new_name=09_BS_DI
mixprep set ocean-floor 2  new_name=11_GTR_AcousticRhythm_L group=AcGtrRhythm
mixprep set ocean-floor 3  new_name=12_GTR_AcousticRhythm_R group=AcGtrRhythm
```

The lead vocal went through an outboard compressor on the way in, so record that now — it changes how you have to export later:

```bash
mixprep set ocean-floor 1 hardware.type=insert hardware.io="out 5/6 -> Distressor -> in 5/6"
```

Not sure what a command will do? Every command that writes takes `--dry-run`:

```bash
mixprep renumber ocean-floor --dry-run
```

### Step 5 — Validate

```bash
mixprep validate ocean-floor
```

Two kinds of finding come back. **ERRORs** are structural (a duplicate track id, an unknown category, a typo'd enum) and exit non-zero — fix them. **WARNINGs** are style and consistency (a name that doesn't match the convention, a gap in the numbering, a group where every layer got cut) and exit zero — read them, act if you agree.

### Step 6 — Print the rename sheet

```bash
mixprep sheet ocean-floor
```

A two-column `original → new` list you work through in the DAW. It looked like this:

```
id   original_name        new_name
---  -------------------  ------------------------
  4  Kick In              01_DR_KickIn
  5  Kick Out             02_DR_KickOut
  6  Snare Top            03_DR_SnareTop
  7  Snare Btm            04_DR_SnareBtm
  8  OH L                 05_DR_OHL
  9  OH R                 06_DR_OHR
 18  Room mic             07_DR_RoomMic
 16  Shaker               08_PRC_Shaker
 10  Bass DI              09_BS_DI
 11  Bass Amp             10_BS_BassAmp
  2  Ac Gtr rhythm L      11_GTR_AcousticRhythm_L
  3  Ac Gtr rhythm R      12_GTR_AcousticRhythm_R
 20  Elec gtr lead        13_GTR_ElecGtrLead
 12  Rhodes               14_KEY_Rhodes
 19  Pad synth            15_SYN_PadSynth
  1  Vox Lead comp        16_VOX_Lead
 13  Vox double           17_VOX_VoxDouble
 14  BGV high             18_BV_BGVHigh
 15  BGV low              19_BV_BGVLow
 17  Riser fx             20_FX_RiserFx
```

### Step 7 — Rename in the DAW, then check it off

In the **copy** (never the original), double-click each track name in Logic's track list and type the new name. Then:

```bash
mixprep check ocean-floor renamed_in_daw
```

Do the renaming *before* you export: Logic names the exported files after the tracks, so renaming first is what makes your stem filenames match your manifest.

> Once `renamed_in_daw` is true, `renumber` will warn if you run it again — the names in the DAW would no longer match the manifest. If you do need to renumber after this point, re-run `sheet` and fix the names in Logic too.

### Step 8 — Read the real-time banner before you bounce

```bash
mixprep status ocean-floor
```

Look for the **Export mode** line:

```
Export mode: DRY: offline OK / WET: REAL TIME
  reason: track 1 (16_VOX_Lead) hardware.type=insert -> wet pass
```

That banner is the whole reason mix-prep asks about hardware. Real-time is a setting for the *entire* export pass in Logic — you can't mix offline and real-time tracks in one run — so mix-prep works it out per pass and tells you:

- **`DRY + WET: offline OK`** — nothing leaves the computer. Bounce both passes offline, fast.
- **`DRY: offline OK / WET: REAL TIME`** — you have outboard gear on an **insert** (a hardware comp or EQ). The dry pass bypasses that insert, so it can run offline. The wet pass **must** have *Bounce in Real Time* ticked, or those tracks record silence or an untreated signal.
- **`DRY + WET: REAL TIME`** — you have a hardware **instrument**, a **sidechain**, or hardware on a **send/return**. Both passes must be real-time. Put the kettle on.

For hardware **external instruments** — a real synth on the desk, played back through the interface — there is no in-the-box signal to bypass, so a dry stem is meaningless. `status` lists any such track that isn't marked yet, and you mark it like this (if Ocean Floor's pad had been a hardware Prophet on track 19):

```bash
mixprep set ocean-floor 19 hardware.type=external_instrument
mixprep set ocean-floor 19 exports.dry.status=n/a
```

If you know the whole song has to bounce in real time regardless of what the tracks say, set the song-level `export.realtime` to `force` (or `off` to suppress the advice entirely). That is a song field rather than a track field, so edit it in the manifest:

```bash
$EDITOR "$(mixprep path ocean-floor)"     # export: → realtime: force
```

### Step 9 — The DRY export

In the **copy**, in Logic:

**File → Export → All Tracks as Audio Files**, then:

- **"Bypass Effect Plug-ins" — CHECKED** ← this is what makes it dry
- **"Bounce in Real Time"** — set per the banner (unticked for Ocean Floor's dry pass)
- Destination: `Exports/Ocean Floor/DRY/`

Dry stems are the ones you actually mix with: clean signal, so you can rebuild the processing properly in the focused mix environment.

### Step 10 — The WET export

Same dialog, same tracks, different switches:

- **"Bypass Effect Plug-ins" — UNCHECKED** ← tracking effects intact
- **"Bounce in Real Time" — CHECKED** (the banner said WET: REAL TIME, because of the Distressor)
- Destination: `Exports/Ocean Floor/WET/`

Wet stems are your A/B reference — "what did it sound like when I recorded it?" — and your safety net if a dry track turns out to have depended on the tracking chain.

Note there is no `_DRY` or `_WET` in any track name. **Dry and wet are carried by the destination folder, not the filename.** One name, two folders, so the same stem name lines up across both passes.

### Step 11 — Record what got exported

```bash
mixprep set ocean-floor 1 \
  exports.dry.status=done \
  exports.dry.path="/Volumes/Music/Exports/Ocean Floor/DRY/16_VOX_Lead.wav"

mixprep set ocean-floor 1 \
  exports.wet.status=done \
  exports.wet.path="/Volumes/Music/Exports/Ocean Floor/WET/16_VOX_Lead.wav"
```

Each track carries its own `exports.dry` and `exports.wet`, each with a `status` (`pending`, `done` or `n/a`) and the resolved stem `path`. When every non-cut track is `done` or `n/a`, tick the song-level flags:

```bash
mixprep check ocean-floor exported_dry
mixprep check ocean-floor exported_wet
```

(Yes, that is a lot of typing for 20 tracks. Phase 2 watches the `DRY/` and `WET/` folders and fills this in for you — see [`docs/phase2-roadmap.md`](docs/phase2-roadmap.md).)

### Step 12 — Log the plugin chains you'll want to rebuild

Before you close the tracking project, write down what was on the tracks. In chain order:

```bash
mixprep fx ocean-floor 1 --add "Channel EQ" --maker Logic \
  --settings "HPF 90Hz, -3dB @ 350, +4dB @ 10k"

mixprep fx ocean-floor 1 --add "Pro-C 2" --maker FabFilter --preset "Vocal Smooth" \
  --param Ratio=3:1 --param Threshold="-22 dB" --param Attack="8 ms" \
  --settings "gentle leveling, ~3dB GR" \
  --ref "/Volumes/Music/MixPrep/presets/leadvox_proc2.aupreset"

mixprep fx ocean-floor 1 --add "Distressor" --maker "Empirical Labs (hardware)" \
  --settings "Dist 3, ~4-6dB GR — OUTBOARD insert, see hardware.io" \
  --ref "/Volumes/Music/MixPrep/presets/leadvox_distressor.jpg"
```

The list order *is* the signal chain order. `--ref` and `--strip-ref` store paths to things you saved yourself — an `.aupreset`, a photo of the outboard front panel, a Logic Channel Strip Setting:

```bash
mixprep fx ocean-floor 1 --strip-ref "/Volumes/Music/MixPrep/presets/OceanFloor_LeadVox.cst"
```

mix-prep only records where those files are. It never reads, copies or moves them.

### Step 13 — Notes, as you go

```bash
mixprep note ocean-floor --text "Second chorus needs the doubled vocal resolved."
mixprep note ocean-floor --track 1 --text "Best take is a comp of 1 and 3."
```

Notes are timestamped automatically and appended. Song-level notes go on the song; `--track` puts them on a track. Use these rather than YAML comments — mix-prep rewrites the manifest on every change and comments are not preserved.

### Step 14 — Keep and cut, as the mix takes shape

Import the stems, start mixing, and record the decisions as you make them:

```bash
mixprep check ocean-floor imported_to_mix
mixprep check ocean-floor mixing_started

mixprep set ocean-floor 1  decision=keep     # 16_VOX_Lead
mixprep set ocean-floor 13 decision=cut      # 17_VOX_VoxDouble — too much in the chorus
mixprep set ocean-floor 11 decision=keep     # 10_BS_BassAmp
mixprep set ocean-floor 10 decision=cut      # 09_BS_DI — amp won
```

Three months from now you will not remember why the DI got cut. Pair the decision with a note:

```bash
mixprep note ocean-floor --track 10 --text "Cut: amp track has the low mids, DI was mud."
```

Cut tracks stop counting against your export progress, and `status` warns about groups where every layer got cut or where a stereo pair got split.

### Step 15 — Where am I?

```bash
mixprep status ocean-floor
```

Workflow flags, dry/wet export progress, keep/cut counts, the real-time banner, and group rollups. Across all songs:

```bash
mixprep list
mixprep tracks ocean-floor --category VOX
mixprep tracks ocean-floor --decision undecided
```

And when you want to hand-edit the manifest in a text editor:

```bash
$EDITOR "$(mixprep path ocean-floor)"
```

---

## Command reference

| Command | What it does |
|---|---|
| `mixprep new <slug>` | Create `songs/<slug>/song.yaml` from the template; records title, source, copy, DAW, sample rate, tempo. |
| `mixprep add <slug>` | Add tracks — `--bulk` reads a pasted Logic track list from stdin, or `--name` adds one. |
| `mixprep suggest <slug>` | Propose a category and convention-compliant name for each track; `--auto` accepts all. |
| `mixprep renumber <slug>` | Recompute every `NN` prefix from category order so alphabetical sort equals mix order. |
| `mixprep set <slug> <track> key=value...` | Edit any track field, including dotted paths like `exports.wet.status=done`. |
| `mixprep note <slug>` | Append (or `--edit`) a timestamped note at song level or on a `--track`. |
| `mixprep fx <slug> <track>` | Append entries to a track's effects chain, or set its `channel_strip_ref`. |
| `mixprep check <slug> <flag>` | Tick a workflow flag (warns if you're skipping ahead). |
| `mixprep uncheck <slug> <flag>` | Untick a workflow flag. |
| `mixprep sheet <slug>` | Print the printable `original → new` rename sheet. |
| `mixprep status <slug>` | Workflow, export progress, keep/cut counts, real-time banner, group rollups. |
| `mixprep tracks <slug>` | List tracks as a table; filter by `--category`, `--decision`, `--group`. |
| `mixprep validate [<slug>]` | Check the manifest against the convention and schema; `--all` for every song. |
| `mixprep list` | List every song in the repo with phase, % exported, % decided. |
| `mixprep path <slug>` | Print the manifest's absolute path (or `--dir` for the song folder), undecorated. |

Every command that writes accepts `--dry-run`. Every command that prompts accepts `--auto` / `--yes`.

## Safety model

mix-prep's promises about your projects, in plain language:

- **Your originals are never touched.** mix-prep will never write to, move, rename or delete a project, an audio file, or anything else it has a path for. In Phase 1 it makes *no* changes to DAW files at all — it only ever writes its own manifests under `songs/<slug>/`. `source_project` is read-only metadata: a string it prints back at you, never a file it opens.
- **Only the copy gets opened.** Everything you do — renaming, exporting, mixing — happens in `mixprep_copy`. Any future automation (Phase 2) will operate only on a copy it has verified with checksums, never on the source.
- **Source ≠ copy.** `mixprep_copy` must never be the same path as `source_project`, and must never live inside it. Phase 1 warns loudly if it does; Phase 2 will refuse to run.
- **Lock the original in Finder.** Get Info → Locked. mix-prep can warn, but it cannot physically stop another app from writing to your project. The Finder lock can, and it is your real seatbelt. Do it once per song and forget about it.
- **No audio, no assets in the repo.** The manifest holds paths and statuses. Stems, presets, screenshots and `.cst` files stay on your drives, wherever you put them, untouched and un-copied.
- **mix-prep writes inside the repo only.** It never writes outside it, and it never follows a stored pointer in order to write something.

## For agents / automation

mix-prep is built so a Claude or local-LLM harness can drive the exact same CLI the human uses — no private API, no separate interface.

- **Structured output.** `status`, `sheet`, `tracks`, `list`, `validate` and `path` accept `--format json` and emit the envelope `{"ok": bool, "warnings": [...], "data": ...}`. Read commands include `schema_version` in `data`.
- **Clean streams.** Machine-readable output goes to **stdout**; human chatter and warnings go to **stderr**. Piping stdout into a parser is always safe.
- **Deterministic exit codes.** `0` on success, *including* when there are advisory warnings. Non-zero only for hard, structural errors — bad YAML, a missing required field, a duplicate id, an unknown category, an unsupported `schema_version`.
- **Nothing blocks.** Guardrails warn rather than refuse. Any command that would prompt runs unattended with `--auto` / `--yes`; `add --bulk` reads piped stdin without a TTY and does not hang on empty or closed input. A command that genuinely needs input and has neither a TTY nor `--yes` errors clearly instead of hanging.
- **Look before you leap.** Every mutating command takes `--dry-run` — it computes and reports the change it *would* make and writes nothing.
- **Finding the file.** `mixprep path <slug>` prints the manifest's absolute path with no decoration, and `--dir` prints the song folder. That is the supported way to locate a manifest for direct reading.

```bash
mixprep status ocean-floor --format json | jq '.data.exports'
mixprep validate --all --format json
cat "$(mixprep path ocean-floor)"
```

## What's next

**Phase 2 — automation.** Scripted safe copies that verify themselves with per-file checksums before recording `copy_made`, and a watcher on `Exports/<song>/DRY/` and `WET/` that fills in each track's export status and stem path as the files appear — so Step 11 above stops being manual. Ableton's `.als` project files are gzipped XML, so mix-prep will be able to read them directly to auto-inventory tracks and confirm your renaming actually landed. Phase 2 also brings `mixprep shots`, which captures plugin settings as recallable artifacts — native Logic channel-strip and AU presets first, screenshots as a supplement for outboard gear and stock plugins that have no Ableton equivalent.

**Phase 3 — mix template + LLM harness.** Generate a ready-made mixing project with the category buses already built and routed from your category codes, then import and route each song's stems into the right group automatically, skipping the tracks you cut. And a Claude / local-LLM harness that drives this same CLI: proposing names, recording decisions, ticking off workflow steps, and building the template — using the same manifests you use, with the same safety guarantees.

Details in [`docs/phase2-roadmap.md`](docs/phase2-roadmap.md).

## Documentation

- [`docs/naming-convention.md`](docs/naming-convention.md) — the naming format, category codes, and how `suggest`/`renumber` use them.
- [`docs/phase2-roadmap.md`](docs/phase2-roadmap.md) — what Phases 2 and 3 will add.
- [`docs/SPEC.md`](docs/SPEC.md) — the full technical specification.
- [`templates/song.yaml`](templates/song.yaml) — an annotated, empty manifest.

# The mix-prep track naming convention

> Reference for `docs/SPEC.md` §8. If this document and the spec ever disagree, the spec wins.

## The one-sentence reason this exists

**Alphabetical sort in any DAW = your intended mix order.**

That's it. Every rule below serves that sentence. Import twenty stems into Ableton, or Logic, or anything else, sort the browser by name, and the drums are at the top, the ear candy is at the bottom, and the stereo pairs are next to each other. No dragging tracks around for ten minutes before you can start mixing. No wondering whether `Audio 14` is a tambourine or a second snare mic.

The secondary payoff: your exported stem filenames come from your track names, so a consistent naming convention means your `DRY/` and `WET/` folders line up file-for-file, and Phase 2's export watcher can match a file back to a track automatically.

## The format

```
NN_CAT_Descriptor[_Variant]
```

Four pieces, separated by underscores.

### `NN` — the sort number

Two digits, always. `01`, not `1`. mix-prep assigns it — you never pick it yourself.

`renumber` sorts the whole song by category order (drums first, misc last), then by track id within each category, and stamps `01`, `02`, `03`… straight through the song. The two digits are what makes the sort work: a plain `1, 2, … 10, 11` sorts as `1, 10, 11, 2`, which is useless.

If a song has more than 99 tracks, `renumber` keeps going (`100_…`) and warns, and `validate` flags it. It won't stop you — it'll just tell you the sort is no longer guaranteed.

`NN` is **not** the track's `id`. The `id` is a permanent internal handle, allocated once and never reused, and it's what you pass to commands (`mixprep set ocean-floor 21 decision=keep`). The `NN` is a sorting device that `renumber` rewrites whenever your track list changes. A track with `id: 1` may well be called `16_VOX_Lead`.

### `CAT` — the category code

One of exactly ten codes: `DR PRC BS GTR KEY SYN VOX BV FX MISC`. Full table below.

The code does three jobs: it drives the numbering order, it makes the name self-describing at a glance, and — in Phase 3 — it's the join key that decides which bus a stem gets routed to in the generated mix template. That last one is why the codes are a **stable, additive-only** list: new codes can be added, existing codes are never renamed.

### `Descriptor` — what the track actually is

CamelCase, letters and digits only: `KickIn`, `SnareTop`, `AcousticRhythm`, `HarmHigh`, `Rhodes`, `808`.

No spaces, no hyphens, no apostrophes, no parentheses — those come out in the wash when you export to a filesystem anyway. Capitalise each word so the name stays readable without separators. Existing all-caps abbreviations stay as they are: `DI`, `OHL`, `BGV`.

Descriptors don't need to repeat the category. `14_KEY_Rhodes`, not `14_KEY_KeysRhodes`. `16_VOX_Lead`, not `16_VOX_VoxLead`.

### `_Variant` — optional, and repeatable

Zero or more extra segments, each letters and digits only, each preceded by an underscore.

```
11_GTR_AcousticRhythm_L
12_GTR_AcousticRhythm_R
17_VOX_Lead_Double
18_BV_Harm_High_Take2
```

Variants are for things that are *the same part*, differentiated: the two halves of a stereo pair, a doubled take, an alternate performance, a distinct comp. If the descriptor is a different instrument or a different part, it's not a variant — it's a different descriptor.

**Stereo pairs use `_L` and `_R` variants and share a `group`:**

```bash
mixprep set ocean-floor 2 new_name=11_GTR_AcousticRhythm_L group=AcGtrRhythm
mixprep set ocean-floor 3 new_name=12_GTR_AcousticRhythm_R group=AcGtrRhythm
```

The `group` field is what lets `status` roll up keep/cut decisions per group, and warn you when you've cut the left channel of a stereo pair and kept the right — which is exactly the mistake that costs you an hour later.

`group` is also how you link alternative layers of the same part (three vocal takes, four guitar overdubs) so mix-prep can tell you when a group has no `keep` at all.

### Allowed characters, overall

`[A-Za-z0-9_]` and nothing else. Letters, digits, underscore. This keeps every name safe as a filename on any filesystem, safe in a shell without quoting, and safe inside both Logic's and Ableton's track lists.

Underscore is a **separator**, so it can't appear inside a descriptor or a variant segment.

### Dry/wet is never in the name

There is no `_DRY` and no `_WET` suffix. Ever.

Dry and wet are carried by the **export destination folder**:

```
Exports/<song>/DRY/16_VOX_Lead.wav      ← effects bypassed
Exports/<song>/WET/16_VOX_Lead.wav      ← tracking effects intact
```

One track name, two folders, identical filenames. That means you can drop either folder into your mix session and everything lines up, you can A/B a dry stem against its wet counterpart by swapping folders, and `exports.dry.path` / `exports.wet.path` in the manifest differ only in one path segment. Encoding dry/wet in the track name would mean renaming tracks in the DAW between the two passes — which is precisely the manual step this convention exists to eliminate.

## The category codes

Ten codes, in canonical order. That order is the numbering order.

| # | Code | Name | Realistic Logic track names that belong here |
|---|---|---|---|
| 1 | `DR` | Drums | `Kick In`, `Kick Out`, `Snare Top`, `SNARE BOTTOM (new mic)`, `Hat`, `HH`, `Rack Tom`, `Floor Tom`, `Ride`, `Crash`, `OH L`, `OH R`, `Room mic (mono)`, `Drum Kit`, `Kick sample layer` |
| 2 | `PRC` | Percussion | `Shaker`, `Shaker OD`, `Tambourine`, `Tamb 2`, `Conga`, `Bongo`, `Claps`, `Cowbell`, `perc loop` |
| 3 | `BS` | Bass | `Bass DI`, `Bass Amp`, `Bass amp mic 57`, `Sub Bass`, `808`, `Synth bass` |
| 4 | `GTR` | Guitar | `Ac Gtr rhythm L`, `Ac Gtr rhythm R`, `Elec gtr lead`, `Strat clean`, `Tele overdub`, `Gtr amp room`, `Acoustic capo 3` |
| 5 | `KEY` | Keys / acoustic-electric keyboards | `Piano`, `Grand pno`, `Rhodes ~ verse only`, `Wurli`, `Organ B3`, `Keys bridge` |
| 6 | `SYN` | Synths | `prophet pad take 2`, `Pad synth`, `Pluck`, `Arp`, `Saw lead`, `Sub pad`, `Analog stack` |
| 7 | `VOX` | Lead vocals | `Vox Lead comp`, `Vox Lead comp FINAL v3`, `Lead vocal verse 2`, `Vox double`, `Adlib`, `Vocal chorus` |
| 8 | `BV` | Backing vocals | `BGV high`, `BGV's high`, `BV low`, `Backing vox stack`, `Harm 3rd`, `Choir pad`, `Gang vox` |
| 9 | `FX` | Effects / ear candy / risers | `riser 1`, `Riser fx`, `Impact`, `Swell`, `Whoosh`, `Reverse cymbal`, `SFX vinyl noise` |
| 10 | `MISC` | Uncategorised / other / loops | `Audio 7`, `Audio 12`, `Click`, `Talkback`, `Loop`, `Ref mix`, `Count in` |

Buses and aux returns get categories too — a drum bus is `DR`, a vocal reverb return is `FX` or `VOX` depending on what you want it grouped with. Mark them with `track_kind: bus` or `track_kind: aux` so reports know they aren't recorded audio.

`MISC` is a real answer, not a failure. If you genuinely don't know what `Audio 7` is yet, leave it `MISC`, add a note, and come back to it.

## The validation regex

```
^\d{2}_(DR|PRC|BS|GTR|KEY|SYN|VOX|BV|FX|MISC)_[A-Za-z0-9]+(_[A-Za-z0-9]+)*$
```

Read left to right: two digits, underscore, one of the ten codes, underscore, a descriptor of letters and digits, then any number of further underscore-separated letter-and-digit segments.

**This regex is generated in code from the canonical category list — it is never transcribed by hand.** `naming.NAME_RE` is built from `model.CATEGORIES`, which is the single source of truth for the codes. Adding a category means adding it to that tuple; the regex, the numbering order, the `set` validation and the Phase 3 bus mapping all follow automatically. The version printed above is for humans reading this document; don't copy it into code.

## Before and after

Twelve names from real tracking sessions, and what they become. The `NN` values shown assume one song containing all twelve — `renumber` computes them from the whole track list, so they'll differ in your song.

| Original name in Logic | Convention-compliant name | What happened |
|---|---|---|
| `Kick In` | `01_DR_KickIn` | Straightforward: spaces collapse, words capitalise. |
| `SNARE BOTTOM (new mic)` | `02_DR_SnareBtm` | Parentheses and the note dropped; shouting normalised; `Btm` matches the `Snare Top` sibling. |
| `OH L` | `03_DR_OHL` | Could equally be `03_DR_OH_L` with a `group` — do that if you want the pair rollup. |
| `Room mic (mono)` | `04_DR_RoomMic` | `(mono)` is not part of the name; put it in a note if it matters. |
| `Shaker OD` | `05_PRC_Shaker` | "OD" (overdub) is session bookkeeping, not identity. |
| `Bass DI` | `06_BS_DI` | The category already says bass, so the descriptor doesn't repeat it. `DI` keeps its capitals. |
| `gtr acoustic L` | `07_GTR_AcousticRhythm_L` | The trailing `L` becomes a proper `_Variant`; descriptor made specific. Add `group=AcGtr`. |
| `gtr acoustic R` | `08_GTR_AcousticRhythm_R` | Same group, matching descriptor, other variant. |
| `Rhodes ~ verse only` | `09_KEY_Rhodes` | `~ verse only` is arrangement info — move it to a track note. |
| `prophet pad take 2` | `10_SYN_Pad` | Take number goes in a note (or `source.takes`); if you keep both takes, use `_Take1` / `_Take2` variants and a shared `group`. |
| `Vox Lead comp FINAL v3` | `11_VOX_Lead` | `comp`, `FINAL` and `v3` are all "which file is the good one" — that question is answered by the manifest now. |
| `BGV's high` | `12_BV_HarmHigh` | Apostrophe illegal; descriptor says what the part is rather than repeating the category. |
| `Audio 12` | `13_MISC_Audio12` | Nothing to go on. Leave it `MISC`, listen to it, then `set` a real name. |

The pattern across all of them: **the name says what the track is.** Everything about *when*, *which take*, *whether it's the good one* and *what mic* moves into the manifest — into `notes`, `source`, `group` and `decision`, where you can actually search it.

## How the commands use the convention

### `suggest` — propose a category and a name

```bash
mixprep suggest ocean-floor          # asks about each track
mixprep suggest ocean-floor --auto   # accepts every proposal, no prompts
```

For each track it:

1. Case-folds the `original_name` and walks an ordered keyword table looking for the first match — `kick`, `snare`, `oh`, `room` → `DR`; `shaker`, `tamb`, `clap` → `PRC`; `bass`, `808`, `sub` → `BS`; and so on. **First match wins**, and the order is deliberate: `bgv`/`backing`/`harm` are checked before `vox`/`vocal`, so `BGV high` doesn't get filed as a lead vocal. No match at all → `MISC`.
2. Turns the original name into a CamelCase descriptor: split on every non-alphanumeric character, capitalise each piece, join them up. Existing interior capitals survive (`DI` stays `DI`). Anything that can't produce a usable descriptor falls back to `Track`.
3. Proposes the full `NN_CAT_Descriptor` and waits for you to accept or correct it.

Because non-alphanumerics are stripped rather than passed through, **`suggest` output always satisfies the regex.** It may be wrong, but it is never invalid.

Two things `suggest` will not do:

- **It never infers `_Variant` segments.** `gtr acoustic L` becomes `GTR_GtrAcousticL`, not `GTR_Acoustic_L`. mix-prep can't tell a stereo pair from a track that merely has an L in its name, and guessing wrong would silently pair up unrelated tracks. Add variants yourself with `set` — that is the one part of naming that needs your ears.
- **It never overrides you.** `--only-unnamed` restricts it to tracks with no `new_name` yet, so re-running it won't undo your corrections. And if it picks a category you disagree with, `mixprep set <slug> <track> category=PRC` settles it.

### `renumber` — assign the sort numbers

```bash
mixprep renumber ocean-floor
mixprep renumber ocean-floor --dry-run   # show the plan, change nothing
```

It orders every track by `(category order, track id)` — so drums come before percussion before bass, and within drums the tracks stay in the order you added them — and rewrites the leading two digits of each `new_name`. Numbering is continuous across the whole song, starting at `01`.

Two behaviours worth knowing:

- **It skips non-conforming names rather than splicing them.** If a track has no `new_name`, or has one that fails the regex, `renumber` leaves it completely alone and reports it as skipped with a reason. It will not try to bolt `07_` onto the front of `my weird name` and hand you a name that's still broken. Run `suggest` (or fix it with `set`), then renumber again.
- **It warns if `renamed_in_daw` is already true.** Once you've typed the names into Logic, renumbering changes the manifest but not the DAW, and the two drift apart. The warning doesn't block you — if you meant it, re-run `mixprep sheet` and fix the names in the DAW to match.

`renumber` only ever rewrites the `NN` prefix. It never touches a track's `id`, its descriptor, or its variants.

### `validate` — check the whole manifest

```bash
mixprep validate ocean-floor
mixprep validate --all
```

Findings come in two severities, and the difference decides the exit code.

| Severity | Exit code | Raised for |
|---|---|---|
| **ERROR** | non-zero | YAML that won't parse; a missing required field; a `schema_version` newer than this mix-prep understands; two tracks sharing an `id`; two tracks sharing a `new_name`; an unknown `category`; an invalid enum value for `decision`, an export `status`, `track_kind`, `hardware.type`, `export.realtime` or `mix_daw`. |
| **WARNING** | `0` | A `new_name` that fails the regex; a missing `new_name`; gaps in the `NN` sequence or numbers out of order; a workflow flag ticked out of pipeline order; `mixprep_copy` equal to or nested inside `source_project`; an export marked `done` with no stem path recorded; an empty `original_name`; a `group` with no `keep` at all, or with a split stereo-pair decision; an `NN` past 99. |

The split is deliberate. **Errors mean the file is structurally wrong** — something is broken or ambiguous and a program reading this manifest could do the wrong thing. **Warnings mean the file is fine but you probably didn't mean it** — the naming is untidy, the workflow got ticked out of order, a group looks suspicious. mix-prep warns; it does not block. You are allowed to have a half-named song in progress, and `validate` will still exit `0` and let your scripts keep running.

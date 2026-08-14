"""Unit tests for the naming convention (SPEC section 8)."""

import pytest

from mixprep import model, naming


class TestRegex:
    @pytest.mark.parametrize(
        "name",
        [
            "01_DR_KickIn",
            "07_GTR_AcousticRhythm_L",
            "21_VOX_Lead",
            "99_MISC_Track",
            "03_BV_DemoBackgroundVocals",
            "05_SYN_Pad_Double_2",
        ],
    )
    def test_accepts_valid(self, name):
        assert naming.is_valid_name(name)

    @pytest.mark.parametrize(
        "name",
        [
            "1_DR_Kick",          # NN must be two digits
            "01_DRUMS_Kick",      # not a category code
            "01_DR_",             # empty descriptor
            "01_DR_Kick In",      # space is not in the charset
            "01_DR_Kick-In",      # hyphen is not in the charset
            "DR_01_Kick",         # wrong order
            "kick track",         # not remotely conforming
            "",
            None,
            42,
        ],
    )
    def test_rejects_invalid(self, name):
        assert not naming.is_valid_name(name)

    def test_regex_is_built_from_the_canonical_category_list(self):
        # Single source of truth: every category must be accepted by the regex.
        for code in model.CATEGORIES:
            assert naming.is_valid_name("01_%s_Thing" % code), code

    def test_parse_round_trips(self):
        parsed = naming.parse_name("07_GTR_AcousticRhythm_L")
        assert parsed["nn"] == 7
        assert parsed["category"] == "GTR"
        assert parsed["descriptor"] == "AcousticRhythm"
        assert parsed["variants"] == ["L"]


class TestDescriptor:
    @pytest.mark.parametrize(
        "original",
        [
            "Audio 1",
            "Kick In 2",
            "gtr-acoustic_L",
            "  ",
            "",
            "12",
            "!!!",
            "Vox Lead comp",
            "Mango Tree World bgs 7-12",
        ],
    )
    def test_descriptor_always_yields_a_valid_name(self, original):
        """A suggestion must never be able to fail the convention regex."""
        descriptor = naming.descriptor_from(original)
        assert descriptor
        assert naming.is_valid_name("01_MISC_%s" % descriptor), descriptor

    def test_preserves_interior_capitals(self):
        assert naming.descriptor_from("Bass DI") == "BassDI"


class TestCategoryInference:
    @pytest.mark.parametrize(
        "original,expected",
        [
            ("Kick In 2", "DR"),
            ("Bass Drum", "DR"),          # drum compound must beat bare 'bass'
            ("OH L", "DR"),
            ("Shaker", "PRC"),
            ("Bass DI", "BS"),
            ("808", "BS"),
            ("gtr-acoustic_L", "GTR"),
            ("Rhodes", "KEY"),
            ("Lead Synth 3", "SYN"),      # 'lead synth' must beat bare 'lead'
            ("Vox Lead comp", "VOX"),
            ("Main Vocals", "VOX"),
            ("Riser FX", "FX"),
            ("Audio 1", "MISC"),
            ("Click", "MISC"),
        ],
    )
    def test_known_mappings(self, original, expected):
        assert naming.suggest_category(original) == expected

    @pytest.mark.parametrize(
        "original",
        [
            "demo background vocals",
            "background vox",
            "BGV stack hi",
            "bgvs",
            "Mango Tree World bgs 7-12",
            "Mango Tree World less bgs 7-12",
            "backing vocal 3",
            "harm high",
        ],
    )
    def test_backing_vocals_never_fall_through_to_lead(self, original):
        """Regression: a real session used 'background vocals' and 'bgs',
        both of which used to be miscategorised as VOX / MISC."""
        assert naming.suggest_category(original) == "BV"

    def test_case_folded(self):
        assert naming.suggest_category("KICK IN") == "DR"
        assert naming.suggest_category("kick in") == "DR"


class TestRenumber:
    def _track(self, track_id, category, new_name):
        return {"id": track_id, "category": category, "new_name": new_name}

    def test_orders_by_category_then_id(self):
        tracks = [
            self._track(1, "VOX", "09_VOX_Lead"),
            self._track(2, "DR", "04_DR_Kick"),
            self._track(3, "BS", "07_BS_DI"),
            self._track(4, "DR", "05_DR_Snare"),
        ]
        plan = {e["id"]: e for e in naming.renumber_plan(tracks)}
        assert plan[2]["new"] == "01_DR_Kick"
        assert plan[4]["new"] == "02_DR_Snare"
        assert plan[3]["new"] == "03_BS_DI"
        assert plan[1]["new"] == "04_VOX_Lead"

    def test_skips_rather_than_splices_bad_names(self):
        tracks = [
            self._track(1, "DR", "not a convention name"),
            self._track(2, "DR", None),
        ]
        plan = {e["id"]: e for e in naming.renumber_plan(tracks)}
        assert plan[1]["skipped"] and plan[1]["reason"]
        assert plan[2]["skipped"] and plan[2]["reason"]

    def test_only_the_number_changes(self):
        tracks = [self._track(1, "GTR", "88_GTR_AcousticRhythm_L")]
        entry = naming.renumber_plan(tracks)[0]
        assert entry["new"] == "01_GTR_AcousticRhythm_L"

    def test_is_idempotent(self):
        tracks = [
            self._track(1, "DR", "04_DR_Kick"),
            self._track(2, "VOX", "09_VOX_Lead"),
        ]
        first = naming.renumber_plan(tracks)
        for entry in first:
            for track in tracks:
                if track["id"] == entry["id"] and entry.get("new"):
                    track["new_name"] = entry["new"]
        second = naming.renumber_plan(tracks)
        assert all(e["old"] == e["new"] for e in second)

    def test_overflow_past_99_is_flagged_not_dropped(self):
        tracks = [
            self._track(i, "DR", "01_DR_T%d" % i) for i in range(1, 101)
        ]
        plan = naming.renumber_plan(tracks)
        overflow = [e for e in plan if e.get("reason") == "overflow"]
        assert overflow, "the 100th track should be flagged"
        assert not overflow[0]["skipped"], "flagged, but still numbered"

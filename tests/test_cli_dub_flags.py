"""subreplace-batch phai dung duoc tinh nang moi ma khong can UI."""
from __future__ import annotations

import pytest

from app.cli import build_parser
from app.providers.tts.edge import VOICE_FEMALE, VOICE_MALE
from app.providers.translation.json_contract import prompt_for_translation


def _parse(*extra):
    return build_parser().parse_args(["--source", "a.mp4", "--project", "p", *extra])


def test_dubbing_is_on_and_erasing_is_off_by_default():
    args = _parse()
    assert args.no_dub is False
    assert args.erase_subtitles is False
    assert args.dub_voice_female == VOICE_FEMALE
    assert args.dub_voice_male == VOICE_MALE
    assert args.dub_default_gender == "female"
    assert args.duck_ratio == 12


def test_dubbing_can_be_turned_off():
    assert _parse("--no-dub").no_dub is True


def test_erasing_can_be_turned_on():
    assert _parse("--erase-subtitles").erase_subtitles is True


def test_duck_ratio_accepts_the_documented_levels():
    for ratio in (6, 12, 20):
        assert _parse("--duck-ratio", str(ratio)).duck_ratio == ratio


def test_default_gender_is_restricted_to_male_or_female():
    with pytest.raises(SystemExit):
        _parse("--dub-default-gender", "other")


def test_translation_prompt_asks_for_dub_friendly_length():
    prompt = prompt_for_translation([], "vi", {})
    lowered = prompt.lower()
    assert "dub" in lowered or "spoken" in lowered

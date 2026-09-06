from integrations.music.lyrics import LrclibProvider
from integrations.music.models import LyricLine
from integrations.music.visual_planner import TypographicPlanner, classify_mood


def test_lrc_parser_builds_reliable_intervals() -> None:
    result = LrclibProvider._parse(
        "[00:01.00]primeira linha\n[00:03.50]segunda linha\n[00:07.00]fim", 9000
    )
    assert [(line.start_ms, line.end_ms) for line in result] == [
        (1000, 3500), (3500, 7000), (7000, 9000)
    ]


def test_visual_plan_is_deterministic_and_refrain_evolves() -> None:
    lines = [LyricLine(0, 1000, "fica comigo"), LyricLine(1000, 2000, "fica comigo")]
    planner = TypographicPlanner()
    first = planner.plan("track-1", lines)
    assert first == planner.plan("track-1", lines)
    assert first[1].scale > first[0].scale
    assert first[1].emphasis == "chorus"


def test_word_repeated_across_track_is_marked_strong_without_a_fixed_list() -> None:
    # "estrada" isn't in the curated word list -- it should still surface as
    # important purely for recurring across separate lines of the track.
    lines = [
        LyricLine(0, 1000, "a estrada continua"),
        LyricLine(1000, 2000, "essa estrada e longa"),
        LyricLine(2000, 3000, "sigo pela estrada"),
    ]
    planner = TypographicPlanner()
    cues = planner.plan("track-2", lines)
    assert any("estrada" in cue.words for cue in cues)


def test_mood_is_classified_from_the_track_own_lyrics() -> None:
    # Spotify's audio-features endpoint (energy/valence) is unavailable for
    # this app (verified live: HTTP 403) -- mood comes from the actual
    # lyrics instead.
    intense = [LyricLine(0, 1000, "fogo e sangue, guerra sem fim")]
    tender = [LyricLine(0, 1000, "amor, um beijo, um sorriso lindo")]
    assert classify_mood(intense) == "intense"
    assert classify_mood(tender) == "tender"
    assert classify_mood([]) == "bright"

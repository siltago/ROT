from __future__ import annotations

from perception.speech.wake_word import matches_wake_word


def test_matches_common_phonetic_variants() -> None:
    assert matches_wake_word("ei bob, tudo bem?")
    assert matches_wake_word("Ei Bob")
    assert matches_wake_word("oi bob você está aí")


def test_matches_real_stt_transcripts_seen_in_practice() -> None:
    assert matches_wake_word("ei, bob")
    assert matches_wake_word("Bob")


def test_matches_bare_e_lead_in_seen_in_practice() -> None:
    # The STT frequently transcribes "ei" as a bare "E".
    assert matches_wake_word("E Bob")
    assert matches_wake_word("e bob")


def test_matches_merged_lead_in_seen_in_practice() -> None:
    # The STT sometimes runs the lead-in and name together with no gap,
    # normalizing "ei"/"a" to a bare letter glued onto the name.
    assert matches_wake_word("Ebob")
    assert matches_wake_word("Abob")


def test_ignores_unrelated_words_that_merely_contain_bob() -> None:
    assert not matches_wake_word("que bobagem")
    assert not matches_wake_word("essa bobina queimou")
    assert not matches_wake_word("e bobagem essa")
    assert not matches_wake_word("a bobina está solta")
    assert not matches_wake_word("que horas são")


def test_is_accent_and_case_insensitive() -> None:
    assert matches_wake_word("EI BOB")

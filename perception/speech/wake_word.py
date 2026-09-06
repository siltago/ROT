"""Free, always-on-anyway matching for the wake word "ei Bob". Runs against
every final transcript the STT pipeline already produces -- no extra
recognition step, no extra cost -- so the brain can decide whether a given
utterance should become a real (LLM-costing) turn or was just someone waking
the robot up.

"Bob" is a real, phonetically simple name (the robot was previously called
"Ybi", then briefly "Lyn" -- both replaced for the same reason: a common,
clearly-enunciated name is far more reliable for general-purpose STT to
transcribe than an invented or less common one). Real observed transcripts
still vary ("ei bob" with the lead-in worn down to a bare "e", "bob" with no
lead-in at all, punctuation glued on), so matching stays two-tiered: a
lead-in word (ei/oi/hei/...) followed by a name-ish sound with any
punctuation/spacing between them, or a small set of standalone sounds
distinctive enough to trust without a lead-in.
"""
from __future__ import annotations

import re

_ACCENTED = "áàâãäéèêëíìîïóòôõöúùûüç"
_PLAIN = "aaaaaeeeeiiiiooooouuuuc"
_ACCENT_TABLE = str.maketrans(_ACCENTED, _PLAIN)

# In practice the STT often hears "ei" as a bare "E" or "A" (even merging it
# straight into the name with no gap), so both bare letters have to be
# accepted as lead-ins too -- but "e" is also the conjunction "and" and "a"
# is also the article "the", so "e bobina"/"a bobagem" must NOT trigger. The
# trailing \b handles that: it requires the name-sound to end right there,
# so "bob" followed by more word characters ("-ina", "-agem") fails to match
# while an isolated "bob" at the end of the utterance succeeds. The leading
# \b matters just as much: without it a bare "e"/"a" would match inside
# "que"/"sala", and "ai"/"hei" would match mid-word in unrelated text.
_LEAD_IN_NAME_PATTERN = re.compile(r"\b(?:ei|oi|hei|ai|hey|e|a)\W*(?:bob)\b")

# Distinctive enough alone that a lead-in isn't required (the STT sometimes
# drops it entirely).
_STANDALONE_PATTERN = re.compile(r"\bbob\b")


def matches_wake_word(text: str) -> bool:
    normalized = text.lower().strip().translate(_ACCENT_TABLE)
    if _LEAD_IN_NAME_PATTERN.search(normalized):
        return True
    return bool(_STANDALONE_PATTERN.search(normalized))

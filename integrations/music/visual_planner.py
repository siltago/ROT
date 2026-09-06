from __future__ import annotations

import hashlib, re
from integrations.music.models import LyricLine, VisualCue

# Spotify's own per-track audio analysis (energy/valence) -- the original,
# more precise signal this used -- returned HTTP 403 in practice: Spotify
# restricted `/v1/audio-features` (and artist `genres`) to apps with
# extended API access in late 2024, which a newly-created app like this one
# doesn't have. Mood is classified from the lyrics' own words instead --
# real, track-specific content already fetched and cached, not a guess and
# not an unavailable API. Classified per *line* (see `TypographicPlanner`),
# not once for the whole track, so the typography actually alternates as
# the song moves between, say, an angry verse and a tender chorus.
_MOOD_KEYWORDS: dict[str, set[str]] = {
    "intense": {
        "raiva", "guerra", "fogo", "sangue", "grito", "gritar", "odio",
        "luta", "lutar", "poder", "destruir", "morte", "matar", "dor",
        "rage", "fight", "fire", "blood", "scream", "hate", "war", "kill",
        "destroy", "power", "burn", "loud", "crazy", "insane",
    },
    "tender": {
        "amor", "amar", "carinho", "beijo", "abraco", "docura", "querida",
        "querido", "coracao", "sonho", "feliz", "sorriso", "linda", "lindo",
        "love", "sweet", "kiss", "gentle", "soft", "tender", "heart",
        "dream", "happy", "smile", "beautiful", "darling",
    },
    "melancholic": {
        "triste", "sozinho", "sozinha", "chorar", "choro", "saudade",
        "perdido", "perdida", "solidao", "vazio", "lagrimas", "adeus",
        "sad", "alone", "cry", "lost", "broken", "tears", "goodbye",
        "empty", "lonely", "gone", "miss",
    },
}


def classify_mood(lines: list[LyricLine]) -> str:
    if not lines:
        return "bright"
    words = re.findall(r"\w+", " ".join(line.text for line in lines).casefold())
    scores = {mood: sum(1 for w in words if w in keywords) for mood, keywords in _MOOD_KEYWORDS.items()}
    best_mood, best_score = max(scores.items(), key=lambda kv: kv[1])
    return best_mood if best_score > 0 else "bright"


class TypographicPlanner:
    """Creates stable art direction once per track, with no live AI calls."""
    _strong = {"amor", "love", "never", "nunca", "sempre", "alone", "sozinho", "vida", "morte", "heart"}
    # Common function words (PT/EN) excluded from the frequency count below --
    # otherwise "que"/"the"/"e"/"and" would dominate as "important" in almost
    # any song purely by being common, not by carrying meaning.
    _stopwords = {
        "a", "o", "as", "os", "de", "da", "do", "das", "dos", "em", "no", "na",
        "nos", "nas", "um", "uma", "uns", "umas", "e", "ou", "que", "com",
        "por", "para", "pra", "pro", "se", "eu", "tu", "ele", "ela", "nos",
        "voce", "voces", "eles", "elas", "me", "te", "lhe", "meu", "minha",
        "teu", "tua", "seu", "sua", "e", "era", "foi", "ser", "estar", "esta",
        "nao", "sim", "mais", "mas", "como", "ja", "so", "ainda", "tambem",
        "ate", "the", "a", "an", "of", "in", "on", "at", "to", "for", "and",
        "or", "but", "is", "are", "was", "were", "be", "been", "i", "you",
        "he", "she", "it", "we", "they", "my", "your", "his", "her", "its",
        "our", "their", "this", "that", "these", "those", "not", "no", "so",
        "just", "still", "also", "with",
    }

    def plan(self, track_id: str, lines: list[LyricLine]) -> list[VisualCue]:
        # A word that recurs often across the *whole* track (not just within
        # one line -- `repeat` below already covers a repeated whole line)
        # is a reasonable, zero-AI proxy for a thematically central word,
        # regardless of language -- computed once per track, not per line.
        word_counts: dict[str, int] = {}
        for line in lines:
            for word in line.text.split():
                normalized_word = re.sub(r"\W", "", word.casefold())
                if len(normalized_word) >= 3 and normalized_word not in self._stopwords:
                    word_counts[normalized_word] = word_counts.get(normalized_word, 0) + 1
        frequent = {word for word, count in word_counts.items() if count >= 3}

        seen, cues = {}, []
        layouts = ("center", "lower_left", "upper_right", "left", "right")
        for index, line in enumerate(lines):
            normalized = re.sub(r"\W+", " ", line.text.casefold()).strip()
            repeat = seen.get(normalized, 0); seen[normalized] = repeat + 1
            words, duration = line.text.split(), max(300, line.end_ms - line.start_ms)
            strong = [w for w in words if re.sub(r"\W", "", w.casefold()) in self._strong
                      or re.sub(r"\W", "", w.casefold()) in frequent]
            seed = int(hashlib.sha1(f"{track_id}:{index}".encode()).hexdigest()[:8], 16)
            scale = min(1.8, .82 + max(0, 6 - len(words)) * .10 + repeat * .16)
            # A repeat always reads as "chorus" (its growing `scale` is what
            # communicates the repetition intensifying) -- otherwise a short,
            # held line (a very common shape for a chorus hook) would hit the
            # "hero" case below on *every* repeat and never actually evolve
            # into a distinct "chorus" treatment.
            if repeat:
                emphasis = "chorus"
            elif strong or (len(words) <= 2 and duration > 900):
                emphasis = "hero"
            else:
                emphasis = "normal"
            cues.append(VisualCue(line.start_ms, line.end_ms, line.text, emphasis,
                layouts[(seed + repeat) % len(layouts)], scale, strong[:2],
                classify_mood([line])))
        return cues

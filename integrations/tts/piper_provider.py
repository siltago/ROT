"""Local neural TTS via Piper (ONNX, runs on CPU, no network/API cost).

Mirrors the LLMProvider pattern (integrations/llm/base.py): callers depend
only on `synthesize`, never on Piper internals, and a failed/missing model
degrades to `None` rather than raising -- the caller falls back to the
tablet's own flutter_tts, the same way ResponseEngine falls back to a
template reply when the LLM provider fails.
"""
from __future__ import annotations

import asyncio
import io
import logging
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from piper import PiperVoice, SynthesisConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RobotVoiceEffect:
    """All "robot voice" tuning in one place, sourced from Settings (see
    app/config.py) so it can be dialed in via env vars without touching
    code. Three independent layers, each of which can be zeroed out on its
    own while tasting the result: prosody (how Piper itself speaks), pitch
    (raise/lower the whole voice, formants included), and a post-processing
    effect (ring modulation + optional bitcrush) for an overtly robotic
    buzz -- off by default now that the target is a normal-sounding voice,
    just with its own character."""

    noise_scale: float = 0.5
    noise_w_scale: float = 0.5
    length_scale: float = 1.0
    pitch_shift_semitones: float = 0.0
    ring_mod_hz: float = 45.0
    ring_mod_wet: float = 0.0
    bitcrush_levels: int = 0  # 0 disables the bitcrush entirely.


def _pitch_shift(samples: np.ndarray, semitones: float) -> np.ndarray:
    """Cheap pitch shift: resample fewer/more samples over the same
    waveform (raises/lowers pitch, and speeds up/slows down playback as a
    side effect) -- the speed side effect is pre-compensated by adjusting
    Piper's own length_scale before synthesis (see _synthesis_config), so
    the final clip keeps roughly its natural duration. Formants move with
    pitch here (no formant-preserving correction), so large shifts start
    sounding like a sped-up/slowed-down version of the same voice rather
    than a genuinely different one -- keep it moderate."""
    if semitones == 0:
        return samples
    ratio = 2 ** (semitones / 12)
    new_length = max(1, int(round(len(samples) / ratio)))
    old_index = np.linspace(0, len(samples) - 1, new_length)
    return np.interp(old_index, np.arange(len(samples)), samples).astype(np.float32)


def _robotize(samples: np.ndarray, sample_rate: int, effect: RobotVoiceEffect) -> np.ndarray:
    """Ring-modulates (classic Dalek/Portal-turret "robot voice" -- multiply
    the signal by a low-frequency carrier tone) and optionally bitcrushes
    for a more "digital" texture. Both are mixed in rather than fully
    replacing the dry signal, so speech stays legible under the effect."""
    if effect.ring_mod_wet > 0:
        t = np.arange(len(samples)) / sample_rate
        carrier = np.sin(2 * np.pi * effect.ring_mod_hz * t)
        modulated = samples * carrier
        samples = samples * (1 - effect.ring_mod_wet) + modulated * effect.ring_mod_wet
    if effect.bitcrush_levels > 0:
        samples = np.round(samples * effect.bitcrush_levels) / effect.bitcrush_levels
    peak = float(np.max(np.abs(samples))) or 1.0
    return (samples / peak * 0.95).astype(np.float32)


class PiperTtsProvider:
    def __init__(self, voice: PiperVoice, effect: RobotVoiceEffect | None = None) -> None:
        self._voice = voice
        self._effect = effect or RobotVoiceEffect()
        # Pre-compensate for the speed side effect of _pitch_shift: raising
        # pitch by `ratio` also speeds playback by `ratio`, so synthesize
        # slower by the same ratio up front to land near the original pace.
        pitch_ratio = 2 ** (self._effect.pitch_shift_semitones / 12)
        self._synthesis_config = SynthesisConfig(
            noise_scale=self._effect.noise_scale,
            noise_w_scale=self._effect.noise_w_scale,
            length_scale=self._effect.length_scale * pitch_ratio,
        )

    @classmethod
    def try_create(cls, voice_path: Path, effect: RobotVoiceEffect | None = None) -> "PiperTtsProvider | None":
        """Loads the voice model once at startup. Returns None (never
        raises) if the model file is missing or fails to load, so a robot
        without a downloaded voice just keeps using local TTS."""
        if not voice_path.exists():
            logger.warning("Piper voice model not found at %s; TTS falls back to the tablet's local voice", voice_path)
            return None
        try:
            voice = PiperVoice.load(str(voice_path))
        except Exception:
            logger.exception("Failed to load Piper voice model at %s", voice_path)
            return None
        return cls(voice, effect)

    async def synthesize(self, text: str) -> bytes | None:
        """Synthesizes `text` to a complete WAV file's bytes. Runs the
        blocking ONNX inference in a worker thread so it never stalls the
        event loop. Never raises -- returns None on any failure."""
        try:
            return await asyncio.to_thread(self._synthesize_sync, text)
        except Exception:
            logger.exception("Piper synthesis failed; falling back to local TTS")
            return None

    def _synthesize_sync(self, text: str) -> bytes:
        chunks = list(self._voice.synthesize(text, syn_config=self._synthesis_config))
        if not chunks:
            raise RuntimeError("Piper produced no audio for this text")
        sample_rate = chunks[0].sample_rate
        audio = np.concatenate([chunk.audio_float_array for chunk in chunks])
        audio = _pitch_shift(audio, self._effect.pitch_shift_semitones)
        audio = _robotize(audio, sample_rate, self._effect)
        pcm16 = (audio * 32767).astype(np.int16)

        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm16.tobytes())
        return buffer.getvalue()

from __future__ import annotations

import asyncio, json, re, urllib.parse, urllib.request
from integrations.music.models import LyricLine, PlaybackState

_LRC = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\](.*)")


class LrclibProvider:
    def __init__(self, *, timeout: float = 6) -> None: self.timeout = timeout

    async def synchronized(self, track: PlaybackState) -> list[LyricLine]:
        query = urllib.parse.urlencode({"track_name": track.title, "artist_name": track.artist,
            "album_name": track.album, "duration": round(track.duration_ms / 1000)})
        req = urllib.request.Request("https://lrclib.net/api/get?" + query, headers={"User-Agent": "BobRobot/0.1"})
        try:
            data = await asyncio.to_thread(self._read, req)
            parsed = self._parse(str(data.get("syncedLyrics") or ""), track.duration_ms)
            return parsed if len(parsed) >= 3 else []
        except Exception:
            return []

    def _read(self, req):
        with urllib.request.urlopen(req, timeout=self.timeout) as response: return json.loads(response.read())

    @staticmethod
    def _parse(raw: str, duration_ms: int) -> list[LyricLine]:
        starts = []
        for line in raw.splitlines():
            match = _LRC.match(line.strip())
            if match and match.group(3).strip():
                starts.append((int((int(match.group(1)) * 60 + float(match.group(2))) * 1000), match.group(3).strip()))
        return [LyricLine(start, starts[i + 1][0] if i + 1 < len(starts) else duration_ms, text)
                for i, (start, text) in enumerate(starts) if start < duration_ms]

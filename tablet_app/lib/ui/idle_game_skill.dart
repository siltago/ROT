import 'dart:convert';
import 'dart:io';

/// How much less random Bob's chess/checkers moves should be right now
/// (0..1) -- see api/server.py's `GET /idle/game_skill`. Any failure
/// (offline, timeout, unexpected response) degrades to 0, i.e. the
/// original fully-random behavior, never an error.
Future<double> fetchGameSkill(String httpBaseUrl) async {
  final client = HttpClient();
  try {
    final request = await client
        .getUrl(Uri.parse('$httpBaseUrl/idle/game_skill'))
        .timeout(const Duration(seconds: 3));
    final response = await request.close().timeout(const Duration(seconds: 3));
    if (response.statusCode != 200) return 0;
    final body = await response.transform(utf8.decoder).join();
    final decoded = jsonDecode(body);
    if (decoded is Map && decoded['skill'] is num) {
      return (decoded['skill'] as num).toDouble().clamp(0.0, 1.0);
    }
    return 0;
  } catch (_) {
    return 0;
  } finally {
    client.close(force: true);
  }
}

/// Reports that a match just concluded (Bob's own king/piece count fell)
/// -- see api/server.py's `POST /idle/game_result`, which nudges
/// game_skill up a small, slow amount. Fire-and-forget; any failure is
/// swallowed, never a visible error over a cosmetic vignette detail.
Future<void> postGameResult(String httpBaseUrl) async {
  final client = HttpClient();
  try {
    final request = await client
        .postUrl(Uri.parse('$httpBaseUrl/idle/game_result'))
        .timeout(const Duration(seconds: 3));
    await request.close().timeout(const Duration(seconds: 3));
  } catch (_) {
    // Ignored on purpose -- see doc comment above.
  } finally {
    client.close(force: true);
  }
}

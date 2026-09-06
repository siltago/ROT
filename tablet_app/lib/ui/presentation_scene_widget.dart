import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:palette_generator/palette_generator.dart';

import '../robot/presentation_scene.dart';

class PresentationSceneWidget extends StatefulWidget {
  const PresentationSceneWidget({super.key, required this.scene});

  final PresentationScene scene;

  @override
  State<PresentationSceneWidget> createState() =>
      _PresentationSceneWidgetState();
}

class _PresentationSceneWidgetState extends State<PresentationSceneWidget>
    with SingleTickerProviderStateMixin {
  late final AnimationController _motion = AnimationController(
    vsync: this,
    duration: const Duration(seconds: 3),
  )..repeat();

  @override
  void dispose() {
    _motion.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: Colors.black,
      child: AnimatedBuilder(
        animation: _motion,
        builder: (context, _) => switch (widget.scene.kind) {
          'clock' => _ClockScene(scene: widget.scene, progress: _motion.value),
          'date' => _DateScene(scene: widget.scene),
          'weather' =>
            _WeatherScene(scene: widget.scene, progress: _motion.value),
          'music' => _MusicScene(scene: widget.scene, progress: _motion.value),
          _ => const Center(
              child: Icon(Icons.auto_awesome, color: Colors.white, size: 72),
            ),
        },
      ),
    );
  }
}

class _ClockScene extends StatefulWidget {
  const _ClockScene({required this.scene, required this.progress});
  final PresentationScene scene;
  final double progress;

  @override
  State<_ClockScene> createState() => _ClockSceneState();
}

class _ClockSceneState extends State<_ClockScene> {
  late DateTime _clock;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    final parts = '${widget.scene.data['time'] ?? '00:00'}'.split(':');
    final now = DateTime.now();
    _clock = DateTime(
      now.year,
      now.month,
      now.day,
      int.tryParse(parts.first) ?? now.hour,
      parts.length > 1 ? int.tryParse(parts[1]) ?? now.minute : now.minute,
      (widget.scene.data['seconds'] as num?)?.toInt() ?? now.second,
    );
    _timer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) {
        setState(() => _clock = _clock.add(const Duration(seconds: 1)));
      }
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // Matches the robot's own default (standby/neutral mood) eye color --
    // see _moodColor's neutral case in robot_face_widget.dart -- instead of
    // an unrelated green, so the clock scene stays visually consistent
    // with the rest of the robot's own look.
    const eyeColor = Color(0xFF75B6D7);
    final data = widget.scene.data;
    final period = '${data['period'] ?? _periodForHour(_clock.hour)}';
    final weekday = _weekdayLabel(data['weekday'], _clock.weekday);
    final date = '${data['date'] ?? _formatDate(_clock)}';
    final time = '${_clock.hour.toString().padLeft(2, '0')}:'
        '${_clock.minute.toString().padLeft(2, '0')}:'
        '${_clock.second.toString().padLeft(2, '0')}';

    return LayoutBuilder(
      builder: (context, constraints) => Stack(
        children: [
          Positioned.fill(
            child: CustomPaint(
              painter: _ClockAtmospherePainter(
                period: period,
                progress: widget.progress,
                color: eyeColor,
              ),
            ),
          ),
          Padding(
            padding: EdgeInsets.symmetric(
              horizontal: constraints.maxWidth * .075,
              vertical: constraints.maxHeight * .075,
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    SizedBox(
                      width: constraints.maxWidth * .52,
                      height: constraints.maxHeight * .105,
                      child: _SevenSegmentText(
                        value: date,
                        color: eyeColor,
                      ),
                    ),
                    const Spacer(),
                    SizedBox(
                      width: constraints.maxWidth * .15,
                      height: constraints.maxHeight * .105,
                      child: _SevenSegmentText(
                        value: weekday,
                        color: eyeColor,
                      ),
                    ),
                  ],
                ),
                const Spacer(),
                Center(
                  child: SizedBox(
                    width: constraints.maxWidth * .86,
                    height: constraints.maxHeight * .38,
                    child: _SevenSegmentText(
                      value: time,
                      color: eyeColor,
                    ),
                  ),
                ),
                const Spacer(),
                const SizedBox(height: 12),
              ],
            ),
          ),
          if (data['temperature'] != null)
            Positioned(
              right: constraints.maxWidth * .075,
              bottom: constraints.maxHeight * .07,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(
                    '${data['temperature'] is num ? (data['temperature'] as num).round() : data['temperature']}°',
                    style: TextStyle(
                      color: eyeColor,
                      fontSize: constraints.maxHeight * .11,
                      fontWeight: FontWeight.w400,
                    ),
                  ),
                  if ('${data['location'] ?? ''}'.isNotEmpty)
                    Text(
                      '${data['location']}'.toUpperCase(),
                      style: TextStyle(
                        color: eyeColor.withValues(alpha: .62),
                        fontSize: constraints.maxHeight * .03,
                        letterSpacing: 3,
                      ),
                    ),
                ],
              ),
            ),
        ],
      ),
    );
  }

  static String _periodForHour(int hour) => hour >= 5 && hour < 8
      ? 'dawn'
      : hour >= 8 && hour < 18
          ? 'day'
          : 'night';

  static String _formatDate(DateTime value) =>
      '${value.day.toString().padLeft(2, '0')}/${value.month.toString().padLeft(2, '0')}/${value.year}';

  static String _weekdayLabel(Object? raw, int localWeekday) {
    final index = raw is num ? raw.toInt() : localWeekday - 1;
    return _weekdays[index.clamp(0, 6)];
  }

  static const _weekdays = ['SEG', 'TER', 'QUA', 'QUI', 'SEX', 'SAB', 'DOM'];
}

class _ClockAtmospherePainter extends CustomPainter {
  const _ClockAtmospherePainter({
    required this.period,
    required this.progress,
    required this.color,
  });
  final String period;
  final double progress;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    if (period == 'night') {
      _paintPixelStars(canvas, size);
      _paintPixelMoon(canvas, size);
      _paintPixelClouds(canvas, size, night: true);
      return;
    }
    _paintPixelSun(canvas, size, low: period == 'dawn');
    _paintPixelClouds(canvas, size, night: false);
  }

  void _paintPixelStars(Canvas canvas, Size size) {
    final pulse = .35 + math.sin(progress * math.pi * 2).abs() * .25;
    final paint = Paint()..isAntiAlias = false;
    const positions = <Offset>[
      Offset(.05, .16),
      Offset(.12, .28),
      Offset(.19, .10),
      Offset(.28, .23),
      Offset(.36, .13),
      Offset(.45, .25),
      Offset(.68, .09),
      Offset(.73, .28),
      Offset(.94, .16),
      Offset(.92, .34),
      Offset(.53, .08),
      Offset(.62, .29),
    ];
    final pixel = math.max(4.0, size.shortestSide * .012);
    for (var i = 0; i < positions.length; i++) {
      paint.color = color.withValues(alpha: i.isEven ? pulse : .28);
      final point = positions[i];
      canvas.drawRect(
        Rect.fromLTWH(
            point.dx * size.width, point.dy * size.height, pixel, pixel),
        paint,
      );
    }
  }

  void _paintPixelMoon(Canvas canvas, Size size) {
    final unit = math.max(5.0, size.shortestSide * .016);
    final origin = Offset(size.width * .61, size.height * .10);
    const rows = <String>[
      '..XXXX..',
      '.XXXXXX.',
      'XXXXXXXX',
      'XXXXXXXX',
      'XXXXXXXX',
      'XXXXXXXX',
      '.XXXXXX.',
      '..XXXX..',
    ];
    final moon = Paint()
      ..color = const Color(0xFFFFFFD7)
      ..isAntiAlias = false;
    final shade = Paint()
      ..color = const Color(0xFF9DB3B3)
      ..isAntiAlias = false;
    for (var y = 0; y < rows.length; y++) {
      for (var x = 0; x < rows[y].length; x++) {
        if (rows[y][x] != 'X') continue;
        final shaded = (x == 1 && y > 2) || (x == 5 && (y == 2 || y == 5));
        canvas.drawRect(
          Rect.fromLTWH(
              origin.dx + x * unit, origin.dy + y * unit, unit + .4, unit + .4),
          shaded ? shade : moon,
        );
      }
    }
  }

  void _paintPixelSun(Canvas canvas, Size size, {required bool low}) {
    final unit = math.max(5.0, size.shortestSide * .014);
    final center = Offset(size.width * .64, size.height * (low ? .28 : .12));
    final paint = Paint()
      ..color = color.withValues(alpha: .78)
      ..isAntiAlias = false;
    for (var y = -3; y <= 3; y++) {
      for (var x = -3; x <= 3; x++) {
        if (x.abs() + y.abs() <= 4) {
          canvas.drawRect(
              Rect.fromLTWH(
                  center.dx + x * unit, center.dy + y * unit, unit, unit),
              paint);
        }
      }
    }
  }

  void _paintPixelClouds(Canvas canvas, Size size, {required bool night}) {
    final dark = Paint()
      ..color = Color(night ? 0x551AA4C0 : 0x4431CDE0)
      ..isAntiAlias = false;
    final deep = Paint()
      ..color = const Color(0x66205265)
      ..isAntiAlias = false;
    final unit = math.max(7.0, size.shortestSide * .018);
    void block(double x, double y, double w, double h, Paint paint) {
      canvas.drawRect(
          Rect.fromLTWH(x * size.width, y * size.height, w * unit, h * unit),
          paint);
    }

    block(0, .78, 13, 3, dark);
    block(.08, .72, 8, 2, dark);
    block(.19, .84, 18, 3, dark);
    block(.47, .76, 11, 2, deep);
    block(.72, .82, 16, 4, dark);
    block(.83, .71, 8, 3, dark);
    block(.02, .93, 28, 1, deep);
    block(.52, .91, 22, 1, deep);
  }

  @override
  bool shouldRepaint(covariant _ClockAtmospherePainter oldDelegate) =>
      oldDelegate.progress != progress ||
      oldDelegate.period != period ||
      oldDelegate.color != color;
}

class _SevenSegmentText extends StatelessWidget {
  const _SevenSegmentText({required this.value, required this.color});
  final String value;
  final Color color;

  @override
  Widget build(BuildContext context) => CustomPaint(
        painter: _SevenSegmentPainter(value: value, color: color),
      );
}

class _SevenSegmentPainter extends CustomPainter {
  const _SevenSegmentPainter({required this.value, required this.color});
  final String value;
  final Color color;

  static const _segments = <String, Set<int>>{
    '0': {0, 1, 2, 4, 5, 6},
    '1': {2, 5},
    '2': {0, 2, 3, 4, 6},
    '3': {0, 2, 3, 5, 6},
    '4': {1, 2, 3, 5},
    '5': {0, 1, 3, 5, 6},
    '6': {0, 1, 3, 4, 5, 6},
    '7': {0, 2, 5},
    '8': {0, 1, 2, 3, 4, 5, 6},
    '9': {0, 1, 2, 3, 5, 6},
    'A': {0, 1, 2, 3, 4, 5},
    'B': {1, 3, 4, 5, 6},
    'D': {2, 3, 4, 5, 6},
    'E': {0, 1, 3, 4, 6},
    'G': {0, 1, 4, 5, 6},
    'I': {1, 4},
    'M': {0, 1, 2, 4, 5},
    'O': {0, 1, 2, 4, 5, 6},
    'Q': {0, 1, 2, 3, 5, 6},
    'R': {4, 3},
    'S': {0, 1, 3, 5, 6},
    'T': {1, 3, 4, 6},
    'U': {1, 2, 4, 5, 6},
  };

  @override
  void paint(Canvas canvas, Size size) {
    final units = value.split('');
    final separatorCount =
        units.where((unit) => unit == ':' || unit == '/').length;
    final digitCount = units.length - separatorCount;
    final gap = size.width * .018;
    final colonWidth = size.width * .07;
    final digitWidth =
        (size.width - gap * (units.length - 1) - colonWidth * separatorCount) /
            digitCount;
    var x = 0.0;
    for (final unit in units) {
      if (unit == ':') {
        final paint = Paint()..color = color;
        canvas.drawRRect(
            RRect.fromRectAndRadius(
                Rect.fromCenter(
                    center: Offset(x + colonWidth / 2, size.height * .34),
                    width: colonWidth * .32,
                    height: colonWidth * .32),
                const Radius.circular(3)),
            paint);
        canvas.drawRRect(
            RRect.fromRectAndRadius(
                Rect.fromCenter(
                    center: Offset(x + colonWidth / 2, size.height * .67),
                    width: colonWidth * .32,
                    height: colonWidth * .32),
                const Radius.circular(3)),
            paint);
        x += colonWidth + gap;
        continue;
      }
      if (unit == '/') {
        canvas.drawLine(
          Offset(x + colonWidth * .2, size.height * .88),
          Offset(x + colonWidth * .8, size.height * .12),
          Paint()
            ..color = color
            ..strokeWidth = math.max(2, colonWidth * .18)
            ..strokeCap = StrokeCap.round,
        );
        x += colonWidth + gap;
        continue;
      }
      _paintDigit(canvas, Rect.fromLTWH(x, 0, digitWidth, size.height),
          _segments[unit] ?? const {});
      x += digitWidth + gap;
    }
  }

  void _paintDigit(Canvas canvas, Rect box, Set<int> active) {
    final thickness = math.min(box.width, box.height) * .16;
    final inset = thickness * .62;
    final half = box.height / 2;
    final horizontal = [
      Rect.fromLTWH(
          box.left + inset, box.top, box.width - inset * 2, thickness),
      Rect.fromLTWH(box.left + inset, box.top + half - thickness / 2,
          box.width - inset * 2, thickness),
      Rect.fromLTWH(box.left + inset, box.bottom - thickness,
          box.width - inset * 2, thickness),
    ];
    final vertical = [
      Rect.fromLTWH(box.left, box.top + inset, thickness, half - inset * 1.5),
      Rect.fromLTWH(box.right - thickness, box.top + inset, thickness,
          half - inset * 1.5),
      Rect.fromLTWH(
          box.left, box.top + half + inset / 2, thickness, half - inset * 1.5),
      Rect.fromLTWH(box.right - thickness, box.top + half + inset / 2,
          thickness, half - inset * 1.5),
    ];
    final rects = [
      horizontal[0],
      vertical[0],
      vertical[1],
      horizontal[1],
      vertical[2],
      vertical[3],
      horizontal[2]
    ];
    for (var index = 0; index < rects.length; index++) {
      final enabled = active.contains(index);
      final paint = Paint()
        ..isAntiAlias = true
        ..color = color.withValues(alpha: enabled ? 1 : .025);
      canvas.drawRRect(
          RRect.fromRectAndRadius(
              rects[index], Radius.circular(thickness * .35)),
          paint);
    }
  }

  @override
  bool shouldRepaint(covariant _SevenSegmentPainter oldDelegate) =>
      oldDelegate.value != value || oldDelegate.color != color;
}

class _DateScene extends StatelessWidget {
  const _DateScene({required this.scene});
  final PresentationScene scene;

  @override
  Widget build(BuildContext context) => Center(
        child: Text(
          '${scene.data['date'] ?? '--/--/----'}',
          style: const TextStyle(
            color: Colors.white,
            fontSize: 104,
            fontWeight: FontWeight.w300,
            letterSpacing: 5,
          ),
        ),
      );
}

class _WeatherScene extends StatelessWidget {
  const _WeatherScene({required this.scene, required this.progress});
  final PresentationScene scene;
  final double progress;

  @override
  Widget build(BuildContext context) {
    final temperature = scene.data['temperature'];
    final minimum = scene.data['minimum_temperature'];
    final maximum = scene.data['maximum_temperature'];
    final periodLabel = '${scene.data['period_label'] ?? ''}';
    return Stack(
      children: [
        Positioned.fill(
          child: CustomPaint(
            painter: _WeatherPainter(
              variant: scene.variant,
              progress: progress,
            ),
          ),
        ),
        if (periodLabel.isNotEmpty)
          Positioned(
            left: 38,
            top: 28,
            child: Text(
              periodLabel,
              style: const TextStyle(
                color: Color(0xFF20C4DA),
                fontSize: 34,
                fontWeight: FontWeight.w700,
                letterSpacing: 6,
              ),
            ),
          ),
        if (temperature != null)
          Positioned(
            right: 38,
            bottom: 28,
            child: Text(
              '${temperature is num ? temperature.round() : temperature}°',
              style: const TextStyle(
                color: Colors.white,
                fontSize: 64,
                fontWeight: FontWeight.w300,
              ),
            ),
          ),
        if (minimum != null && maximum != null)
          Positioned(
            right: 38,
            bottom: 28,
            child: Text(
              '${(minimum as num).round()}°  /  ${(maximum as num).round()}°',
              style: const TextStyle(
                color: Colors.white,
                fontSize: 58,
                fontWeight: FontWeight.w500,
                letterSpacing: 4,
              ),
            ),
          ),
      ],
    );
  }
}

class _WeatherPainter extends CustomPainter {
  const _WeatherPainter({required this.variant, required this.progress});
  final String variant;
  final double progress;

  @override
  void paint(Canvas canvas, Size size) {
    if (variant == 'night') {
      _paintNight(canvas, size);
      return;
    }
    if (variant == 'sunny') {
      _paintSun(canvas, size);
      return;
    }
    _paintCloud(canvas, size);
    if (variant == 'rain' || variant == 'storm') _paintRain(canvas, size);
    if (variant == 'storm' && progress > .45 && progress < .52) {
      final flash = Paint()..color = Colors.white.withValues(alpha: .22);
      canvas.drawRect(Offset.zero & size, flash);
    }
  }

  void _paintNight(Canvas canvas, Size size) {
    const cyan = Color(0xFF20A9C2);
    final pixel = math.max(5.0, size.shortestSide * .014);
    final star = Paint()
      ..color = cyan.withValues(alpha: .65)
      ..isAntiAlias = false;
    for (var i = 0; i < 24; i++) {
      final x = ((i * 73) % 97) / 100 * size.width;
      final y = ((i * 41) % 71) / 100 * size.height;
      canvas.drawRect(Rect.fromLTWH(x, y, pixel, pixel), star);
    }
    final unit = size.shortestSide * .035;
    final origin = Offset(size.width * .38, size.height * .20);
    const rows = [
      '..XXXX..',
      '.XXXXXX.',
      'XXXXXXXX',
      'XXXXXXXX',
      'XXXXXXXX',
      '.XXXXXX.',
      '..XXXX..'
    ];
    for (var y = 0; y < rows.length; y++) {
      for (var x = 0; x < rows[y].length; x++) {
        if (rows[y][x] == 'X') {
          final shaded = (x == 1 && y > 2) || (x == 5 && y == 2);
          canvas.drawRect(
            Rect.fromLTWH(origin.dx + x * unit, origin.dy + y * unit, unit + .5,
                unit + .5),
            Paint()
              ..color =
                  shaded ? const Color(0xFF9EB3B4) : const Color(0xFFFFFFD9)
              ..isAntiAlias = false,
          );
        }
      }
    }
  }

  void _paintSun(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height / 2);
    final pulse = 1 + math.sin(progress * math.pi * 2) * .04;
    final unit = math.min(size.width, size.height) * .035 * pulse;
    final paint = Paint()
      ..color = const Color(0xFFFFD34E)
      ..isAntiAlias = false;
    for (var y = -4; y <= 4; y++) {
      for (var x = -4; x <= 4; x++) {
        if (x.abs() + y.abs() <= 6) {
          canvas.drawRect(
            Rect.fromCenter(
              center: center + Offset(x * unit, y * unit),
              width: unit,
              height: unit,
            ),
            paint,
          );
        }
      }
    }
  }

  void _paintCloud(Canvas canvas, Size size) {
    // A flat single-color silhouette read as "just a blue block" rather
    // than a cloud (reported directly). A thin darker-blue outline plus a
    // white puffy top over a blue base band -- the same structure as a
    // typical pixel-art cloud icon -- gives it an actual shape and depth.
    final outline = Paint()
      ..color = variant == 'storm' ? const Color(0xFF3A3E46) : const Color(0xFF4A90D9)
      ..isAntiAlias = false;
    final base = Paint()
      ..color = variant == 'storm' ? const Color(0xFF6B6F78) : const Color(0xFF8FC6F0)
      ..isAntiAlias = false;
    final puff = Paint()
      ..color = variant == 'storm' ? const Color(0xFFD8DADD) : Colors.white
      ..isAntiAlias = false;
    final cx = size.width / 2;
    final cy = size.height * .35;
    final unit = math.min(size.width, size.height) * .055;
    const rows = <String>[
      '....XXXX....',
      '..XXXXXXXX..',
      '.XXXXXXXXXX.',
      'XXXXXXXXXXXX',
      'XXXXXXXXXXXX',
    ];
    bool filled(int y, int x) =>
        y >= 0 && y < rows.length && x >= 0 && x < rows[y].length && rows[y][x] == 'X';
    for (var y = -1; y <= rows.length; y++) {
      for (var x = -1; x <= 13; x++) {
        if (filled(y, x)) continue;
        final touchesCloud = filled(y - 1, x) || filled(y + 1, x) || filled(y, x - 1) || filled(y, x + 1);
        if (!touchesCloud) continue;
        canvas.drawRect(
          Rect.fromLTWH(cx + (x - 6) * unit, cy + (y - 2) * unit, unit + .5, unit + .5),
          outline,
        );
      }
    }
    for (var y = 0; y < rows.length; y++) {
      for (var x = 0; x < rows[y].length; x++) {
        if (rows[y][x] != 'X') continue;
        // The top lobes read as the puffy highlight (white, like a
        // reference pixel-cloud icon); the bottom two full-width rows are
        // the cloud's flatter base band.
        final paint = y < rows.length - 2 ? puff : base;
        canvas.drawRect(
          Rect.fromLTWH(cx + (x - 6) * unit, cy + (y - 2) * unit, unit + .5, unit + .5),
          paint,
        );
      }
    }
  }

  void _paintRain(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = const Color(0xFF63C7FF)
      ..isAntiAlias = false;
    for (var i = 0; i < 13; i++) {
      final x = size.width * (.18 + i * .052);
      final travel = (progress + i * .117) % 1;
      final y = size.height * (.48 + travel * .5);
      canvas.drawRect(Rect.fromLTWH(x, y, 7, 22), paint);
    }
  }

  @override
  bool shouldRepaint(covariant _WeatherPainter oldDelegate) =>
      oldDelegate.progress != progress || oldDelegate.variant != variant;
}

/// Maps a lyric line's own mood (classified backend-side from that line's
/// actual words, see `MusicExperienceService`/`_classify_mood_from_lyrics`)
/// to a distinct typographic voice -- computed *per line*, not once for the
/// whole track, so the type actually alternates as the song moves between
/// an angry verse and a tender chorus, say. Four bundled, OFL-licensed
/// fonts (assets/fonts/), deliberately not the Android system font the
/// first version used, which still read as "default" despite the weight/
/// style variation. Deliberately *not* decorative icons/imagery, since an
/// unrelated drawing (a flower on a metal track, say) reads as more wrong
/// than no decoration at all -- the real album art's own colors (see
/// `_MusicSceneState._palette`) carry the "this looks like *this* song"
/// job instead, since they can never mismatch the track.
class _MoodStyle {
  const _MoodStyle({
    required this.fontFamily,
    required this.baseWeight,
    required this.strongWeight,
    required this.fontStyle,
    required this.strongDecoration,
    required this.letterSpacing,
  });

  final String fontFamily;
  final FontWeight baseWeight;
  final FontWeight strongWeight;
  final FontStyle fontStyle;
  final TextDecoration strongDecoration;
  final double letterSpacing;

  static _MoodStyle forMood(String mood) => switch (mood) {
        'intense' => const _MoodStyle(
            fontFamily: 'BebasNeue',
            baseWeight: FontWeight.w400,
            strongWeight: FontWeight.w700,
            fontStyle: FontStyle.normal,
            strongDecoration: TextDecoration.none,
            letterSpacing: 1.2,
          ),
        'melancholic' => const _MoodStyle(
            fontFamily: 'PlayfairDisplayItalic',
            baseWeight: FontWeight.w400,
            strongWeight: FontWeight.w700,
            fontStyle: FontStyle.italic,
            strongDecoration: TextDecoration.none,
            letterSpacing: 0,
          ),
        'tender' => const _MoodStyle(
            fontFamily: 'Quicksand',
            baseWeight: FontWeight.w400,
            strongWeight: FontWeight.w700,
            fontStyle: FontStyle.normal,
            strongDecoration: TextDecoration.underline,
            letterSpacing: 0,
          ),
        _ => const _MoodStyle( // 'bright' and any unrecognized value
            fontFamily: 'Poppins',
            baseWeight: FontWeight.w400,
            strongWeight: FontWeight.w700,
            fontStyle: FontStyle.normal,
            strongDecoration: TextDecoration.none,
            letterSpacing: .2,
          ),
      };
}

class _MusicScene extends StatefulWidget {
  const _MusicScene({required this.scene, required this.progress});
  final PresentationScene scene;
  final double progress;

  @override
  State<_MusicScene> createState() => _MusicSceneState();
}

class _MusicSceneState extends State<_MusicScene> {
  // Keyed by track_id, shared across every _MusicScene instance -- the sync
  // loop re-sends the scene roughly once a second, and re-downloading +
  // re-analyzing the same artwork on every one of those would be wasteful
  // and would make the backdrop visibly flicker as it re-settles.
  static final Map<String, PaletteGenerator> _paletteCache = {};

  late final Timer _ticker;
  PaletteGenerator? _palette;
  String? _paletteFor;
  // The tablet's own clock, not the server's `observed_at_ms` -- comparing
  // a timestamp stamped by a *different* machine against this device's
  // `DateTime.now()` is only as accurate as those two clocks agree, and in
  // practice they don't (a real, previously-measured multi-second offset
  // between this tablet and the PC running the brain). That skew doesn't
  // just shift the displayed time by a constant -- it can make elapsed-
  // since-update come out negative, which the old code silently clamped to
  // 0, freezing the display until the *next* update jumped it forward by
  // however much real time had actually passed (the "counts by 2s" bug).
  // Recording "when *this device* saw this progress value" and measuring
  // elapsed against that instead keeps both sides of the subtraction on
  // the same clock.
  int? _lastKnownProgressMs;
  DateTime _lastProgressSeenAt = DateTime.now();

  @override
  void initState() {
    super.initState();
    _lastKnownProgressMs = (widget.scene.data['progress_ms'] as num?)?.toInt();
    _ticker = Timer.periodic(const Duration(milliseconds: 80), (_) {
      if (mounted) setState(() {});
    });
  }

  @override
  void didUpdateWidget(covariant _MusicScene oldWidget) {
    super.didUpdateWidget(oldWidget);
    final progress = (widget.scene.data['progress_ms'] as num?)?.toInt();
    if (progress != _lastKnownProgressMs) {
      _lastKnownProgressMs = progress;
      _lastProgressSeenAt = DateTime.now();
    }
  }

  @override
  void dispose() {
    _ticker.cancel();
    super.dispose();
  }

  int get _position {
    final data = widget.scene.data;
    final base = (data['progress_ms'] as num?)?.toInt() ?? 0;
    if (data['is_playing'] != true) return base;
    final elapsed = DateTime.now().difference(_lastProgressSeenAt).inMilliseconds;
    // This ceiling only guards against runaway extrapolation if updates
    // stop arriving altogether (e.g. the connection drops), so it can be
    // generous -- normal jitter between the ~1s server updates should
    // never come close to it.
    return base + elapsed.clamp(0, 30000);
  }

  String _time(int milliseconds) {
    final seconds = (milliseconds.clamp(0, 86400000) / 1000).floor();
    return '${seconds ~/ 60}:${(seconds % 60).toString().padLeft(2, '0')}';
  }

  void _ensurePalette(String trackId, String artworkUrl) {
    if (trackId.isEmpty || trackId == _paletteFor) return;
    _paletteFor = trackId;
    final cached = _paletteCache[trackId];
    if (cached != null) {
      scheduleMicrotask(() { if (mounted) setState(() => _palette = cached); });
      return;
    }
    if (artworkUrl.isEmpty) return;
    PaletteGenerator.fromImageProvider(
      NetworkImage(artworkUrl),
      size: const Size(80, 80),
      maximumColorCount: 12,
    ).then((generator) {
      _paletteCache[trackId] = generator;
      if (mounted && _paletteFor == trackId) setState(() => _palette = generator);
    }).catchError((_) {
      // No artwork, or a network hiccup -- the neutral fallback gradient
      // below covers this without breaking the scene.
    });
  }

  /// A gradient built from the *actual* album art's own colors -- always
  /// accurate to this specific track, unlike a generic or searched image.
  Widget _backdrop({required Widget child}) {
    final glow = _palette?.vibrantColor?.color ??
        _palette?.dominantColor?.color ??
        const Color(0xFF2A2A2A);
    final base = _palette?.darkMutedColor?.color ??
        _palette?.darkVibrantColor?.color ??
        Colors.black;
    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: RadialGradient(
          center: const Alignment(-.4, .6),
          radius: 1.35,
          colors: [glow.withValues(alpha: .55), base.withValues(alpha: .92), Colors.black],
          stops: const [0, .55, 1],
        ),
      ),
      child: child,
    );
  }

  /// Centered title/artist header for Lyric Mode -- the typographic
  /// composition below is the star of the screen, but it's still nice to
  /// always know what's playing without it competing for attention, so
  /// this stays legible but modest (Player Mode already shows title/artist
  /// prominently in its own layout and doesn't need this too).
  Widget _titleLabel(Map<String, dynamic> data) {
    final title = '${data['title'] ?? ''}';
    final artist = '${data['artist'] ?? ''}';
    if (title.isEmpty) return const SizedBox.shrink();
    final accent = _palette?.lightVibrantColor?.color ?? _palette?.vibrantColor?.color ?? Colors.white70;
    return Positioned(
      top: 22,
      left: 24,
      right: 24,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(title, textAlign: TextAlign.center, maxLines: 1, overflow: TextOverflow.ellipsis,
            style: const TextStyle(color: Colors.white, fontSize: 22, fontWeight: FontWeight.w800, letterSpacing: .2)),
          if (artist.isNotEmpty) ...[
            const SizedBox(height: 3),
            Text(artist, textAlign: TextAlign.center, maxLines: 1, overflow: TextOverflow.ellipsis,
              style: TextStyle(color: accent.withValues(alpha: .85), fontSize: 14, fontWeight: FontWeight.w500)),
          ],
        ],
      ),
    );
  }

  /// A small persistent "now playing" anchor for Lyric Mode -- a rotating
  /// vinyl-style disc using the track's own artwork, plus a slim progress
  /// bar. Player Mode already shows the full artwork/progress prominently
  /// and doesn't need this too.
  Widget _miniDisc(Map<String, dynamic> data) {
    final artwork = '${data['artwork_url'] ?? ''}';
    final duration = (data['duration_ms'] as num?)?.toInt() ?? 1;
    final position = _position.clamp(0, duration);
    final isPlaying = data['is_playing'] == true;
    final accent = _palette?.lightVibrantColor?.color ?? _palette?.vibrantColor?.color ?? Colors.white;
    return Positioned(
      left: 24,
      bottom: 24,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Transform.rotate(
            angle: isPlaying ? widget.progress * 2 * math.pi : 0,
            child: Container(
              width: 56,
              height: 56,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                border: Border.all(color: Colors.white24, width: 2),
                color: const Color(0xFF1A1A1A),
                image: artwork.isEmpty ? null : DecorationImage(
                  image: NetworkImage(artwork), fit: BoxFit.cover, onError: (_, __) {}),
              ),
              child: Center(
                child: Container(width: 10, height: 10,
                  decoration: const BoxDecoration(shape: BoxShape.circle, color: Colors.black87)),
              ),
            ),
          ),
          const SizedBox(width: 12),
          SizedBox(
            width: 130,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                ClipRRect(borderRadius: BorderRadius.circular(2), child: LinearProgressIndicator(
                  minHeight: 3, value: duration <= 0 ? 0 : position / duration,
                  backgroundColor: Colors.white12, valueColor: AlwaysStoppedAnimation(accent))),
                const SizedBox(height: 4),
                Text('${_time(position)} / ${_time(duration)}',
                  style: const TextStyle(color: Colors.white54, fontSize: 11)),
              ],
            ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final data = widget.scene.data;
    _ensurePalette('${data['track_id'] ?? ''}', '${data['artwork_url'] ?? ''}');
    final mood = _MoodStyle.forMood('${data['mood'] ?? 'bright'}');
    final isLyrics = widget.scene.variant == 'lyrics';
    final content = isLyrics ? _lyrics(mood) : _player(mood);
    return SizedBox.expand(
      child: _backdrop(
        child: Stack(children: [
          content,
          if (isLyrics) _titleLabel(data),
          if (isLyrics) _miniDisc(data),
        ]),
      ),
    );
  }

  Widget _player(_MoodStyle mood) {
    final data = widget.scene.data;
    final title = '${data['title'] ?? data['query'] ?? 'Tocando agora'}';
    final artist = '${data['artist'] ?? ''}';
    final artwork = '${data['artwork_url'] ?? ''}';
    final duration = (data['duration_ms'] as num?)?.toInt() ?? 1;
    final position = _position.clamp(0, duration);
    final accent = _palette?.lightVibrantColor?.color ?? _palette?.vibrantColor?.color ?? Colors.white;
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 52, vertical: 34),
      child: Row(children: [
        Expanded(flex: 5, child: AspectRatio(aspectRatio: 1,
          child: ClipRRect(borderRadius: BorderRadius.circular(22),
            child: artwork.isEmpty ? const ColoredBox(color: Color(0xFF111111))
              : Image.network(artwork, fit: BoxFit.cover,
                  errorBuilder: (_, __, ___) => const ColoredBox(color: Color(0xFF111111)))))),
        const SizedBox(width: 48),
        Expanded(flex: 6, child: Column(crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisAlignment: MainAxisAlignment.center, children: [
            Text(title, maxLines: 2, overflow: TextOverflow.ellipsis,
              style: TextStyle(color: Colors.white, fontSize: 44, height: 1.05,
                fontFamily: mood.fontFamily, fontWeight: mood.strongWeight)),
            const SizedBox(height: 14),
            Text(artist, maxLines: 1, overflow: TextOverflow.ellipsis,
              style: const TextStyle(color: Colors.white60, fontSize: 25)),
            const SizedBox(height: 42),
            ClipRRect(borderRadius: BorderRadius.circular(3), child: LinearProgressIndicator(
              minHeight: 5, value: duration <= 0 ? 0 : position / duration,
              backgroundColor: Colors.white12, valueColor: AlwaysStoppedAnimation(accent))),
            const SizedBox(height: 10),
            Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
              Text(_time(position), style: const TextStyle(color: Colors.white54, fontSize: 16)),
              Icon(data['is_playing'] == true ? Icons.pause_rounded : Icons.play_arrow_rounded,
                color: accent, size: 30),
              Text(_time(duration), style: const TextStyle(color: Colors.white54, fontSize: 16)),
            ])
          ]))
      ]),
    );
  }

  Widget _lyrics(_MoodStyle mood) {
    final raw = widget.scene.data['visual_cues'];
    final cues = raw is List ? raw.whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList() : <Map<String, dynamic>>[];
    // No synced lyrics for this track at all -- Player Mode is the correct
    // fallback. A gap *between* known lines (intro, instrumental bridge...)
    // is different: still gets its own indicator below instead of bouncing
    // the whole scene over to Player Mode for a few seconds.
    if (cues.isEmpty) return _player(mood);
    final position = _position;
    Map<String, dynamic>? cue;
    for (final candidate in cues) {
      final start = (candidate['start_ms'] as num?)?.toInt() ?? 0;
      final end = (candidate['end_ms'] as num?)?.toInt() ?? start;
      if (position >= start && position < end) { cue = candidate; break; }
    }
    if (cue == null) return _gapIndicator();
    final layout = '${cue['layout'] ?? 'center'}';
    final scale = (cue['scale'] as num?)?.toDouble() ?? 1;
    final emphasis = '${cue['emphasis'] ?? 'normal'}';
    // Mood is classified per line on the backend -- using it here (instead
    // of the whole-track mood passed in) is what makes the typography
    // actually alternate as the song itself moves between, say, an angry
    // verse and a tender chorus, rather than picking one voice for the
    // entire track.
    final lineMood = _MoodStyle.forMood('${cue['mood'] ?? 'bright'}');
    Alignment alignment = Alignment.center;
    TextAlign align = TextAlign.center;
    if (layout == 'lower_left') { alignment = const Alignment(-.72, .62); align = TextAlign.left; }
    if (layout == 'upper_right') { alignment = const Alignment(.72, -.58); align = TextAlign.right; }
    if (layout == 'left') { alignment = const Alignment(-.65, 0); align = TextAlign.left; }
    if (layout == 'right') { alignment = const Alignment(.65, 0); align = TextAlign.right; }
    final accent = _palette?.lightVibrantColor?.color ?? _palette?.vibrantColor?.color ?? Colors.white;
    // "hero" (a short, held, high-impact line) and "chorus" (a repeat,
    // intensifying each time via `scale`) are the closest zero-AI proxy
    // this has for "a shouted/peak moment" -- there's no per-line loudness
    // data available, but a line already earning one of those treatments
    // is a reasonable stand-in, so it reads in full caps.
    final shout = emphasis == 'hero' || emphasis == 'chorus';
    final rawWords = cue['words'];
    final strongWords = rawWords is List
      ? rawWords.map((w) => _stripPunctuation('$w')).where((w) => w.isNotEmpty).toSet()
      : const <String>{};
    final text = shout ? '${cue['text']}'.toUpperCase() : '${cue['text']}';
    final baseStyle = TextStyle(color: Colors.white, height: .94,
      letterSpacing: lineMood.letterSpacing, fontFamily: lineMood.fontFamily, fontStyle: lineMood.fontStyle,
      fontSize: 52 * scale, fontWeight: emphasis == 'normal' ? lineMood.baseWeight : lineMood.strongWeight);
    // Most lines carry no per-word emphasis (an empty `words` list, the
    // common case) -- a plain Text avoids building a TextSpan tree for
    // nothing. When a line does have standout words, each gets a
    // noticeably bigger/heavier style than the rest of the same line, so
    // "some words matter more than others" reads as a real typographic
    // choice rather than uniform text.
    final textWidget = strongWords.isEmpty
      ? Text(text, textAlign: align, style: baseStyle)
      : Text.rich(TextSpan(children: [
          for (final (i, word) in text.split(' ').indexed) ...[
            // The separator must carry the same font size as its
            // neighbours -- an unstyled space defaults to the ambient
            // 14px style, which reads as almost no gap at all next to
            // 50-90px word text and is what made lines look like their
            // words were running together.
            if (i > 0) TextSpan(text: ' ', style: baseStyle),
            TextSpan(
              text: word,
              style: strongWords.contains(_stripPunctuation(word))
                ? baseStyle.copyWith(
                    fontSize: baseStyle.fontSize! * 1.32,
                    fontWeight: lineMood.strongWeight,
                    decoration: lineMood.strongDecoration,
                    decorationColor: accent,
                    decorationThickness: 3,
                    color: accent,
                  )
                : baseStyle,
            ),
          ],
        ]), textAlign: align);
    return AnimatedSwitcher(
      duration: const Duration(milliseconds: 360),
      transitionBuilder: (child, animation) => FadeTransition(opacity: animation,
        child: ScaleTransition(scale: Tween(begin: .96, end: 1.0).animate(animation), child: child)),
      child: Align(key: ValueKey('${cue['start_ms']}'), alignment: alignment,
        child: FractionallySizedBox(widthFactor: .72, child: textWidget)));
  }

  /// Shown between known lines (intro, instrumental bridge...) instead of
  /// falling all the way back to Player Mode for a few seconds -- three
  /// softly pulsing dots, the same idea as Spotify's own lyric view during
  /// a gap, riding the same looping animation the rest of the scene uses.
  Widget _gapIndicator() {
    return Align(
      key: const ValueKey('lyric_gap'),
      alignment: Alignment.center,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (var i = 0; i < 3; i++)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 7),
              child: Opacity(
                opacity: .25 + .65 * ((math.sin(widget.progress * 2 * math.pi - i * 1.1) + 1) / 2),
                child: Container(
                  width: 14,
                  height: 14,
                  decoration: const BoxDecoration(shape: BoxShape.circle, color: Colors.white),
                ),
              ),
            ),
        ],
      ),
    );
  }

  static String _stripPunctuation(String word) =>
      word.toLowerCase().replaceAll(RegExp(r'[^\w]', unicode: true), '');
}

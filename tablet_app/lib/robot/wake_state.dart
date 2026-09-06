/// Whether the robot is passively waiting for its wake word (free, local
/// recognizer only) or actively listening/conversing (the better but
/// paid-per-use streaming pipeline). Orthogonal to [RobotDisplayState]:
/// a full conversation turn (listening/thinking/speaking) can happen while
/// [active], but nothing in [standby] ever leaves the device.
enum WakeState { standby, active }

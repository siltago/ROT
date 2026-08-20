enum RobotDisplayState {
  offline,
  idle,
  listening,
  thinking,
  acting,
  speaking,
  error,
  sleeping,
}

extension RobotDisplayStateX on RobotDisplayState {
  String get label => switch (this) {
        RobotDisplayState.offline => 'OFFLINE',
        RobotDisplayState.idle => 'IDLE',
        RobotDisplayState.listening => 'LISTENING',
        RobotDisplayState.thinking => 'THINKING',
        RobotDisplayState.acting => 'ACTING',
        RobotDisplayState.speaking => 'SPEAKING',
        RobotDisplayState.error => 'ERROR',
        RobotDisplayState.sleeping => 'SLEEPING',
      };
}

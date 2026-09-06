import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:web_socket_channel/web_socket_channel.dart';

import '../../app/config.dart';
import '../protocol/protocol.dart';

enum ConnectionStatus { disconnected, connecting, connected }

typedef WebSocketConnector = WebSocketChannel Function(Uri uri);

class RobotConnection {
  RobotConnection({
    WebSocketConnector? connector,
    this.baseReconnectDelay = AppConfig.reconnectDelay,
    this.maxReconnectDelay = AppConfig.maxReconnectDelay,
  }) : _connector = connector ?? WebSocketChannel.connect;

  final WebSocketConnector _connector;
  final Duration baseReconnectDelay;
  final Duration maxReconnectDelay;
  final StreamController<Map<String, dynamic>> _messages =
      StreamController<Map<String, dynamic>>.broadcast();
  final StreamController<Uint8List> _binaryMessages =
      StreamController<Uint8List>.broadcast();
  final StreamController<ConnectionStatus> _statuses =
      StreamController<ConnectionStatus>.broadcast();
  WebSocketChannel? _channel;
  StreamSubscription<dynamic>? _subscription;
  Timer? _reconnectTimer;
  String? _url;
  bool _disposed = false;
  int _attempt = 0;
  ConnectionStatus _status = ConnectionStatus.disconnected;

  Stream<Map<String, dynamic>> get onMessage => _messages.stream;
  Stream<Uint8List> get onBinaryMessage => _binaryMessages.stream;
  Stream<ConnectionStatus> get onStatus => _statuses.stream;
  ConnectionStatus get status => _status;
  bool get isConnected => _status == ConnectionStatus.connected;

  Future<void> connect(String url) async {
    _url = url;
    _reconnectTimer?.cancel();
    await _open();
  }

  Future<void> _open() async {
    if (_disposed || _url == null || _status == ConnectionStatus.connecting) {
      return;
    }
    _setStatus(ConnectionStatus.connecting);
    try {
      await _subscription?.cancel();
      await _channel?.sink.close();
      final channel = _connector(Uri.parse(_url!));
      _channel = channel;
      await channel.ready.timeout(AppConfig.connectionTimeout);
      if (_disposed) {
        await channel.sink.close();
        return;
      }
      _attempt = 0;
      _reconnectTimer?.cancel();
      _setStatus(ConnectionStatus.connected);
      _subscription = channel.stream.listen(
        _handleFrame,
        onError: (_) => _handleDisconnect(),
        onDone: _handleDisconnect,
        cancelOnError: true,
      );
    } catch (_) {
      await _channel?.sink.close();
      _handleDisconnect();
    }
  }

  void _handleFrame(dynamic data) {
    if (data is List<int>) {
      _binaryMessages.add(Uint8List.fromList(data));
      return;
    }
    try {
      final decoded = jsonDecode(data.toString());
      if (decoded is Map) _messages.add(Map<String, dynamic>.from(decoded));
    } on FormatException {
      // Ignore malformed frames without taking down the device connection.
    }
  }

  void _handleDisconnect() {
    if (_disposed) return;
    _setStatus(ConnectionStatus.disconnected);
    _scheduleReconnect();
  }

  void _scheduleReconnect() {
    if (_disposed || _url == null || _reconnectTimer?.isActive == true) return;
    final multiplier = 1 << _attempt.clamp(0, 4).toInt();
    final calculated = baseReconnectDelay * multiplier;
    final delay =
        calculated > maxReconnectDelay ? maxReconnectDelay : calculated;
    _attempt++;
    _reconnectTimer = Timer(delay, _open);
  }

  bool sendMessage(RobotMessage message) {
    if (!isConnected || _channel == null) return false;
    _channel!.sink.add(jsonEncode(message.toJson()));
    return true;
  }

  bool sendBinary(Uint8List data) {
    if (!isConnected || _channel == null) return false;
    _channel!.sink.add(data);
    return true;
  }

  void _setStatus(ConnectionStatus value) {
    if (_status == value) return;
    _status = value;
    if (!_statuses.isClosed) _statuses.add(value);
  }

  Future<void> dispose() async {
    _disposed = true;
    _reconnectTimer?.cancel();
    await _subscription?.cancel();
    await _channel?.sink.close();
    await _messages.close();
    await _binaryMessages.close();
    await _statuses.close();
  }
}

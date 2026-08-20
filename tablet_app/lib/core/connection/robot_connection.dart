import 'dart:async';
import 'dart:convert';

import 'package:web_socket_channel/web_socket_channel.dart';

import '../protocol/protocol.dart';

class RobotConnection {
  WebSocketChannel? _channel;
  final StreamController<Map<String, dynamic>> _controller = StreamController.broadcast();
  bool _isConnected = false;

  Stream<Map<String, dynamic>> get onMessage => _controller.stream;

  bool get isConnected => _isConnected;

  Future<void> connect(String url) async {
    _channel = WebSocketChannel.connect(Uri.parse(url));
    _isConnected = true;

    _channel!.stream.listen(
      (data) {
        try {
          final decoded = jsonDecode(data);
          if (decoded is Map<String, dynamic>) {
            _controller.add(decoded);
          } else if (decoded is Map) {
            _controller.add(Map<String, dynamic>.from(decoded));
          }
        } catch (_) {
          // ignore invalid frames until robust parser is added
        }
      },
      onError: (_) {
        _isConnected = false;
      },
      onDone: () {
        _isConnected = false;
      },
    );
  }

  void sendMessage(RobotMessage message) {
    if (_channel == null) return;
    _channel!.sink.add(jsonEncode(message.toJson()));
  }

  void dispose() {
    _channel?.sink.close();
    _controller.close();
  }
}

import 'package:flutter/material.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key, required this.initialUrl});

  final String initialUrl;

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  late final TextEditingController _controller;
  String? _error;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: widget.initialUrl);
  }

  void _save() {
    final value = _controller.text.trim();
    final uri = Uri.tryParse(value);
    if (uri == null || !uri.hasAuthority || (uri.scheme != 'ws' && uri.scheme != 'wss')) {
      setState(() => _error = 'Use ws:// ou wss:// com endereço e porta.');
      return;
    }
    Navigator.of(context).pop(value);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Conexão com o cérebro')),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            TextField(
              controller: _controller,
              autofocus: true,
              keyboardType: TextInputType.url,
              decoration: InputDecoration(
                labelText: 'WebSocket do Robot Brain',
                hintText: 'ws://192.168.1.10:8000/ws/device',
                errorText: _error,
                border: const OutlineInputBorder(),
              ),
              onSubmitted: (_) => _save(),
            ),
            const SizedBox(height: 16),
            FilledButton(onPressed: _save, child: const Text('Salvar e reconectar')),
          ],
        ),
      ),
    );
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }
}

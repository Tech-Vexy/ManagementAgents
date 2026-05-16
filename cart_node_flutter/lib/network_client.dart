import 'dart:convert';
import 'dart:io' show Platform;
import 'package:http/http.dart' as http;
import 'package:web_socket_channel/web_socket_channel.dart';

class NetworkClient {
  static String? authToken;
  static WebSocketChannel? _channel;

  // Use 10.0.2.2 for Android Emulator, localhost for iOS simulator
  static String get baseUrl => Platform.isAndroid ? '10.0.2.2:8000' : 'localhost:8000';

  static Future<bool> login(String username, String password) async {
    try {
      final response = await http.post(
        Uri.parse('http://$baseUrl/login'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'username': username, 'password': password}),
      );
      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        authToken = data['token'];
        return true;
      }
    } catch (e) {
      print('Login error: $e');
    }
    return false;
  }

  static WebSocketChannel connectWebSocket() {
    _channel = WebSocketChannel.connect(
      Uri.parse('ws://$baseUrl/live/audio'),
    );
    // Send auth frame immediately
    _channel!.sink.add(jsonEncode({'token': authToken}));
    return _channel!;
  }

  static Future<bool> confirmBill() async {
    if (authToken == null) return false;
    try {
      final response = await http.post(
        Uri.parse('http://$baseUrl/confirm_bill'),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $authToken'
        },
      );
      return response.statusCode == 200;
    } catch (e) {
      print('Confirmation error: $e');
      return false;
    }
  }
}

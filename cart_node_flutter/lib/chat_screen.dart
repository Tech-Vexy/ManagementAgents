import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:record/record.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'network_client.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';

class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key});

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final List<String> _messages = [];
  bool _isRecording = false;
  bool _isProcessing = false;

  // UI Signals
  bool _showMap = false;
  bool _showAddressInput = false;
  bool _showBill = false;
  double _billAmount = 0.0;
  double _shippingFee = 0.0;
  List<String> _billItems = [];
  String? _trackingStatus;
  String? _trackingEta;

  late AudioRecorder _audioRecorder;
  StreamSubscription<Uint8List>? _audioStreamSubscription;
  WebSocketChannel? _channel;

  @override
  void initState() {
    super.initState();
    _audioRecorder = AudioRecorder();
  }

  @override
  void dispose() {
    _audioRecorder.dispose();
    _channel?.sink.close();
    super.dispose();
  }

  Future<void> _startRecording() async {
    final status = await Permission.microphone.request();
    if (status != PermissionStatus.granted) {
      _addMessage("System: Microphone permission denied.");
      return;
    }

    setState(() {
      _isRecording = true;
      _isProcessing = false;
    });

    _channel = NetworkClient.connectWebSocket();
    _addMessage("System: Connected to Gemini Live API.");

    _channel!.stream.listen(
      (message) {
        if (message is String) {
          _handleBackendSignal(message);
        }
      },
      onError: (error) {
        _addMessage("Connection Error: $error");
        setState(() => _isProcessing = false);
      },
      onDone: () {
        // Channel closed
      }
    );

    final stream = await _audioRecorder.startStream(const RecordConfig(
      encoder: AudioEncoder.pcm16bits,
      sampleRate: 16000,
      numChannels: 1,
    ));

    _audioStreamSubscription = stream.listen((data) {
      if (_channel != null) {
        _channel!.sink.add(data);
      }
    });
  }

  Future<void> _stopRecording() async {
    if (!_isRecording) return;

    await _audioStreamSubscription?.cancel();
    await _audioRecorder.stop();

    setState(() {
      _isRecording = false;
      _isProcessing = true;
    });

    _channel?.sink.add(jsonEncode({"type": "end_of_turn"}));
  }

  void _handleBackendSignal(String message) {
    try {
      final jsonMsg = jsonDecode(message);
      final type = jsonMsg["type"];

      if (type == "text") {
        final data = jsonMsg["data"] ?? "";
        if (data.contains("request_address")) {
           setState(() => _showAddressInput = true);
        } else if (data.contains("trigger_maps_ui")) {
           setState(() => _showMap = true);
        } else if (data.contains("present_bill")) {
            // Extract the full JSON payload
            _parseBillPayload(data);
        } else if (data.contains("track_package")) {
            _parseTrackingPayload(data);
        } else {
           _addMessage("Gemini: $data");
        }
      } else if (type == "turn_complete") {
        setState(() => _isProcessing = false);
        _channel?.sink.add(jsonEncode({"type": "close"}));
        _channel?.sink.close();
      } else if (jsonMsg["error"] != null) {
        _addMessage("Error: ${jsonMsg["error"]}");
        setState(() => _isProcessing = false);
        _channel?.sink.close();
      }
    } catch (e) {
      // Ignored non-json string or failed parse
    }
  }

  void _parseBillPayload(String rawData) {
     try {
       // A cheap way to extract the json payload roughly
       final startIndex = rawData.indexOf("{");
       final endIndex = rawData.lastIndexOf("}");
       if (startIndex != -1 && endIndex != -1) {
           final jsonStr = rawData.substring(startIndex, endIndex + 1);
           final payload = jsonDecode(jsonStr);

           setState(() {
             _billAmount = (payload["amount"] as num?)?.toDouble() ?? 0.0;
             _shippingFee = (payload["shipping_fee"] as num?)?.toDouble() ?? 0.0;
             final items = payload["items"] as List<dynamic>?;
             if (items != null) {
                _billItems = items.map((e) => "${e["name"]} : \$${e["price"]}").toList();
             }
             _showBill = true;
           });
       }
     } catch (e) {
        setState(() => _showBill = true);
     }
  }

  void _parseTrackingPayload(String rawData) {
     try {
       final startIndex = rawData.indexOf("{");
       final endIndex = rawData.lastIndexOf("}");
       if (startIndex != -1 && endIndex != -1) {
           final jsonStr = rawData.substring(startIndex, endIndex + 1);
           final payload = jsonDecode(jsonStr);

           setState(() {
             _trackingStatus = payload["status"];
             _trackingEta = payload["eta"];
           });
       }
     } catch (e) {
       // Ignored
     }
  }

  void _addMessage(String text) {
    setState(() {
      _messages.insert(0, text);
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Cart Node AI')),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          children: [
            if (_showMap)
              Container(
                height: 200,
                margin: const EdgeInsets.only(bottom: 8),
                child: const GoogleMap(
                  initialCameraPosition: CameraPosition(
                    target: LatLng(40.7128, -74.0060),
                    zoom: 15,
                  ),
                ),
              ),

            if (_showAddressInput)
               Padding(
                 padding: const EdgeInsets.only(bottom: 8.0),
                 child: ElevatedButton(
                   onPressed: () {
                     // Native intent launcher for Places typically handled via MethodChannels,
                     // but we'll mock the response for the Flutter UI MVP
                     setState(() {
                        _showAddressInput = false;
                        _addMessage("You: Selected address 123 Fake St (Validated)");
                     });
                   },
                   child: const Text("Search Address"),
                 ),
               ),

            if (_trackingStatus != null)
               Card(
                 color: Colors.blue.shade50,
                 margin: const EdgeInsets.only(bottom: 8.0),
                 child: Padding(
                   padding: const EdgeInsets.all(16.0),
                   child: Column(
                     crossAxisAlignment: CrossAxisAlignment.stretch,
                     children: [
                       Text("Package Tracking", style: Theme.of(context).textTheme.titleMedium),
                       const SizedBox(height: 4),
                       Text("Status: $_trackingStatus"),
                       if (_trackingEta != null) Text("ETA: $_trackingEta"),
                     ],
                   ),
                 ),
               ),

            if (_showBill)
               Card(
                 margin: const EdgeInsets.only(bottom: 8.0),
                 child: Padding(
                   padding: const EdgeInsets.all(16.0),
                   child: Column(
                     crossAxisAlignment: CrossAxisAlignment.stretch,
                     children: [
                       Text("Itemized Receipt", style: Theme.of(context).textTheme.titleMedium),
                       const SizedBox(height: 8),
                       ..._billItems.map((item) => Text("- $item")),
                       Text("- Shipping: \$$_shippingFee"),
                       const Divider(height: 16),
                       Text("Total Bill: \$$_billAmount", style: Theme.of(context).textTheme.titleLarge),
                       const SizedBox(height: 16),
                       ElevatedButton(
                         onPressed: () async {
                           _addMessage("You: Confirmed payment of \$$_billAmount");
                           setState(() => _showBill = false);
                           final success = await NetworkClient.confirmBill();
                           if (!success) {
                             _addMessage("Error sending confirmation.");
                           }
                         },
                         child: const Text("Confirm & Pay"),
                       ),
                     ],
                   ),
                 ),
               ),

            Expanded(
              child: ListView.separated(
                reverse: true,
                itemCount: _messages.length,
                separatorBuilder: (context, index) => const Divider(),
                itemBuilder: (context, index) {
                  return Padding(
                    padding: const EdgeInsets.symmetric(vertical: 4.0),
                    child: Text(_messages[index]),
                  );
                },
              ),
            ),
            const SizedBox(height: 16),
            GestureDetector(
              onTapDown: (_) => _startRecording(),
              onTapUp: (_) => _stopRecording(),
              onTapCancel: () => _stopRecording(),
              child: Container(
                width: 120,
                height: 120,
                decoration: BoxDecoration(
                  color: _isRecording ? Colors.red : Theme.of(context).primaryColor,
                  shape: BoxShape.circle,
                ),
                child: Center(
                  child: Text(
                    _isRecording ? "Recording..." : _isProcessing ? "Thinking..." : "Hold to Speak",
                    style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

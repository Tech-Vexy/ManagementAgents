package com.cartnode

import android.Manifest
import android.app.Activity
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.google.android.gms.maps.model.CameraPosition
import com.google.android.gms.maps.model.LatLng
import com.google.android.libraries.places.api.Places
import com.google.android.libraries.places.api.model.Place
import com.google.android.libraries.places.widget.Autocomplete
import com.google.android.libraries.places.widget.model.AutocompleteActivityMode
import com.google.maps.android.compose.GoogleMap
import com.google.maps.android.compose.Marker
import com.google.maps.android.compose.MarkerState
import com.google.maps.android.compose.rememberCameraPositionState
import io.ktor.client.plugins.websocket.*
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.client.statement.HttpResponse
import io.ktor.client.statement.bodyAsText
import io.ktor.http.ContentType
import io.ktor.http.contentType
import io.ktor.websocket.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.coroutines.isActive
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonPrimitive
import java.util.concurrent.atomic.AtomicBoolean

@Serializable
data class LoginRequest(val username: String, val password: String)

@Serializable
data class LoginResponse(val token: String)

class MainActivity : ComponentActivity() {

    private var hasAudioPermission by mutableStateOf(false)

    private val requestPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { isGranted: Boolean ->
        hasAudioPermission = isGranted
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Initialize Places SDK using the meta-data key if available, or a fallback.
        val applicationInfo = packageManager.getApplicationInfo(packageName, PackageManager.GET_META_DATA)
        val apiKey = applicationInfo.metaData?.getString("com.google.android.geo.API_KEY") ?: ""
        if (!Places.isInitialized()) {
            Places.initialize(applicationContext, apiKey)
        }

        hasAudioPermission = ContextCompat.checkSelfPermission(
            this, Manifest.permission.RECORD_AUDIO
        ) == PackageManager.PERMISSION_GRANTED

        if (!hasAudioPermission) {
            requestPermissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
        }

        setContent {
            MaterialTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    var isLoggedIn by remember { mutableStateOf(false) }

                    if (isLoggedIn) {
                        if (hasAudioPermission) {
                            ChatScreen()
                        } else {
                            Text("Microphone permission required for voice orders.", modifier = Modifier.padding(16.dp))
                        }
                    } else {
                        LoginScreen(onLoginSuccess = { isLoggedIn = true })
                    }
                }
            }
        }
    }
}

@Composable
fun LoginScreen(onLoginSuccess: () -> Unit) {
    var username by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var message by remember { mutableStateOf("") }
    val coroutineScope = rememberCoroutineScope()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.Center
    ) {
        OutlinedTextField(
            value = username,
            onValueChange = { username = it },
            label = { Text("Username") },
            modifier = Modifier.fillMaxWidth()
        )
        Spacer(modifier = Modifier.height(8.dp))
        OutlinedTextField(
            value = password,
            onValueChange = { password = it },
            label = { Text("Password") },
            modifier = Modifier.fillMaxWidth()
        )
        Spacer(modifier = Modifier.height(16.dp))
        Button(
            onClick = {
                coroutineScope.launch {
                    try {
                        val response: HttpResponse = NetworkClient.client.post("http://10.0.2.2:8000/login") {
                            contentType(ContentType.Application.Json)
                            setBody(LoginRequest(username, password))
                        }

                        if (response.status.value in 200..299) {
                            val responseBody = response.bodyAsText()
                            val loginResponse = Json.decodeFromString<LoginResponse>(responseBody)
                            NetworkClient.authToken = loginResponse.token
                            onLoginSuccess()
                        } else {
                            message = "Login failed: ${response.status}"
                        }
                    } catch (e: Exception) {
                        message = "Error: ${e.message}"
                    }
                }
            },
            modifier = Modifier.fillMaxWidth()
        ) {
            Text("Login")
        }
        Spacer(modifier = Modifier.height(16.dp))
        Text(text = message)
    }
}

@Composable
fun ChatScreen() {
    var messages by remember { mutableStateOf(listOf<String>()) }
    var isRecording by remember { mutableStateOf(false) }
    var isProcessing by remember { mutableStateOf(false) }
    var showAddressInput by remember { mutableStateOf(false) }
    var showMap by remember { mutableStateOf(false) }
    val coroutineScope = rememberCoroutineScope()

    // To handle microphone recording state safely
    val isRecordingState = remember { AtomicBoolean(false) }

    // Mock user location / destination for demo
    val destination = LatLng(40.7128, -74.0060)
    val cameraPositionState = rememberCameraPositionState {
        position = CameraPosition.fromLatLngZoom(destination, 15f)
    }

    // Places Autocomplete Launcher
    val context = androidx.compose.ui.platform.LocalContext.current
    val intentLauncher = androidx.activity.compose.rememberLauncherForActivityResult(
        contract = ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == Activity.RESULT_OK) {
            result.data?.let { intent ->
                val place = Autocomplete.getPlaceFromIntent(intent)
                messages = messages + "You: Selected address ${place.address}"
                showAddressInput = false
                // Normally this would be streamed back to the agent via WebSocket
            }
        }
    }

    Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        if (showMap) {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(200.dp)
                    .padding(bottom = 8.dp),
                contentAlignment = Alignment.Center
            ) {
                GoogleMap(
                    modifier = Modifier.fillMaxSize(),
                    cameraPositionState = cameraPositionState
                ) {
                    Marker(
                        state = MarkerState(position = destination),
                        title = "Delivery Destination"
                    )
                }
            }
        }

        if (showAddressInput) {
            Button(
                onClick = {
                    val fields = listOf(Place.Field.ID, Place.Field.NAME, Place.Field.ADDRESS)
                    val intent = Autocomplete.IntentBuilder(AutocompleteActivityMode.OVERLAY, fields)
                        .build(context)
                    intentLauncher.launch(intent)
                },
                modifier = Modifier.fillMaxWidth().padding(bottom = 8.dp)
            ) {
                Text("Search Address")
            }
        }

        LazyColumn(
            modifier = Modifier.weight(1f).fillMaxWidth(),
            reverseLayout = true
        ) {
            items(messages.reversed()) { msg ->
                Text(text = msg, modifier = Modifier.padding(vertical = 4.dp))
                HorizontalDivider()
            }
        }

        Spacer(modifier = Modifier.height(16.dp))

        Box(
            modifier = Modifier.fillMaxWidth(),
            contentAlignment = Alignment.Center
        ) {
            Button(
                onClick = { },
                modifier = Modifier
                    .size(120.dp)
                    .pointerInput(Unit) {
                        detectTapGestures(
                            onPress = {
                                if (isProcessing) return@detectTapGestures

                                isRecording = true
                                isRecordingState.set(true)

                                val job = coroutineScope.launch(Dispatchers.IO) {
                                    handleLiveVoiceOrder(
                                        isRecordingState = isRecordingState,
                                        onMessageReceived = { newMsg ->
                                            messages = messages + newMsg
                                        },
                                        onProcessingStateChanged = { state ->
                                            isProcessing = state
                                        },
                                        onUiSignal = { signal ->
                                            if (signal == "request_address") {
                                                showAddressInput = true
                                            } else if (signal == "trigger_maps_ui") {
                                                showMap = true
                                            }
                                        }
                                    )
                                }

                                tryAwaitRelease()

                                isRecording = false
                                isRecordingState.set(false)
                            }
                        )
                    },
                colors = ButtonDefaults.buttonColors(
                    containerColor = if (isRecording) Color.Red else MaterialTheme.colorScheme.primary
                )
            ) {
                Text(if (isRecording) "Recording..." else if (isProcessing) "Thinking..." else "Hold to Speak")
            }
        }
    }
}

private suspend fun handleLiveVoiceOrder(
    isRecordingState: AtomicBoolean,
    onMessageReceived: (String) -> Unit,
    onProcessingStateChanged: (Boolean) -> Unit,
    onUiSignal: (String) -> Unit
) {
    try {
        NetworkClient.client.webSocket("ws://10.0.2.2:8000/live/audio") {
            // First, authenticate
            val authMsg = """{"token": "${NetworkClient.authToken}"}"""
            send(Frame.Text(authMsg))

            withContext(Dispatchers.Main) {
                onMessageReceived("System: Connected to Gemini Live API.")
            }

            // Setup AudioRecord
            val sampleRate = 16000
            val channelConfig = AudioFormat.CHANNEL_IN_MONO
            val audioFormat = AudioFormat.ENCODING_PCM_16BIT
            val minBufferSize = AudioRecord.getMinBufferSize(sampleRate, channelConfig, audioFormat)

            val audioRecord = AudioRecord(
                MediaRecorder.AudioSource.MIC,
                sampleRate,
                channelConfig,
                audioFormat,
                minBufferSize
            )

            if (audioRecord.state != AudioRecord.STATE_INITIALIZED) {
                withContext(Dispatchers.Main) {
                    onMessageReceived("Error: Microphone initialization failed.")
                }
                return@webSocket
            }

            audioRecord.startRecording()

            val recordJob = launch(Dispatchers.IO) {
                val buffer = ByteArray(minBufferSize)
                while (isRecordingState.get() && isActive) {
                    val readResult = audioRecord.read(buffer, 0, buffer.size)
                    if (readResult > 0) {
                        val validData = buffer.copyOf(readResult)
                        send(Frame.Binary(fin = true, data = validData))
                    }
                }
                audioRecord.stop()
                audioRecord.release()

                // Signal to backend that the audio stream (user turn) is complete
                send(Frame.Text("""{"type": "end_of_turn"}"""))

                withContext(Dispatchers.Main) {
                    onProcessingStateChanged(true)
                }
            }

            // Receive responses
            val receiveJob = launch(Dispatchers.IO) {
                try {
                    for (frame in incoming) {
                        when (frame) {
                            is Frame.Text -> {
                                val text = frame.readText()
                                try {
                                    val json = Json.decodeFromString<JsonObject>(text)
                                    if (json["type"]?.jsonPrimitive?.contentOrNull == "text") {
                                        val data = json["data"]?.jsonPrimitive?.contentOrNull ?: ""
                                        if (data.contains("request_address")) {
                                            withContext(Dispatchers.Main) {
                                                onUiSignal("request_address")
                                            }
                                        } else if (data.contains("trigger_maps_ui")) {
                                            withContext(Dispatchers.Main) {
                                                onUiSignal("trigger_maps_ui")
                                            }
                                        } else {
                                            withContext(Dispatchers.Main) {
                                                onMessageReceived("Gemini: $data")
                                            }
                                        }
                                    } else if (json["type"]?.jsonPrimitive?.contentOrNull == "turn_complete") {
                                        withContext(Dispatchers.Main) {
                                            onProcessingStateChanged(false)
                                        }
                                        // Once turn is complete, close connection gracefully
                                        send(Frame.Text("""{"type": "close"}"""))
                                        close()
                                        break
                                    } else if (json["error"] != null) {
                                        withContext(Dispatchers.Main) {
                                            onMessageReceived("Error: ${json["error"]?.jsonPrimitive?.contentOrNull}")
                                            onProcessingStateChanged(false)
                                        }
                                        close()
                                        break
                                    }
                                } catch (e: Exception) {
                                    // Not JSON or unexpected format
                                }
                            }
                            // We ignore incoming audio chunks for now in this MVP UI since it's a text chat interface
                            else -> {}
                        }
                    }
                } catch (e: Exception) {
                     // Handle cancellation or close
                }
            }

            // Wait for recording to finish, then wait a bit for the final processing response
            recordJob.join()
            // We wait until turn_complete or timeout to close websocket
            receiveJob.join()
        }
    } catch (e: Exception) {
        withContext(Dispatchers.Main) {
            onMessageReceived("Connection Error: ${e.message}")
            onProcessingStateChanged(false)
        }
    }
}

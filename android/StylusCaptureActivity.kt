package dev.example.galaxytabled

import android.content.Context
import android.os.Bundle
import android.view.MotionEvent
import android.view.View
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.io.BufferedReader
import java.io.BufferedWriter
import java.io.EOFException
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.InetSocketAddress
import java.net.Socket
import java.util.concurrent.atomic.AtomicLong
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.sin

/** Replace these values with app settings before shipping. Use 127.0.0.1 for adb reverse. */
private const val HOST = "127.0.0.1"
private const val PORT = 8765
private const val SESSION_TOKEN = "MySecretToken123"

class StylusCaptureActivity : ComponentActivity() {
    private var captureView: StylusCaptureView? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            AndroidView(
                modifier = Modifier.fillMaxSize(),
                factory = { context ->
                    StylusCaptureView(context, HOST, PORT, SESSION_TOKEN).also { captureView = it }
                }
            )
        }
    }

    override fun onDestroy() {
        captureView?.close()
        captureView = null
        super.onDestroy()
    }
}

/** A full-screen View is used so the app receives platform MotionEvents and batched history. */
private class StylusCaptureView(
    context: Context,
    host: String,
    port: Int,
    token: String
) : View(context) {
    private val sender = TcpPenSender(host, port, token)
    private val sequence = AtomicLong(0)
    private var inContact = false

    init {
        isFocusable = true
        isFocusableInTouchMode = true
        contentDescription = "S Pen drawing surface"
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        val action = event.actionMasked
        when (action) {
            MotionEvent.ACTION_DOWN, MotionEvent.ACTION_POINTER_DOWN -> {
                val index = if (action == MotionEvent.ACTION_POINTER_DOWN) event.actionIndex else 0
                if (isStylus(event, index)) {
                    inContact = true
                    emitWithHistory(event, index, "down")
                    return true
                }
            }
            MotionEvent.ACTION_MOVE -> {
                var handled = false
                for (index in 0 until event.pointerCount) {
                    if (isStylus(event, index)) {
                        emitWithHistory(event, index, if (inContact) "move" else "hover")
                        handled = true
                    }
                }
                if (handled) return true
            }
            MotionEvent.ACTION_UP, MotionEvent.ACTION_POINTER_UP -> {
                val index = if (action == MotionEvent.ACTION_POINTER_UP) event.actionIndex else 0
                if (isStylus(event, index)) {
                    emitCurrent(event, index, "up")
                    inContact = false
                    return true
                }
            }
            MotionEvent.ACTION_CANCEL -> {
                if (inContact) emitCurrent(event, 0, "cancel")
                inContact = false
                return true
            }
        }
        return true // Consume finger events so they do not draw through this surface.
    }

    override fun onGenericMotionEvent(event: MotionEvent): Boolean {
        val index = 0
        if (!isStylus(event, index)) return super.onGenericMotionEvent(event)
        when (event.actionMasked) {
            MotionEvent.ACTION_HOVER_ENTER, MotionEvent.ACTION_HOVER_MOVE -> {
                emitWithHistory(event, index, "hover")
                return true
            }
            MotionEvent.ACTION_HOVER_EXIT -> {
                emitCurrent(event, index, "leave")
                return true
            }
            MotionEvent.ACTION_BUTTON_PRESS, MotionEvent.ACTION_BUTTON_RELEASE -> {
                emitCurrent(event, index, if (inContact) "move" else "hover")
                return true
            }
        }
        return super.onGenericMotionEvent(event)
    }

    private fun isStylus(event: MotionEvent, index: Int): Boolean =
        index in 0 until event.pointerCount &&
            event.getToolType(index) in setOf(
                MotionEvent.TOOL_TYPE_STYLUS,
                MotionEvent.TOOL_TYPE_ERASER
            )

    private fun emitWithHistory(event: MotionEvent, pointer: Int, phase: String) {
        for (historyIndex in 0 until event.historySize) {
            emit(
                event = event,
                pointer = pointer,
                phase = phase,
                x = event.getHistoricalX(pointer, historyIndex),
                y = event.getHistoricalY(pointer, historyIndex),
                pressure = event.getHistoricalAxisValue(MotionEvent.AXIS_PRESSURE, pointer, historyIndex),
                tiltRadians = event.getHistoricalAxisValue(MotionEvent.AXIS_TILT, pointer, historyIndex),
                orientation = event.getHistoricalAxisValue(MotionEvent.AXIS_ORIENTATION, pointer, historyIndex),
                timeMs = event.getHistoricalEventTime(historyIndex)
            )
        }
        emitCurrent(event, pointer, phase)
    }

    private fun emitCurrent(event: MotionEvent, pointer: Int, phase: String) {
        emit(
            event = event,
            pointer = pointer,
            phase = phase,
            x = event.getX(pointer),
            y = event.getY(pointer),
            pressure = event.getAxisValue(MotionEvent.AXIS_PRESSURE, pointer),
            tiltRadians = event.getAxisValue(MotionEvent.AXIS_TILT, pointer),
            orientation = event.getAxisValue(MotionEvent.AXIS_ORIENTATION, pointer),
            timeMs = event.eventTime
        )
    }

    private fun emit(
        event: MotionEvent,
        pointer: Int,
        phase: String,
        x: Float,
        y: Float,
        pressure: Float,
        tiltRadians: Float,
        orientation: Float,
        timeMs: Long
    ) {
        val nx = if (width > 1) (x / (width - 1)).coerceIn(0f, 1f) else 0f
        val ny = if (height > 1) (y / (height - 1)).coerceIn(0f, 1f) else 0f
        // Android tilt is one angle from perpendicular plus an azimuth. Windows needs X/Y angles.
        val tiltDegrees = (tiltRadians * 180.0 / PI).toFloat().coerceIn(0f, 90f)
        val tiltX = (tiltDegrees * sin(orientation)).coerceIn(-90f, 90f)
        val tiltY = (-tiltDegrees * cos(orientation)).coerceIn(-90f, 90f)
        val buttons = event.buttonState
        val primaryButton = (buttons and MotionEvent.BUTTON_STYLUS_PRIMARY) != 0
        val secondaryButton = (buttons and MotionEvent.BUTTON_STYLUS_SECONDARY) != 0
        val normalizedPressure = if (phase == "up" || phase == "leave" || phase == "cancel") {
            0f
        } else {
            pressure.coerceIn(0f, 1f)
        }

        sender.send(
            JSONObject()
                .put("type", "pen")
                .put("v", 1)
                .put("seq", sequence.incrementAndGet())
                .put("time_ms", timeMs)
                .put("phase", phase)
                .put("x", nx.toDouble())
                .put("y", ny.toDouble())
                .put("pressure", normalizedPressure.toDouble())
                .put("tilt_x", tiltX.toDouble())
                .put("tilt_y", tiltY.toDouble())
                .put("inverted", event.getToolType(pointer) == MotionEvent.TOOL_TYPE_ERASER)
                .put("buttons", JSONObject().put("primary", primaryButton).put("secondary", secondaryButton))
        )
    }

    fun close() = sender.close()
}

/** Single ordered TCP writer. A bounded production queue should preserve DOWN/UP while shedding MOVE. */
private class TcpPenSender(
    private val host: String,
    private val port: Int,
    private val token: String
) {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val outgoing = Channel<String>(capacity = 512)
    @Volatile private var activeSocket: Socket? = null
    @Volatile private var ready = false

    init {
        scope.launch {
            var backoffMs = 250L
            while (isActive) {
                var socket: Socket? = null
                try {
                    socket = Socket().apply {
                        tcpNoDelay = true
                        connect(InetSocketAddress(host, port), 3000)
                    }
                    activeSocket = socket
                    val reader = BufferedReader(InputStreamReader(socket.getInputStream(), Charsets.UTF_8))
                    val writer = BufferedWriter(OutputStreamWriter(socket.getOutputStream(), Charsets.UTF_8))
                    writer.write(JSONObject().put("type", "hello").put("v", 1).put("token", token).toString())
                    writer.newLine()
                    writer.flush()
                    val response = reader.readLine() ?: throw EOFException("Host closed before ready")
                    if (JSONObject(response).optString("type") != "ready") {
                        throw IllegalStateException("Host rejected the session")
                    }
                    // Discard any stale samples from a prior session before accepting new events.
                    while (outgoing.tryReceive().isSuccess) { }
                    ready = true
                    backoffMs = 250L

                    kotlinx.coroutines.coroutineScope {
                        launch {
                            while (isActive) {
                                val line = reader.readLine() ?: throw EOFException("Host disconnected")
                            }
                        }
                        launch {
                            for (line in outgoing) {
                                writer.write(line)
                                writer.newLine()
                                writer.flush()
                            }
                        }
                    }
                } catch (_: Exception) {
                    // Reconnect below. The host releases an active pointer when this socket closes.
                } finally {
                    ready = false
                    try { socket?.close() } catch (_: Exception) { }
                    activeSocket = null
                }
                delay(backoffMs)
                backoffMs = (backoffMs * 2).coerceAtMost(5000L)
            }
        }
    }

    fun send(message: JSONObject) {
        if (!ready) return
        if (outgoing.trySend(message.toString()).isFailure) {
            // A congested queue must not lose a pen-up and leave a stroke held on Windows.
            // Closing the connection makes the host synthesize a cancel, then the sender reconnects.
            ready = false
            try { activeSocket?.close() } catch (_: Exception) { }
        }
    }

    fun close() {
        ready = false
        try { activeSocket?.close() } catch (_: Exception) { }
        outgoing.close()
        scope.cancel()
    }
}

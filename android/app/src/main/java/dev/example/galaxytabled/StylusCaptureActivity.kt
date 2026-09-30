package dev.example.galaxytabled

import android.content.Context
import android.content.Intent
import android.provider.Settings
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Path
import android.os.Bundle
import android.view.MotionEvent
import android.view.View
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.BasicText
import androidx.compose.ui.Alignment
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.setValue
import androidx.activity.compose.BackHandler
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import org.json.JSONObject
import java.io.BufferedInputStream
import java.io.BufferedWriter
import java.io.ByteArrayOutputStream
import java.io.DataInputStream
import java.io.OutputStreamWriter
import java.net.Inet4Address
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.NetworkInterface
import java.net.ServerSocket
import java.net.Socket
import java.net.SocketException
import java.net.SocketTimeoutException
import java.security.MessageDigest
import java.security.SecureRandom
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicLong
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec
import kotlin.concurrent.thread
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.sin

private const val TETHER_PORT = 8765
private const val PROTOCOL_VERSION = 2
private const val MAX_PROTOCOL_LINE = 64 * 1024
private const val MAX_SCREEN_FRAME_BYTES = 16 * 1024 * 1024

class StylusCaptureActivity : ComponentActivity() {
    private var captureView: StylusCaptureView? = null
    private var tetherLink: TetherTcpLink? = null
    private var latestDesktopFrame: Bitmap? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            var connectionMessage by remember { mutableStateOf("Turn on USB tethering, then open the PC app and tap Connect phone.") }
            var fullScreen by remember { mutableStateOf(false) }
            var pairedToPc by remember { mutableStateOf(false) }
            var pairingCode by remember { mutableStateOf("") }
            val link = remember {
                TetherTcpLink(
                    context = applicationContext,
                    onConnectionState = { connected, message ->
                        runOnUiThread {
                            connectionMessage = if (connected) "Connected — ready to draw" else message
                        }
                    },
                    onPairingState = { paired, code ->
                        runOnUiThread {
                            pairedToPc = paired
                            pairingCode = code
                        }
                    },
                    onScreenFrame = { bitmap ->
                        runOnUiThread {
                            val previousFrame = latestDesktopFrame
                            latestDesktopFrame = bitmap
                            captureView?.setDesktopFrame(bitmap)
                            if (previousFrame != null && previousFrame !== bitmap && !previousFrame.isRecycled) {
                                previousFrame.recycle()
                            }
                        }
                    }
                ).also { tetherLink = it }
            }
            LaunchedEffect(fullScreen) { setImmersiveMode(fullScreen) }
            BackHandler(enabled = fullScreen) { fullScreen = false }
            DisposableEffect(link) {
                link.start()
                onDispose { link.close() }
            }
            if (fullScreen) {
                Box(Modifier.fillMaxSize().background(Color.Black)) {
                    AndroidView(
                        modifier = Modifier.fillMaxSize(),
                        factory = { context ->
                            StylusCaptureView(context, link::send).also {
                                captureView = it
                                it.setDesktopFrame(latestDesktopFrame)
                            }
                        }
                    )
                    BasicText(
                        "Exit full screen",
                        modifier = Modifier
                            .align(Alignment.TopEnd)
                            .padding(18.dp)
                            .background(Color(0x99000000), RoundedCornerShape(8.dp))
                            .clickable { fullScreen = false }
                            .padding(horizontal = 14.dp, vertical = 10.dp),
                        style = TextStyle(color = Color.White, fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
                    )
                }
            } else {
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .background(Color(0xFFF2F5FA))
                        .statusBarsPadding()
                        .navigationBarsPadding()
                        .padding(horizontal = 18.dp, vertical = 10.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(
                            modifier = Modifier
                                .size(48.dp)
                                .clip(RoundedCornerShape(15.dp))
                                .background(Color(0xFF1D5FBF)),
                            contentAlignment = Alignment.Center
                        ) {
                            BasicText("V", style = TextStyle(fontSize = 25.sp, fontWeight = FontWeight.Bold, color = Color.White))
                        }
                        Spacer(Modifier.width(12.dp))
                        Column {
                            BasicText("VirtualDT", style = TextStyle(fontSize = 22.sp, fontWeight = FontWeight.Bold, color = Color(0xFF17243A)))
                            BasicText("Your Android stylus, on your Windows PC", style = TextStyle(fontSize = 13.sp, color = Color(0xFF64748B)))
                        }
                    }

                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(18.dp))
                            .background(Color(0xFFE8EFF9))
                            .padding(horizontal = 14.dp, vertical = 11.dp),
                        verticalArrangement = Arrangement.spacedBy(4.dp)
                    ) {
                        BasicText(
                            if (pairedToPc) "PC paired" else "Pair your PC once",
                            style = TextStyle(fontSize = 13.sp, fontWeight = FontWeight.Bold, color = Color(0xFF25436B))
                        )
                        if (pairedToPc) {
                            BasicText("The paired session key stays encrypted on this phone and the PC.", style = TextStyle(fontSize = 12.sp, color = Color(0xFF42556E)))
                            BasicText(
                                "Reset pairing",
                                modifier = Modifier.clickable { link.resetPairing() }.padding(vertical = 3.dp),
                                style = TextStyle(fontSize = 12.sp, fontWeight = FontWeight.SemiBold, color = Color(0xFF1D5FBF))
                            )
                        } else {
                            BasicText("When the PC app asks, enter this one-time code:", style = TextStyle(fontSize = 12.sp, color = Color(0xFF42556E)))
                            BasicText(
                                pairingCode.chunked(4).joinToString("-").ifBlank { "---- ---- ----" },
                                style = TextStyle(fontSize = 22.sp, fontWeight = FontWeight.Bold, color = Color(0xFF1D5FBF))
                            )
                        }
                    }

                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(20.dp))
                            .background(Color.White)
                            .border(1.dp, Color(0xFFE5EAF1), RoundedCornerShape(20.dp))
                            .padding(15.dp)
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Box(
                                Modifier.size(9.dp).clip(CircleShape)
                                    .background(if (connectionMessage.startsWith("Connected")) Color(0xFF2CA66F) else Color(0xFFE1A438))
                            )
                            Spacer(Modifier.width(9.dp))
                            BasicText(
                                if (connectionMessage.startsWith("Connected")) "Connected" else "USB tether connection",
                                style = TextStyle(fontSize = 15.sp, fontWeight = FontWeight.Bold, color = Color(0xFF203149))
                            )
                        }
                        BasicText(
                            connectionMessage,
                            modifier = Modifier.padding(top = 7.dp),
                            style = TextStyle(fontSize = 13.sp, lineHeight = 18.sp, color = Color(0xFF5D6B7E))
                        )
                        BasicText(
                            "Open USB tethering settings  ›",
                            modifier = Modifier
                                .padding(top = 12.dp)
                                .clip(RoundedCornerShape(12.dp))
                                .background(Color(0xFF1D5FBF))
                                .clickable { openTetherSettings() }
                                .padding(horizontal = 14.dp, vertical = 10.dp),
                            style = TextStyle(fontSize = 13.sp, fontWeight = FontWeight.SemiBold, color = Color.White)
                        )
                    }

                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(18.dp))
                            .background(Color(0xFFE8EFF9))
                            .padding(horizontal = 14.dp, vertical = 11.dp),
                        verticalArrangement = Arrangement.spacedBy(5.dp)
                    ) {
                        BasicText("Quick setup", style = TextStyle(fontSize = 13.sp, fontWeight = FontWeight.Bold, color = Color(0xFF25436B)))
                        BasicText("1  Plug the phone into the PC with a USB data cable.", style = TextStyle(fontSize = 12.sp, color = Color(0xFF42556E)))
                        BasicText("2  Turn on USB tethering in Android Settings.", style = TextStyle(fontSize = 12.sp, color = Color(0xFF42556E)))
                        BasicText("3  Open the PC app and choose Connect phone.", style = TextStyle(fontSize = 12.sp, color = Color(0xFF42556E)))
                    }

                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            BasicText("Drawing pad", style = TextStyle(fontSize = 15.sp, fontWeight = FontWeight.Bold, color = Color(0xFF25354B)))
                            BasicText("Android stylus · PC screen preview appears here", style = TextStyle(fontSize = 11.sp, color = Color(0xFF758196)))
                        }
                        BasicText(
                            "FULL SCREEN",
                            modifier = Modifier
                                .clip(RoundedCornerShape(10.dp))
                                .background(Color(0xFFDCE8F8))
                                .clickable { fullScreen = true }
                                .padding(horizontal = 12.dp, vertical = 9.dp),
                            style = TextStyle(fontSize = 11.sp, fontWeight = FontWeight.Bold, color = Color(0xFF1D5FBF))
                        )
                    }

                    AndroidView(
                        modifier = Modifier
                            .weight(1f)
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(20.dp))
                            .border(1.dp, Color(0xFFE4E9F0), RoundedCornerShape(20.dp))
                            .background(Color.White),
                        factory = { context ->
                            StylusCaptureView(context, link::send).also {
                                captureView = it
                                it.setDesktopFrame(latestDesktopFrame)
                            }
                        }
                    )
                    BasicText("Finger touches are ignored. Use a stylus supported by your Android device.", style = TextStyle(fontSize = 11.sp, color = Color(0xFF758196), textAlign = TextAlign.Center))
                }
            }
        }
    }

    private fun openTetherSettings() {
        try {
            startActivity(Intent("android.settings.TETHER_SETTINGS"))
        } catch (_: Exception) {
            try {
                startActivity(Intent(Settings.ACTION_WIRELESS_SETTINGS))
            } catch (_: Exception) {
                startActivity(Intent(Settings.ACTION_SETTINGS))
            }
        }
    }

    @Suppress("DEPRECATION")
    private fun setImmersiveMode(enabled: Boolean) {
        window.decorView.systemUiVisibility = if (enabled) {
            (View.SYSTEM_UI_FLAG_FULLSCREEN or View.SYSTEM_UI_FLAG_HIDE_NAVIGATION or
                View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY or View.SYSTEM_UI_FLAG_LAYOUT_STABLE)
        } else 0
    }

    override fun onDestroy() {
        captureView?.close()
        captureView = null
        tetherLink?.close()
        tetherLink = null
        latestDesktopFrame?.let { if (!it.isRecycled) it.recycle() }
        latestDesktopFrame = null
        super.onDestroy()
    }
}

/** A full-screen View is used so the app receives platform MotionEvents and batched history. */
private class StylusCaptureView(
    context: Context,
    private val sendPacket: (JSONObject) -> Unit
) : View(context) {
    private val sequence = AtomicLong(0)
    private var desktopFrame: Bitmap? = null
    private var inContact = false
    private val localStroke = Path()
    private var hasLocalStroke = false
    private val strokePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = android.graphics.Color.rgb(35, 94, 190)
        style = Paint.Style.STROKE
        strokeWidth = 4f * resources.displayMetrics.density
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
    }
    private val hintPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = android.graphics.Color.rgb(139, 151, 168)
        textAlign = Paint.Align.CENTER
        textSize = 16f * resources.displayMetrics.density
    }

    init {
        setBackgroundColor(android.graphics.Color.WHITE)
        isFocusable = true
        isFocusableInTouchMode = true
        contentDescription = "Android stylus drawing surface"
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        val frame = desktopFrame
        if (frame != null) {
            canvas.drawBitmap(frame, null, android.graphics.Rect(0, 0, width, height), null)
        } else if (!hasLocalStroke) {
            canvas.drawText("Move your stylus here to begin", width / 2f, height / 2f, hintPaint)
        }
        canvas.drawPath(localStroke, strokePaint)
    }

    fun setDesktopFrame(bitmap: Bitmap?) {
        desktopFrame = bitmap
        invalidate()
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
                val stylusIndex = (0 until event.pointerCount).firstOrNull { isStylus(event, it) }
                if (inContact && stylusIndex != null) emitCurrent(event, stylusIndex, "cancel")
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

    private fun isStylus(event: MotionEvent, index: Int): Boolean {
        if (index !in 0 until event.pointerCount) return false
        val tool = event.getToolType(index)
        return tool == MotionEvent.TOOL_TYPE_STYLUS || tool == MotionEvent.TOOL_TYPE_ERASER
    }

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

    private fun normalizePressure(event: MotionEvent, pressure: Float): Float {
        val device = event.device
        val range = device?.getMotionRange(MotionEvent.AXIS_PRESSURE, event.source)
            ?: device?.getMotionRange(MotionEvent.AXIS_PRESSURE)
        val min = range?.min ?: 0f
        val max = range?.max ?: 1f
        val scaled = if (max > min) (pressure - min) / (max - min) else pressure
        return scaled.coerceIn(0f, 1f)
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
        when (phase) {
            "down" -> {
                localStroke.reset()
                localStroke.moveTo(x, y)
                hasLocalStroke = true
            }
            "move" -> if (inContact) localStroke.lineTo(x, y)
            "up", "cancel" -> localStroke.lineTo(x, y)
        }
        invalidate()

        val nx = if (width > 1) (x / (width - 1)).coerceIn(0f, 1f) else 0f
        val ny = if (height > 1) (y / (height - 1)).coerceIn(0f, 1f) else 0f
        // Android tilt is one angle from perpendicular plus an azimuth. Windows needs X/Y angles.
        val tiltDegrees = (tiltRadians * 180.0 / PI).toFloat().coerceIn(0f, 90f)
        val tiltX = (tiltDegrees * sin(orientation)).coerceIn(-90f, 90f)
        val tiltY = (-tiltDegrees * cos(orientation)).coerceIn(-90f, 90f)
        val buttons = event.buttonState
        val primaryButton = (buttons and MotionEvent.BUTTON_STYLUS_PRIMARY) != 0
        val secondaryButton = (buttons and MotionEvent.BUTTON_STYLUS_SECONDARY) != 0
        val normalizedPressure = if (phase == "up" || phase == "leave" || phase == "cancel") 0f
        else normalizePressure(event, pressure)

        sendPacket(
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

    fun close() = Unit
}

private fun newPairingCode(): String {
    val alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    val random = SecureRandom()
    return buildString { repeat(12) { append(alphabet[random.nextInt(alphabet.length)]) } }
}

private fun newChallenge(): String {
    val bytes = ByteArray(32)
    SecureRandom().nextBytes(bytes)
    return bytes.toHexString()
}

private fun ByteArray.toHexString(): String = buildString(size * 2) {
    val digits = "0123456789abcdef"
    for (byte in this@toHexString) {
        val value = byte.toInt() and 0xff
        append(digits[value ushr 4])
        append(digits[value and 0x0f])
    }
}

private fun decodeHex(value: String): ByteArray? {
    if (value.length != 64 || value.any { it !in "0123456789abcdefABCDEF" }) return null
    return ByteArray(32) { index -> value.substring(index * 2, index * 2 + 2).toInt(16).toByte() }
}

private fun makeAuthProof(token: String, nonceHex: String): String {
    val nonce = decodeHex(nonceHex) ?: throw IllegalArgumentException("Invalid VirtualDT authentication challenge.")
    val mac = Mac.getInstance("HmacSHA256")
    mac.init(SecretKeySpec(token.toByteArray(Charsets.UTF_8), "HmacSHA256"))
    return mac.doFinal(nonce).toHexString()
}

/** Hosts the pen service only on Android's USB-tether network interface. */
private class TetherTcpLink(
    context: Context,
    private val onConnectionState: (Boolean, String) -> Unit,
    private val onPairingState: (Boolean, String) -> Unit,
    private val onScreenFrame: (Bitmap?) -> Unit
) {
    private val pairingStore = PairingStore(context.applicationContext)
    @Volatile private var sessionToken: String? = pairingStore.loadToken()
    @Volatile private var pairingCode = newPairingCode()
    private val outgoing = LinkedBlockingQueue<String>(512)
    @Volatile private var closed = false
    @Volatile private var serverSocket: ServerSocket? = null
    @Volatile private var activeSocket: Socket? = null
    @Volatile private var writerThread: Thread? = null
    @Volatile private var workerThread: Thread? = null
    @Volatile private var connected = false
    @Volatile private var lastStatus = ""

    fun start() {
        if (closed || workerThread?.isAlive == true) return
        publishPairingState()
        workerThread = thread(name = "UsbTetherPenServer", isDaemon = true) { serve() }
    }

    private fun serve() {
        while (!closed) {
            val address = findUsbTetherAddress()
            if (address == null) {
                publish(false, "Turn on USB tethering in Settings → Connections → Mobile Hotspot and Tethering.")
                pause(900)
                continue
            }

            var listener: ServerSocket? = null
            try {
                listener = ServerSocket()
                listener.reuseAddress = true
                listener.bind(InetSocketAddress(address, TETHER_PORT), 2)
                listener.soTimeout = 800
                serverSocket = listener
                publish(false, "USB tethering is on. Open the PC app and tap Connect phone.")
                while (!closed && !listener.isClosed) {
                    try {
                        val socket = listener.accept()
                        socket.tcpNoDelay = true
                        socket.keepAlive = true
                        activeSocket = socket
                        runSession(socket)
                    } catch (_: SocketTimeoutException) {
                        // Periodically re-check the tether interface and app lifecycle.
                    }
                }
            } catch (error: Exception) {
                if (!closed) {
                    publish(false, "USB tether link changed. Waiting for it to reconnect…")
                }
            } finally {
                if (serverSocket === listener) serverSocket = null
                try { listener?.close() } catch (_: Exception) { }
            }
            pause(700)
        }
    }

    private fun runSession(socket: Socket) {
        try {
            val input = DataInputStream(BufferedInputStream(socket.getInputStream(), 32 * 1024))
            val output = BufferedWriter(OutputStreamWriter(socket.getOutputStream(), Charsets.UTF_8), 8192)
            val tokenAtGreeting = sessionToken
            val challenge = newChallenge()
            val greeting = JSONObject()
                .put("type", "service")
                .put("name", "virtualdt")
                .put("v", PROTOCOL_VERSION)
                .put("nonce", challenge)
                .put("paired", tokenAtGreeting != null)
                .put("proof", makeAuthProof(tokenAtGreeting ?: pairingCode, challenge))
            writeLine(output, greeting.toString())

            val hello = readLimitedLine(input) ?: throw IllegalStateException("PC closed the connection.")
            val request = JSONObject(hello)
            if (request.optInt("v") != PROTOCOL_VERSION) {
                writeLine(output, JSONObject().put("type", "error").put("message", "protocol_mismatch").toString())
                throw IllegalStateException("PC app protocol does not match. Install matching VirtualDT releases.")
            }

            if (tokenAtGreeting == null && request.optString("type") == "pair") {
                val suppliedCode = request.optString("code", "").uppercase().replace("-", "")
                val proposedToken = request.optString("token", "")
                if (suppliedCode != pairingCode || !proposedToken.matches(Regex("[A-Za-z0-9_-]{40,64}"))) {
                    writeLine(output, JSONObject().put("type", "error").put("message", "pairing_code_invalid").toString())
                    throw IllegalStateException("VirtualDT pairing code was rejected.")
                }
                pairingStore.saveToken(proposedToken)
                sessionToken = proposedToken
                onPairingState(true, "")
            } else if (tokenAtGreeting != null && request.optString("type") == "hello") {
                val expectedProof = makeAuthProof(tokenAtGreeting, challenge)
                val suppliedProof = request.optString("proof", "")
                val valid = MessageDigest.isEqual(
                    expectedProof.toByteArray(Charsets.US_ASCII),
                    suppliedProof.toByteArray(Charsets.US_ASCII)
                )
                if (!valid) {
                    writeLine(output, JSONObject().put("type", "error").put("message", "unauthorized").toString())
                    throw IllegalStateException("VirtualDT PC authentication failed.")
                }
            } else {
                writeLine(output, JSONObject().put("type", "error").put("message", "unauthorized").toString())
                throw IllegalStateException("VirtualDT PC pairing state does not match.")
            }

            outgoing.clear()
            writeLine(output, JSONObject().put("type", "ready").put("v", PROTOCOL_VERSION).toString())
            connected = true
            publish(true, "Connected — ready to draw")
            writerThread = thread(name = "UsbTetherPenWriter", isDaemon = true) {
                try {
                    while (!closed && !socket.isClosed && !Thread.currentThread().isInterrupted) {
                        val message = outgoing.poll(250, TimeUnit.MILLISECONDS) ?: continue
                        writeLine(output, message)
                    }
                } catch (_: Exception) {
                    try { socket.close() } catch (_: Exception) { }
                }
            }

            while (!closed && !socket.isClosed) {
                val line = readLimitedLine(input) ?: break
                val packet = JSONObject(line)
                if (packet.optString("type") == "screen") {
                    val frameBytes = packet.optLong("bytes", -1)
                    if (packet.optInt("v") != PROTOCOL_VERSION || packet.optString("format") != "jpeg" ||
                        frameBytes !in 1..MAX_SCREEN_FRAME_BYTES.toLong()
                    ) throw IllegalArgumentException("PC sent an invalid screen frame header.")
                    val bytes = ByteArray(frameBytes.toInt())
                    input.readFully(bytes)
                    val options = BitmapFactory.Options().apply { inPreferredConfig = Bitmap.Config.RGB_565 }
                    val bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.size, options)
                    if (bitmap != null) onScreenFrame(bitmap)
                }
            }
            if (!closed) publish(false, "PC disconnected. The phone is ready to reconnect.")
        } catch (error: Exception) {
            if (!closed && connected) {
                publish(false, "Connection ended. Check the cable and USB tethering, then reconnect.")
            }
        } finally {
            connected = false
            outgoing.clear()
            writerThread?.interrupt()
            writerThread = null
            if (activeSocket === socket) activeSocket = null
            try { socket.close() } catch (_: Exception) { }
            onScreenFrame(null)
        }
    }

    fun send(message: JSONObject) {
        if (closed || !connected) return
        if (!outgoing.offer(message.toString())) {
            // End this session rather than leave Windows holding a pen-down state.
            try { activeSocket?.close() } catch (_: Exception) { }
        }
    }

    fun resetPairing() {
        if (closed) return
        pairingStore.clear()
        sessionToken = null
        pairingCode = newPairingCode()
        onPairingState(false, pairingCode)
        try { activeSocket?.close() } catch (_: Exception) { }
    }

    private fun findUsbTetherAddress(): InetAddress? {
        return try {
            val interfaces = NetworkInterface.getNetworkInterfaces() ?: return null
            while (interfaces.hasMoreElements()) {
                val network = interfaces.nextElement()
                val name = network.name.lowercase()
                if (!name.contains("rndis") && !name.contains("usb")) continue
                if (!network.isUp) continue
                val addresses = network.inetAddresses
                while (addresses.hasMoreElements()) {
                    val address = addresses.nextElement()
                    if (address is Inet4Address && !address.isLoopbackAddress) return address
                }
            }
            null
        } catch (_: SocketException) {
            null
        }
    }

    private fun readLimitedLine(input: DataInputStream): String? {
        val line = ByteArrayOutputStream()
        while (true) {
            val next = input.read()
            if (next == -1) return if (line.size() == 0) null else line.toString(Charsets.UTF_8.name())
            if (next == '\n'.code) return line.toString(Charsets.UTF_8.name()).removeSuffix("\r")
            if (line.size() >= MAX_PROTOCOL_LINE) throw IllegalArgumentException("Protocol message is too large.")
            line.write(next)
        }
    }

    private fun writeLine(writer: BufferedWriter, message: String) {
        writer.write(message)
        writer.newLine()
        writer.flush()
    }

    private fun publish(isConnected: Boolean, message: String) {
        if (lastStatus == message && connected == isConnected) return
        lastStatus = message
        onConnectionState(isConnected, message)
    }

    private fun publishPairingState() {
        val paired = sessionToken != null
        onPairingState(paired, if (paired) "" else pairingCode)
    }

    private fun pause(milliseconds: Long) {
        try { Thread.sleep(milliseconds) } catch (_: InterruptedException) { }
    }

    fun close() {
        if (closed) return
        closed = true
        try { serverSocket?.close() } catch (_: Exception) { }
        try { activeSocket?.close() } catch (_: Exception) { }
        writerThread?.interrupt()
        workerThread?.interrupt()
        onScreenFrame(null)
    }
}

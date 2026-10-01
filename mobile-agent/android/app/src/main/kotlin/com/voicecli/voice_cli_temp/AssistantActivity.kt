package com.voicecli.voice_cli_temp

import android.os.Bundle
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.android.FlutterActivityLaunchConfigs.BackgroundMode
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class AssistantActivity : FlutterActivity() {
    private val CHANNEL = "com.voila/intent"

    override fun onCreate(savedInstanceState: Bundle?) {
        setTheme(R.style.TransparentTheme)
        super.onCreate(savedInstanceState)
    }

    // CRITICAL FIX (Bug #1): Reuse the pre-warmed engine from MainActivity.
    // This prevents a second Dart VM from being created, which causes Firebase /
    // flutter_background / speech_to_text to crash on double-initialization.
    override fun getCachedEngineId(): String = MainActivity.ENGINE_ID

    // CRITICAL FIX: When using a cached engine, we must NOT destroy it on Activity finish,
    // because the engine is shared with and owned by MainActivity.
    override fun shouldDestroyEngineWithHost(): Boolean = false

    override fun getBackgroundMode(): BackgroundMode = BackgroundMode.transparent

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        // Notify the already-running Dart code that this is an assistant overlay
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, CHANNEL)
            .invokeMethod("onIntentChanged", true)
    }

    override fun onDestroy() {
        // Notify Flutter we are leaving overlay mode so the UI can reset
        flutterEngine?.let {
            MethodChannel(it.dartExecutor.binaryMessenger, CHANNEL)
                .invokeMethod("onIntentChanged", false)
        }
        super.onDestroy()
    }
}

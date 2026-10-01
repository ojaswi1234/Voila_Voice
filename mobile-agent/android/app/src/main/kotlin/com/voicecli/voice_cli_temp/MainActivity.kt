package com.voicecli.voice_cli_temp

import android.os.Bundle
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.android.FlutterActivityLaunchConfigs.BackgroundMode
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    private val CHANNEL = "com.voila/intent"

    override fun onCreate(savedInstanceState: Bundle?) {
        setTheme(R.style.NormalTheme)
        // Warm up / retrieve the shared engine BEFORE super.onCreate() so it
        // is guaranteed to be in the cache when FlutterActivity looks for it.
        EngineManager.getOrCreate(this)
        super.onCreate(savedInstanceState)
    }

    override fun getCachedEngineId(): String = EngineManager.ENGINE_ID

    /**
     * CRITICAL FIX: Do NOT destroy the engine when MainActivity goes to
     * background. The engine is shared with AssistantActivity — destroying it
     * here would kill the Dart VM that AssistantActivity depends on.
     */
    override fun shouldDestroyEngineWithHost(): Boolean = false

    override fun getBackgroundMode(): BackgroundMode = BackgroundMode.opaque

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        val channel = MethodChannel(flutterEngine.dartExecutor.binaryMessenger, CHANNEL)

        // Pull-based handler: Dart calls isAssistantIntent when IT is ready,
        // avoiding the race where we push invokeMethod before Dart is listening.
        channel.setMethodCallHandler { call, result ->
            when (call.method) {
                "isAssistantIntent" -> result.success(false)
                else -> result.notImplemented()
            }
        }

        // Also push for hot re-attachment (app already running, comes to foreground)
        channel.invokeMethod("onIntentChanged", false)
    }
}

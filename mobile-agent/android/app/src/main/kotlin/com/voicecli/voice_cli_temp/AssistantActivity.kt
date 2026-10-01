package com.voicecli.voice_cli_temp

import android.os.Bundle
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.android.FlutterActivityLaunchConfigs.BackgroundMode
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class AssistantActivity : FlutterActivity() {
    private val CHANNEL = "com.voila/intent"
    private var channel: MethodChannel? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        setTheme(R.style.TransparentTheme)
        // COLD-START FIX: If the user long-presses home BEFORE ever opening the
        // app, the engine cache is empty. getOrCreate() boots the Dart VM here.
        EngineManager.getOrCreate(this)
        super.onCreate(savedInstanceState)
    }

    override fun getCachedEngineId(): String = EngineManager.ENGINE_ID

    /**
     * CRITICAL FIX: Do NOT destroy the shared engine when the overlay closes.
     * MainActivity owns the engine's lifecycle; we're just borrowing it.
     */
    override fun shouldDestroyEngineWithHost(): Boolean = false

    override fun getBackgroundMode(): BackgroundMode = BackgroundMode.transparent

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        channel = MethodChannel(flutterEngine.dartExecutor.binaryMessenger, CHANNEL)

        // RACE CONDITION FIX: Use a pull-based handler so Dart calls us when IT
        // is ready — not us pushing invokeMethod before Dart is listening.
        channel?.setMethodCallHandler { call, result ->
            when (call.method) {
                "isAssistantIntent" -> result.success(true)
                else -> result.notImplemented()
            }
        }

        // Also push for hot re-attachment (Dart is already running in background)
        channel?.invokeMethod("onIntentChanged", true)
    }

    override fun onStop() {
        // LIFECYCLE FIX: Signal Flutter BEFORE the channel tears down in onDestroy.
        // onStop is the last safe place to send messages via the MethodChannel
        // because the Activity is still alive and the channel is still attached.
        channel?.invokeMethod("onIntentChanged", false)
        super.onStop()
    }

    override fun onDestroy() {
        channel = null
        super.onDestroy()
    }
}

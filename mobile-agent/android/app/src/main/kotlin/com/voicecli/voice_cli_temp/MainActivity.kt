package com.voicecli.voice_cli_temp

import android.os.Bundle
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.android.FlutterActivityLaunchConfigs.BackgroundMode
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    private val CHANNEL = "com.voila/intent"
    private var channel: MethodChannel? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        setTheme(R.style.NormalTheme)
        EngineManager.getOrCreate(this)
        super.onCreate(savedInstanceState)

        // configureFlutterEngine() is skipped when using a cached engine.
        // Initialize the MethodChannel here after super.onCreate() instead.
        flutterEngine?.let { engine ->
            channel = MethodChannel(engine.dartExecutor.binaryMessenger, CHANNEL)
        }
    }

    override fun getCachedEngineId(): String = EngineManager.ENGINE_ID

    override fun shouldDestroyEngineWithHost(): Boolean = false

    override fun getBackgroundMode(): BackgroundMode = BackgroundMode.opaque

    override fun onResume() {
        super.onResume()
        // Re-register handler every resume to reclaim ownership from AssistantActivity
        // which may have overwritten the shared-engine handler while overlay was open.
        registerMainChannel()
    }

    private fun registerMainChannel() {
        val ch = channel ?: return
        ch.setMethodCallHandler { call, result ->
            when (call.method) {
                "isAssistantIntent" -> result.success(false)
                else -> result.notImplemented()
            }
        }
        ch.invokeMethod("onIntentChanged", false)
    }
}

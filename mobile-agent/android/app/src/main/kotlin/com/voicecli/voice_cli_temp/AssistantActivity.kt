package com.voicecli.voice_cli_temp

import android.content.Intent
import android.os.Bundle
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.android.FlutterActivityLaunchConfigs.BackgroundMode
import io.flutter.plugin.common.MethodChannel

class AssistantActivity : FlutterActivity() {
    private val CHANNEL = "com.voila/intent"
    private var channel: MethodChannel? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        setTheme(R.style.TransparentTheme)
        EngineManager.getOrCreate(this)
        super.onCreate(null)
        
        flutterEngine?.let { engine ->
            channel = MethodChannel(engine.dartExecutor.binaryMessenger, CHANNEL)
        }
    }

    override fun getCachedEngineId(): String = EngineManager.ENGINE_ID

    override fun shouldDestroyEngineWithHost(): Boolean = false

    override fun getBackgroundMode(): BackgroundMode = BackgroundMode.transparent

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        registerAssistantChannel()
    }

    override fun onResume() {
        super.onResume()
        registerAssistantChannel()
    }

    private fun registerAssistantChannel() {
        val ch = channel ?: return
        ch.setMethodCallHandler { call, result ->
            when (call.method) {
                "isAssistantIntent" -> result.success(true)
                else -> result.notImplemented()
            }
        }
        ch.invokeMethod("onIntentChanged", true)
    }

    override fun onPause() {
        // LIFECYCLE FIX: Signal Flutter BEFORE transition animation starts
        channel?.invokeMethod("onIntentChanged", false)
        super.onPause()
    }

    override fun onDestroy() {
        channel = null
        super.onDestroy()
    }
}

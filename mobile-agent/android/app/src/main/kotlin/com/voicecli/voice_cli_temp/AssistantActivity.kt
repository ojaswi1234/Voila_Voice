package com.voicecli.voice_cli_temp

import android.content.Intent
import android.os.Bundle
import android.view.WindowManager
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.android.FlutterActivityLaunchConfigs.BackgroundMode
import io.flutter.plugin.common.MethodChannel

class AssistantActivity : FlutterActivity() {
    private val CHANNEL = "com.voila/intent"
    private var channel: MethodChannel? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        setTheme(R.style.TransparentTheme)
        EngineManager.getOrCreate(this)
        // Note: pass actual savedInstanceState (not null) so Android can
        // correctly restore Activity state if the process was killed & resumed.
        super.onCreate(savedInstanceState)

        // TOUCH PASSTHROUGH FIX: With a transparent Flutter window, the upper
        // portion of the screen (where no overlay UI is drawn) is visually clear
        // but still blocks all touches. FLAG_NOT_TOUCH_MODAL makes touches
        // outside the Activity's "focus region" pass through to the app below.
        // This is essential for a voice assistant overlay UX.
        window.addFlags(
            WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL
        )

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
        channel?.invokeMethod("onIntentChanged", false)
        super.onPause()
    }

    override fun onDestroy() {
        channel = null
        super.onDestroy()
    }
}

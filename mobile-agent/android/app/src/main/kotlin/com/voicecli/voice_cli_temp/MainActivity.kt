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
        
        // BUGFIX (Scenario 5): Pass null to prevent Android from restoring stale Fragment
        // state onto the fresh cached FlutterEngine if the process was killed.
        super.onCreate(null)
        
        // BUGFIX (Scenario 2): configureFlutterEngine is skipped when using a cached engine.
        // We must initialize our MethodChannel here after super.onCreate(null).
        flutterEngine?.let { engine ->
            channel = MethodChannel(engine.dartExecutor.binaryMessenger, CHANNEL)
        }
    }

    override fun getCachedEngineId(): String = EngineManager.ENGINE_ID

    override fun shouldDestroyEngineWithHost(): Boolean = false

    override fun getBackgroundMode(): BackgroundMode = BackgroundMode.opaque

    override fun onResume() {
        super.onResume()
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

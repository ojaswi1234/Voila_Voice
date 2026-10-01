package com.voicecli.voice_cli_temp

import android.os.Bundle
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.android.FlutterActivityLaunchConfigs.BackgroundMode
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class AssistantActivity: FlutterActivity() {
    private val CHANNEL = "com.voila/intent"

    override fun onCreate(savedInstanceState: Bundle?) {
        setTheme(R.style.TransparentTheme)
        super.onCreate(savedInstanceState)
    }

    override fun getBackgroundMode(): BackgroundMode {
        return BackgroundMode.transparent
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        val methodChannel = MethodChannel(flutterEngine.dartExecutor.binaryMessenger, CHANNEL)
        methodChannel.setMethodCallHandler { call, result ->
            if (call.method == "isAssistantIntent") {
                result.success(true)
            } else {
                result.notImplemented()
            }
        }
    }
}

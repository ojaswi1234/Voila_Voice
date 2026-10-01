package com.voicecli.voice_cli_temp

import android.content.Intent
import android.os.Bundle
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.android.FlutterActivityLaunchConfigs.BackgroundMode
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity: FlutterActivity() {
    private val CHANNEL = "com.voila/intent"
    private var methodChannel: MethodChannel? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        val action = intent?.action
        val isLauncher = action == Intent.ACTION_MAIN
        if (!isLauncher) {
            setTheme(R.style.TransparentTheme)
        } else {
            setTheme(R.style.NormalTheme)
        }
        super.onCreate(savedInstanceState)
    }

    override fun getBackgroundMode(): BackgroundMode {
        val action = intent?.action
        val isLauncher = action == Intent.ACTION_MAIN
        return if (!isLauncher) BackgroundMode.transparent else BackgroundMode.opaque
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        methodChannel = MethodChannel(flutterEngine.dartExecutor.binaryMessenger, CHANNEL)
        methodChannel?.setMethodCallHandler { call, result ->
            if (call.method == "isAssistantIntent") {
                val action = intent?.action
                val isLauncher = action == Intent.ACTION_MAIN
                result.success(!isLauncher)
            } else {
                result.notImplemented()
            }
        }
    }

    override fun onNewIntent(newIntent: Intent) {
        val oldAction = intent?.action
        super.onNewIntent(newIntent)
        setIntent(newIntent)

        val newAction = newIntent.action
        val oldIsLauncher = oldAction == Intent.ACTION_MAIN
        val newIsLauncher = newAction == Intent.ACTION_MAIN
        
        if (oldIsLauncher != newIsLauncher) {
            recreate()
            return
        }

        methodChannel?.invokeMethod("onIntentChanged", !newIsLauncher)
    }
}

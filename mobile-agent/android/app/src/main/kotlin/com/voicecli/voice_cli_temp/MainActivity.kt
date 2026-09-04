package com.voicecli.voice_cli_temp

import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.android.FlutterActivityLaunchConfigs.BackgroundMode
import android.content.Intent

class MainActivity: FlutterActivity() {
    override fun getBackgroundMode(): BackgroundMode {
        return BackgroundMode.transparent
    }
}

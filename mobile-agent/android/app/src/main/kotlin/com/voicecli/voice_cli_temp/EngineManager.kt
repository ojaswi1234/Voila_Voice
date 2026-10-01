package com.voicecli.voice_cli_temp

import android.content.Context
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.embedding.engine.FlutterEngineCache
import io.flutter.embedding.engine.dart.DartExecutor

/**
 * Singleton engine manager that ensures exactly ONE Flutter Dart VM is alive
 * across both MainActivity (normal app) and AssistantActivity (overlay).
 *
 * CRITICAL: Uses applicationContext so the engine is never tied to a single
 * Activity's lifecycle and won't be GC'd when an Activity goes to background.
 */
object EngineManager {
    const val ENGINE_ID = "voila_shared_engine"

    fun getOrCreate(context: Context): FlutterEngine {
        var engine = FlutterEngineCache.getInstance().get(ENGINE_ID)
        if (engine == null) {
            engine = FlutterEngine(context.applicationContext)
            engine.dartExecutor.executeDartEntrypoint(
                DartExecutor.DartEntrypoint.createDefault()
            )
            FlutterEngineCache.getInstance().put(ENGINE_ID, engine)
        }
        return engine
    }
}

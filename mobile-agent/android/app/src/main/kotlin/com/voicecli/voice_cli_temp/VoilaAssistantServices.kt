package com.voicecli.voice_cli_temp

import android.service.voice.VoiceInteractionSessionService
import android.service.voice.VoiceInteractionService
import android.service.voice.VoiceInteractionSession
import android.content.Context
import android.os.Bundle
import android.content.Intent
import android.speech.RecognitionService

class VoilaVoiceInteractionService : VoiceInteractionService() {
    override fun onReady() {
        super.onReady()
    }
}

class VoilaVoiceInteractionSessionService : VoiceInteractionSessionService() {
    override fun onNewSession(args: Bundle?): VoiceInteractionSession {
        return VoilaVoiceInteractionSession(this)
    }
}

class VoilaVoiceInteractionSession(context: Context) : VoiceInteractionSession(context) {

    override fun onShow(args: Bundle?, showFlags: Int) {
        super.onShow(args, showFlags)
        launchAssistantActivity()
    }

    override fun onHandleAssist(
        data: Bundle?,
        structure: android.app.assist.AssistStructure?,
        content: android.app.assist.AssistContent?
    ) {
        super.onHandleAssist(data, structure, content)
        // Do NOT call launchAssistantActivity() here — onShow() is the authoritative trigger.
        // Calling it twice causes rapid-fire Activity creation and crash.
    }

    private fun launchAssistantActivity() {
        val intent = Intent(context, AssistantActivity::class.java).apply {
            // CRITICAL FIX (Bug #2): Remove FLAG_ACTIVITY_SINGLE_TOP.
            // With singleInstance launchMode, SINGLE_TOP is redundant and prevents
            // the Activity from fully resetting state, causing a blank overlay.
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            action = Intent.ACTION_ASSIST
        }
        startVoiceActivity(intent)
    }
}

class VoilaRecognitionService : RecognitionService() {
    override fun onStartListening(recognizerIntent: Intent?, listener: Callback?) {}
    override fun onCancel(listener: Callback?) {}
    override fun onStopListening(listener: Callback?) {}
}

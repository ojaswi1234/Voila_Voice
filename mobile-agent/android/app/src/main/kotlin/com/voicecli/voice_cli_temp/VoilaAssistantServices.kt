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
        // INTENTIONALLY EMPTY: onShow() is the single authoritative trigger.
        // Calling launchAssistantActivity() here causes a double-launch crash.
    }

    private fun launchAssistantActivity() {
        val intent = Intent(context, AssistantActivity::class.java).apply {
            // FLAG_ACTIVITY_NEW_TASK is required for startVoiceActivity.
            // Do NOT add SINGLE_TOP — it would skip onCreate on a paused instance.
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

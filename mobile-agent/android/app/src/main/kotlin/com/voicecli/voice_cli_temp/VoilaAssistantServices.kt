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
    override fun onHandleAssist(data: Bundle?, structure: android.app.assist.AssistStructure?, content: android.app.assist.AssistContent?) {
        super.onHandleAssist(data, structure, content)
        val intent = Intent(context, MainActivity::class.java)
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        intent.action = Intent.ACTION_ASSIST
        context.startActivity(intent)
    }
}

class VoilaRecognitionService : RecognitionService() {
    override fun onStartListening(recognizerIntent: Intent?, listener: android.speech.RecognitionService.Callback?) {}
    override fun onCancel(listener: android.speech.RecognitionService.Callback?) {}
    override fun onStopListening(listener: android.speech.RecognitionService.Callback?) {}
}

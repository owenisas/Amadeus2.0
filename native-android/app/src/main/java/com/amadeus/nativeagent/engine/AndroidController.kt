package com.amadeus.nativeagent.engine

import android.content.Context
import com.amadeus.nativeagent.model.AgentDecision
import com.amadeus.nativeagent.model.CapturedScreen
import com.amadeus.nativeagent.runtime.NativeAgentRuntime
import com.amadeus.nativeagent.service.AndroidControlService
import com.amadeus.nativeagent.service.ScreenCaptureService
import java.io.File

class AndroidController(private val context: Context) {
    fun isReady(): Boolean =
        AndroidControlService.instance != null && ScreenCaptureService.instance?.isProjectionReady() == true

    fun launchApp(packageName: String): Boolean =
        AndroidControlService.instance?.launchApp(packageName) ?: false

    fun capture(runDir: File): CapturedScreen {
        val control = AndroidControlService.instance ?: error("Accessibility service is not connected.")
        val screenCapture = ScreenCaptureService.instance ?: error("Screen capture service is not running.")
        return control.captureScreen(runDir, screenCapture)
    }

    fun perform(decision: AgentDecision, currentScreen: CapturedScreen): Boolean {
        val control = AndroidControlService.instance ?: return false
        return control.performDecision(decision, currentScreen)
    }
}

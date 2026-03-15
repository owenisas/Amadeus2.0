package com.amadeus.nativeagent

import android.app.Application
import android.content.ComponentName
import android.content.Context
import android.provider.Settings
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.amadeus.nativeagent.runtime.NativeAgentRuntime
import com.amadeus.nativeagent.service.AndroidControlService
import com.amadeus.nativeagent.service.ScreenCaptureService
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

class NativeAgentViewModel(application: Application) : AndroidViewModel(application) {
    private val runtime = NativeAgentRuntime.get(application)

    val snapshot = runtime.sessionStore.snapshot()
        .stateIn(viewModelScope, SharingStarted.Eagerly, runtime.sessionStore.snapshot().value)
    val apiKey = runtime.settingsRepository.geminiApiKey
        .stateIn(viewModelScope, SharingStarted.Eagerly, "")
    val model = runtime.settingsRepository.geminiModel
        .stateIn(viewModelScope, SharingStarted.Eagerly, "gemini-3.1-pro-preview")

    fun setApiKey(value: String) {
        viewModelScope.launch { runtime.settingsRepository.setGeminiApiKey(value) }
    }

    fun setModel(value: String) {
        viewModelScope.launch { runtime.settingsRepository.setGeminiModel(value) }
    }

    fun refreshPermissions() {
        val context = getApplication<Application>()
        runtime.sessionStore.updatePermissions(
            projectionGranted = ScreenCaptureService.instance?.isProjectionReady() == true,
            overlayGranted = Settings.canDrawOverlays(context),
            accessibilityGranted = isAccessibilityEnabled(context),
        )
    }

    private fun isAccessibilityEnabled(context: Context): Boolean {
        val enabledServices = Settings.Secure.getString(
            context.contentResolver,
            Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES,
        ).orEmpty()
        val component = ComponentName(context, AndroidControlService::class.java).flattenToString()
        return enabledServices.contains(component)
    }
}

package com.amadeus.nativeagent.runtime

import android.content.Context
import androidx.core.content.ContextCompat
import com.amadeus.nativeagent.engine.SafetyEngine
import com.amadeus.nativeagent.engine.VisionEngine
import com.amadeus.nativeagent.service.AgentForegroundService
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob

class NativeAgentRuntime private constructor(context: Context) {
    private val appContext = context.applicationContext

    val appRegistry = AppRegistry
    val skillRepository = SkillRepository(appContext)
    val settingsRepository = SettingsRepository(appContext)
    val approvalCoordinator = ApprovalCoordinator()
    val sessionStore = SessionStore()
    val safetyEngine = SafetyEngine()
    val visionEngine = VisionEngine(appContext, settingsRepository)
    val applicationScope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)

    fun startRun(specJson: String) {
        val intent = AgentForegroundService.startIntent(appContext, specJson)
        ContextCompat.startForegroundService(appContext, intent)
    }

    fun approvePendingAction(runId: String, action: String) {
        approvalCoordinator.resolve(runId, action)
    }

    fun cancelRun(runId: String) {
        val intent = AgentForegroundService.cancelIntent(appContext, runId)
        appContext.startService(intent)
    }

    companion object {
        @Volatile
        private var instance: NativeAgentRuntime? = null

        fun initialize(context: Context): NativeAgentRuntime {
            return instance ?: synchronized(this) {
                instance ?: NativeAgentRuntime(context).also { instance = it }
            }
        }

        fun get(context: Context): NativeAgentRuntime = initialize(context)
    }
}

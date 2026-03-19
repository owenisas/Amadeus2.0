package com.amadeus.nativeagent.engine

import com.amadeus.nativeagent.model.AgentDecision
import com.amadeus.nativeagent.model.AutomationScript
import com.amadeus.nativeagent.model.CapturedScreen
import com.amadeus.nativeagent.model.ScriptStep
import com.amadeus.nativeagent.runtime.SkillRepository
import java.io.File
import kotlinx.coroutines.delay

/**
 * Replays saved automation scripts step-by-step using the [AndroidController].
 * Each mutating step is followed by a screen recapture so subsequent label
 * lookups resolve against the current UI state.
 */
class ScriptExecutor(
    private val controller: AndroidController,
    private val skillRepository: SkillRepository,
) {
    data class ScriptResult(
        val ok: Boolean,
        val stepsExecuted: Int,
        val totalSteps: Int,
        val lastScreen: CapturedScreen?,
        val error: String? = null,
    )

    suspend fun execute(
        appId: String,
        scriptName: String,
        runDir: File,
        initialScreen: CapturedScreen?,
        log: (String) -> Unit,
    ): ScriptResult {
        val script = try {
            skillRepository.readScript(appId, scriptName)
        } catch (e: Exception) {
            return ScriptResult(ok = false, stepsExecuted = 0, totalSteps = 0, lastScreen = initialScreen, error = e.message)
        }
        return executeScript(appId, script, runDir, initialScreen, log)
    }

    private suspend fun executeScript(
        appId: String,
        script: AutomationScript,
        runDir: File,
        initialScreen: CapturedScreen?,
        log: (String) -> Unit,
    ): ScriptResult {
        val steps = script.steps
        if (steps.isEmpty()) {
            return ScriptResult(ok = true, stepsExecuted = 0, totalSteps = 0, lastScreen = initialScreen)
        }
        var current = initialScreen
        var executed = 0

        for (step in steps) {
            val action = step.action.trim()
            if (action.isBlank()) continue
            log("script_step action=$action label=${step.targetLabel.orEmpty()} text=${step.inputText.orEmpty()}")

            when (action) {
                "launch_app" -> {
                    val pkg = step.packageName.orEmpty()
                    if (pkg.isNotBlank()) {
                        controller.launchApp(pkg)
                    }
                }

                "tap" -> {
                    val resolved = resolveTargetBox(step, current)
                    val decision = AgentDecision(
                        screenClassification = "script_tap",
                        goalProgress = "scripted",
                        nextAction = "tap",
                        targetNodeId = resolveNodeId(step, current),
                        targetBox = resolved,
                        confidence = 1.0f,
                        reason = "Script step: tap ${step.targetLabel.orEmpty()}",
                        riskLevel = "low",
                        targetLabel = step.targetLabel,
                    )
                    if (current != null) {
                        controller.perform(decision, current)
                    }
                }

                "type" -> {
                    val text = step.inputText.orEmpty()
                    if (text.isNotBlank() && current != null) {
                        val decision = AgentDecision(
                            screenClassification = "script_type",
                            goalProgress = "scripted",
                            nextAction = "type",
                            confidence = 1.0f,
                            reason = "Script step: type '${text.take(30)}'",
                            riskLevel = "low",
                            inputText = text,
                            targetLabel = step.targetLabel,
                        )
                        controller.perform(decision, current)
                    }
                }

                "swipe" -> {
                    if (current != null) {
                        val decision = AgentDecision(
                            screenClassification = "script_swipe",
                            goalProgress = "scripted",
                            nextAction = "swipe",
                            confidence = 1.0f,
                            reason = "Script step: swipe",
                            riskLevel = "low",
                        )
                        controller.perform(decision, current)
                    }
                }

                "back" -> {
                    if (current != null) {
                        val decision = AgentDecision(
                            screenClassification = "script_back",
                            goalProgress = "scripted",
                            nextAction = "back",
                            confidence = 1.0f,
                            reason = "Script step: back",
                            riskLevel = "low",
                        )
                        controller.perform(decision, current)
                    }
                }

                "home" -> {
                    if (current != null) {
                        val decision = AgentDecision(
                            screenClassification = "script_home",
                            goalProgress = "scripted",
                            nextAction = "home",
                            confidence = 1.0f,
                            reason = "Script step: home",
                            riskLevel = "low",
                        )
                        controller.perform(decision, current)
                    }
                }

                "wait" -> {
                    val ms = ((if (step.waitSeconds > 0f) step.waitSeconds else 2f) * 1000).toLong()
                    delay(ms)
                }

                "run_script" -> {
                    val nestedName = step.scriptName.orEmpty()
                    if (nestedName.isNotBlank()) {
                        val nestedResult = execute(appId, nestedName, runDir, current, log)
                        current = nestedResult.lastScreen
                        if (!nestedResult.ok) {
                            return ScriptResult(
                                ok = false,
                                stepsExecuted = executed,
                                totalSteps = steps.size,
                                lastScreen = current,
                                error = "Nested script '$nestedName' failed: ${nestedResult.error}",
                            )
                        }
                    }
                }
            }
            executed++
            // Recapture after mutating actions
            if (action !in listOf("wait", "run_script")) {
                current = controller.capture(runDir)
            }
        }
        return ScriptResult(ok = true, stepsExecuted = executed, totalSteps = steps.size, lastScreen = current)
    }

    /** Resolve a target box by matching the step's label against live screen components. */
    private fun resolveTargetBox(step: ScriptStep, screen: CapturedScreen?): com.amadeus.nativeagent.model.BoundingBox? {
        // Prefer explicit box from the script
        if (step.targetBox != null) return step.targetBox
        // Dynamic label lookup from current screen
        val label = step.targetLabel?.lowercase() ?: return null
        return screen?.components
            ?.firstOrNull { it.label.lowercase() == label }
            ?.targetBox
    }

    /** Resolve a node ID by matching the step's label against live screen components. */
    private fun resolveNodeId(step: ScriptStep, screen: CapturedScreen?): String? {
        val label = step.targetLabel?.lowercase() ?: return null
        return screen?.components
            ?.firstOrNull { it.label.lowercase() == label }
            ?.nodeId
    }
}

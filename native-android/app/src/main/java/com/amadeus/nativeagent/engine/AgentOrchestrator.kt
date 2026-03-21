package com.amadeus.nativeagent.engine

import android.content.Context
import android.content.Intent
import com.amadeus.nativeagent.model.AgentDecision
import com.amadeus.nativeagent.model.ApprovalRequest
import com.amadeus.nativeagent.model.AutomationScript
import com.amadeus.nativeagent.model.RunActionRecord
import com.amadeus.nativeagent.model.RunRecord
import com.amadeus.nativeagent.model.RunSpec
import com.amadeus.nativeagent.model.ScriptStep
import com.amadeus.nativeagent.runtime.NativeAgentRuntime
import com.amadeus.nativeagent.service.ApprovalOverlayService
import java.io.File
import java.util.UUID
import kotlinx.coroutines.delay

class AgentOrchestrator(
    private val context: Context,
    private val runtime: NativeAgentRuntime,
    private val controller: AndroidController,
) {
    companion object {
        const val YOLO_NOTICE =
            "YOLO mode enabled: native approval overlays are bypassed and the agent will auto-continue through approval surfaces when it finds a stable action. Purchase and other local safety blocks still apply."
    }

    suspend fun run(runId: String, spec: RunSpec): RunRecord {
        val app = runtime.appRegistry.byId(spec.appId)
        val skill = runtime.skillRepository.loadSkill(spec.appId)
        val runDir = File(runtime.skillRepository.runsDirectory(), runId).apply { mkdirs() }
        val notice = if (spec.yoloMode) YOLO_NOTICE else null
        val debugLogFile = File(runDir, "agent_debug.log")
        fun log(message: String) {
            val line = "[${System.currentTimeMillis()}] $message"
            debugLogFile.appendText("$line\n")
            runtime.sessionStore.appendDebugLine(line)
        }

        runtime.sessionStore.clearDebugLines()
        runtime.sessionStore.setSkills(runtime.skillRepository.listSkillIds())
        runtime.sessionStore.updateProvider("Gemini")
        runtime.sessionStore.setCurrentRun(
            RunRecord(
                runId = runId,
                appId = spec.appId,
                goal = spec.goal,
                status = "running",
                reason = "Preparing automation runtime.",
                notice = notice,
                runDir = runDir.absolutePath,
            )
        )
        log("run_started app=${spec.appId} goal=${spec.goal} exploration=${spec.explorationEnabled} yolo=${spec.yoloMode}")

        repeat(50) {
            if (controller.isReady()) {
                log("controller_ready")
                return@repeat
            }
            delay(100)
        }
        if (!controller.isReady()) {
            log("controller_not_ready")
            return result(runId, spec, "blocked", "Accessibility and screen capture permissions are required.", runDir)
        }
        if (!controller.launchApp(app.packageName)) {
            log("launch_failed package=${app.packageName}")
            return result(runId, spec, "error", "Failed to launch ${app.title}.", runDir)
        }
        log("launch_succeeded package=${app.packageName}")

        var previousScreenId: String? = null
        var current = controller.capture(runDir)
        log("captured_screen package=${current.packageName} class=${current.classNameHint.orEmpty()} visible=${current.visibleText.take(4)}")
        var stallCount = 0
        val actions = mutableListOf<RunActionRecord>()

        for (step in 1..spec.maxSteps) {
            runtime.sessionStore.setCurrentRun(
                RunRecord(
                    runId = runId,
                    appId = spec.appId,
                    goal = spec.goal,
                    status = "running",
                    reason = "Step $step on ${current.packageName}",
                    notice = notice,
                    stepCount = actions.size,
                    runDir = runDir.absolutePath,
                    actions = actions,
                    lastScreenId = runtime.skillRepository.screenId(current),
                )
            )
            runtime.skillRepository.recordObservation(spec.appId, current)
            runtime.skillRepository.mergeDynamicSelectors(spec.appId, current.components, current)

            if (runtime.safetyEngine.detectManualLoginRequired(app, current, yoloMode = spec.yoloMode)) {
                log("manual_login_required screen=${runtime.skillRepository.screenId(current)}")
                return finish(
                    runId = runId,
                    spec = spec,
                    status = "manual_login_required",
                    reason = "Manual login required before automation can continue.",
                    runDir = runDir,
                    actions = actions,
                    current = current,
                    previous = current,
                    transitionConfidence = 0f,
                )
            }

            val decision = runtime.visionEngine.decide(
                goal = spec.goal,
                screen = current,
                skill = skill,
                systemInstruction = runtime.skillRepository.loadSystemSkill(),
                actionHistory = actions,
                availableActions = app.allowedActions,
                explorationEnabled = spec.explorationEnabled,
                yoloMode = spec.yoloMode,
            )
            log(
                "decision step=$step action=${decision.nextAction} " +
                    "screen=${decision.screenClassification} confidence=${decision.confidence} " +
                    "label=${decision.targetLabel.orEmpty()} reason=${decision.reason}"
            )

            var effectiveDecision = decision
            var approvedByUser = false
            if (runtime.safetyEngine.requiresApproval(current, decision, yoloMode = spec.yoloMode)) {
                log("approval_requested reason=${decision.reason}")
                val request = ApprovalRequest(
                    runId = runId,
                    requestId = UUID.randomUUID().toString(),
                    title = "Approval required",
                    message = decision.reason,
                    actionLabel = decision.targetLabel ?: "Allow this action",
                    alternativeLabel = "Deny",
                )
                val pending = RunRecord(
                    runId = runId,
                    appId = spec.appId,
                    goal = spec.goal,
                    status = "approval_required",
                    reason = decision.reason,
                    notice = notice,
                    stepCount = step,
                    runDir = runDir.absolutePath,
                    actions = actions,
                    pendingApproval = request,
                    lastScreenId = runtime.skillRepository.screenId(current),
                )
                runtime.sessionStore.setCurrentRun(pending)
                context.startService(ApprovalOverlayService.startIntent(context, request))
                val resolution = runtime.approvalCoordinator.requestApproval(request).await()
                log("approval_resolution value=$resolution")
                when (resolution) {
                    "deny" -> {
                        return finish(
                            runId = runId,
                            spec = spec,
                            status = "blocked",
                            reason = "User denied the approval request.",
                            runDir = runDir,
                            actions = actions,
                            current = current,
                            previous = current,
                            transitionConfidence = 0f,
                        )
                    }

                    "manual" -> {
                        return finish(
                            runId = runId,
                            spec = spec,
                            status = "paused_for_manual",
                            reason = "User chose to take over manually.",
                            runDir = runDir,
                            actions = actions,
                            current = current,
                            previous = current,
                            transitionConfidence = 0f,
                        )
                    }
                }
                approvedByUser = true
                effectiveDecision = when {
                    decision.nextAction != "stop" -> decision
                    decision.targetNodeId != null || decision.targetBox != null -> {
                        decision.copy(nextAction = "tap")
                    }
                    else -> {
                        return finish(
                            runId = runId,
                            spec = spec,
                            status = "blocked",
                            reason = "Approved action had no executable target.",
                            runDir = runDir,
                            actions = actions,
                            current = current,
                            previous = current,
                            transitionConfidence = 0f,
                        )
                    }
                }
                delay(400)
            }

            val (allowed, verdictReason) = runtime.safetyEngine.evaluate(app, current, effectiveDecision)
            log("safety_verdict allowed=$allowed reason=$verdictReason")
            if (!allowed) {
                return finish(
                    runId = runId,
                    spec = spec,
                    status = "blocked",
                    reason = verdictReason,
                    runDir = runDir,
                    actions = actions,
                    current = current,
                    previous = current,
                    transitionConfidence = 0f,
                )
            }

            actions += RunActionRecord(
                step = step,
                action = effectiveDecision.nextAction,
                reason = effectiveDecision.reason,
                packageName = current.packageName,
                classNameHint = current.classNameHint,
                approvedByUser = approvedByUser,
            )

            if (effectiveDecision.nextAction == "stop") {
                log("run_completed reason=${effectiveDecision.reason}")
                return finish(
                    runId = runId,
                    spec = spec,
                    status = "completed",
                    reason = effectiveDecision.reason,
                    runDir = runDir,
                    actions = actions,
                    current = current,
                    previous = current,
                    transitionConfidence = 1f,
                )
            }

            if (effectiveDecision.nextAction == "wait") {
                log("wait_step")
                delay(1000)
            } else if (effectiveDecision.nextAction == "tool" && effectiveDecision.toolName in listOf("run_script", "save_script", "list_scripts")) {
                val toolResult = executeToolAction(
                    appId = spec.appId,
                    decision = effectiveDecision,
                    runDir = runDir,
                    currentScreen = current,
                    log = ::log,
                )
                log("tool_result tool=${effectiveDecision.toolName} ok=${toolResult.first} detail=${toolResult.second}")
                if (!toolResult.first) {
                    return finish(
                        runId = runId,
                        spec = spec,
                        status = "error",
                        reason = toolResult.second,
                        runDir = runDir,
                        actions = actions,
                        current = current,
                        previous = current,
                        transitionConfidence = 0f,
                    )
                }
            } else if (!controller.perform(effectiveDecision, current)) {
                log("perform_failed action=${effectiveDecision.nextAction}")
                return finish(
                    runId = runId,
                    spec = spec,
                    status = "error",
                    reason = "Failed to execute ${effectiveDecision.nextAction}.",
                    runDir = runDir,
                    actions = actions,
                    current = current,
                    previous = current,
                    transitionConfidence = 0f,
                )
            }

            val next = controller.capture(runDir)
            log("captured_next package=${next.packageName} class=${next.classNameHint.orEmpty()} visible=${next.visibleText.take(4)}")
            val nextScreenId = runtime.skillRepository.screenId(next)
            stallCount = if (nextScreenId == previousScreenId) stallCount + 1 else 0
            previousScreenId = nextScreenId
            if (stallCount >= 3) {
                log("run_stalled screen=$nextScreenId")
                return finish(
                    runId = runId,
                    spec = spec,
                    status = "stalled",
                    reason = "Screen did not change after repeated actions.",
                    runDir = runDir,
                    actions = actions,
                    current = next,
                    previous = current,
                    transitionConfidence = 0.1f,
                )
            }
            current = next
        }

        return finish(
            runId = runId,
            spec = spec,
            status = "max_steps_reached",
            reason = "Max steps reached.",
            runDir = runDir,
            actions = actions,
            current = current,
            previous = current,
            transitionConfidence = 0.4f,
        )
    }

    private suspend fun executeToolAction(
        appId: String,
        decision: AgentDecision,
        runDir: File,
        currentScreen: com.amadeus.nativeagent.model.CapturedScreen,
        log: (String) -> Unit,
    ): Pair<Boolean, String> {
        return when (decision.toolName) {
            "run_script" -> {
                val scriptName = decision.inputText.orEmpty().ifBlank {
                    decision.targetLabel.orEmpty()
                }
                if (scriptName.isBlank()) {
                    return false to "run_script requires a script name."
                }
                val executor = ScriptExecutor(controller, runtime.skillRepository)
                val result = executor.execute(appId, scriptName, runDir, currentScreen, log)
                if (result.ok) {
                    true to "Script '$scriptName' executed: ${result.stepsExecuted}/${result.totalSteps} steps."
                } else {
                    false to (result.error ?: "Script '$scriptName' failed.")
                }
            }

            "save_script" -> {
                val scriptName = decision.targetLabel.orEmpty().ifBlank {
                    decision.inputText.orEmpty()
                }
                if (scriptName.isBlank()) {
                    return false to "save_script requires a script name in targetLabel or inputText."
                }
                // The model can encode steps in the reason field as JSON
                val script = AutomationScript(
                    name = scriptName,
                    description = decision.reason,
                    steps = emptyList(),
                )
                runtime.skillRepository.saveScript(appId, scriptName, script)
                true to "Script '$scriptName' saved."
            }

            "list_scripts" -> {
                val scripts = runtime.skillRepository.listScripts(appId)
                true to "Available scripts: ${scripts.joinToString(", ").ifBlank { "(none)" }}"
            }

            else -> false to "Unknown tool '${decision.toolName}'."
        }
    }

    private fun finish(
        runId: String,
        spec: RunSpec,
        status: String,
            reason: String,
            runDir: File,
            actions: List<RunActionRecord>,
            current: com.amadeus.nativeagent.model.CapturedScreen,
            previous: com.amadeus.nativeagent.model.CapturedScreen,
            transitionConfidence: Float,
    ): RunRecord {
        runtime.skillRepository.recordTransition(
            spec.appId,
            before = previous,
            after = current,
            actionHistory = actions,
            status = status,
            reason = reason,
            transitionConfidence = transitionConfidence,
        )
        runtime.skillRepository.appendMemory(spec.appId, "$status: $reason")
        val record = RunRecord(
            runId = runId,
            appId = spec.appId,
            goal = spec.goal,
            status = status,
            reason = reason,
            notice = if (spec.yoloMode) YOLO_NOTICE else null,
            stepCount = actions.size,
            runDir = runDir.absolutePath,
            actions = actions,
            lastScreenId = runtime.skillRepository.screenId(current),
        )
        runtime.sessionStore.setCurrentRun(record)
        return record
    }

    private fun result(
        runId: String,
        spec: RunSpec,
        status: String,
        reason: String,
        runDir: File,
    ): RunRecord {
        val record = RunRecord(
            runId = runId,
            appId = spec.appId,
            goal = spec.goal,
            status = status,
            reason = reason,
            notice = if (spec.yoloMode) YOLO_NOTICE else null,
            runDir = runDir.absolutePath,
        )
        runtime.sessionStore.setCurrentRun(record)
        return record
    }
}

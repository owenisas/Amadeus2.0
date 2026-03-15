package com.amadeus.nativeagent.engine

import android.content.Context
import android.content.Intent
import com.amadeus.nativeagent.model.AgentDecision
import com.amadeus.nativeagent.model.ApprovalRequest
import com.amadeus.nativeagent.model.RunActionRecord
import com.amadeus.nativeagent.model.RunRecord
import com.amadeus.nativeagent.model.RunSpec
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
    suspend fun run(runId: String, spec: RunSpec): RunRecord {
        val app = runtime.appRegistry.byId(spec.appId)
        val skill = runtime.skillRepository.loadSkill(spec.appId)
        val runDir = File(runtime.skillRepository.runsDirectory(), runId).apply { mkdirs() }
        runtime.sessionStore.setSkills(runtime.skillRepository.listSkillIds())
        runtime.sessionStore.updateProvider("Gemini")

        if (!controller.isReady()) {
            return result(runId, spec, "blocked", "Accessibility and screen capture permissions are required.", runDir)
        }
        if (!controller.launchApp(app.packageName)) {
            return result(runId, spec, "error", "Failed to launch ${app.title}.", runDir)
        }

        var previousScreenId: String? = null
        var current = controller.capture(runDir)
        var stallCount = 0
        val actions = mutableListOf<RunActionRecord>()

        for (step in 1..spec.maxSteps) {
            runtime.skillRepository.recordObservation(spec.appId, current)
            runtime.skillRepository.mergeDynamicSelectors(spec.appId, current.components, current)

            if (runtime.safetyEngine.detectManualLoginRequired(app, current)) {
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
            )

            if (runtime.safetyEngine.requiresApproval(current, decision)) {
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
                    stepCount = step,
                    runDir = runDir.absolutePath,
                    actions = actions,
                    pendingApproval = request,
                    lastScreenId = runtime.skillRepository.screenId(current),
                )
                runtime.sessionStore.setCurrentRun(pending)
                context.startService(ApprovalOverlayService.startIntent(context, request))
                val resolution = runtime.approvalCoordinator.requestApproval(request).await()
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
            }

            val (allowed, verdictReason) = runtime.safetyEngine.evaluate(app, current, decision)
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
                action = decision.nextAction,
                reason = decision.reason,
                packageName = current.packageName,
                classNameHint = current.classNameHint,
            )

            if (decision.nextAction == "stop") {
                return finish(
                    runId = runId,
                    spec = spec,
                    status = "completed",
                    reason = decision.reason,
                    runDir = runDir,
                    actions = actions,
                    current = current,
                    previous = current,
                    transitionConfidence = 1f,
                )
            }

            if (decision.nextAction == "wait") {
                delay(1000)
            } else if (!controller.perform(decision, current)) {
                return finish(
                    runId = runId,
                    spec = spec,
                    status = "error",
                    reason = "Failed to execute ${decision.nextAction}.",
                    runDir = runDir,
                    actions = actions,
                    current = current,
                    previous = current,
                    transitionConfidence = 0f,
                )
            }

            val next = controller.capture(runDir)
            val nextScreenId = runtime.skillRepository.screenId(next)
            stallCount = if (nextScreenId == previousScreenId) stallCount + 1 else 0
            previousScreenId = nextScreenId
            if (stallCount >= 3) {
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
            runDir = runDir.absolutePath,
        )
        runtime.sessionStore.setCurrentRun(record)
        return record
    }
}

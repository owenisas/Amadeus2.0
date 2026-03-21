package com.amadeus.nativeagent.engine

import android.content.Context
import com.amadeus.nativeagent.model.AgentDecision
import com.amadeus.nativeagent.model.BoundingBox
import com.amadeus.nativeagent.model.CapturedScreen
import com.amadeus.nativeagent.model.RunActionRecord
import com.amadeus.nativeagent.model.SkillBundle
import com.amadeus.nativeagent.model.VisionProviderRequest
import com.amadeus.nativeagent.model.VisionProviderResponse
import com.amadeus.nativeagent.runtime.JsonSupport
import com.amadeus.nativeagent.runtime.SettingsRepository
import java.io.File
import java.util.Locale
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.flow.first
import kotlinx.serialization.encodeToString
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject

class VisionEngine(
    private val context: Context,
    private val settingsRepository: SettingsRepository,
) {
    companion object {
        private val yoloPrimaryActionTokens = listOf(
            "allow",
            "agree",
            "accept",
            "continue",
            "ok",
            "got it",
            "next",
            "yes",
            "open",
            "允许",
            "同意",
            "继续",
            "确定",
            "知道了",
            "下一步",
            "完成",
            "打开",
            "同意并继续",
            "转至 gmail",
        )
        private val yoloSecondaryActionTokens = listOf(
            "not now",
            "later",
            "skip",
            "dismiss",
            "close",
            "cancel",
            "don't allow",
            "don’t allow",
            "deny",
            "以后再说",
            "稍后",
            "跳过",
            "关闭",
            "取消",
            "不允许",
        )
    }

    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .writeTimeout(10, TimeUnit.SECONDS)
        .callTimeout(15, TimeUnit.SECONDS)
        .build()

    suspend fun decide(
        goal: String,
        screen: CapturedScreen,
        skill: SkillBundle,
        systemInstruction: String,
        actionHistory: List<RunActionRecord>,
        availableActions: List<String>,
        explorationEnabled: Boolean = true,
        yoloMode: Boolean = false,
    ): AgentDecision {
        val heuristic = HeuristicVisionProvider().decide(goal, screen, skill, actionHistory, yoloMode = yoloMode)
        val apiKey = settingsRepository.geminiApiKey.first().trim()
        val model = settingsRepository.geminiModel.first().trim()
        if (apiKey.isBlank() || (heuristic.requiresUserApproval && !yoloMode)) {
            return heuristic
        }
        // When exploration is disabled, prefer deterministic heuristics over model calls
        if (!explorationEnabled && heuristic.confidence >= 0.7f) {
            return heuristic
        }
        return try {
            geminiDecision(
                apiKey = apiKey,
                model = model.ifBlank { "gemini-3.1-pro-preview" },
                request = VisionProviderRequest(
                    goal = goal,
                    systemInstruction = systemInstruction,
                    skillInstructions = skill.instructions,
                    actionHistory = actionHistory.takeLast(8),
                    availableActions = availableActions,
                    screen = screen,
                ),
                yoloMode = yoloMode,
            )
        } catch (_: Exception) {
            heuristic
        }
    }

    private fun geminiDecision(
        apiKey: String,
        model: String,
        request: VisionProviderRequest,
        yoloMode: Boolean,
    ): AgentDecision {
        val prompt = buildPrompt(request, yoloMode = yoloMode)
        val screenshotBytes = File(request.screen.screenshotPath).readBytes()
        val body = JSONObject()
            .put(
                "contents",
                JSONArray().put(
                    JSONObject()
                        .put("role", "user")
                        .put(
                            "parts",
                            JSONArray()
                                .put(JSONObject().put("text", prompt))
                                .put(
                                    JSONObject().put(
                                        "inline_data",
                                        JSONObject()
                                            .put("mime_type", "image/png")
                                            .put("data", android.util.Base64.encodeToString(screenshotBytes, android.util.Base64.NO_WRAP))
                                    )
                                )
                        )
                )
            )
            .put(
                "generationConfig",
                JSONObject()
                    .put("responseMimeType", "application/json")
                    .put("temperature", 0.1),
            )

        val httpRequest = Request.Builder()
            .url("https://generativelanguage.googleapis.com/v1beta/models/$model:generateContent?key=$apiKey")
            .post(body.toString().toRequestBody("application/json".toMediaType()))
            .build()
        client.newCall(httpRequest).execute().use { response ->
            if (!response.isSuccessful) {
                error("Gemini request failed with ${response.code}")
            }
            val payload = JSONObject(response.body?.string().orEmpty())
            val text = payload
                .getJSONArray("candidates")
                .getJSONObject(0)
                .getJSONObject("content")
                .getJSONArray("parts")
                .getJSONObject(0)
                .getString("text")
            val decoded = com.amadeus.nativeagent.runtime.JsonSupport.json.decodeFromString<VisionProviderResponse>(text)
            val decision = AgentDecision(
                screenClassification = decoded.screenClassification,
                goalProgress = decoded.goalProgress,
                nextAction = decoded.nextAction.lowercase(Locale.US),
                targetNodeId = decoded.targetNodeId,
                targetBox = decoded.targetBox,
                confidence = decoded.confidence,
                reason = decoded.reason,
                riskLevel = decoded.riskLevel,
                inputText = decoded.inputText,
                targetLabel = decoded.targetLabel,
                toolName = decoded.toolName,
                requiresUserApproval = decoded.requiresUserApproval,
            )
            return if (yoloMode) applyYoloOverrides(screen = request.screen, decision = decision) else decision
        }
    }

    private fun buildPrompt(request: VisionProviderRequest, yoloMode: Boolean): String {
        val treeSnippet = JsonSupport.json.encodeToString(request.screen.rawTree).take(12000)
        val components = JsonSupport.json.encodeToString(request.screen.components.take(20))
        val approvalPolicy = if (yoloMode) {
            "YOLO mode is enabled. Do not ask for approval on onboarding, permission, or consent prompts. " +
                "Pick the safest viable action and continue autonomously. Never invent credentials. If a password or verification code is required, stop."
        } else {
            "Stop and require user approval for permissions, subscriptions, purchases, account changes, and ambiguous popups."
        }
        return """
            You are controlling an Android phone using AccessibilityService and screenshots.
            Follow the system instruction and app skill. Prefer safe, reversible actions.
            $approvalPolicy

            System instruction:
            ${request.systemInstruction}

            App skill:
            ${request.skillInstructions}

            Goal:
            ${request.goal}

            Available actions:
            ${request.availableActions}

            Recent actions:
            ${request.actionHistory}

            Visible text:
            ${request.screen.visibleText.take(40)}

            Clickable text:
            ${request.screen.clickableText.take(25)}

            Components:
            $components

            Accessibility tree excerpt:
            $treeSnippet

            Return JSON with:
            screenClassification, goalProgress, nextAction, targetNodeId, targetBox, confidence, reason, riskLevel, inputText, targetLabel, toolName, requiresUserApproval

            Tool actions:
            To save a reusable automation script, use nextAction="tool", toolName="save_script", targetLabel=<script_name>, reason=<description>.
            To replay a saved script, use nextAction="tool", toolName="run_script", inputText=<script_name>.
            To list available scripts, use nextAction="tool", toolName="list_scripts".
            Use scripts for repetitive navigation sequences like searching, dismissing popups, or multi-step flows you have done before.
        """.trimIndent()
    }

    private fun applyYoloOverrides(screen: CapturedScreen, decision: AgentDecision): AgentDecision {
        if (!decision.requiresUserApproval) {
            return decision
        }
        if (decision.nextAction != "stop") {
            return decision.copy(requiresUserApproval = false)
        }
        autoApprovalDecision(screen, preferredLabel = decision.targetLabel)?.let { return it }
        return decision.copy(requiresUserApproval = false)
    }

    private fun autoApprovalDecision(
        screen: CapturedScreen,
        preferredLabel: String? = null,
    ): AgentDecision? {
        val preferred = preferredLabel?.trim().orEmpty()
        if (preferred.isNotBlank()) {
            screen.components.firstOrNull { it.label.equals(preferred, ignoreCase = true) }?.let { component ->
                return AgentDecision(
                    screenClassification = "approval_surface",
                    goalProgress = "yolo_auto_approval",
                    nextAction = "tap",
                    targetNodeId = component.nodeId,
                    targetBox = component.targetBox,
                    confidence = 0.96f,
                    reason = "YOLO mode auto-continued through an approval surface.",
                    riskLevel = "low",
                    targetLabel = component.label,
                )
            }
        }
        for (tokens in listOf(yoloPrimaryActionTokens, yoloSecondaryActionTokens)) {
            for (token in tokens) {
                screen.components.firstOrNull { component ->
                    component.label.isNotBlank() &&
                        component.enabled &&
                        component.label.lowercase().contains(token)
                }?.let { component ->
                    return AgentDecision(
                        screenClassification = "approval_surface",
                        goalProgress = "yolo_auto_approval",
                        nextAction = "tap",
                        targetNodeId = component.nodeId,
                        targetBox = component.targetBox,
                        confidence = 0.95f,
                        reason = "YOLO mode auto-continued through an approval surface.",
                        riskLevel = "low",
                        targetLabel = component.label,
                    )
                }
            }
        }
        return null
    }
}

private class HeuristicVisionProvider {
    fun decide(
        goal: String,
        screen: CapturedScreen,
        skill: SkillBundle,
        actionHistory: List<RunActionRecord>,
        yoloMode: Boolean,
    ): AgentDecision {
        val text = screen.visibleText.joinToString(" ").lowercase()
        val labeledComponents = screen.components.filter { it.label.isNotBlank() }
        fun findLabel(vararg labels: String) = labeledComponents.firstOrNull { component ->
            val value = component.label.lowercase()
            labels.any { it == value }
        }

        if (listOf("password", "verification code").any { it in text } ||
            (!yoloMode && listOf("choose an account", "sign in").any { it in text })
        ) {
            return AgentDecision(
                screenClassification = "account_gate",
                goalProgress = "blocked",
                nextAction = "stop",
                confidence = 0.98f,
                reason = "Account or sign-in surface requires explicit user handling.",
                riskLevel = "medium",
                requiresUserApproval = true,
            )
        }

        findLabel("got it", "continue", "skip", "next")?.let { dismissComponent ->
            return AgentDecision(
                screenClassification = "onboarding_dismiss",
                goalProgress = "navigating",
                nextAction = "tap",
                targetNodeId = dismissComponent.nodeId,
                targetBox = dismissComponent.targetBox,
                confidence = 0.96f,
                reason = "Dismiss the onboarding surface and continue toward the app content.",
                riskLevel = "low",
                targetLabel = dismissComponent.label,
            )
        }

        findLabel("allow", "允许", "while using the app", "允许在使用应用期间").let { allowComponent ->
            if (allowComponent != null && listOf("permission", "notification", "allow").any { it in text }) {
                if (yoloMode) {
                    return AgentDecision(
                        screenClassification = "approval_surface",
                        goalProgress = "yolo_auto_approval",
                        nextAction = "tap",
                        targetNodeId = allowComponent.nodeId,
                        targetBox = allowComponent.targetBox,
                        confidence = 0.98f,
                        reason = "YOLO mode auto-continued through an approval surface.",
                        riskLevel = "low",
                        targetLabel = allowComponent.label,
                    )
                }
                val summary = screen.visibleText.take(3).joinToString("; ")
                val actions = screen.clickableText.take(4).joinToString(", ")
                return AgentDecision(
                    screenClassification = "permission_prompt",
                    goalProgress = "awaiting_user_approval",
                    nextAction = "stop",
                    targetNodeId = allowComponent.nodeId,
                    targetBox = allowComponent.targetBox,
                    confidence = 0.98f,
                    reason = "User approval required for permission prompt: $summary. Available actions: $actions.",
                    riskLevel = "medium",
                    targetLabel = allowComponent.label,
                    requiresUserApproval = true,
                )
            }
        }

        findLabel("agree", "accept", "continue", "同意", "继续", "同意并继续").let { consentComponent ->
            if (consentComponent != null && listOf("privacy", "agreement", "用户须知", "隐私", "同意").any { it in text }) {
                return AgentDecision(
                    screenClassification = if (yoloMode) "approval_surface" else "consent_gate",
                    goalProgress = if (yoloMode) "yolo_auto_approval" else "navigating",
                    nextAction = "tap",
                    targetNodeId = consentComponent.nodeId,
                    targetBox = consentComponent.targetBox,
                    confidence = 0.95f,
                    reason = if (yoloMode) {
                        "YOLO mode auto-continued through an approval surface."
                    } else {
                        "Accept the low-risk consent surface and continue into the app."
                    },
                    riskLevel = "low",
                    targetLabel = consentComponent.label,
                )
            }
        }

        findLabel("not now", "以后再说", "skip").let { dismissComponent ->
            if (dismissComponent != null && listOf("promo", "games", "later", "以后再说", "not now").any { it in text }) {
                return AgentDecision(
                    screenClassification = "promo_dismiss",
                    goalProgress = "navigating",
                    nextAction = "tap",
                    targetNodeId = dismissComponent.nodeId,
                    targetBox = dismissComponent.targetBox,
                    confidence = 0.9f,
                    reason = "Dismiss the low-risk promo/interstitial and continue.",
                    riskLevel = "low",
                    targetLabel = dismissComponent.label,
                )
            }
        }

        if (screen.packageName == "com.google.android.gm" && listOf("inbox", "primary", "收件箱", "主要").any { it in text }) {
            return AgentDecision(
                screenClassification = "gmail_inbox",
                goalProgress = "complete",
                nextAction = "stop",
                confidence = 0.9f,
                reason = "Gmail inbox is visible and can be inspected read-only.",
                riskLevel = "low",
            )
        }
        if (screen.packageName == "com.android.vending") {
            skill.selectors.firstOrNull { selector ->
                selector.anchorText.all { anchor -> anchor.lowercase() in text } &&
                    selector.targetBox != null
            }?.let { selector ->
                return AgentDecision(
                    screenClassification = "selector_match",
                    goalProgress = "navigating",
                    nextAction = "tap",
                    targetBox = selector.targetBox,
                    confidence = 0.74f,
                    reason = selector.reason,
                    riskLevel = "low",
                    targetLabel = selector.label,
                )
            }
            if ("search" in goal.lowercase() && actionHistory.none { it.action == "type" }) {
                val searchComponent = screen.components.firstOrNull { it.componentType == "search_action" }
                if (searchComponent?.targetBox != null) {
                    return AgentDecision(
                        screenClassification = "playstore_search_ready",
                        goalProgress = "navigating",
                        nextAction = "tap",
                        targetBox = searchComponent.targetBox,
                        targetNodeId = searchComponent.nodeId,
                        confidence = 0.7f,
                        reason = "Open the Play Store search affordance.",
                        riskLevel = "low",
                        targetLabel = searchComponent.label,
                    )
                }
            }
        }
        val searchInput = screen.components.firstOrNull { it.componentType == "text_input" && it.searchRelated }
        if (searchInput != null && goal.lowercase().contains("search")) {
            val query = extractQuery(goal)
            if (query.isNotBlank()) {
                return AgentDecision(
                    screenClassification = "search_input",
                    goalProgress = "typing",
                    nextAction = "type",
                    targetNodeId = searchInput.nodeId,
                    targetBox = searchInput.targetBox,
                    confidence = 0.7f,
                    reason = "Type the requested search query into the visible search field.",
                    riskLevel = "low",
                    inputText = query,
                    targetLabel = searchInput.label,
                )
            }
        }
        return AgentDecision(
            screenClassification = "unknown",
            goalProgress = "observing",
            nextAction = if (screen.components.any { it.componentType == "touch_target" }) "wait" else "stop",
            confidence = 0.5f,
            reason = "No deterministic heuristic matched; keep the run safe.",
            riskLevel = "low",
        )
    }

    private fun extractQuery(goal: String): String {
        val quoted = "\"([^\"]+)\"".toRegex().find(goal)?.groupValues?.getOrNull(1)
        if (!quoted.isNullOrBlank()) {
            return quoted
        }
        return goal.substringAfter("search", "").substringAfter("for").trim()
    }
}

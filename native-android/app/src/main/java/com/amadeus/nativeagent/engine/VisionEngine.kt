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
    private val client = OkHttpClient()

    suspend fun decide(
        goal: String,
        screen: CapturedScreen,
        skill: SkillBundle,
        systemInstruction: String,
        actionHistory: List<RunActionRecord>,
        availableActions: List<String>,
    ): AgentDecision {
        val heuristic = HeuristicVisionProvider().decide(goal, screen, skill, actionHistory)
        val apiKey = settingsRepository.geminiApiKey.first().trim()
        val model = settingsRepository.geminiModel.first().trim()
        if (apiKey.isBlank() || heuristic.requiresUserApproval) {
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
            )
        } catch (_: Exception) {
            heuristic
        }
    }

    private fun geminiDecision(
        apiKey: String,
        model: String,
        request: VisionProviderRequest,
    ): AgentDecision {
        val prompt = buildPrompt(request)
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
            return AgentDecision(
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
        }
    }

    private fun buildPrompt(request: VisionProviderRequest): String {
        val treeSnippet = JsonSupport.json.encodeToString(request.screen.rawTree).take(12000)
        val components = JsonSupport.json.encodeToString(request.screen.components.take(20))
        return """
            You are controlling an Android phone using AccessibilityService and screenshots.
            Follow the system instruction and app skill. Prefer safe, reversible actions.
            Stop and require user approval for permissions, subscriptions, purchases, account changes, and ambiguous popups.

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
        """.trimIndent()
    }
}

private class HeuristicVisionProvider {
    fun decide(
        goal: String,
        screen: CapturedScreen,
        skill: SkillBundle,
        actionHistory: List<RunActionRecord>,
    ): AgentDecision {
        val text = screen.visibleText.joinToString(" ").lowercase()
        if (listOf("allow", "deny", "not now", "以后再说", "允许", "不允许").any { it in text }) {
            return AgentDecision(
                screenClassification = "approval_gate",
                goalProgress = "blocked",
                nextAction = "stop",
                confidence = 1f,
                reason = "User approval required for the current popup.",
                riskLevel = "medium",
                requiresUserApproval = true,
            )
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

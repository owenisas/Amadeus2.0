package com.amadeus.nativeagent.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class BoundingBox(
    val x: Float,
    val y: Float,
    val width: Float,
    val height: Float,
)

@Serializable
data class DeviceMetrics(
    val width: Int,
    val height: Int,
    val densityDpi: Int,
    val orientation: String,
    val packageName: String,
    val classNameHint: String? = null,
)

@Serializable
data class RawAccessibilityNode(
    val nodeId: String,
    val className: String? = null,
    val packageName: String? = null,
    val viewIdResourceName: String? = null,
    val text: String? = null,
    val contentDescription: String? = null,
    val boundsInScreen: BoundingBox? = null,
    val clickable: Boolean = false,
    val enabled: Boolean = false,
    val editable: Boolean = false,
    val focused: Boolean = false,
    val focusable: Boolean = false,
    val scrollable: Boolean = false,
    val checkable: Boolean = false,
    val checked: Boolean = false,
    val selected: Boolean = false,
    val children: List<RawAccessibilityNode> = emptyList(),
)

@Serializable
data class UiComponent(
    val nodeId: String,
    val componentType: String,
    val label: String = "",
    val className: String = "",
    val packageName: String = "",
    val resourceId: String = "",
    val enabled: Boolean = false,
    val clickable: Boolean = false,
    val focused: Boolean = false,
    val searchRelated: Boolean = false,
    val targetBox: BoundingBox? = null,
)

@Serializable
data class CapturedScreen(
    val capturedAtEpochMs: Long,
    val screenshotPath: String,
    val rawTreePath: String,
    val screenshotSha256: String,
    val rawTree: RawAccessibilityNode,
    val visibleText: List<String>,
    val clickableText: List<String>,
    val components: List<UiComponent>,
    val packageName: String,
    val classNameHint: String? = null,
    val device: DeviceMetrics,
)

@Serializable
data class SelectorRecord(
    val label: String,
    val packageName: String,
    val screenId: String,
    val reason: String,
    val anchorText: List<String> = emptyList(),
    val resourceId: String? = null,
    val className: String? = null,
    val componentType: String? = null,
    val searchRelated: Boolean = false,
    val targetBox: BoundingBox? = null,
)

@Serializable
data class ScreenRecord(
    val screenId: String,
    val packageName: String,
    val classNameHint: String? = null,
    val visibleText: List<String> = emptyList(),
    val clickableText: List<String> = emptyList(),
    val components: List<UiComponent> = emptyList(),
)

@Serializable
data class AppStateRecord(
    val status: String = "idle",
    val reason: String = "",
    val lastSuccessfulScreen: String? = null,
    val lastActionChain: List<String> = emptyList(),
    val failureCount: Int = 0,
    val transitionConfidence: Float = 0f,
    val lastKnownResultScreen: String? = null,
    val searchTransitions: Map<String, String> = emptyMap(),
)

@Serializable
data class SkillBundle(
    val appId: String,
    val instructions: String,
    val screens: Map<String, ScreenRecord>,
    val selectors: List<SelectorRecord>,
    val state: AppStateRecord,
    val memory: String,
)

@Serializable
data class AgentDecision(
    val screenClassification: String,
    val goalProgress: String,
    val nextAction: String,
    val targetNodeId: String? = null,
    val targetBox: BoundingBox? = null,
    val confidence: Float,
    val reason: String,
    val riskLevel: String,
    val inputText: String? = null,
    val targetLabel: String? = null,
    val toolName: String? = null,
    val requiresUserApproval: Boolean = false,
)

@Serializable
data class ApprovalRequest(
    val runId: String,
    val requestId: String,
    val title: String,
    val message: String,
    val actionLabel: String,
    val alternativeLabel: String? = null,
)

@Serializable
data class RunActionRecord(
    val step: Int,
    val action: String,
    val reason: String,
    val packageName: String,
    val classNameHint: String? = null,
    val approvedByUser: Boolean = false,
)

@Serializable
data class RunRecord(
    val runId: String,
    val appId: String,
    val goal: String,
    val status: String,
    val reason: String,
    val stepCount: Int = 0,
    val runDir: String,
    val actions: List<RunActionRecord> = emptyList(),
    val pendingApproval: ApprovalRequest? = null,
    val lastScreenId: String? = null,
)

@Serializable
data class AppDefinition(
    val id: String,
    val title: String,
    val packageName: String,
    val launchActivity: String? = null,
    val allowedActions: List<String>,
    val blockedKeywords: List<String>,
    val highRiskSignatures: List<String>,
    val manualLoginTokens: List<String>,
    val defaultGoalHint: String,
)

@Serializable
data class RunSpec(
    val appId: String,
    val goal: String,
    val maxSteps: Int,
    val explorationEnabled: Boolean,
)

@Serializable
data class RuntimeSnapshot(
    val currentRun: RunRecord? = null,
    val runHistory: List<RunRecord> = emptyList(),
    val skills: List<String> = emptyList(),
    val providerLabel: String = "Gemini",
    val projectionGranted: Boolean = false,
    val overlayGranted: Boolean = false,
    val accessibilityGranted: Boolean = false,
    val debugLines: List<String> = emptyList(),
)

@Serializable
data class VisionProviderRequest(
    val goal: String,
    val systemInstruction: String,
    val skillInstructions: String,
    val actionHistory: List<RunActionRecord>,
    val availableActions: List<String>,
    val screen: CapturedScreen,
)

@Serializable
data class VisionProviderResponse(
    @SerialName("screen_classification")
    val screenClassification: String,
    @SerialName("goal_progress")
    val goalProgress: String,
    @SerialName("next_action")
    val nextAction: String,
    @SerialName("target_node_id")
    val targetNodeId: String? = null,
    @SerialName("target_box")
    val targetBox: BoundingBox? = null,
    val confidence: Float,
    val reason: String,
    @SerialName("risk_level")
    val riskLevel: String,
    @SerialName("input_text")
    val inputText: String? = null,
    @SerialName("target_label")
    val targetLabel: String? = null,
    @SerialName("tool_name")
    val toolName: String? = null,
    @SerialName("requires_user_approval")
    val requiresUserApproval: Boolean = false,
)

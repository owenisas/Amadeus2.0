package com.amadeus.nativeagent

import com.amadeus.nativeagent.engine.SafetyEngine
import com.amadeus.nativeagent.model.AgentDecision
import com.amadeus.nativeagent.model.AppDefinition
import com.amadeus.nativeagent.model.CapturedScreen
import com.amadeus.nativeagent.model.DeviceMetrics
import com.amadeus.nativeagent.model.RawAccessibilityNode
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class SafetyEngineTest {
    private val engine = SafetyEngine()

    @Test
    fun `detects manual login from screen text`() {
        val app = appDefinition()
        val screen = capturedScreen(visibleText = listOf("Sign in", "Enter password"))
        assertTrue(engine.detectManualLoginRequired(app, screen))
    }

    @Test
    fun `requires approval for permission prompts`() {
        val screen = capturedScreen(
            packageName = "com.google.android.permissioncontroller",
            visibleText = listOf("Allow Gmail to send notifications?", "Allow", "Deny"),
            classNameHint = "GrantPermissionsActivity",
        )
        val decision = AgentDecision(
            screenClassification = "permission",
            goalProgress = "blocked",
            nextAction = "stop",
            confidence = 1f,
            reason = "Permission prompt",
            riskLevel = "medium",
        )
        assertTrue(engine.requiresApproval(screen, decision))
    }

    @Test
    fun `blocks high risk keywords`() {
        val app = appDefinition()
        val screen = capturedScreen(visibleText = listOf("Review your order"))
        val decision = AgentDecision(
            screenClassification = "checkout",
            goalProgress = "blocked",
            nextAction = "tap",
            confidence = 0.8f,
            reason = "Tap buy now",
            riskLevel = "high",
            targetLabel = "Buy now",
        )
        val (allowed, _) = engine.evaluate(app, screen, decision)
        assertFalse(allowed)
    }

    private fun appDefinition() = AppDefinition(
        id = "amazon",
        title = "Amazon",
        packageName = "com.amazon.mShop.android.shopping",
        allowedActions = listOf("tap", "stop"),
        blockedKeywords = listOf("buy now", "place your order"),
        highRiskSignatures = listOf("review your order", "payment method"),
        manualLoginTokens = listOf("sign in", "password"),
        defaultGoalHint = "",
    )

    private fun capturedScreen(
        packageName: String = "com.google.android.gm",
        classNameHint: String? = ".ConversationListActivityGmail",
        visibleText: List<String>,
    ) = CapturedScreen(
        capturedAtEpochMs = 0L,
        screenshotPath = "/tmp/fake.png",
        rawTreePath = "/tmp/fake.json",
        screenshotSha256 = "abc",
        rawTree = RawAccessibilityNode(nodeId = "root"),
        visibleText = visibleText,
        clickableText = visibleText,
        components = emptyList(),
        packageName = packageName,
        classNameHint = classNameHint,
        device = DeviceMetrics(
            width = 1080,
            height = 2400,
            densityDpi = 420,
            orientation = "portrait",
            packageName = packageName,
            classNameHint = classNameHint,
        ),
    )
}

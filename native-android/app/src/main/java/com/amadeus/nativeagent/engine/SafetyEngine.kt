package com.amadeus.nativeagent.engine

import com.amadeus.nativeagent.model.AgentDecision
import com.amadeus.nativeagent.model.AppDefinition
import com.amadeus.nativeagent.model.CapturedScreen

class SafetyEngine {
    fun detectManualLoginRequired(app: AppDefinition, screen: CapturedScreen, yoloMode: Boolean = false): Boolean {
        if (yoloMode) {
            return false
        }
        val text = screen.visibleText.joinToString(" ").lowercase()
        return app.manualLoginTokens.any { token -> token.lowercase() in text }
    }

    fun requiresApproval(screen: CapturedScreen, decision: AgentDecision, yoloMode: Boolean = false): Boolean {
        if (yoloMode) {
            return false
        }
        if (decision.requiresUserApproval) {
            return true
        }
        val text = screen.visibleText.joinToString(" ").lowercase()
        val approvalTokens = listOf(
            "choose an account",
            "sign in",
            "password",
            "verification",
            "payment",
            "purchase",
            "subscribe",
            "购买",
            "付费",
            "credit card",
        )
        return approvalTokens.any { token -> token in text }
    }

    fun evaluate(app: AppDefinition, screen: CapturedScreen, decision: AgentDecision): Pair<Boolean, String> {
        if (decision.nextAction == "stop") {
            return true to decision.reason
        }
        val screenText = if (decision.screenClassification == "approval_surface") "" else screen.visibleText.joinToString(" ").lowercase()
        val riskText = buildString {
            append(screenText)
            append(' ')
            append(decision.reason.lowercase())
            append(' ')
            append(decision.targetLabel.orEmpty().lowercase())
        }
        if (app.blockedKeywords.any { keyword -> keyword.lowercase() in riskText }) {
            return false to "Blocked by app safety policy."
        }
        if (app.highRiskSignatures.any { keyword -> keyword.lowercase() in riskText }) {
            return false to "High-risk action requires explicit approval."
        }
        return true to "Allowed by safety policy."
    }
}

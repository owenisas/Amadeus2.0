package com.amadeus.nativeagent.runtime

import com.amadeus.nativeagent.model.AppDefinition

object AppRegistry {
    val apps: List<AppDefinition> = listOf(
        AppDefinition(
            id = "gmail",
            title = "Gmail",
            packageName = "com.google.android.gm",
            launchActivity = ".ConversationListActivityGmail",
            allowedActions = listOf("tap", "type", "swipe", "back", "home", "wait", "stop"),
            blockedKeywords = listOf(
                "compose",
                "send",
                "reply",
                "reply all",
                "forward",
                "archive",
                "delete",
                "spam",
                "move to",
                "label",
            ),
            highRiskSignatures = listOf("compose", "send", "reply", "forward", "trash"),
            manualLoginTokens = listOf("sign in", "password", "verification", "choose an account"),
            defaultGoalHint = "Open Gmail, inspect the inbox read-only, and stop without composing, replying, deleting, or archiving.",
        ),
        AppDefinition(
            id = "playstore",
            title = "Play Store",
            packageName = "com.android.vending",
            allowedActions = listOf("tap", "type", "swipe", "back", "home", "wait", "stop"),
            blockedKeywords = listOf("buy", "purchase", "subscribe", "付费", "购买"),
            highRiskSignatures = listOf("buy", "purchase", "subscribe", "$", "¥"),
            manualLoginTokens = listOf("sign in", "password", "verification"),
            defaultGoalHint = "Search the Play Store, open a free app or game page, install it only when explicitly requested, then stop when Open or Play appears.",
        ),
    )

    fun byId(appId: String): AppDefinition =
        apps.firstOrNull { it.id == appId }
            ?: error("Unknown app '$appId'. Supported apps: ${apps.joinToString { it.id }}")
}

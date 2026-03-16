package com.amadeus.nativeagent.service

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.content.Intent
import android.graphics.Path
import android.os.Bundle
import android.os.SystemClock
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import com.amadeus.nativeagent.engine.AccessibilityTreeSerializer
import com.amadeus.nativeagent.model.AgentDecision
import com.amadeus.nativeagent.model.CapturedScreen
import com.amadeus.nativeagent.model.DeviceMetrics
import com.amadeus.nativeagent.model.RawAccessibilityNode
import com.amadeus.nativeagent.runtime.JsonSupport
import com.amadeus.nativeagent.util.FileHash.sha256
import java.io.File

class AndroidControlService : AccessibilityService() {
    private var lastPackageName: String = ""
    private var lastClassName: String? = null

    override fun onServiceConnected() {
        instance = this
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        lastPackageName = event?.packageName?.toString().orEmpty().ifBlank { lastPackageName }
        lastClassName = event?.className?.toString() ?: lastClassName
    }

    override fun onInterrupt() = Unit

    override fun onDestroy() {
        if (instance === this) {
            instance = null
        }
        super.onDestroy()
    }

    fun launchApp(packageName: String): Boolean {
        val intent = packageManager.getLaunchIntentForPackage(packageName) ?: return false
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        startActivity(intent)
        return waitForPackage(packageName)
    }

    fun captureScreen(runDir: File, screenCaptureService: ScreenCaptureService): CapturedScreen {
        val root = rootInActiveWindow ?: error("No active accessibility root available.")
        val screenshot = screenCaptureService.captureToFile(runDir)
        val metrics = DeviceMetrics(
            width = resources.displayMetrics.widthPixels,
            height = resources.displayMetrics.heightPixels,
            densityDpi = resources.displayMetrics.densityDpi,
            orientation = if (resources.configuration.orientation == android.content.res.Configuration.ORIENTATION_LANDSCAPE) "landscape" else "portrait",
            packageName = root.packageName?.toString().orEmpty().ifBlank { lastPackageName },
            classNameHint = lastClassName ?: root.className?.toString(),
        )
        val rawTree = AccessibilityTreeSerializer.serializeTree(root, metrics)
        val treeFile = File(runDir, "${System.currentTimeMillis()}.json")
        treeFile.writeText(JsonSupport.json.encodeToString(RawAccessibilityNode.serializer(), rawTree))
        return CapturedScreen(
            capturedAtEpochMs = System.currentTimeMillis(),
            screenshotPath = screenshot.file.absolutePath,
            rawTreePath = treeFile.absolutePath,
            screenshotSha256 = sha256(screenshot.file),
            rawTree = rawTree,
            visibleText = AccessibilityTreeSerializer.visibleText(rawTree),
            clickableText = AccessibilityTreeSerializer.clickableText(rawTree),
            components = AccessibilityTreeSerializer.components(rawTree),
            packageName = metrics.packageName,
            classNameHint = metrics.classNameHint,
            device = metrics,
        )
    }

    fun performDecision(decision: AgentDecision, currentScreen: CapturedScreen): Boolean {
        return when (decision.nextAction) {
            "tap" -> tap(decision, currentScreen)
            "type" -> type(decision)
            "swipe" -> swipe(currentScreen)
            "back" -> performGlobalAction(GLOBAL_ACTION_BACK)
            "home" -> performGlobalAction(GLOBAL_ACTION_HOME)
            "wait" -> true
            else -> true
        }
    }

    private fun tap(decision: AgentDecision, currentScreen: CapturedScreen): Boolean {
        decision.targetNodeId?.let { nodeId ->
            findNodeById(rootInActiveWindow, nodeId)?.let { node ->
                if (node.performAction(AccessibilityNodeInfo.ACTION_CLICK)) {
                    return true
                }
            }
        }
        val box = decision.targetBox ?: return false
        val centerX = ((box.x + (box.width / 2f)) * currentScreen.device.width).toInt()
        val centerY = ((box.y + (box.height / 2f)) * currentScreen.device.height).toInt()
        val path = Path().apply { moveTo(centerX.toFloat(), centerY.toFloat()) }
        val gesture = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0, 80))
            .build()
        return dispatchGesture(gesture, null, null)
    }

    private fun type(decision: AgentDecision): Boolean {
        val node = decision.targetNodeId?.let { findNodeById(rootInActiveWindow, it) }
            ?: findFirstEditable(rootInActiveWindow)
            ?: return false
        val bundle = Bundle().apply {
            putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, decision.inputText.orEmpty())
        }
        return node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, bundle)
    }

    private fun swipe(currentScreen: CapturedScreen): Boolean {
        val scrollable = findFirstScrollable(rootInActiveWindow)
        if (scrollable?.performAction(AccessibilityNodeInfo.ACTION_SCROLL_FORWARD) == true) {
            return true
        }
        val startX = currentScreen.device.width / 2f
        val startY = currentScreen.device.height * 0.75f
        val endY = currentScreen.device.height * 0.25f
        val path = Path().apply {
            moveTo(startX, startY)
            lineTo(startX, endY)
        }
        val gesture = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0, 250))
            .build()
        return dispatchGesture(gesture, null, null)
    }

    private fun findNodeById(root: AccessibilityNodeInfo?, nodeId: String): AccessibilityNodeInfo? {
        root ?: return null
        if (nodeId == "root") {
            return root
        }
        var current: AccessibilityNodeInfo? = root
        nodeId.removePrefix("root.").split('.').forEach { segment ->
            val index = segment.toIntOrNull() ?: return null
            current = current?.getChild(index) ?: return null
        }
        return current
    }

    private fun findFirstEditable(root: AccessibilityNodeInfo?): AccessibilityNodeInfo? {
        root ?: return null
        if (root.isEditable) {
            return root
        }
        for (index in 0 until root.childCount) {
            findFirstEditable(root.getChild(index))?.let { return it }
        }
        return null
    }

    private fun findFirstScrollable(root: AccessibilityNodeInfo?): AccessibilityNodeInfo? {
        root ?: return null
        if (root.isScrollable) {
            return root
        }
        for (index in 0 until root.childCount) {
            findFirstScrollable(root.getChild(index))?.let { return it }
        }
        return null
    }

    private fun waitForPackage(packageName: String, timeoutMs: Long = 5_000): Boolean {
        val deadline = SystemClock.uptimeMillis() + timeoutMs
        while (SystemClock.uptimeMillis() < deadline) {
            val activePackage = rootInActiveWindow?.packageName?.toString().orEmpty().ifBlank { lastPackageName }
            if (activePackage == packageName) {
                return true
            }
            SystemClock.sleep(100)
        }
        return false
    }

    companion object {
        @Volatile
        var instance: AndroidControlService? = null
            private set
    }
}

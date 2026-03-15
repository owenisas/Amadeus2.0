package com.amadeus.nativeagent.engine

import android.graphics.Rect
import android.view.accessibility.AccessibilityNodeInfo
import com.amadeus.nativeagent.model.BoundingBox
import com.amadeus.nativeagent.model.DeviceMetrics
import com.amadeus.nativeagent.model.RawAccessibilityNode
import com.amadeus.nativeagent.model.UiComponent

object AccessibilityTreeSerializer {
    fun serializeTree(root: AccessibilityNodeInfo, metrics: DeviceMetrics): RawAccessibilityNode {
        return serializeNode(root, "root", metrics)
    }

    fun visibleText(root: RawAccessibilityNode): List<String> =
        flatten(root)
            .mapNotNull { node -> elementText(node).takeIf { it.isNotBlank() } }
            .distinctBy { it.lowercase() }

    fun clickableText(root: RawAccessibilityNode): List<String> =
        flatten(root)
            .filter { it.clickable }
            .mapNotNull { node -> elementText(node).ifBlank { descendantText(node) }.takeIf { it.isNotBlank() } }
            .distinctBy { it.lowercase() }

    fun components(root: RawAccessibilityNode): List<UiComponent> =
        flatten(root)
            .mapNotNull { node ->
                val componentType = componentType(node) ?: return@mapNotNull null
                UiComponent(
                    nodeId = node.nodeId,
                    componentType = componentType,
                    label = elementText(node).ifBlank { descendantText(node) },
                    className = node.className.orEmpty(),
                    packageName = node.packageName.orEmpty(),
                    resourceId = node.viewIdResourceName.orEmpty(),
                    enabled = node.enabled,
                    clickable = node.clickable,
                    focused = node.focused,
                    searchRelated = isSearchRelated(node),
                    targetBox = node.boundsInScreen,
                )
            }
            .distinctBy { "${it.componentType}|${it.resourceId}|${it.label.lowercase()}" }

    private fun serializeNode(
        node: AccessibilityNodeInfo,
        nodeId: String,
        metrics: DeviceMetrics,
    ): RawAccessibilityNode {
        val bounds = Rect()
        node.getBoundsInScreen(bounds)
        return RawAccessibilityNode(
            nodeId = nodeId,
            className = node.className?.toString(),
            packageName = node.packageName?.toString(),
            viewIdResourceName = node.viewIdResourceName,
            text = node.text?.toString(),
            contentDescription = node.contentDescription?.toString(),
            boundsInScreen = normalize(bounds, metrics),
            clickable = node.isClickable,
            enabled = node.isEnabled,
            editable = node.isEditable,
            focused = node.isFocused,
            focusable = node.isFocusable,
            scrollable = node.isScrollable,
            checkable = node.isCheckable,
            checked = node.isChecked,
            selected = node.isSelected,
            children = buildList {
                for (index in 0 until node.childCount) {
                    node.getChild(index)?.let { child ->
                        add(serializeNode(child, "$nodeId.$index", metrics))
                    }
                }
            },
        )
    }

    private fun flatten(root: RawAccessibilityNode): List<RawAccessibilityNode> =
        buildList {
            add(root)
            root.children.forEach { addAll(flatten(it)) }
        }

    private fun normalize(rect: Rect, metrics: DeviceMetrics): BoundingBox =
        BoundingBox(
            x = (rect.left / metrics.width.toFloat()).coerceIn(0f, 1f),
            y = (rect.top / metrics.height.toFloat()).coerceIn(0f, 1f),
            width = ((rect.right - rect.left) / metrics.width.toFloat()).coerceIn(0f, 1f),
            height = ((rect.bottom - rect.top) / metrics.height.toFloat()).coerceIn(0f, 1f),
        )

    private fun componentType(node: RawAccessibilityNode): String? {
        val className = node.className.orEmpty()
        if (node.editable || className.contains("EditText")) {
            return "text_input"
        }
        if (!node.clickable) {
            return null
        }
        val label = elementText(node).ifBlank { descendantText(node) }
        return when {
            isSearchRelated(node) -> "search_action"
            className.contains("Button") || className.contains("ImageButton") || className.contains("Switch") -> "button"
            label.isNotBlank() -> "touch_target"
            else -> null
        }
    }

    private fun isSearchRelated(node: RawAccessibilityNode): Boolean {
        val combined = listOf(
            node.viewIdResourceName.orEmpty(),
            node.text.orEmpty(),
            node.contentDescription.orEmpty(),
        ).joinToString(" ").lowercase()
        return listOf("search", "find", "query", "搜索", "apps & games").any { it in combined }
    }

    private fun elementText(node: RawAccessibilityNode): String =
        (node.text ?: node.contentDescription ?: "").trim()

    private fun descendantText(node: RawAccessibilityNode): String =
        flatten(node)
            .map { elementText(it) }
            .filter { it.isNotBlank() }
            .distinctBy { it.lowercase() }
            .take(4)
            .joinToString(" | ")
}

package com.amadeus.nativeagent

import com.amadeus.nativeagent.engine.AccessibilityTreeSerializer
import com.amadeus.nativeagent.model.BoundingBox
import com.amadeus.nativeagent.model.RawAccessibilityNode
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class AccessibilityTreeSerializerTest {
    @Test
    fun `extracts visible text and clickable labels`() {
        val tree = RawAccessibilityNode(
            nodeId = "root",
            className = "android.widget.FrameLayout",
            children = listOf(
                RawAccessibilityNode(
                    nodeId = "root.0",
                    className = "android.widget.Button",
                    text = "Search",
                    clickable = true,
                    enabled = true,
                    boundsInScreen = BoundingBox(0f, 0f, 0.5f, 0.1f),
                ),
                RawAccessibilityNode(
                    nodeId = "root.1",
                    className = "android.widget.TextView",
                    text = "Inbox",
                ),
            ),
        )

        assertEquals(listOf("Search", "Inbox"), AccessibilityTreeSerializer.visibleText(tree))
        assertEquals(listOf("Search"), AccessibilityTreeSerializer.clickableText(tree))
    }

    @Test
    fun `classifies search input and button components`() {
        val tree = RawAccessibilityNode(
            nodeId = "root",
            className = "android.widget.FrameLayout",
            children = listOf(
                RawAccessibilityNode(
                    nodeId = "root.0",
                    className = "android.widget.EditText",
                    text = "Search mail",
                    editable = true,
                    enabled = true,
                    boundsInScreen = BoundingBox(0f, 0f, 1f, 0.1f),
                ),
                RawAccessibilityNode(
                    nodeId = "root.1",
                    className = "android.widget.Button",
                    text = "Install",
                    clickable = true,
                    enabled = true,
                    boundsInScreen = BoundingBox(0f, 0.2f, 1f, 0.1f),
                ),
            ),
        )

        val components = AccessibilityTreeSerializer.components(tree)
        assertTrue(components.any { it.componentType == "text_input" && it.searchRelated })
        assertTrue(components.any { it.componentType == "button" && it.label == "Install" })
    }
}

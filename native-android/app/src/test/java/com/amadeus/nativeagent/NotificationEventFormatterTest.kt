package com.amadeus.nativeagent

import com.amadeus.nativeagent.model.NotificationEvent
import com.amadeus.nativeagent.service.NotificationEventFormatter
import kotlinx.serialization.json.Json
import org.junit.Assert.assertTrue
import org.junit.Test

class NotificationEventFormatterTest {
    @Test
    fun `formats notification events as normalized json`() {
        val json = NotificationEventFormatter.envelope(
            NotificationEvent(
                eventType = "notification_posted",
                postedAt = 123L,
                packageName = "com.facebook.katana",
                appLabel = "Facebook",
                title = "New message",
                text = "Hello",
                subtext = "Marketplace",
                category = "msg",
                conversation = "Inbox",
                key = "abc",
                isOngoing = false,
            ),
        )

        val payload = Json.parseToJsonElement(json).toString()

        assertTrue(!json.contains("\n"))
        assertTrue(payload.contains("\"event_type\":\"notification_posted\""))
        assertTrue(payload.contains("\"package_name\":\"com.facebook.katana\""))
        assertTrue(payload.contains("\"title\":\"New message\""))
        assertTrue(payload.contains("\"conversation\":\"Inbox\""))
        assertTrue(payload.contains("\"key\":\"abc\""))
    }
}

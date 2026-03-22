package com.amadeus.nativeagent.service

import android.app.Notification
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.util.Log
import com.amadeus.nativeagent.model.NotificationEvent
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

private const val LOG_TAG = "AGENT_NOTIFICATION"

@Serializable
private data class NotificationLogEnvelope(
    @SerialName("event_type")
    val eventType: String,
    @SerialName("posted_at")
    val postedAt: Long,
    @SerialName("package_name")
    val packageName: String,
    @SerialName("app_label")
    val appLabel: String? = null,
    val title: String? = null,
    val text: String? = null,
    val subtext: String? = null,
    val category: String? = null,
    val conversation: String? = null,
    val key: String,
    @SerialName("is_ongoing")
    val isOngoing: Boolean = false,
)

object NotificationEventFormatter {
    private val compactJson = Json {
        prettyPrint = false
        ignoreUnknownKeys = true
    }

    fun envelope(event: NotificationEvent): String {
        return compactJson.encodeToString(
            NotificationLogEnvelope.serializer(),
            NotificationLogEnvelope(
                eventType = event.eventType,
                postedAt = event.postedAt,
                packageName = event.packageName,
                appLabel = event.appLabel,
                title = event.title,
                text = event.text,
                subtext = event.subtext,
                category = event.category,
                conversation = event.conversation,
                key = event.key,
                isOngoing = event.isOngoing,
            ),
        )
    }
}

class AgentNotificationListenerService : NotificationListenerService() {
    override fun onNotificationPosted(sbn: StatusBarNotification) {
        super.onNotificationPosted(sbn)
        emitEvent("notification_posted", sbn)
    }

    override fun onNotificationRemoved(sbn: StatusBarNotification) {
        super.onNotificationRemoved(sbn)
        emitEvent("notification_removed", sbn)
    }

    private fun emitEvent(eventType: String, sbn: StatusBarNotification) {
        val event = NotificationEvent(
            eventType = eventType,
            postedAt = sbn.postTime,
            packageName = sbn.packageName,
            appLabel = appLabelForPackage(sbn.packageName),
            title = bundleText(sbn.notification, Notification.EXTRA_TITLE),
            text = bundleText(sbn.notification, Notification.EXTRA_TEXT),
            subtext = bundleText(sbn.notification, Notification.EXTRA_SUB_TEXT),
            category = sbn.notification.category,
            conversation = bundleText(sbn.notification, Notification.EXTRA_CONVERSATION_TITLE),
            key = sbn.key,
            isOngoing = sbn.isOngoing,
        )
        Log.i(LOG_TAG, NotificationEventFormatter.envelope(event))
    }

    private fun bundleText(notification: Notification, key: String): String? {
        return notification.extras?.getCharSequence(key)?.toString()?.takeIf { it.isNotBlank() }
    }

    private fun appLabelForPackage(packageName: String): String? {
        return runCatching {
            val info = packageManager.getApplicationInfo(packageName, 0)
            packageManager.getApplicationLabel(info).toString()
        }.getOrNull()
    }
}

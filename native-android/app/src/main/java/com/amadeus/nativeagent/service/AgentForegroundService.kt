package com.amadeus.nativeagent.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import androidx.core.app.NotificationCompat
import androidx.lifecycle.LifecycleService
import androidx.lifecycle.lifecycleScope
import com.amadeus.nativeagent.MainActivity
import com.amadeus.nativeagent.R
import com.amadeus.nativeagent.engine.AgentOrchestrator
import com.amadeus.nativeagent.engine.AndroidController
import com.amadeus.nativeagent.model.RunSpec
import com.amadeus.nativeagent.runtime.JsonSupport
import com.amadeus.nativeagent.runtime.NativeAgentRuntime
import java.util.UUID
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch

class AgentForegroundService : LifecycleService() {
    private var activeRunJob: Job? = null

    override fun onCreate() {
        super.onCreate()
        createChannel()
        startForeground(NOTIFICATION_ID, notification("Idle"))
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_START_RUN -> {
                val specJson = intent.getStringExtra(EXTRA_SPEC_JSON).orEmpty()
                val spec = JsonSupport.json.decodeFromString<RunSpec>(specJson)
                activeRunJob?.cancel()
                activeRunJob = lifecycleScope.launch {
                    val runtime = NativeAgentRuntime.get(this@AgentForegroundService)
                    val orchestrator = AgentOrchestrator(
                        context = this@AgentForegroundService,
                        runtime = runtime,
                        controller = AndroidController(this@AgentForegroundService),
                    )
                    val runId = UUID.randomUUID().toString()
                    val record = orchestrator.run(runId, spec)
                    startForeground(NOTIFICATION_ID, notification("${record.status}: ${record.reason}"))
                }
            }

            ACTION_CANCEL_RUN -> {
                activeRunJob?.cancel()
                stopSelf()
            }
        }
        return START_STICKY
    }

    private fun createChannel() {
        val manager = getSystemService(NotificationManager::class.java)
        val channel = NotificationChannel(
            CHANNEL_ID,
            "Native agent runs",
            NotificationManager.IMPORTANCE_LOW,
        )
        manager.createNotificationChannel(channel)
    }

    private fun notification(text: String): Notification {
        val pendingIntent = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE,
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle(getString(R.string.app_name))
            .setContentText(text)
            .setSmallIcon(android.R.drawable.ic_media_play)
            .setContentIntent(pendingIntent)
            .build()
    }

    companion object {
        private const val CHANNEL_ID = "agent_runs"
        private const val NOTIFICATION_ID = 2002
        private const val ACTION_START_RUN = "com.amadeus.nativeagent.action.START_RUN"
        private const val ACTION_CANCEL_RUN = "com.amadeus.nativeagent.action.CANCEL_RUN"
        private const val EXTRA_SPEC_JSON = "spec_json"
        private const val EXTRA_RUN_ID = "run_id"

        fun startIntent(context: Context, specJson: String): Intent =
            Intent(context, AgentForegroundService::class.java).apply {
                action = ACTION_START_RUN
                putExtra(EXTRA_SPEC_JSON, specJson)
            }

        fun cancelIntent(context: Context, runId: String): Intent =
            Intent(context, AgentForegroundService::class.java).apply {
                action = ACTION_CANCEL_RUN
                putExtra(EXTRA_RUN_ID, runId)
            }
    }
}

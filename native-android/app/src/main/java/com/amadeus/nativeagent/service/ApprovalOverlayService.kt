package com.amadeus.nativeagent.service

import android.app.Service
import android.content.Context
import android.content.Intent
import android.graphics.PixelFormat
import android.os.IBinder
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import androidx.core.content.getSystemService
import android.view.View.IMPORTANT_FOR_ACCESSIBILITY_YES
import com.amadeus.nativeagent.runtime.NativeAgentRuntime
import com.amadeus.nativeagent.model.ApprovalRequest

class ApprovalOverlayService : Service() {
    private var overlayView: View? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val request = ApprovalRequest(
            runId = intent?.getStringExtra(EXTRA_RUN_ID).orEmpty(),
            requestId = intent?.getStringExtra(EXTRA_REQUEST_ID).orEmpty(),
            title = intent?.getStringExtra(EXTRA_TITLE).orEmpty(),
            message = intent?.getStringExtra(EXTRA_MESSAGE).orEmpty(),
            actionLabel = intent?.getStringExtra(EXTRA_ACTION_LABEL).orEmpty(),
            alternativeLabel = intent?.getStringExtra(EXTRA_ALT_LABEL),
        )
        showOverlay(request)
        return START_NOT_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        removeOverlay()
        super.onDestroy()
    }

    private fun showOverlay(request: ApprovalRequest) {
        removeOverlay()
        val windowManager = getSystemService<WindowManager>() ?: return
        val runtime = NativeAgentRuntime.get(this)
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(0xEE111827.toInt())
            setPadding(32, 32, 32, 32)
            importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_YES
            isFocusable = true
            isClickable = true
        }
        val titleView = TextView(this).apply {
            text = request.title
            setTextColor(0xFFFFFFFF.toInt())
            textSize = 18f
            importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_YES
        }
        val messageView = TextView(this).apply {
            text = request.message
            setTextColor(0xFFE5E7EB.toInt())
            textSize = 14f
            importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_YES
        }
        val allow = Button(this).apply {
            text = "Allow this action"
            contentDescription = "Allow this action"
            importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_YES
            isFocusable = true
            setOnClickListener {
                runtime.approvePendingAction(request.runId, "allow")
                stopSelf()
            }
        }
        val deny = Button(this).apply {
            text = request.alternativeLabel ?: "Deny"
            contentDescription = request.alternativeLabel ?: "Deny"
            importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_YES
            isFocusable = true
            setOnClickListener {
                runtime.approvePendingAction(request.runId, "deny")
                stopSelf()
            }
        }
        val manual = Button(this).apply {
            text = "Take over manually"
            contentDescription = "Take over manually"
            importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_YES
            isFocusable = true
            setOnClickListener {
                runtime.approvePendingAction(request.runId, "manual")
                stopSelf()
            }
        }
        layout.addView(titleView)
        layout.addView(messageView)
        layout.addView(allow)
        layout.addView(deny)
        layout.addView(manual)
        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
            PixelFormat.TRANSLUCENT,
        ).apply {
            gravity = Gravity.TOP
        }
        windowManager.addView(layout, params)
        overlayView = layout
    }

    private fun removeOverlay() {
        val windowManager = getSystemService<WindowManager>() ?: return
        overlayView?.let { view ->
            runCatching { windowManager.removeView(view) }
        }
        overlayView = null
    }

    companion object {
        private const val EXTRA_RUN_ID = "run_id"
        private const val EXTRA_REQUEST_ID = "request_id"
        private const val EXTRA_TITLE = "title"
        private const val EXTRA_MESSAGE = "message"
        private const val EXTRA_ACTION_LABEL = "action_label"
        private const val EXTRA_ALT_LABEL = "alt_label"

        fun startIntent(context: Context, request: ApprovalRequest): Intent =
            Intent(context, ApprovalOverlayService::class.java).apply {
                putExtra(EXTRA_RUN_ID, request.runId)
                putExtra(EXTRA_REQUEST_ID, request.requestId)
                putExtra(EXTRA_TITLE, request.title)
                putExtra(EXTRA_MESSAGE, request.message)
                putExtra(EXTRA_ACTION_LABEL, request.actionLabel)
                putExtra(EXTRA_ALT_LABEL, request.alternativeLabel)
            }
    }
}

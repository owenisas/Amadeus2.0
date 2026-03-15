package com.amadeus.nativeagent.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.PixelFormat
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import com.amadeus.nativeagent.MainActivity
import com.amadeus.nativeagent.R
import java.io.File
import java.io.FileOutputStream

class ScreenCaptureService : Service() {
    private var mediaProjection: MediaProjection? = null
    private var imageReader: ImageReader? = null
    private var virtualDisplay: VirtualDisplay? = null

    override fun onCreate() {
        super.onCreate()
        instance = this
        createChannel()
        startForeground(NOTIFICATION_ID, notification())
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_INIT_PROJECTION -> {
                val resultCode = intent.getIntExtra(EXTRA_RESULT_CODE, 0)
                val data = if (Build.VERSION.SDK_INT >= 33) {
                    intent.getParcelableExtra(EXTRA_RESULT_DATA, Intent::class.java)
                } else {
                    @Suppress("DEPRECATION")
                    intent.getParcelableExtra(EXTRA_RESULT_DATA)
                }
                if (data != null) {
                    initializeProjection(resultCode, data)
                }
            }

            ACTION_STOP -> stopSelf()
        }
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        virtualDisplay?.release()
        imageReader?.close()
        mediaProjection?.stop()
        if (instance === this) {
            instance = null
        }
        super.onDestroy()
    }

    fun isProjectionReady(): Boolean = mediaProjection != null && imageReader != null

    fun captureToFile(targetDir: File): CaptureResult {
        val reader = imageReader ?: error("MediaProjection is not initialized.")
        val image = waitForImage(reader) ?: error("No image available from MediaProjection.")
        image.use {
            val plane = image.planes.first()
            val buffer = plane.buffer
            val width = image.width
            val height = image.height
            val pixelStride = plane.pixelStride
            val rowStride = plane.rowStride
            val rowPadding = rowStride - pixelStride * width
            val bitmap = Bitmap.createBitmap(
                width + rowPadding / pixelStride,
                height,
                Bitmap.Config.ARGB_8888,
            )
            bitmap.copyPixelsFromBuffer(buffer)
            val cropped = Bitmap.createBitmap(bitmap, 0, 0, width, height)
            val file = File(targetDir, "${System.currentTimeMillis()}.png")
            FileOutputStream(file).use { output ->
                cropped.compress(Bitmap.CompressFormat.PNG, 100, output)
            }
            bitmap.recycle()
            cropped.recycle()
            return CaptureResult(file)
        }
    }

    private fun initializeProjection(resultCode: Int, data: Intent) {
        val metrics = resources.displayMetrics
        imageReader?.close()
        virtualDisplay?.release()
        val projectionManager = getSystemService(MediaProjectionManager::class.java)
        mediaProjection = projectionManager.getMediaProjection(resultCode, data)
        imageReader = ImageReader.newInstance(
            metrics.widthPixels,
            metrics.heightPixels,
            PixelFormat.RGBA_8888,
            3,
        )
        virtualDisplay = mediaProjection?.createVirtualDisplay(
            "native-agent-capture",
            metrics.widthPixels,
            metrics.heightPixels,
            metrics.densityDpi,
            DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
            imageReader?.surface,
            null,
            null,
        )
    }

    private fun waitForImage(reader: ImageReader): android.media.Image? {
        repeat(20) {
            reader.acquireLatestImage()?.let { return it }
            Thread.sleep(80)
        }
        return null
    }

    private fun createChannel() {
        val manager = getSystemService(NotificationManager::class.java)
        val channel = NotificationChannel(
            CHANNEL_ID,
            "Native agent capture",
            NotificationManager.IMPORTANCE_LOW,
        )
        manager.createNotificationChannel(channel)
    }

    private fun notification(): Notification {
        val intent = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE,
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle(getString(R.string.app_name))
            .setContentText("Screen capture service is ready.")
            .setSmallIcon(android.R.drawable.ic_menu_camera)
            .setContentIntent(intent)
            .build()
    }

    data class CaptureResult(val file: File)

    companion object {
        private const val CHANNEL_ID = "capture_service"
        private const val NOTIFICATION_ID = 2001
        private const val ACTION_INIT_PROJECTION = "com.amadeus.nativeagent.action.INIT_PROJECTION"
        private const val ACTION_STOP = "com.amadeus.nativeagent.action.STOP_CAPTURE"
        private const val EXTRA_RESULT_CODE = "result_code"
        private const val EXTRA_RESULT_DATA = "result_data"

        @Volatile
        var instance: ScreenCaptureService? = null
            private set

        fun initIntent(context: Context, resultCode: Int, data: Intent): Intent =
            Intent(context, ScreenCaptureService::class.java).apply {
                action = ACTION_INIT_PROJECTION
                putExtra(EXTRA_RESULT_CODE, resultCode)
                putExtra(EXTRA_RESULT_DATA, data)
            }
    }
}

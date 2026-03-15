package com.amadeus.nativeagent

import android.app.Application
import com.amadeus.nativeagent.runtime.NativeAgentRuntime

class NativeAgentApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        NativeAgentRuntime.initialize(this)
    }
}

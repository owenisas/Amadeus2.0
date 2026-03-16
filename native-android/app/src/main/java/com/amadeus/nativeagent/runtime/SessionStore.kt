package com.amadeus.nativeagent.runtime

import com.amadeus.nativeagent.model.RunRecord
import com.amadeus.nativeagent.model.RuntimeSnapshot
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update

class SessionStore {
    private val state = MutableStateFlow(RuntimeSnapshot())

    fun snapshot(): StateFlow<RuntimeSnapshot> = state

    fun updatePermissions(
        projectionGranted: Boolean,
        overlayGranted: Boolean,
        accessibilityGranted: Boolean,
    ) {
        state.update {
            it.copy(
                projectionGranted = projectionGranted,
                overlayGranted = overlayGranted,
                accessibilityGranted = accessibilityGranted,
            )
        }
    }

    fun updateProvider(providerLabel: String) {
        state.update { it.copy(providerLabel = providerLabel) }
    }

    fun setProjectionGranted(projectionGranted: Boolean) {
        state.update { it.copy(projectionGranted = projectionGranted) }
    }

    fun setSkills(skills: List<String>) {
        state.update { it.copy(skills = skills) }
    }

    fun clearDebugLines() {
        state.update { it.copy(debugLines = emptyList()) }
    }

    fun appendDebugLine(line: String) {
        state.update { snapshot ->
            snapshot.copy(debugLines = (snapshot.debugLines + line).takeLast(80))
        }
    }

    fun setCurrentRun(run: RunRecord?) {
        state.update { snapshot ->
            val history = buildList {
                run?.let { add(it) }
                addAll(snapshot.runHistory.filterNot { item -> item.runId == run?.runId })
            }.take(20)
            snapshot.copy(currentRun = run, runHistory = history)
        }
    }
}

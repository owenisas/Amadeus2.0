package com.amadeus.nativeagent.runtime

import com.amadeus.nativeagent.model.ApprovalRequest
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

class ApprovalCoordinator {
    private val pendingFlow = MutableStateFlow<ApprovalRequest?>(null)
    private val deferredByRunId = mutableMapOf<String, CompletableDeferred<String>>()

    fun pending(): StateFlow<ApprovalRequest?> = pendingFlow

    fun requestApproval(request: ApprovalRequest): CompletableDeferred<String> {
        val deferred = CompletableDeferred<String>()
        deferredByRunId[request.runId] = deferred
        pendingFlow.value = request
        return deferred
    }

    fun resolve(runId: String, action: String) {
        deferredByRunId.remove(runId)?.complete(action)
        if (pendingFlow.value?.runId == runId) {
            pendingFlow.value = null
        }
    }
}

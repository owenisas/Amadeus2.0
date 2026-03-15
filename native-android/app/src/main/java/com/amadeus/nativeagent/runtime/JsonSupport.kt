package com.amadeus.nativeagent.runtime

import kotlinx.serialization.json.Json

object JsonSupport {
    val json = Json {
        prettyPrint = true
        ignoreUnknownKeys = true
    }
}

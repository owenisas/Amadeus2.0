package com.amadeus.nativeagent.runtime

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

private val Context.dataStore by preferencesDataStore(name = "native_agent_settings")

class SettingsRepository(private val context: Context) {
    private val geminiApiKeyKey = stringPreferencesKey("gemini_api_key")
    private val geminiModelKey = stringPreferencesKey("gemini_model")
    private val yoloModeKey = booleanPreferencesKey("yolo_mode")

    val geminiApiKey: Flow<String> = context.dataStore.data.map { it[geminiApiKeyKey].orEmpty() }
    val geminiModel: Flow<String> = context.dataStore.data.map { it[geminiModelKey] ?: "gemini-3.1-pro-preview" }
    val yoloMode: Flow<Boolean> = context.dataStore.data.map { it[yoloModeKey] ?: false }

    suspend fun setGeminiApiKey(value: String) {
        context.dataStore.edit { prefs -> prefs[geminiApiKeyKey] = value.trim() }
    }

    suspend fun setGeminiModel(value: String) {
        context.dataStore.edit { prefs -> prefs[geminiModelKey] = value.trim() }
    }

    suspend fun setYoloMode(value: Boolean) {
        context.dataStore.edit { prefs -> prefs[yoloModeKey] = value }
    }
}

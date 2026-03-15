package com.amadeus.nativeagent.runtime

import android.content.Context
import com.amadeus.nativeagent.model.AppStateRecord
import com.amadeus.nativeagent.model.CapturedScreen
import com.amadeus.nativeagent.model.RunActionRecord
import com.amadeus.nativeagent.model.ScreenRecord
import com.amadeus.nativeagent.model.SelectorRecord
import com.amadeus.nativeagent.model.SkillBundle
import com.amadeus.nativeagent.model.UiComponent
import java.io.File
import java.security.MessageDigest
import kotlinx.serialization.Serializable

class SkillRepository(private val context: Context) {
    private val rootDir = File(context.filesDir, "native_agent")
    private val skillsDir = File(rootDir, "skills")
    private val appSkillsDir = File(skillsDir, "apps")
    private val systemSkillsDir = File(skillsDir, "system")
    private val runsDir = File(rootDir, "runs")

    init {
        ensureBootstrapped()
    }

    fun runsDirectory(): File {
        runsDir.mkdirs()
        return runsDir
    }

    fun loadSystemSkill(): String {
        val file = File(systemSkillsDir, "android_navigation/SKILL.md")
        return file.readText()
    }

    fun listSkillIds(): List<String> =
        appSkillsDir.listFiles()
            ?.filter { it.isDirectory }
            ?.map { it.name }
            ?.sorted()
            .orEmpty()

    fun readSkillFile(appId: String, fileName: String): String =
        File(File(appSkillsDir, appId), fileName).readText()

    fun loadSkill(appId: String): SkillBundle {
        val appDir = File(appSkillsDir, appId)
        val instructions = File(appDir, "SKILL.md").readText()
        val screens = readScreens(File(appDir, "screens.json"))
        val selectors = readSelectors(File(appDir, "selectors.json"))
        val state = readState(File(appDir, "state.json"))
        val memory = File(appDir, "memory.md").takeIf { it.exists() }?.readText().orEmpty()
        return SkillBundle(
            appId = appId,
            instructions = instructions,
            screens = screens,
            selectors = selectors,
            state = state,
            memory = memory,
        )
    }

    fun recordObservation(appId: String, screen: CapturedScreen) {
        val appDir = ensureAppDir(appId)
        val screens = readScreens(File(appDir, "screens.json")).toMutableMap()
        val screenId = screenId(screen)
        screens[screenId] = ScreenRecord(
            screenId = screenId,
            packageName = screen.packageName,
            classNameHint = screen.classNameHint,
            visibleText = screen.visibleText.take(20),
            clickableText = screen.clickableText.take(20),
            components = screen.components.take(20),
        )
        writeScreens(File(appDir, "screens.json"), screens)
    }

    fun recordTransition(
        appId: String,
        before: CapturedScreen,
        after: CapturedScreen,
        actionHistory: List<RunActionRecord>,
        status: String,
        reason: String,
        transitionConfidence: Float,
    ) {
        val appDir = ensureAppDir(appId)
        val state = AppStateRecord(
            status = status,
            reason = reason,
            lastSuccessfulScreen = screenId(after),
            lastActionChain = actionHistory.takeLast(8).map { it.action },
            failureCount = 0,
            transitionConfidence = transitionConfidence,
            lastKnownResultScreen = screenId(after),
            searchTransitions = mapOf(screenId(before) to screenId(after)),
        )
        File(appDir, "state.json").writeText(JsonSupport.json.encodeToString(AppStateRecord.serializer(), state))
    }

    fun appendMemory(appId: String, line: String) {
        val appDir = ensureAppDir(appId)
        val file = File(appDir, "memory.md")
        val prefix = if (file.exists()) "\n" else ""
        file.appendText("$prefix- $line\n")
    }

    fun saveSelectors(appId: String, selectors: List<SelectorRecord>) {
        val appDir = ensureAppDir(appId)
        File(appDir, "selectors.json").writeText(
            JsonSupport.json.encodeToString(SelectorFile.serializer(), SelectorFile(selectors))
        )
    }

    fun mergeDynamicSelectors(appId: String, components: List<UiComponent>, screen: CapturedScreen) {
        val current = loadSkill(appId).selectors.toMutableList()
        val screenId = screenId(screen)
        val knownKeys = current.map { "${it.label}|${it.resourceId}|${it.screenId}" }.toMutableSet()
        components
            .filter { it.label.isNotBlank() }
            .take(10)
            .forEach { component ->
                val selector = SelectorRecord(
                    label = component.label,
                    packageName = component.packageName.ifBlank { screen.packageName },
                    screenId = screenId,
                    reason = "Observed dynamic component from native accessibility hierarchy.",
                    anchorText = screen.visibleText.take(6),
                    resourceId = component.resourceId.ifBlank { null },
                    className = component.className.ifBlank { null },
                    componentType = component.componentType,
                    searchRelated = component.searchRelated,
                    targetBox = component.targetBox,
                )
                val key = "${selector.label}|${selector.resourceId}|${selector.screenId}"
                if (key !in knownKeys) {
                    knownKeys += key
                    current += selector
                }
            }
        saveSelectors(appId, current)
    }

    fun ensureAppDir(appId: String): File {
        val appDir = File(appSkillsDir, appId)
        appDir.mkdirs()
        return appDir
    }

    private fun ensureBootstrapped() {
        rootDir.mkdirs()
        if (File(systemSkillsDir, "android_navigation/SKILL.md").exists()) {
            return
        }
        copyAssetTree("bootstrap_skills", skillsDir)
    }

    private fun copyAssetTree(assetPath: String, targetDir: File) {
        targetDir.mkdirs()
        val children = context.assets.list(assetPath).orEmpty()
        if (children.isEmpty()) {
            context.assets.open(assetPath).use { input ->
                val outputFile = File(targetDir, assetPath.substringAfterLast("/"))
                outputFile.outputStream().use { output -> input.copyTo(output) }
            }
            return
        }
        children.forEach { child ->
            val childPath = "$assetPath/$child"
            val grandChildren = context.assets.list(childPath).orEmpty()
            if (grandChildren.isEmpty()) {
                context.assets.open(childPath).use { input ->
                    val outputFile = File(targetDir, child)
                    outputFile.parentFile?.mkdirs()
                    outputFile.outputStream().use { output -> input.copyTo(output) }
                }
            } else {
                copyAssetTree(childPath, File(targetDir, child))
            }
        }
    }

    private fun readScreens(file: File): Map<String, ScreenRecord> {
        if (!file.exists()) {
            return emptyMap()
        }
        val payload = JsonSupport.json.decodeFromString(ScreensFile.serializer(), file.readText())
        return payload.screens
    }

    private fun writeScreens(file: File, screens: Map<String, ScreenRecord>) {
        file.writeText(JsonSupport.json.encodeToString(ScreensFile.serializer(), ScreensFile(screens)))
    }

    private fun readSelectors(file: File): List<SelectorRecord> {
        if (!file.exists()) {
            return emptyList()
        }
        return JsonSupport.json.decodeFromString(SelectorFile.serializer(), file.readText()).selectors
    }

    private fun readState(file: File): AppStateRecord {
        if (!file.exists()) {
            return AppStateRecord()
        }
        return JsonSupport.json.decodeFromString(AppStateRecord.serializer(), file.readText())
    }

    fun screenId(screen: CapturedScreen): String {
        val digest = MessageDigest.getInstance("SHA-256")
            .digest(screen.visibleText.joinToString("\n").toByteArray())
            .joinToString("") { "%02x".format(it) }
            .take(16)
        val classHint = screen.classNameHint?.substringAfterLast('.')?.lowercase().orEmpty()
        return listOf(screen.packageName.replace('.', '-'), classHint, digest)
            .filter { it.isNotBlank() }
            .joinToString("-")
    }

    @Serializable
    private data class SelectorFile(val selectors: List<SelectorRecord> = emptyList())

    @Serializable
    private data class ScreensFile(val screens: Map<String, ScreenRecord> = emptyMap())
}

package com.amadeus.nativeagent

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.amadeus.nativeagent.model.RunSpec
import com.amadeus.nativeagent.runtime.JsonSupport
import com.amadeus.nativeagent.runtime.NativeAgentRuntime
import com.amadeus.nativeagent.service.ScreenCaptureService

class MainActivity : ComponentActivity() {
    private val viewModel by viewModels<NativeAgentViewModel>()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                NativeAgentApp(viewModel)
            }
        }
    }
}

@Composable
private fun NativeAgentApp(viewModel: NativeAgentViewModel) {
    val context = LocalContext.current
    val runtime = remember { NativeAgentRuntime.get(context) }
    val snapshot by viewModel.snapshot.collectAsStateWithLifecycle()
    val apiKey by viewModel.apiKey.collectAsStateWithLifecycle()
    val model by viewModel.model.collectAsStateWithLifecycle()
    val yoloMode by viewModel.yoloMode.collectAsStateWithLifecycle()
    var selectedTab by rememberSaveable { mutableIntStateOf(0) }

    val projectionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.StartActivityForResult(),
    ) { result ->
        if (result.resultCode != 0 && result.data != null) {
            ContextCompat.startForegroundService(
                context,
                ScreenCaptureService.initIntent(context, result.resultCode, result.data!!),
            )
            viewModel.refreshPermissions()
        }
    }

    LaunchedEffect(Unit) {
        viewModel.refreshPermissions()
    }

    Column(modifier = Modifier.fillMaxSize().padding(16.dp)) {
        TabRow(selectedTabIndex = selectedTab) {
            listOf("Home", "Run Composer", "Run Monitor", "Skills", "Runs").forEachIndexed { index, title ->
                Tab(selected = selectedTab == index, onClick = { selectedTab = index }, text = { Text(title) })
            }
        }
        Spacer(modifier = Modifier.height(16.dp))
        when (selectedTab) {
            0 -> HomeScreen(
                apiKey = apiKey,
                model = model,
                yoloMode = yoloMode,
                snapshot = snapshot,
                onApiKeyChange = viewModel::setApiKey,
                onModelChange = viewModel::setModel,
                onYoloModeChange = viewModel::setYoloMode,
                onRequestAccessibility = {
                    context.startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                },
                onRequestOverlay = {
                    context.startActivity(
                        Intent(
                            Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                            Uri.parse("package:${context.packageName}"),
                        ).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    )
                },
                onRequestProjection = {
                    val manager = context.getSystemService(android.media.projection.MediaProjectionManager::class.java)
                    projectionLauncher.launch(manager.createScreenCaptureIntent())
                },
            )

            1 -> RunComposerScreen(
                runtime = runtime,
                yoloMode = yoloMode,
                onYoloModeChange = viewModel::setYoloMode,
                onStartRun = { appId, goal, maxSteps, exploration, runYoloMode ->
                    val spec = RunSpec(
                        appId = appId,
                        goal = goal,
                        maxSteps = maxSteps,
                        explorationEnabled = exploration,
                        yoloMode = runYoloMode,
                    )
                    runtime.startRun(JsonSupport.json.encodeToString(RunSpec.serializer(), spec))
                },
            )

            2 -> RunMonitorScreen(snapshot = snapshot)
            3 -> SkillsScreen(runtime = runtime)
            4 -> RunsScreen(snapshot = snapshot)
        }
    }
}

@Composable
private fun HomeScreen(
    apiKey: String,
    model: String,
    yoloMode: Boolean,
    snapshot: com.amadeus.nativeagent.model.RuntimeSnapshot,
    onApiKeyChange: (String) -> Unit,
    onModelChange: (String) -> Unit,
    onYoloModeChange: (Boolean) -> Unit,
    onRequestAccessibility: () -> Unit,
    onRequestOverlay: () -> Unit,
    onRequestProjection: () -> Unit,
) {
    LazyColumn(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Runtime status", fontWeight = FontWeight.Bold)
                    Text("Provider: ${snapshot.providerLabel}")
                    Text("Accessibility: ${if (snapshot.accessibilityGranted) "ready" else "missing"}")
                    Text("Overlay: ${if (snapshot.overlayGranted) "ready" else "missing"}")
                    Text("Screen capture: ${if (snapshot.projectionGranted) "ready" else "missing"}")
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Button(onClick = onRequestAccessibility) { Text("Accessibility settings") }
                        Button(onClick = onRequestOverlay) { Text("Overlay permission") }
                    }
                    Button(onClick = onRequestProjection) { Text("Grant screen capture") }
                }
            }
        }
        item {
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Gemini provider", fontWeight = FontWeight.Bold)
                    OutlinedTextField(
                        value = apiKey,
                        onValueChange = onApiKeyChange,
                        label = { Text("Gemini API key") },
                        modifier = Modifier.fillMaxWidth(),
                    )
                    OutlinedTextField(
                        value = model,
                        onValueChange = onModelChange,
                        label = { Text("Gemini model") },
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            }
        }
        item {
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Approval mode", fontWeight = FontWeight.Bold)
                    Button(onClick = { onYoloModeChange(!yoloMode) }) {
                        Text("YOLO mode: ${if (yoloMode) "enabled" else "disabled"}")
                    }
                    if (yoloMode) {
                        Text(
                            "Notice: YOLO mode bypasses native approval overlays and auto-continues through approval surfaces when it finds a stable action. Purchase and other local safety blocks still remain active.",
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun RunComposerScreen(
    runtime: NativeAgentRuntime,
    yoloMode: Boolean,
    onYoloModeChange: (Boolean) -> Unit,
    onStartRun: (String, String, Int, Boolean, Boolean) -> Unit,
) {
    var selectedAppId by rememberSaveable { mutableStateOf(runtime.appRegistry.apps.first().id) }
    var goal by rememberSaveable { mutableStateOf(runtime.appRegistry.apps.first().defaultGoalHint) }
    var maxSteps by rememberSaveable { mutableStateOf("12") }
    var explorationEnabled by rememberSaveable { mutableStateOf(true) }

    LazyColumn(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            Text("Choose target app", fontWeight = FontWeight.Bold)
            runtime.appRegistry.apps.forEach { app ->
                Button(
                    onClick = {
                        selectedAppId = app.id
                        goal = app.defaultGoalHint
                    },
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text(if (selectedAppId == app.id) "Selected: ${app.title}" else app.title)
                }
            }
        }
        item {
            OutlinedTextField(
                value = goal,
                onValueChange = { goal = it },
                label = { Text("Goal") },
                modifier = Modifier.fillMaxWidth(),
            )
        }
        item {
            OutlinedTextField(
                value = maxSteps,
                onValueChange = { maxSteps = it.filter(Char::isDigit) },
                label = { Text("Max steps") },
                modifier = Modifier.fillMaxWidth(),
            )
        }
        item {
            Button(onClick = { explorationEnabled = !explorationEnabled }) {
                Text("Exploration: ${if (explorationEnabled) "enabled" else "disabled"}")
            }
        }
        item {
            Button(onClick = { onYoloModeChange(!yoloMode) }) {
                Text("Approval mode: ${if (yoloMode) "YOLO" else "manual approval"}")
            }
        }
        if (yoloMode) {
            item {
                Text("Notice: this run will bypass approval overlays and continue automatically when a stable approval action is available.")
            }
        }
        item {
            Button(
                onClick = { onStartRun(selectedAppId, goal, maxSteps.toIntOrNull() ?: 12, explorationEnabled, yoloMode) },
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text("Start run")
            }
        }
    }
}

@Composable
private fun RunMonitorScreen(snapshot: com.amadeus.nativeagent.model.RuntimeSnapshot) {
    val currentRun = snapshot.currentRun
    LazyColumn(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("Current run", fontWeight = FontWeight.Bold)
                    Text(currentRun?.status ?: "No active run")
                    Text(currentRun?.reason ?: "Start a run from Run Composer.")
                    currentRun?.let {
                        it.notice?.let { notice -> Text(notice) }
                        Text("Goal: ${it.goal}")
                        Text("Steps: ${it.stepCount}")
                        Text("Run dir: ${it.runDir}")
                    }
                }
            }
        }
        currentRun?.let { run ->
            item {
                val screenshot = run.runDir.let { dir ->
                    java.io.File(dir).listFiles()
                        ?.filter { it.extension == "png" }
                        ?.maxByOrNull { it.lastModified() }
                }
                screenshot?.let { file ->
                    android.graphics.BitmapFactory.decodeFile(file.absolutePath)?.let { bitmap ->
                        Image(bitmap = bitmap.asImageBitmap(), contentDescription = "Latest run screenshot", modifier = Modifier.fillMaxWidth())
                    }
                }
            }
        }
        if (snapshot.debugLines.isNotEmpty()) {
            item {
                Card(modifier = Modifier.fillMaxWidth()) {
                    Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text("Debug trace", fontWeight = FontWeight.Bold)
                        snapshot.debugLines.takeLast(20).forEach { line ->
                            Text(line)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun SkillsScreen(runtime: NativeAgentRuntime) {
    val skills = remember { runtime.skillRepository.listSkillIds() }
    LazyColumn(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        items(skills) { skillId ->
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(skillId, fontWeight = FontWeight.Bold)
                    Text(runtime.skillRepository.readSkillFile(skillId, "SKILL.md"))
                }
            }
        }
    }
}

@Composable
private fun RunsScreen(snapshot: com.amadeus.nativeagent.model.RuntimeSnapshot) {
    LazyColumn(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        items(snapshot.runHistory) { run ->
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(modifier = Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("${run.appId}: ${run.status}", fontWeight = FontWeight.Bold)
                    Text(run.reason)
                    run.notice?.let { notice -> Text(notice) }
                    Text("Steps: ${run.stepCount}")
                    Text("Run dir: ${run.runDir}")
                }
            }
        }
    }
}

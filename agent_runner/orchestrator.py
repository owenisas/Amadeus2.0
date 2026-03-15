from __future__ import annotations

from pathlib import Path

from agent_runner.android_adapter import AndroidAdapter
from agent_runner.agent_tools import AgentToolExecutor
from agent_runner.models import ActionRecord, RunContext, RunResult, ScreenState, VisionDecision
from agent_runner.safety import detect_manual_login_required, evaluate_decision
from agent_runner.skill_manager import SkillManager
from agent_runner.utils import describe_state_signature, ensure_directory, timestamp_slug
from agent_runner.vision_agent import VisionAgent


class Orchestrator:
    def __init__(
        self,
        *,
        android_adapter: AndroidAdapter,
        tool_executor: AgentToolExecutor,
        vision_agent: VisionAgent,
        skill_manager: SkillManager,
        runs_dir: Path,
    ) -> None:
        self.android_adapter = android_adapter
        self.tool_executor = tool_executor
        self.vision_agent = vision_agent
        self.skill_manager = skill_manager
        self.runs_dir = runs_dir

    def run(self, context: RunContext) -> RunResult:
        with self.android_adapter.session_lock():
            try:
                run_dir = ensure_directory(self.runs_dir / f"{context.app.name}-{timestamp_slug()}")
                context.run_dir = run_dir
                bundle = self.skill_manager.load_skill(context.app)
                system_instruction = self.skill_manager.load_system_skill()

                if not self.android_adapter.is_package_installed(context.app.package_name):
                    self.skill_manager.update_run_state(
                        bundle,
                        status="error",
                        reason="App is not installed on the emulator.",
                        last_screen_id=None,
                        action_history=[],
                        failure_count=0,
                    )
                    return RunResult(
                        status="error",
                        reason=f"{context.app.package_name} is not installed on {self.android_adapter.device_serial}.",
                        steps=0,
                        run_dir=run_dir,
                    )

                self.android_adapter.launch_app(context.app.package_name, context.app.launch_activity)

                last_screen_id: str | None = None
                failure_count = 0
                state = self.android_adapter.capture_state(run_dir)
                last_state: ScreenState | None = state

                for step in range(1, context.max_steps + 1):
                    last_state = state

                    if detect_manual_login_required(context.app, state):
                        reason = "Manual login required before automation can continue."
                        self.skill_manager.update_after_observation(bundle, state, None)
                        self.skill_manager.update_run_state(
                            bundle,
                            status="manual_login_required",
                            reason=reason,
                            last_screen_id=last_screen_id,
                            action_history=[item.to_dict() for item in context.action_history],
                            failure_count=failure_count,
                        )
                        return RunResult(
                            status="manual_login_required",
                            reason=reason,
                            steps=step,
                            run_dir=run_dir,
                            last_state=state,
                        )

                    decision = self.vision_agent.decide(
                        goal=context.goal,
                        state=state,
                        skill=bundle,
                        system_instruction=system_instruction,
                        action_history=[item.to_dict() for item in context.action_history],
                        available_tools=[tool.to_dict() for tool in self.tool_executor.list_tools()],
                    )
                    last_screen_id = self.skill_manager.update_after_observation(bundle, state, decision)

                    verdict = evaluate_decision(context.app, state, decision)
                    if not verdict.allowed:
                        context.action_history.append(
                            ActionRecord(
                                step=step,
                                action=decision.next_action,
                                reason=verdict.reason,
                                allowed=verdict.allowed,
                                package_name=state.package_name,
                                activity_name=state.activity_name,
                                tool_name=decision.tool_name,
                                tool_arguments=decision.tool_arguments,
                            )
                        )
                        self.skill_manager.update_run_state(
                            bundle,
                            status="blocked",
                            reason=verdict.reason,
                            last_screen_id=last_screen_id,
                            action_history=[item.to_dict() for item in context.action_history],
                            failure_count=failure_count,
                        )
                        return RunResult(
                            status="blocked",
                            reason=verdict.reason,
                            steps=step,
                            run_dir=run_dir,
                            last_state=state,
                        )

                    action_record = ActionRecord(
                        step=step,
                        action=decision.next_action,
                        reason=verdict.reason,
                        allowed=True,
                        package_name=state.package_name,
                        activity_name=state.activity_name,
                        tool_name=decision.tool_name,
                        tool_arguments=decision.tool_arguments,
                    )

                    if decision.next_action == "stop":
                        status = "approval_required" if decision.requires_user_approval else "completed"
                        context.action_history.append(action_record)
                        self.skill_manager.update_run_state(
                            bundle,
                            status=status,
                            reason=decision.reason,
                            last_screen_id=last_screen_id,
                            action_history=[item.to_dict() for item in context.action_history],
                            failure_count=failure_count,
                        )
                        return RunResult(
                            status=status,
                            reason=decision.reason,
                            steps=step,
                            run_dir=run_dir,
                            last_state=state,
                        )

                    if decision.next_action == "tool":
                        tool_result = self.tool_executor.execute(
                            tool_name=decision.tool_name or "",
                            arguments=decision.tool_arguments,
                            run_dir=run_dir,
                            current_state=state,
                            app=context.app,
                            skill=bundle,
                        )
                        action_record.tool_output = tool_result.output
                        context.action_history.append(action_record)
                        if not tool_result.ok:
                            reason = tool_result.error or f"Tool '{tool_result.tool_name}' failed."
                            self.skill_manager.update_run_state(
                                bundle,
                                status="error",
                                reason=reason,
                                last_screen_id=last_screen_id,
                                action_history=[item.to_dict() for item in context.action_history],
                                failure_count=failure_count,
                            )
                            return RunResult(
                                status="error",
                                reason=reason,
                                steps=step,
                                run_dir=run_dir,
                                last_state=state,
                            )
                        next_state = state
                        if tool_result.captured_state is not None:
                            next_state = tool_result.captured_state
                        elif tool_result.refresh_state:
                            next_state = self.android_adapter.capture_state(run_dir)
                    else:
                        self.android_adapter.perform(decision, state)
                        next_state = self.android_adapter.capture_state(run_dir)
                        context.action_history.append(action_record)
                    self.skill_manager.update_after_transition(
                        bundle,
                        before_state=state,
                        decision=decision,
                        after_state=next_state,
                    )
                    before_signature = describe_state_signature(state)
                    current_signature = describe_state_signature(next_state)
                    if before_signature == current_signature and decision.next_action != "wait":
                        failure_count += 1
                    else:
                        failure_count = 0
                    state = next_state

                    if failure_count >= 3:
                        reason = "Screen did not change after repeated actions."
                        self.skill_manager.update_run_state(
                            bundle,
                            status="stalled",
                            reason=reason,
                            last_screen_id=last_screen_id,
                            action_history=[item.to_dict() for item in context.action_history],
                            failure_count=failure_count,
                        )
                        return RunResult(
                            status="stalled",
                            reason=reason,
                            steps=step,
                            run_dir=run_dir,
                            last_state=next_state,
                        )

                reason = "Max steps reached."
                self.skill_manager.update_run_state(
                    bundle,
                    status="max_steps_reached",
                    reason=reason,
                    last_screen_id=last_screen_id,
                    action_history=[item.to_dict() for item in context.action_history],
                    failure_count=failure_count,
                )
                return RunResult(
                    status="max_steps_reached",
                    reason=reason,
                    steps=context.max_steps,
                    run_dir=run_dir,
                    last_state=last_state,
                )
            finally:
                self.android_adapter.close()

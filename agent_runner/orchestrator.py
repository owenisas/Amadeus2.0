from __future__ import annotations

from pathlib import Path

from agent_runner.android_adapter import AndroidAdapter
from agent_runner.agent_tools import AgentToolExecutor
from agent_runner.models import ActionRecord, RunContext, RunResult, ScreenState, SkillBundle, VisionDecision
from agent_runner.safety import detect_manual_login_required, evaluate_decision
from agent_runner.skill_manager import SkillManager
from agent_runner.utils import describe_state_signature, ensure_directory, timestamp_slug
from agent_runner.vision_agent import VisionAgent


class Orchestrator:
    YOLO_NOTICE = (
        "YOLO mode enabled: interactive approval prompts are bypassed and the agent will "
        "auto-continue through approval surfaces when it finds a stable action. Purchase and "
        "other local safety blocks still apply."
    )

    def __init__(
        self,
        *,
        android_adapter: AndroidAdapter,
        tool_executor: AgentToolExecutor,
        vision_agent: VisionAgent,
        skill_manager: SkillManager,
        runs_dir: Path,
        approval_handler: "callable | None" = None,
    ) -> None:
        self.android_adapter = android_adapter
        self.tool_executor = tool_executor
        self.vision_agent = vision_agent
        self.skill_manager = skill_manager
        self.runs_dir = runs_dir
        self.approval_handler = approval_handler or self._default_approval_handler

    @staticmethod
    def _default_approval_handler(decision: VisionDecision, state: ScreenState) -> str:
        """Interactive terminal approval. Returns 'allow', 'deny', or 'manual'."""
        import sys
        print(f"\n{'='*60}")
        print(f"APPROVAL REQUIRED")
        print(f"  Surface: {state.package_name} / {state.activity_name}")
        print(f"  Reason:  {decision.reason}")
        if decision.target_label:
            print(f"  Action:  {decision.target_label}")
        clickable = state.clickable_text[:6]
        if clickable:
            print(f"  Available: {', '.join(clickable)}")
        print(f"{'='*60}")
        print("  [a] Allow this action")
        print("  [d] Deny and stop the run")
        print("  [m] Take over manually")
        while True:
            try:
                choice = input("Choose [a/d/m]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                return "deny"
            if choice in ("a", "allow"):
                return "allow"
            if choice in ("d", "deny"):
                return "deny"
            if choice in ("m", "manual"):
                return "manual"
            print("  Invalid choice. Enter a, d, or m.")

    def run(self, context: RunContext) -> RunResult:
        with self.android_adapter.session_lock():
            try:
                run_dir = ensure_directory(self.runs_dir / f"{context.app.name}-{timestamp_slug()}")
                context.run_dir = run_dir
                bundle = self.skill_manager.load_skill(context.app)
                system_instruction = self.skill_manager.load_system_skill()
                notice = self.YOLO_NOTICE if context.yolo_mode else None

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
                        notice=notice,
                    )

                self.android_adapter.launch_app(context.app.package_name, context.app.launch_activity)

                last_screen_id: str | None = None
                failure_count = 0
                state = self.android_adapter.capture_state(run_dir)
                last_state: ScreenState | None = state

                for step in range(1, context.max_steps + 1):
                    last_state = state

                    if not context.yolo_mode and detect_manual_login_required(context.app, state):
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
                            notice=notice,
                        )

                    decision = self.vision_agent.decide(
                        goal=context.goal,
                        state=state,
                        skill=bundle,
                        system_instruction=system_instruction,
                        action_history=[item.to_dict() for item in context.action_history],
                        available_tools=[tool.to_dict() for tool in self.tool_executor.list_tools()],
                        yolo_mode=context.yolo_mode,
                    )
                    last_screen_id = self.skill_manager.update_after_observation(bundle, state, decision)

                    # --- Approval gate: prompt user and resume if approved ---
                    if decision.requires_user_approval and decision.next_action == "stop":
                        resolution = self._request_approval(
                            decision=decision,
                            state=state,
                            step=step,
                            context=context,
                            bundle=bundle,
                            last_screen_id=last_screen_id,
                            failure_count=failure_count,
                            run_dir=run_dir,
                        )
                        if resolution == "deny":
                            return RunResult(
                                status="blocked",
                                reason="User denied the approval request.",
                                steps=step,
                                run_dir=run_dir,
                                last_state=state,
                                notice=notice,
                            )
                        if resolution == "manual":
                            return RunResult(
                                status="paused_for_manual",
                                reason="User chose to take over manually.",
                                steps=step,
                                run_dir=run_dir,
                                last_state=state,
                                notice=notice,
                            )
                        # User approved — convert the stop into the concrete action
                        if decision.target_label and decision.target_box:
                            decision = VisionDecision(
                                screen_classification=decision.screen_classification,
                                goal_progress="approved_by_user",
                                next_action="tap",
                                target_box=decision.target_box,
                                confidence=1.0,
                                reason=f"User approved: {decision.reason}",
                                risk_level="low",
                                target_label=decision.target_label,
                            )
                        else:
                            # Recapture — user may have acted manually
                            state = self.android_adapter.capture_state(run_dir)
                            continue

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
                            notice=notice,
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
                        context.action_history.append(action_record)
                        self.skill_manager.update_run_state(
                            bundle,
                            status="completed",
                            reason=decision.reason,
                            last_screen_id=last_screen_id,
                            action_history=[item.to_dict() for item in context.action_history],
                            failure_count=failure_count,
                        )
                        return RunResult(
                            status="completed",
                            reason=decision.reason,
                            steps=step,
                            run_dir=run_dir,
                            last_state=state,
                            notice=notice,
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
                                notice=notice,
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
                            notice=notice,
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
                    notice=notice,
                )
            finally:
                self.android_adapter.close()

    def _request_approval(
        self,
        *,
        decision: VisionDecision,
        state: ScreenState,
        step: int,
        context: RunContext,
        bundle: SkillBundle,
        last_screen_id: str | None,
        failure_count: int,
        run_dir: Path,
    ) -> str:
        """Ask the user to approve, deny, or take over manually. Returns 'allow', 'deny', or 'manual'."""
        self.skill_manager.update_run_state(
            bundle,
            status="approval_required",
            reason=decision.reason,
            last_screen_id=last_screen_id,
            action_history=[item.to_dict() for item in context.action_history],
            failure_count=failure_count,
        )
        return self.approval_handler(decision, state)

from __future__ import annotations

from pathlib import Path

from agent_runner.android_adapter import AndroidAdapter
from agent_runner.agent_tools import AgentToolExecutor
from agent_runner.models import ActionRecord, RunContext, RunResult, ScreenState, SkillBundle, VisionDecision
from agent_runner.safety import detect_manual_intervention_reason, evaluate_decision
from agent_runner.skill_manager import SkillManager
from agent_runner.utils import append_jsonl, describe_state_signature, ensure_directory, timestamp_slug
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
        event_callback: "callable | None" = None,
    ) -> None:
        self.android_adapter = android_adapter
        self.tool_executor = tool_executor
        self.vision_agent = vision_agent
        self.skill_manager = skill_manager
        self.runs_dir = runs_dir
        self.approval_handler = approval_handler or self._default_approval_handler
        self.event_callback = event_callback

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
                context_log_path = run_dir / "agent_context.jsonl"
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
                self._emit_event(
                    "run_started",
                    {
                        "app_name": context.app.name,
                        "goal": context.goal,
                        "run_dir": str(run_dir),
                        "yolo_mode": context.yolo_mode,
                    },
                )
                self._emit_event("state_captured", {"step": 0, "state": self._serialize_state(state)})
                self._append_context_log(
                    context_log_path,
                    {
                        "type": "state_captured",
                        "step": 0,
                        "state": self._serialize_state(state),
                    },
                )

                step = 0
                while context.max_steps == 0 or step < context.max_steps:
                    step += 1
                    last_state = state

                    intervention_reason = detect_manual_intervention_reason(
                        context.app,
                        state,
                        yolo_mode=context.yolo_mode,
                    )
                    if intervention_reason:
                        status = (
                            "manual_login_required"
                            if "login" in intervention_reason.casefold()
                            else "manual_verification_required"
                        )
                        self._emit_event(
                            "manual_intervention_required",
                            {"step": step, "status": status, "reason": intervention_reason},
                        )
                        self.skill_manager.update_after_observation(bundle, state, None)
                        self.skill_manager.update_run_state(
                            bundle,
                            status=status,
                            reason=intervention_reason,
                            last_screen_id=last_screen_id,
                            action_history=[item.to_dict() for item in context.action_history],
                            failure_count=failure_count,
                        )
                        return RunResult(
                            status=status,
                            reason=intervention_reason,
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
                    self._emit_event(
                        "decision_made",
                        {
                            "step": step,
                            "decision": decision.to_dict(),
                            "decision_meta": getattr(self.vision_agent, "last_decision_meta", None),
                        },
                    )
                    self._append_context_log(
                        context_log_path,
                        {
                            "type": "decision_made",
                            "step": step,
                            "state": self._serialize_state(state),
                            "decision": decision.to_dict(),
                            "decision_meta": getattr(self.vision_agent, "last_decision_meta", None),
                            "decision_context": getattr(self.vision_agent, "last_decision_context", None),
                        },
                    )
                    last_screen_id = self.skill_manager.update_after_observation(bundle, state, decision)

                    # --- Approval gate: prompt user and resume if approved ---
                    if decision.requires_user_approval and decision.next_action == "stop":
                        self._emit_event(
                            "approval_requested",
                            {
                                "step": step,
                                "decision": decision.to_dict(),
                                "state": self._serialize_state(state),
                            },
                        )
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
                            self._emit_event("approval_denied", {"step": step})
                            return RunResult(
                                status="blocked",
                                reason="User denied the approval request.",
                                steps=step,
                                run_dir=run_dir,
                                last_state=state,
                                notice=notice,
                            )
                        if resolution == "manual":
                            self._emit_event("manual_takeover", {"step": step})
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

                    verdict = evaluate_decision(context.app, state, decision, goal=context.goal)
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
                        self._emit_event(
                            "action_blocked",
                            {
                                "step": step,
                                "decision": decision.to_dict(),
                                "reason": verdict.reason,
                            },
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
                        target_label=decision.target_label
                        or (str(decision.tool_arguments.get("target_label")) if decision.tool_arguments.get("target_label") else None),
                        target_box=(
                            decision.target_box.to_dict()
                            if decision.target_box is not None
                            else (
                                decision.tool_arguments.get("target_box")
                                if isinstance(decision.tool_arguments.get("target_box"), dict)
                                else None
                            )
                        ),
                        tool_name=decision.tool_name,
                        tool_arguments=decision.tool_arguments,
                    )

                    if decision.next_action == "stop":
                        context.action_history.append(action_record)
                        self._emit_event("run_completed", {"step": step, "decision": decision.to_dict()})
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
                        try:
                            tool_result = self.tool_executor.execute(
                                tool_name=decision.tool_name or "",
                                arguments=decision.tool_arguments,
                                run_dir=run_dir,
                                current_state=state,
                                app=context.app,
                                skill=bundle,
                            )
                        except ValueError as exc:
                            action_record.allowed = False
                            action_record.reason = str(exc)
                            context.action_history.append(action_record)
                            self._emit_event(
                                "action_blocked",
                                {
                                    "step": step,
                                    "decision": decision.to_dict(),
                                    "reason": str(exc),
                                },
                            )
                            self.skill_manager.update_run_state(
                                bundle,
                                status="blocked",
                                reason=str(exc),
                                last_screen_id=last_screen_id,
                                action_history=[item.to_dict() for item in context.action_history],
                                failure_count=failure_count,
                            )
                            return RunResult(
                                status="blocked",
                                reason=str(exc),
                                steps=step,
                                run_dir=run_dir,
                                last_state=state,
                                notice=notice,
                            )
                        action_record.tool_output = tool_result.output
                        context.action_history.append(action_record)
                        self._emit_event(
                            "tool_executed",
                            {
                                "step": step,
                                "tool_name": decision.tool_name,
                                "tool_arguments": decision.tool_arguments,
                                "ok": tool_result.ok,
                                "output": tool_result.output,
                                "error": tool_result.error,
                            },
                        )
                        self._append_context_log(
                            context_log_path,
                            {
                                "type": "tool_executed",
                                "step": step,
                                "tool_name": decision.tool_name,
                                "tool_arguments": decision.tool_arguments,
                                "ok": tool_result.ok,
                                "output": tool_result.output,
                                "error": tool_result.error,
                            },
                        )
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
                        self._emit_event(
                            "action_performed",
                            {
                                "step": step,
                                "action": decision.next_action,
                                "reason": decision.reason,
                                "target_label": decision.target_label,
                            },
                        )
                        self._append_context_log(
                            context_log_path,
                            {
                                "type": "action_performed",
                                "step": step,
                                "action": decision.next_action,
                                "reason": decision.reason,
                                "target_label": decision.target_label,
                            },
                        )
                    self._emit_event("state_captured", {"step": step, "state": self._serialize_state(next_state)})
                    self._append_context_log(
                        context_log_path,
                        {
                            "type": "state_captured",
                            "step": step,
                            "state": self._serialize_state(next_state),
                        },
                    )
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
                        reason = self._stall_reason(next_state, context.action_history)
                        self._emit_event("run_stalled", {"step": step, "reason": reason})
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
                self._emit_event("max_steps_reached", {"step": context.max_steps, "reason": reason})
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

    def _emit_event(self, event_type: str, payload: dict[str, object]) -> None:
        if self.event_callback is None:
            return
        try:
            self.event_callback({"type": event_type, **payload})
        except Exception:
            return

    @staticmethod
    def _append_context_log(path: Path, payload: dict[str, object]) -> None:
        append_jsonl(path, payload)

    @staticmethod
    def _state_has_reload(state: ScreenState) -> bool:
        text = " ".join(state.visible_text[:40]).casefold()
        clickable = " ".join(state.clickable_text[:20]).casefold()
        return "reload" in text or "reload" in clickable

    @staticmethod
    def _is_tap_action(record: ActionRecord) -> bool:
        return record.action == "tap" or (record.action == "tool" and record.tool_name == "tap")

    @classmethod
    def _repeated_same_tap_target(cls, action_history: list[ActionRecord], count: int = 3) -> bool:
        if len(action_history) < count:
            return False
        recent = action_history[-count:]
        if not all(record.allowed and cls._is_tap_action(record) for record in recent):
            return False
        first_box = recent[0].target_box
        if not isinstance(first_box, dict):
            return False
        required = {"x", "y", "width", "height"}
        if not required.issubset(first_box):
            return False
        for record in recent[1:]:
            if record.target_box is None:
                return False
            for key in required:
                if abs(float(record.target_box[key]) - float(first_box[key])) > 0.02:
                    return False
        return True

    @classmethod
    def _stall_reason(cls, state: ScreenState, action_history: list[ActionRecord]) -> str:
        if cls._state_has_reload(state) and cls._repeated_same_tap_target(action_history):
            return "Webview appears stuck: Reload is visible and repeated taps on the same target did not change the screen."
        return "Screen did not change after repeated actions."

    @staticmethod
    def _serialize_state(state: ScreenState) -> dict[str, object]:
        summary = state.summary()
        summary["screenshot_path"] = str(state.screenshot_path)
        summary["hierarchy_path"] = str(state.hierarchy_path)
        return summary

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

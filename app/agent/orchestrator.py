"""LangGraph observe-plan-act-verify loop with hard step and retry limits."""

from __future__ import annotations

import copy
import json
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import TypedDict

from langgraph.graph import END, StateGraph

from app.agent.desktop import choose_youtube_result, desktop_provider, next_desktop_action, point_hits_ad, youtube_search_url
from app.agent.executor import StepExecutor
from app.agent.planner import Planner, public_observation
from app.agent.recovery import decide
from app.agent.state import overall_status, render_report
from app.agent.verifier import verify_step
from app.config.settings import AppSettings
from app.errors import CancellationError
from app.storage.database import Database
from app.storage.models import Plan, TaskReport, TaskStatus, ToolResult
from app.tools.base import ToolContext
from app.tools.registry import ToolRegistry


class AgentGraphState(TypedDict, total=False):
    instruction: str
    route: str
    cursor: int
    results: dict
    revisions: int
    signatures: list
    observations: list
    status: str
    assumptions: list
    clarification: str | None
    error: str | None
    task_id: str
    plan: dict
    last_result: dict
    active_signature: str
    report: str


class DesktopAgent:
    def __init__(
        self,
        *,
        settings: AppSettings,
        registry: ToolRegistry,
        planner: Planner,
        executor: StepExecutor,
        database: Database,
        folders: dict,
        platform: object,
        cancel_event,
        provider=None,
    ) -> None:
        self.settings = settings
        self.registry = registry
        self.planner = planner
        self.executor = executor
        self.database = database
        self.folders = folders
        self.platform = platform
        self.cancel_event = cancel_event
        self.provider = provider
        self.on_step: Callable[[dict], None] | None = None
        self.task_deadline = 0.0
        self._presence_on = False
        self._graph = self._build_graph()

    def run(self, instruction: str) -> TaskReport:
        self.task_deadline = time.monotonic() + self.settings.task_timeout_seconds
        state = {
            "instruction": instruction.strip(),
            "route": "plan",
            "cursor": 0,
            "results": {},
            "revisions": 0,
            "signatures": [],
            "observations": [],
            "status": "running",
            "assumptions": [],
            "clarification": None,
            "error": None,
            "task_id": "",
            "plan": {},
        }
        return self._invoke(state)

    def resume(self, task_id: str) -> TaskReport:
        task = self.database.get_task(task_id)
        if task is None:
            raise KeyError(task_id)
        stored = self.database.list_steps(task_id)
        if not stored:
            return self.run(task["instruction"])
        steps = []
        results = {}
        cursor = 0
        found = False
        for index, step in enumerate(stored):
            status = step["status"]
            if status == "running":
                status = "pending"
            item = {
                "id": step["id"],
                "objective": step["objective"],
                "tool": step["tool"],
                "arguments": step["arguments"],
                "risk": step["risk"],
                "requires_approval": step["requires_approval"],
                "expected_result": step["expected_result"],
                "actual_result": step["actual_result"],
                "status": status,
                "error": step["error"],
                "attempts": 0 if status != "succeeded" else step["attempts"],
                "approval_status": step["approval_status"],
            }
            steps.append(item)
            if status == "succeeded" and step.get("result"):
                results[step["id"]] = step["result"]
            elif not found:
                cursor = index
                found = True
        if not found:
            report = render_report(
                instruction=task["instruction"],
                status="completed",
                steps=steps,
                assumptions=[],
            )
            self.database.update_task(task_id, "completed", report)
            return TaskReport(task_id=task_id, status=TaskStatus.completed, report=report, steps=steps)
        self.task_deadline = time.monotonic() + self.settings.task_timeout_seconds
        state = {
            "instruction": task["instruction"],
            "route": "execute",
            "cursor": cursor,
            "results": results,
            "revisions": 0,
            "signatures": [],
            "observations": [],
            "status": "running",
            "assumptions": [],
            "clarification": None,
            "error": None,
            "task_id": task_id,
            "plan": {"intent": "resume", "assumptions": [], "steps": steps, "clarification": None},
        }
        return self._invoke(state)

    def _invoke(self, state: dict) -> TaskReport:
        try:
            final = self._graph.invoke(state, config={"recursion_limit": self.settings.max_steps * 6 + 20})
        finally:
            if self._presence_on:
                self._set_presence(False)
        status = TaskStatus(final.get("status") or "failed")
        return TaskReport(
            task_id=final.get("task_id") or "",
            status=status,
            report=final.get("report") or "",
            steps=final.get("plan", {}).get("steps", []),
            clarification=final.get("clarification"),
            assumptions=final.get("assumptions") or [],
        )

    def _build_graph(self):
        graph = StateGraph(AgentGraphState)
        graph.add_node("start", lambda state: {})
        graph.add_node("plan", self._plan_node)
        graph.add_node("decide", self._decide_node)
        graph.add_node("execute", self._execute_node)
        graph.add_node("verify", self._verify_node)
        graph.add_node("final", self._final_node)
        graph.set_entry_point("start")
        graph.add_conditional_edges("start", _route, {"plan": "plan", "execute": "execute", "final": "final"})
        graph.add_conditional_edges("plan", _route, {"execute": "execute", "plan": "plan", "decide": "decide", "final": "final"})
        graph.add_conditional_edges("decide", _route, {"execute": "execute", "decide": "decide", "final": "final"})
        graph.add_conditional_edges("execute", _route, {"verify": "verify", "execute": "execute", "final": "final"})
        graph.add_conditional_edges("verify", _route, {"execute": "execute", "plan": "plan", "decide": "decide", "final": "final"})
        graph.add_edge("final", END)
        return graph.compile()

    def _plan_node(self, state: dict) -> dict:
        if self._stopped():
            return {"route": "final", "status": "cancelled", "error": "The task was stopped"}
        plan = self.planner.plan(state["instruction"], state.get("observations") or None)
        if plan.reactive:
            task_id = state.get("task_id") or uuid.uuid4().hex
            if not state.get("task_id"):
                self.database.create_task(task_id, state["instruction"], self.settings.provider, plan.assumptions)
            self.task_deadline = max(self.task_deadline, time.monotonic() + max(self.settings.task_timeout_seconds, 300))
            self._set_presence(True, "Agent is operating")
            return {
                "route": "decide",
                "task_id": task_id,
                "plan": plan.model_dump(mode="json"),
                "cursor": 0,
                "results": {},
                "assumptions": plan.assumptions,
                "observations": [],
                "signatures": [],
            }
        if plan.clarification and not plan.steps:
            task_id = state.get("task_id") or uuid.uuid4().hex
            if not state.get("task_id"):
                self.database.create_task(task_id, state["instruction"], self.settings.provider, plan.assumptions)
            preserved = dict(state.get("plan") or {})
            preserved["clarification"] = plan.clarification
            preserved.setdefault("steps", [])
            return {
                "route": "final",
                "status": "needs_clarification",
                "clarification": plan.clarification,
                "task_id": task_id,
                "plan": preserved,
                "assumptions": state.get("assumptions") or plan.assumptions,
            }
        task_id = state.get("task_id") or uuid.uuid4().hex
        if not state.get("task_id"):
            self.database.create_task(task_id, state["instruction"], self.settings.provider, plan.assumptions)
        else:
            self.database.update_task(task_id, "running", assumptions=plan.assumptions)
            self.database.delete_steps(task_id)
        dumped = plan.model_dump(mode="json")
        for position, step in enumerate(dumped["steps"]):
            self.database.save_step(task_id, position, step, None)
            self._emit(step)
        return {
            "route": "execute",
            "task_id": task_id,
            "plan": dumped,
            "cursor": 0,
            "results": {},
            "assumptions": plan.assumptions,
            "observations": [],
        }

    def _execute_node(self, state: dict) -> dict:
        if self._stopped():
            return {"route": "final", "status": "cancelled", "error": "The task was stopped"}
        if time.monotonic() > self.task_deadline:
            return {"route": "final", "status": "failed", "error": "The task timed out"}
        plan = copy.deepcopy(state["plan"])
        steps = plan["steps"]
        cursor = int(state.get("cursor", 0))
        if cursor >= len(steps) or cursor >= self.settings.max_steps:
            return {"route": "final", "status": overall_status(steps), "plan": plan}
        step = steps[cursor]
        signature = _signature(step)
        prior = [item for item in state.get("signatures", []) if item.get("sig") == signature]
        if not plan.get("reactive") and (any(item.get("ok") for item in prior) or len(prior) >= 2):
            step["status"] = "failed"
            step["error"] = "Stopped because the same action was repeated"
            plan["steps"][cursor] = step
            return {"route": "final", "status": "failed", "plan": plan, "error": step["error"]}
        ctx = self._context()
        try:
            result = self.executor.run_step(
                task_id=state["task_id"],
                position=cursor,
                step=step,
                results=state.get("results", {}),
                ctx=ctx,
            )
        except CancellationError:
            return {"route": "final", "status": "cancelled", "plan": plan, "error": "The task was stopped"}
        plan["steps"][cursor] = step
        self._emit(step)
        return {"route": "verify", "plan": plan, "last_result": result.model_dump(mode="json"), "active_signature": signature}

    def _verify_node(self, state: dict) -> dict:
        plan = copy.deepcopy(state["plan"])
        cursor = int(state.get("cursor", 0))
        step = plan["steps"][cursor]
        result = ToolResult.model_validate(state["last_result"])
        status, detail = verify_step(step["tool"], result)
        route = decide(
            status=status,
            error_code=result.error_code,
            attempts=int(step.get("attempts", 0)),
            revisions=int(state.get("revisions", 0)),
            max_retries=self.settings.max_retries,
            max_replans=self.settings.max_replans,
        )
        if route == "retry":
            step["error"] = detail
            plan["steps"][cursor] = step
            self.database.save_step(state["task_id"], cursor, step, result.data)
            return {"route": "execute", "plan": plan}
        signatures = list(state.get("signatures", []))
        signatures.append({"sig": state.get("active_signature"), "ok": status in {"succeeded", "warning"}})
        if route == "advance":
            step["status"] = status
            step["actual_result"] = result.message or detail
            step["error"] = None if status != "warning" else detail
            results = dict(state.get("results", {}))
            results[step["id"]] = result.data
            self.database.save_step(state["task_id"], cursor, step, result.data)
            self._emit(step)
            plan["steps"][cursor] = step
            if plan.get("reactive"):
                return {
                    "route": "decide",
                    "plan": plan,
                    "cursor": cursor + 1,
                    "results": results,
                    "signatures": signatures,
                    "observations": [*state.get("observations", []), _desktop_observation(step, result)],
                }
            if cursor + 1 >= len(plan["steps"]):
                return {"route": "final", "plan": plan, "results": results, "signatures": signatures}
            return {"route": "execute", "plan": plan, "cursor": cursor + 1, "results": results, "signatures": signatures}
        step["status"] = "failed"
        step["error"] = result.error or detail
        step["actual_result"] = result.message
        plan["steps"][cursor] = step
        self.database.save_step(state["task_id"], cursor, step, result.data)
        self._emit(step)
        if route == "clarify":
            clarification = result.error or "Please describe the goal more specifically."
            return {
                "route": "final",
                "status": "needs_clarification",
                "clarification": clarification,
                "plan": plan,
                "signatures": signatures,
            }
        if route == "stop":
            forced = "cancelled" if result.error_code == "cancelled" else "failed"
            return {"route": "final", "status": forced, "plan": plan, "error": step["error"], "signatures": signatures}
        if plan.get("reactive") and route == "replan":
            return {
                "route": "decide",
                "plan": plan,
                "cursor": cursor + 1,
                "results": state.get("results", {}),
                "signatures": signatures,
                "observations": [*state.get("observations", []), _desktop_observation(step, result)],
            }
        if route == "replan":
            observation = {
                "step_id": step["id"],
                "tool": step["tool"],
                "ok": result.ok,
                "error": result.error,
                "message": result.message,
                "count": result.data.get("count"),
                "paths": _observation_paths(result.data),
            }
            observations = [*state.get("observations", []), public_observation(observation, self.settings)]
            return {
                "route": "plan",
                "plan": plan,
                "revisions": int(state.get("revisions", 0)) + 1,
                "observations": observations,
                "signatures": signatures,
                "cursor": 0,
                "results": {},
            }
        return {"route": "final", "status": "failed", "plan": plan, "error": step["error"], "signatures": signatures}

    def _decide_node(self, state: dict) -> dict:
        if self._stopped():
            return {"route": "final", "status": "cancelled", "error": "The task was stopped"}
        if time.monotonic() > self.task_deadline:
            return {"route": "final", "status": "failed", "error": "The task timed out"}
        plan = copy.deepcopy(state.get("plan") or {})
        steps = list(plan.get("steps") or [])
        observations = list(state.get("observations") or [])
        if _same_action_repeated(observations):
            return {"route": "final", "status": "failed", "plan": plan, "error": "Stopped after the same action succeeded three times without a new result"}
        if len(steps) >= max(self.settings.max_steps, 16):
            return {"route": "final", "status": "failed", "plan": plan, "error": "The step limit was reached before the model finished"}
        provider = desktop_provider(self.provider, self.settings)
        if provider is None:
            return {
                "route": "final",
                "status": "needs_clarification",
                "clarification": "No model is available to look at the screen.",
                "plan": plan,
            }
        instruction = state.get("instruction", "")
        site = youtube_search_url(instruction)
        if site and not plan.get("site_opened"):
            plan["site_opened"] = True
            plan["nav_url"] = site
            self._aim_at_browser()
            return self._queue_desktop(state, plan, steps, "open_browser", {"url": site}, "Open a YouTube search in the browser")
        window = self.platform.find_window("YouTube") if site and plan.get("site_opened") else None
        if site and plan.get("site_opened") and window is None:
            plan["nav_waits"] = int(plan.get("nav_waits") or 0) + 1
            if plan["nav_waits"] > 12:
                return {"route": "final", "status": "failed", "plan": plan, "error": "The browser did not open YouTube"}
            time.sleep(0.8)
            return {"route": "decide", "plan": plan, "observations": observations}
        if window and not plan.get("site_title"):
            plan["site_title"] = window["title"]
        if window and not plan.get("pointer_entered"):
            plan["pointer_entered"] = True
            width = int(window["right"] - window["left"])
            height = int(window["bottom"] - window["top"])
            self._glide_to(int(window["left"]) + int(width * 0.34), int(window["top"]) + int(height * 0.46))
        elif window and plan.get("page_clicks") and window["title"] != plan.get("site_title"):
            return {"route": "final", "status": "completed", "plan": plan, "clarification": f"Opened the video: {window['title']}"}
        if int(plan.get("page_clicks") or 0) >= 3:
            return {"route": "final", "status": "failed", "plan": plan, "error": "A video was clicked, but playback did not start"}
        picked = self._youtube_result(window, plan) if site and window else None
        if picked == "scroll":
            return {"route": "decide", "plan": plan, "observations": observations}
        if picked == "blocked":
            return {"route": "final", "status": "failed", "plan": plan, "error": "The visible results were advertisements, so no video was opened"}
        if isinstance(picked, dict):
            self.platform.focus_window("YouTube")
            return self._queue_desktop(state, plan, steps, "click", {"x": picked["x"], "y": picked["y"]}, "Click the first video that is not an advertisement")
        if observations:
            time.sleep(0.8)
        image_path, image_size, _pixels = self._capture_desktop(window)
        if window and image_size:
            screen_size = (window["right"] - window["left"], window["bottom"] - window["top"])
            origin = (window["left"], window["top"])
        elif image_size:
            bounds = self.platform.virtual_screen()
            screen_size = (int(bounds["width"]), int(bounds["height"]))
            origin = (int(bounds.get("left", 0)), int(bounds.get("top", 0)))
        else:
            screen_size = None
            origin = (0, 0)
        remaining = max(1.0, self.task_deadline - time.monotonic())
        try:
            action = next_desktop_action(
                provider,
                settings=self.settings,
                instruction=(
                    "Skip advertisements labeled Sponsored, Ad, 赞助, or 贊助. "
                    "Click the first ordinary video below them. Do not type."
                )
                if site
                else instruction,
                history=observations,
                image_path=image_path,
                windows=self.platform.window_titles(),
                foreground=self.platform.foreground_title(),
                image_size=image_size,
                screen_size=screen_size,
                origin=origin,
                timeout=min(remaining, max(self.settings.step_timeout_seconds, 60)),
            )
        except Exception as exc:
            return {
                "route": "final",
                "status": "needs_clarification",
                "clarification": f"The model did not provide a runnable next step: {exc}",
                "plan": plan,
            }
        if action["done"] and (not site or plan.get("page_clicks")):
            return {"route": "final", "status": "completed", "plan": plan, "clarification": action["objective"]}
        if site and window and (action["tool"] == "type_text" or not _click_on_page(window, action)):
            action = _video_click(window, int(plan.get("page_clicks") or 0))
        if site and window and action["tool"] == "click" and self._click_lands_on_ad(window, action):
            scrolled = self._scroll_past_ad(window, plan)
            if scrolled == "blocked":
                return {"route": "final", "status": "failed", "plan": plan, "error": "The visible results were advertisements, so no video was opened"}
            return {"route": "decide", "plan": plan, "observations": observations}
        if action["tool"] == "wait":
            time.sleep(min(3.0, max(0.2, float(action["arguments"].get("ms", 1000)) / 1000)))
            observations.append({"tool": "wait", "arguments": {}, "ok": True, "message": "Waited for the screen to settle", "error": None})
            return {"route": "decide", "plan": plan, "observations": observations}
        if window and action["tool"] == "click":
            self.platform.focus_window("YouTube")
        return self._queue_desktop(state, plan, steps, action["tool"], action["arguments"], action["objective"])

    def _queue_desktop(self, state: dict, plan: dict, steps: list, tool: str, arguments: dict, objective: str) -> dict:
        if tool == "click":
            plan["page_clicks"] = int(plan.get("page_clicks") or 0) + 1
        step = {
            "id": f"d{len(steps) + 1}",
            "objective": objective,
            "tool": tool,
            "arguments": arguments,
            "risk": "medium",
            "requires_approval": False,
            "expected_result": "The model chose this step from the screen",
            "actual_result": None,
            "status": "pending",
            "error": None,
            "attempts": 0,
            "approval_status": "not_required",
            "desktop_control": True,
        }
        steps.append(step)
        plan["steps"] = steps
        self.database.save_step(state["task_id"], len(steps) - 1, step, None)
        self._emit(step)
        return {"route": "execute", "plan": plan, "cursor": len(steps) - 1}

    def _capture_desktop(self, window: dict | None = None) -> tuple[str | None, tuple[int, int] | None, tuple[int, int] | None]:
        directory = self.settings.resolved_data_dir() / "screenshots"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{uuid.uuid4().hex}.png"
        try:
            saved = self.platform.capture("full", 1, path)
        except Exception:
            return None, None, None
        try:
            from PIL import Image

            with Image.open(saved) as image:
                view = image
                if window:
                    bounds = self.platform.virtual_screen()
                    left = int(window["left"] - bounds.get("left", 0))
                    top = int(window["top"] - bounds.get("top", 0))
                    right = left + int(window["right"] - window["left"])
                    bottom = top + int(window["bottom"] - window["top"])
                    left, top = max(0, left), max(0, top)
                    right, bottom = min(image.width, right), min(image.height, bottom)
                    if right - left > 50 and bottom - top > 50:
                        view = image.crop((left, top, right, bottom))
                resized = view.convert("RGB")
                crop_size = resized.size
                resized.thumbnail((1280, 720), Image.Resampling.LANCZOS)
                model_path = Path(saved).with_name(Path(saved).stem + "-view.png")
                resized.save(model_path, "PNG")
                return str(model_path), resized.size, crop_size
        except Exception:
            return str(saved), None, None

    def _final_node(self, state: dict) -> dict:
        steps = state.get("plan", {}).get("steps", [])
        status = overall_status(steps, state.get("status"))
        if state.get("status") == "needs_clarification":
            status = "needs_clarification"
        report = render_report(
            instruction=state.get("instruction", ""),
            status=status,
            steps=steps,
            assumptions=state.get("assumptions") or [],
            clarification=state.get("clarification"),
            error=state.get("error"),
        )
        task_id = state.get("task_id") or ""
        if task_id:
            self.database.update_task(task_id, status, report, state.get("assumptions") or [])
        return {"status": status, "report": report, "task_id": task_id}

    def _context(self) -> ToolContext:
        from app.security.permissions import PathGuard, default_protected_prefixes

        now = time.monotonic()
        screenshot_dir = self.settings.resolved_data_dir() / "screenshots"
        return ToolContext(
            guard=PathGuard(list(self.folders.values()), default_protected_prefixes()),
            folders=self.folders,
            platform=self.platform,
            cancel_event=self.cancel_event,
            task_deadline=self.task_deadline,
            step_deadline=min(self.task_deadline, now + self.settings.step_timeout_seconds),
            settings=self.settings,
            provider=self.provider,
            approved=False,
            max_results=self.settings.max_search_results,
            max_hash_bytes=self.settings.max_hash_bytes,
            screenshot_dir=screenshot_dir,
        )

    def _youtube_result(self, window: dict, plan: dict) -> dict | str | None:
        controls = self._window_controls()
        if not controls:
            return None
        choice = choose_youtube_result(controls, window, set(plan.get("used_videos") or []))
        if choice is None:
            return None
        if choice["kind"] == "scroll":
            return self._scroll_past_ad(window, plan)
        plan.setdefault("used_videos", []).append(choice["name"])
        return choice

    def _click_lands_on_ad(self, window: dict, action: dict) -> bool:
        arguments = action.get("arguments") or {}
        if arguments.get("x") is None or arguments.get("y") is None:
            return False
        return point_hits_ad(self._window_controls(), window, int(arguments["x"]), int(arguments["y"]))

    def _window_controls(self) -> list[dict]:
        reader = getattr(self.platform, "list_window_controls", None)
        if reader is None:
            return []
        try:
            controls = reader("YouTube")
        except Exception:
            return []
        return list(controls or [])

    def _scroll_past_ad(self, window: dict, plan: dict) -> str:
        if int(plan.get("ad_scrolls") or 0) >= 4:
            return "blocked"
        plan["ad_scrolls"] = int(plan.get("ad_scrolls") or 0) + 1
        self.platform.focus_window("YouTube")
        x = (int(window["left"]) + int(window["right"])) // 2
        y = int(window["top"]) + int((int(window["bottom"]) - int(window["top"])) * 0.55)
        self._glide_to(x, y)
        move = getattr(self.platform, "move_mouse", None)
        if move is not None:
            try:
                move(x, y)
            except Exception:
                pass
        scroll = getattr(self.platform, "scroll", None)
        if scroll is not None:
            scroll(-8)
        time.sleep(0.6)
        return "scroll"

    def _set_presence(self, active: bool, text: str = "Agent is operating") -> None:
        self._presence_on = active
        setter = getattr(self.platform, "set_agent_presence", None)
        if setter is None:
            return
        try:
            setter(active, text)
        except Exception:
            return

    def _aim_at_browser(self) -> None:
        window = None
        finder = getattr(self.platform, "find_window", None)
        if finder is not None:
            for title in ("Chrome", "Edge", "Browser"):
                window = finder(title)
                if window:
                    break
        if window:
            x = (int(window["left"]) + int(window["right"])) // 2
            self._glide_to(x, int(window["top"]) + 48)
            return
        bounds = self.platform.virtual_screen()
        self._glide_to(int(bounds["left"]) + int(bounds["width"]) // 2, int(bounds["top"]) + 140)

    def _glide_to(self, x: int, y: int) -> None:
        glider = getattr(self.platform, "glide_to", None)
        if glider is None:
            return
        try:
            glider(int(x), int(y))
        except Exception:
            return

    def _stopped(self) -> bool:
        return bool(self.cancel_event is not None and self.cancel_event.is_set())

    def _emit(self, step: dict) -> None:
        if self.on_step is not None:
            self.on_step(copy.deepcopy(step))


def _route(state: dict) -> str:
    return state.get("route") or "final"


def _signature(step: dict) -> str:
    return step.get("tool", "") + ":" + json.dumps(step.get("arguments", {}), sort_keys=True, ensure_ascii=False)


def _desktop_observation(step: dict, result: ToolResult) -> dict:
    return {
        "tool": step.get("tool"),
        "arguments": step.get("arguments") or {},
        "ok": result.ok,
        "message": result.message,
        "error": result.error,
    }


def _click_on_page(window: dict, action: dict) -> bool:
    if action.get("tool") != "click":
        return False
    arguments = action.get("arguments") or {}
    x, y = arguments.get("x"), arguments.get("y")
    if x is None or y is None:
        return False
    width = window["right"] - window["left"]
    height = window["bottom"] - window["top"]
    header = window["top"] + int(height * 0.18)
    return window["left"] + 8 <= int(x) <= window["right"] - 8 and header <= int(y) <= window["bottom"] - 8 and width > 0


def _video_click(window: dict, attempt: int) -> dict:
    width = window["right"] - window["left"]
    height = window["bottom"] - window["top"]
    y_ratio = (0.46, 0.62, 0.76)[min(max(attempt, 0), 2)]
    return {
        "done": False,
        "tool": "click",
        "arguments": {"x": window["left"] + int(width * 0.34), "y": window["top"] + int(height * y_ratio)},
        "objective": "Click a video in the search results",
    }


def _same_action_repeated(observations: list[dict]) -> bool:
    recent = observations[-3:]
    if len(recent) < 3:
        return False
    first = (recent[0].get("tool"), json.dumps(recent[0].get("arguments") or {}, sort_keys=True))
    return all((item.get("tool"), json.dumps(item.get("arguments") or {}, sort_keys=True)) == first and item.get("ok") for item in recent)


def _observation_paths(data: dict) -> list[str]:
    paths: list[str] = []
    for key in ("path", "destination", "latest", "current"):
        value = data.get(key)
        if isinstance(value, str):
            paths.append(value)
    for key in ("destinations", "targets", "removed_sources"):
        value = data.get(key)
        if isinstance(value, list):
            paths.extend(str(item) for item in value[:20])
    return paths[:20]


def plan_from_dump(data: dict) -> Plan:
    return Plan.model_validate(data)

import hashlib
import json
import math
import queue
import re
import sqlite3
import threading
import time
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings, get_settings
from app.resource_paths import get_resource_root
from app.schemas import (
    UniversalNavigationAutomation,
    UniversalNavigationCandidate,
    UniversalNavigationObserveRequest,
    UniversalNavigationObserveResponse,
    UniversalNavigationPerformance,
    UniversalNavigationRecommendation,
)
from app.services.provider_errors import compact_text, response_error_detail
from app.services.android_control_index import AndroidControlEvidence, AndroidControlIndex
from app.services.navigation_semantics import candidate_contexts, infer_goal_plan, rank_candidates
from app.services.navigation_function_catalog import (
    GOAL_CONCRETE_SCORE_FLOOR,
    GOAL_GOVERNANCE_BLOCKED_INTENT,
    NavigationFunctionCatalog,
    get_navigation_function_catalog,
)
from app.services.navigation_performance import StageMeasurement
from app.services.universal_navigation_explorer import (
    _looks_like_reauthentication_candidate,
    explore_universal_navigation,
    manual_route_response_if_available,
)
from app.services.universal_navigation_graph import (
    ObservationResult,
    StoredAction,
    UniversalNavigationGraphRepository,
    fingerprint_goal,
    get_universal_navigation_repository,
    sanitize_text,
)


TOKEN_PATTERN = re.compile(r"[0-9A-Za-z가-힣]+")
RECOMMEND_NAVIGATION_TOOL = "recommend_navigation_action"
DECISION_STRING_FIELDS = (
    "goal_interpretation",
    "target_function",
    "selected_element_id",
    "reason",
    "expected_next_screen",
    "instruction",
)
DECISION_BOOLEAN_FIELDS = (
    "goal_reached",
    "requires_user_confirmation",
)
DECISION_REQUIRED_FIELDS = frozenset((*DECISION_STRING_FIELDS, *DECISION_BOOLEAN_FIELDS, "confidence"))
JSON_FENCE_PATTERN = re.compile(
    r"\A```(?:json)?[ \t]*\r?\n(?P<body>.*)\r?\n```[ \t]*\Z",
    re.DOTALL,
)
TOOL_CALL_TAG_PATTERN = re.compile(
    r"\A<tool_call>[ \t\r\n]*(?P<body>.*?)[ \t\r\n]*</tool_call>\Z",
    re.DOTALL,
)
FINAL_STATE_PATTERN = re.compile(r"(완료|해지됨|삭제됨|꺼짐|중단됨|철회됨|취소됨|success|completed|disabled)", re.IGNORECASE)
HIGH_RISK_TOKENS = (
    "최종 삭제",
    "영구 삭제",
    "계정 삭제",
    "회원 탈퇴",
    "결제하기",
    "구매하기",
    "송금하기",
    "전송하기",
    "주문하기",
    "delete account",
    "pay now",
    "purchase",
    "send money",
)
SAFE_NAVIGATION_RISK_PHRASES = (
    "환급/해지",
    "환급·해지",
    "해지환급금",
    "해약환급금",
    "surrender value",
    "구매 내역",
    "구매 항목 및 멤버십",
    "구매 관리",
    "purchases and memberships",
    "purchases & memberships",
    "purchase history",
    "manage purchases",
)
MEDIUM_RISK_TOKENS = (
    "해지",
    "취소",
    "삭제",
    "로그아웃",
    "동의",
    "허용",
    "일시중지",
    "비활성화",
    "unsubscribe",
    "cancel",
    "delete",
    "sign out",
    "allow",
    "confirm",
)
GENERIC_GATEWAYS = (
    "설정",
    "관리",
    "계정",
    "프로필",
    "메뉴",
    "더보기",
    "내 정보",
    "settings",
    "manage",
    "account",
    "profile",
    "menu",
    "more",
)
INTENT_HINTS = (
    (("해지", "구독", "자동결제", "멤버십", "cancel", "unsubscribe"), ("해지", "구독", "멤버십", "비활성화", "결제", "구매", "관리", "계정", "프로필", "설정")),
    (("탈퇴", "계정 삭제", "delete account"), ("탈퇴", "계정", "개인정보", "내 정보", "프로필", "설정", "삭제")),
    (("마케팅", "광고 알림", "수신 철회", "opt out"), ("마케팅", "광고", "알림", "수신", "개인정보", "설정")),
    (("환불", "결제 취소", "refund"), ("환불", "취소", "결제", "주문", "구매", "고객센터", "도움말")),
    (("알림", "notification"), ("알림", "설정", "환경설정")),
    (("개인정보", "데이터 삭제", "privacy", "my data"), ("개인정보", "데이터", "계정", "내 정보", "설정")),
)

# Screen-only safety sentinels.  These are deliberately high-precision UI
# states rather than broad words such as "load", "error report", or "login".
# The catalog consumes the normalized sentinel, so a loading/error/relogin
# screen stops before graph cache or model selection without teaching the goal
# parser app-specific phrases.
CONSERVATIVE_SCREEN_STATES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "system is loading",
        (
            "loading",
            "loading…",
            "loading...",
            "please wait",
            "processing",
            "불러오는 중",
            "처리 중",
            "잠시만 기다려 주세요",
        ),
    ),
    (
        "system is offline",
        (
            "offline",
            "you are offline",
            "no internet connection",
            "network unavailable",
            "오프라인",
            "인터넷 연결 없음",
            "네트워크에 연결할 수 없음",
        ),
    ),
    (
        "system error",
        (
            "something went wrong",
            "unexpected error",
            "service error",
            "try again later",
            "문제가 발생했습니다",
            "오류가 발생했습니다",
            "나중에 다시 시도해 주세요",
        ),
    ),
    (
        "relogin required",
        (
            "session expired",
            "sign in again",
            "log in again",
            "relogin required",
            "세션이 만료되었습니다",
            "다시 로그인",
            "재로그인 필요",
        ),
    ),
    (
        "wrong record",
        ("wrong record", "record mismatch", "잘못된 기록", "기록 불일치"),
    ),
    (
        "wrong jurisdiction",
        (
            "wrong jurisdiction",
            "jurisdiction mismatch",
            "잘못된 관할",
            "관할 불일치",
        ),
    ),
    (
        "state mismatch",
        (
            "invalid lifecycle state",
            "state mismatch",
            "상태 불일치",
            "잘못된 처리 상태",
        ),
    ),
)
CONSERVATIVE_FAILURE_REASONS = {
    "system is loading": "transient_loading",
    "system is offline": "network_offline",
    "system error": "transient_system_error",
    "relogin required": "relogin_required",
    "wrong record": "record_mismatch",
    "wrong jurisdiction": "jurisdiction_mismatch",
    "state mismatch": "lifecycle_state_mismatch",
}

# ``httpx`` timeouts are inactivity limits for connect/read/write/pool
# operations, not a deadline for the complete request.  In particular, a
# response that keeps yielding a byte before every read timeout can keep the
# synchronous call alive indefinitely.  The API endpoint using this provider
# is deliberately synchronous (FastAPI runs it in its worker pool), and
# Windows has no safe signal-based equivalent of ``SIGALRM``.  Run the blocking
# call in a bounded daemon worker so the request thread can enforce one total
# wall-clock deadline.  Timed-out I/O cannot be killed safely in CPython, so
# the semaphore also prevents abandoned calls from growing without bound while
# their per-operation timeout finishes them in the background.
_EXAONE_HTTP_WORKER_LIMIT = 4
_EXAONE_HTTP_WORKER_SLOTS = threading.BoundedSemaphore(_EXAONE_HTTP_WORKER_LIMIT)


class NavigationDecisionDeadlineExceeded(httpx.TimeoutException):
    """The complete K-EXAONE navigation request exceeded its wall deadline."""


def _post_with_total_deadline(
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout_seconds: float,
) -> httpx.Response:
    """Run one synchronous HTTP request behind a hard caller-side deadline.

    ``timeout_seconds`` is still passed to ``httpx`` as its per-operation
    timeout.  The queue wait independently limits total caller wall time.  A
    timed-out worker is daemonized and remains counted against the small global
    limit until its socket operation exits, keeping the FastAPI worker and the
    process responsive without creating an unbounded thread leak.
    """

    budget = max(0.001, float(timeout_seconds))
    deadline = time.monotonic() + budget
    if not _EXAONE_HTTP_WORKER_SLOTS.acquire(blocking=False):
        raise NavigationDecisionDeadlineExceeded(
            "K-EXAONE navigation request capacity is still occupied by timed-out calls"
        )

    result_queue: queue.Queue[tuple[bool, object]] = queue.Queue(maxsize=1)

    def perform_request() -> None:
        try:
            result: tuple[bool, object] = (
                True,
                httpx.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=budget,
                ),
            )
        except Exception as exc:  # handed back to the synchronous caller
            result = (False, exc)
        finally:
            _EXAONE_HTTP_WORKER_SLOTS.release()
        try:
            result_queue.put_nowait(result)
        except queue.Full:
            # Defensive only: the queue has one producer and is never filled
            # by the caller.  Dropping a late result after timeout is harmless.
            pass

    worker = threading.Thread(
        target=perform_request,
        name="exitguide-exaone-navigation-http",
        daemon=True,
    )
    try:
        worker.start()
    except BaseException:
        _EXAONE_HTTP_WORKER_SLOTS.release()
        raise

    remaining = max(0.0, deadline - time.monotonic())
    try:
        succeeded, result = result_queue.get(timeout=remaining)
    except queue.Empty as exc:
        raise NavigationDecisionDeadlineExceeded(
            f"K-EXAONE navigation request exceeded total wall-clock deadline ({budget:g}s)"
        ) from exc
    if succeeded:
        return result  # type: ignore[return-value]
    if isinstance(result, BaseException):
        raise result
    raise RuntimeError("K-EXAONE navigation request worker returned an invalid result")


@dataclass(frozen=True)
class AgentDecision:
    goal_interpretation: str
    target_function: str
    selected_element_id: str | None
    reason: str
    expected_next_screen: str
    instruction: str
    confidence: float
    goal_reached: bool
    requires_user_confirmation: bool


class NavigationDecisionProvider:
    mode = "deterministic_fallback"

    def decide(
        self,
        *,
        goal_text: str,
        request: UniversalNavigationObserveRequest,
        candidates: list[UniversalNavigationCandidate],
        graph_hints: list[dict[str, object]],
        demonstrations: list[AndroidControlEvidence],
    ) -> AgentDecision:
        raise NotImplementedError


class ExaoneNavigationDecisionProvider(NavigationDecisionProvider):
    mode = "exaone"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def decide(
        self,
        *,
        goal_text: str,
        request: UniversalNavigationObserveRequest,
        candidates: list[UniversalNavigationCandidate],
        graph_hints: list[dict[str, object]],
        demonstrations: list[AndroidControlEvidence],
    ) -> AgentDecision:
        if not self.settings.exaone_api_key or not self.settings.exaone_model:
            raise RuntimeError("K-EXAONE API configuration is unavailable")
        candidate_ids = [candidate.element_id for candidate in candidates]
        tool = _recommendation_tool(candidate_ids)
        prompt = _build_prompt(goal_text, request, candidates, graph_hints, demonstrations)
        payload = {
            "model": self.settings.exaone_model,
            "messages": [
                {"role": "system", "content": _system_prompt()},
                {"role": "user", "content": prompt},
            ],
            "tools": [tool],
            # The current K-EXAONE deployment reliably honors the Hermes path
            # with required tool choice. Only one tool is exposed, so the model
            # cannot select or execute any other capability.
            "tool_choice": "required",
            "parallel_tool_calls": False,
            # Navigation is a constrained classification/planning task. A low
            # temperature materially reduces malformed Hermes arguments and
            # inconsistent homonym choices from the same screen.
            "temperature": 0.1,
            "top_p": 0.9,
            "max_tokens": 1000,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        response = None
        try:
            response = _post_with_total_deadline(
                f"{self.settings.exaone_base_url.rstrip('/')}/chat/completions",
                headers=_exaone_headers(self.settings),
                payload=payload,
                timeout_seconds=self.settings.navigation_agent_timeout_seconds,
            )
            response.raise_for_status()
            message = response.json()["choices"][0]["message"]
            arguments = _tool_arguments(message)
            decision = _decision_from_arguments(arguments)
            _validate_selected_element(decision, candidate_ids)
            return decision
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"K-EXAONE HTTP {exc.response.status_code}: {response_error_detail(exc.response)}"
            ) from exc
        except httpx.HTTPError as exc:
            raise RuntimeError(f"K-EXAONE connection failed: {compact_text(str(exc))}") from exc
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"K-EXAONE returned an invalid navigation decision: {compact_text(str(exc))}") from exc


class DeterministicNavigationDecisionProvider(NavigationDecisionProvider):
    mode = "deterministic_fallback"

    def decide(
        self,
        *,
        goal_text: str,
        request: UniversalNavigationObserveRequest,
        candidates: list[UniversalNavigationCandidate],
        graph_hints: list[dict[str, object]],
        demonstrations: list[AndroidControlEvidence],
    ) -> AgentDecision:
        if _deterministic_goal_reached(goal_text, request):
            return AgentDecision(
                goal_interpretation=sanitize_text(goal_text),
                target_function="목적 달성 상태 확인",
                selected_element_id=None,
                reason="현재 화면에 목적 완료를 나타내는 상태 문구가 있습니다.",
                expected_next_screen="현재 화면에서 완료 상태를 유지합니다.",
                instruction="요청한 목적이 완료된 것으로 보입니다. 결과를 확인해 주세요.",
                confidence=0.82,
                goal_reached=True,
                requires_user_confirmation=False,
            )
        ranked = rank_candidates(
            goal_text=goal_text,
            request=request,
            candidates=candidates,
            demonstrations=demonstrations,
        )
        if not ranked or ranked[0][0] < 0.18:
            return AgentDecision(
                goal_interpretation=sanitize_text(goal_text),
                target_function="다음 기능 메뉴 탐색",
                selected_element_id=None,
                reason="현재 화면의 버튼만으로 안전한 다음 메뉴를 판단하기 어렵습니다.",
                expected_next_screen="",
                instruction="목적과 연결되는 메뉴를 확인하지 못했습니다. 화면을 스크롤하거나 전체 메뉴를 열어 주세요.",
                confidence=0.2,
                goal_reached=False,
                requires_user_confirmation=False,
            )
        score, selected, _ = ranked[0]
        confirmation = selected.risk_level in {"medium", "high", "blocked"}
        return AgentDecision(
            goal_interpretation=sanitize_text(goal_text),
            target_function=_target_function(goal_text, selected.label),
            selected_element_id=selected.element_id,
            reason=f"현재 화면에서 '{selected.label}'이(가) 사용자 목적과 가장 가까운 기능 후보입니다.",
            expected_next_screen=f"{selected.label} 관련 기능 화면",
            instruction=f"‘{selected.label}’ 메뉴를 눌러 주세요.",
            confidence=round(min(0.85, 0.35 + score * 0.55), 2),
            goal_reached=False,
            requires_user_confirmation=confirmation,
        )


def observe_universal_navigation(
    request: UniversalNavigationObserveRequest,
    *,
    settings: Settings | None = None,
    repository: UniversalNavigationGraphRepository | None = None,
    catalog: NavigationFunctionCatalog | None = None,
) -> UniversalNavigationObserveResponse:
    request_started = time.perf_counter()
    timing = {"screen_analysis_ms": 0.0, "db_lookup_ms": 0.0, "model_decision_ms": 0.0}
    settings = settings or get_settings()
    repository = repository or get_universal_navigation_repository(settings)
    screen_started = time.perf_counter()
    candidates = extract_navigation_candidates(request)
    timing["screen_analysis_ms"] += (time.perf_counter() - screen_started) * 1000
    db_started = time.perf_counter()
    observation = repository.observe(request, candidates)
    graph_update = repository.graph_update(observation, request.app_package)
    timing["db_lookup_ms"] += (time.perf_counter() - db_started) * 1000
    # Evaluators may already own a fully validated catalog instance. Reusing it
    # avoids importing and compiling the same multi-thousand-function ontology
    # twice while preserving the normal process-level cache for API callers.
    catalog = catalog or get_navigation_function_catalog(settings)
    # Expensive cross-app priors are intentionally lazy.  An exact verified
    # app/version/function route must be checked before AndroidControl or the
    # LLM is consulted.
    demonstrations: list[AndroidControlEvidence] = []
    graph_hints: list[dict[str, object]] = []
    catalog_goal_plan = catalog.plan_goal(request.goal_text)
    screen_evidence_parts = [request.screen.window_title]
    for element in request.screen.elements:
        if not element.visible:
            continue
        visible_values = tuple(
            value
            for value in (element.text, element.content_description)
            if value
        )
        screen_evidence_parts.extend(visible_values)
        if any(
            sanitize_text(value).strip().casefold() in {"offline", "오프라인"}
            for value in visible_values
        ):
            screen_evidence_parts.append("system is offline")
        if element.clickable and not element.enabled:
            label = sanitize_text(
                " ".join(
                    value
                    for value in (element.text, element.content_description, element.view_id)
                    if value
                )
            )
            if label and any(
                match.function_id == catalog_goal_plan.terminal_function
                and match.score >= 0.46
                for match in catalog.match_candidate(
                    label=label,
                    role=element.role,
                    locale=request.locale,
                    enabled=False,
                    limit=8,
                )
                ):
                screen_evidence_parts.append("disabled control")
    conservative_screen_states = _conservative_screen_state_evidence(request)
    if (
        request.operation_mode == "explore"
        and "relogin required" in conservative_screen_states
        and _has_safe_reauthentication_gateway(request, candidates)
    ):
        # A session-expired screen with one explicit, reversible account-
        # verification gateway is actionable recovery rather than a passive
        # loading state. Keep every credential field and submission boundary
        # user-owned; only the gateway into reauthentication may be explored.
        conservative_screen_states = tuple(
            state for state in conservative_screen_states if state != "relogin required"
        )
    screen_evidence_parts.extend(conservative_screen_states)
    catalog_goal_plan = catalog.apply_governance_evidence_boundary(
        result=catalog_goal_plan,
        evidence_text=" ".join(screen_evidence_parts),
    )
    goal_plan = (
        catalog_goal_plan
        if catalog_goal_plan.intent == GOAL_GOVERNANCE_BLOCKED_INTENT
        else infer_goal_plan(request.goal_text, catalog)
    )
    if request.operation_mode == "record":
        # Gold recording is observation-only.  The human owns every action;
        # neither governance fallback, cached routes, nor a model may replace
        # the candidate they actually chose on the device.
        target_function = (
            goal_plan.terminal_function
            or catalog_goal_plan.terminal_function
            or goal_plan.intent
            or "navigation.unknown"
        )
        db_started = time.perf_counter()
        repository.record_gold_observation(
            request=request,
            candidates=candidates,
            observation=observation,
            target_function=target_function,
        )
        timing["db_lookup_ms"] += (time.perf_counter() - db_started) * 1000
        response = UniversalNavigationObserveResponse(
            request_id=request.request_id,
            session_id=request.session_id,
            status="recording",
            screen_fingerprint=observation.screen_fingerprint,
            goal_interpretation=goal_plan.intent,
            decision_mode="human_recording",
            phase="recording",
            candidates=candidates,
            recommendation=None,
            graph_update=graph_update,
            automation=UniversalNavigationAutomation(
                action="none",
                safe_to_execute=False,
                reason="Human Gold recording never automates user actions.",
            ),
            warnings=[],
        )
        return _attach_performance(
            request=request,
            response=response,
            observation=observation,
            repository=repository,
            request_started=request_started,
            timing=timing,
        )
    low_evidence_stop = _requires_low_evidence_stop(
        catalog_plan=catalog_goal_plan,
        goal_plan=goal_plan,
        request=request,
        candidates=candidates,
        catalog=catalog,
    )
    if (
        goal_plan.intent == GOAL_GOVERNANCE_BLOCKED_INTENT
        or conservative_screen_states
        or low_evidence_stop
    ):
        # This boundary must run before route/cache/provider selection in both
        # guide and explore modes.  Otherwise an LLM or a stale graph action
        # can reintroduce the exact high-risk destination that the catalog
        # rejected for role, asset, permission, state, or jurisdiction.
        recommendation_id = _recommendation_id(
            request,
            observation.screen_fingerprint,
            None,
        )
        governed_stop = goal_plan.intent == GOAL_GOVERNANCE_BLOCKED_INTENT
        safe_hub_target = next(
            (
                function_id
                for function_id, _weight in catalog_goal_plan.preferred_functions
                if (
                    (definition := catalog.function(function_id)) is not None
                    and not definition.terminal
                    and not definition.state_changing
                    and definition.automation_policy == "safe_navigation"
                )
            ),
            "navigation.menu",
        )
        target_function = (
            goal_plan.terminal_function
            or catalog_goal_plan.terminal_function
            or (safe_hub_target if low_evidence_stop else GOAL_GOVERNANCE_BLOCKED_INTENT)
        )
        stop_reason = (
            "권한·대상·상태·관할 안전 조건이 충족되지 않았습니다."
            if governed_stop
            else (
                "화면이 로딩·오프라인·오류·재로그인 상태이므로 안정된 화면을 기다립니다."
                if conservative_screen_states
                else "목적 또는 현재 화면의 근거가 부족해 안전한 다음 메뉴를 확정하지 못했습니다."
            )
        )
        recommendation = UniversalNavigationRecommendation(
            recommendation_id=recommendation_id,
            selected_element_id=None,
            selected_element_key=None,
            selected_label=None,
            target_function=target_function,
            instruction=(
                "화면 상태와 목적을 확인한 뒤 다시 시도해 주세요."
            ),
            reason=stop_reason,
            expected_next_screen="",
            confidence=goal_plan.confidence,
            risk_level="blocked" if governed_stop else "low",
            requires_user_confirmation=governed_stop,
        )
        failure_reason = (
            "governance_blocked"
            if governed_stop
            else (
                CONSERVATIVE_FAILURE_REASONS.get(
                    conservative_screen_states[0],
                    "conservative_screen_state",
                )
                if conservative_screen_states
                else "insufficient_screen_evidence"
            )
        )
        repository.record_recommendation(
            recommendation_id=recommendation_id,
            session_id=request.session_id,
            app_package=request.app_package,
            app_version=request.app_version,
            locale=request.locale,
            goal_text=request.goal_text,
            goal_interpretation=(
                goal_plan.intent if governed_stop else "insufficient_screen_evidence"
            ),
            target_function=target_function,
            decision_mode="deterministic_fallback",
            screen_fingerprint=observation.screen_fingerprint,
            action_id=None,
            confidence=goal_plan.confidence,
        )
        response = UniversalNavigationObserveResponse(
            request_id=request.request_id,
            session_id=request.session_id,
            status="needs_user_input" if candidates else "no_safe_action",
            screen_fingerprint=observation.screen_fingerprint,
            goal_interpretation=(
                goal_plan.intent if governed_stop else "insufficient_screen_evidence"
            ),
            decision_mode="deterministic_fallback",
            phase="stopped",
            candidates=candidates,
            recommendation=recommendation,
            graph_update=graph_update,
            failure_reason=failure_reason,
            warnings=[
                f"{stop_reason} 어떠한 버튼도 선택하지 않았습니다."
            ],
        )
        return _attach_performance(
            request=request,
            response=response,
            observation=observation,
            repository=repository,
            request_started=request_started,
            timing=timing,
        )

    serving_route_match = None
    if goal_plan.terminal_function:
        db_started = time.perf_counter()
        serving_route_match = repository.route_action(
            app_package=request.app_package,
            app_version=request.app_version,
            locale=request.locale,
            target_function=goal_plan.terminal_function,
            screen_fingerprint=observation.screen_fingerprint,
        )
        timing["db_lookup_ms"] += (time.perf_counter() - db_started) * 1000
    if serving_route_match is None:
        # AndroidControl is a cold-start prior only.  It never outranks an
        # independently validated app-specific function graph.
        db_started = time.perf_counter()
        demonstrations = _android_control_demonstrations(settings, request, candidates)
        graph_hints = repository.graph_hints(observation.screen_fingerprint)
        timing["db_lookup_ms"] += (time.perf_counter() - db_started) * 1000
    if request.operation_mode == "explore":
        def semantic_tiebreaker(allowed_candidates: list[UniversalNavigationCandidate]) -> str | None:
            # The model is only a last-resort tie-breaker here.  A slow model
            # call must not consume most of the physical-device exploration
            # budget before deterministic graph search gets another screen.
            tiebreaker_settings = settings.model_copy(
                update={
                    "exaone_timeout_seconds": min(
                        settings.exaone_timeout_seconds,
                        5.0,
                    )
                }
            )
            provider = _provider_for(tiebreaker_settings)
            if provider.mode != "exaone":
                return None
            model_started = time.perf_counter()
            try:
                tie_decision = provider.decide(
                    goal_text=request.goal_text,
                    request=request,
                    candidates=allowed_candidates,
                    graph_hints=graph_hints,
                    demonstrations=demonstrations,
                )
            except RuntimeError:
                return None
            finally:
                timing["model_decision_ms"] += (time.perf_counter() - model_started) * 1000
            return tie_decision.selected_element_id

        response = explore_universal_navigation(
            request=request,
            settings=settings,
            repository=repository,
            catalog=catalog,
            candidates=candidates,
            observation=observation,
            graph_update=graph_update,
            demonstrations=demonstrations,
            semantic_tiebreaker=semantic_tiebreaker,
        )
        return _attach_performance(
            request=request,
            response=response,
            observation=observation,
            repository=repository,
            request_started=request_started,
            timing=timing,
        )
    db_started = time.perf_counter()
    route_response = manual_route_response_if_available(
        request=request,
        repository=repository,
        catalog=catalog,
        candidates=candidates,
        observation=observation,
        graph_update=graph_update,
    )
    timing["db_lookup_ms"] += (time.perf_counter() - db_started) * 1000
    if route_response is not None:
        return _attach_performance(
            request=request,
            response=route_response,
            observation=observation,
            repository=repository,
            request_started=request_started,
            timing=timing,
        )
    db_started = time.perf_counter()
    cached = repository.cached_action(observation.screen_fingerprint, request.goal_text)
    timing["db_lookup_ms"] += (time.perf_counter() - db_started) * 1000
    warnings: list[str] = []

    decision_mode = "graph_cache"
    decision = _decision_from_cache(cached, candidates, request.goal_text)
    if decision is None:
        provider = _provider_for(settings)
        decision_mode = provider.mode
        exaone_attempted = provider.mode == "exaone"
        model_started = time.perf_counter()
        try:
            decision = provider.decide(
                goal_text=request.goal_text,
                request=request,
                candidates=candidates,
                graph_hints=graph_hints,
                demonstrations=demonstrations,
            )
            if provider.mode == "exaone":
                guarded_decision, guard_reason = _guard_exaone_decision(
                    decision,
                    goal_text=request.goal_text,
                    request=request,
                    candidates=candidates,
                    graph_hints=graph_hints,
                    demonstrations=demonstrations,
                )
                if guard_reason:
                    decision = guarded_decision
                    decision_mode = "deterministic_fallback"
                    warnings.append(f"K-EXAONE 판단을 의미 점수 가드레일로 교정했습니다: {guard_reason}")
        except RuntimeError as exc:
            if not settings.navigation_agent_allow_fallback:
                raise
            warnings.append(f"K-EXAONE 판단을 사용할 수 없어 결정론적 폴백을 사용했습니다: {compact_text(str(exc), 180)}")
            provider = DeterministicNavigationDecisionProvider()
            decision_mode = provider.mode
            decision = provider.decide(
                goal_text=request.goal_text,
                request=request,
                candidates=candidates,
                graph_hints=graph_hints,
                demonstrations=demonstrations,
            )
        finally:
            # ``provider`` is deliberately replaced by the deterministic
            # implementation in the fallback branch.  Remember the original
            # attempt so failed/malformed K-EXAONE calls are still represented
            # in the performance telemetry.
            if exaone_attempted:
                timing["model_decision_ms"] += (time.perf_counter() - model_started) * 1000

    if decision_mode != "graph_cache":
        gated_decision, gate_reason = _apply_confidence_gate(
            decision,
            goal_text=request.goal_text,
            request=request,
            candidates=candidates,
            demonstrations=demonstrations,
            min_confidence=settings.navigation_agent_min_confidence,
            min_margin=settings.navigation_agent_min_candidate_margin,
        )
        if gate_reason:
            decision = gated_decision
            decision_mode = "deterministic_fallback"
            warnings.append(f"낮은 확신의 안내를 중단했습니다: {gate_reason}")

    selected_candidate = next(
        (candidate for candidate in candidates if candidate.element_id == decision.selected_element_id),
        None,
    )
    if decision.selected_element_id and selected_candidate is None:
        warnings.append("모델이 현재 화면에 없는 버튼을 선택해 추천을 중단했습니다.")
        decision = AgentDecision(
            goal_interpretation=decision.goal_interpretation,
            target_function=decision.target_function,
            selected_element_id=None,
            reason="선택한 버튼이 현재 접근성 화면 트리에 존재하지 않습니다.",
            expected_next_screen="",
            instruction="현재 화면을 다시 읽어 주세요.",
            confidence=0.0,
            goal_reached=False,
            requires_user_confirmation=False,
        )

    recommendation_id = _recommendation_id(request, observation.screen_fingerprint, decision.selected_element_id)
    status = "guided"
    if decision.goal_reached:
        status = "goal_completed"
    elif decision.selected_element_id is None:
        status = "needs_user_input" if candidates else "no_safe_action"

    recommendation = UniversalNavigationRecommendation(
        recommendation_id=recommendation_id,
        selected_element_id=None if selected_candidate is None else selected_candidate.element_id,
        selected_element_key=None if selected_candidate is None else selected_candidate.element_key,
        selected_label=None if selected_candidate is None else selected_candidate.label,
        target_function=decision.target_function,
        instruction=decision.instruction,
        reason=decision.reason,
        expected_next_screen=decision.expected_next_screen,
        confidence=max(0.0, min(1.0, decision.confidence)),
        risk_level="low" if selected_candidate is None else selected_candidate.risk_level,
        requires_user_confirmation=decision.requires_user_confirmation
        or (selected_candidate is not None and selected_candidate.risk_level in {"medium", "high", "blocked"}),
    )
    selected_action = None if selected_candidate is None else observation.actions_by_element_id.get(selected_candidate.element_id)
    repository.record_recommendation(
        recommendation_id=recommendation_id,
        session_id=request.session_id,
        app_package=request.app_package,
        app_version=request.app_version,
        locale=request.locale,
        goal_text=request.goal_text,
        goal_interpretation=decision.goal_interpretation,
        target_function=decision.target_function,
        decision_mode=decision_mode,
        screen_fingerprint=observation.screen_fingerprint,
        action_id=None if selected_action is None else selected_action.action_id,
        confidence=decision.confidence,
    )
    # Persist the current session before marking it complete. This also keeps a
    # goal that is already complete on the first observation out of "active".
    if decision.goal_reached:
        repository.mark_goal_completed(request.session_id, request.goal_text)
    if recommendation.risk_level == "high":
        warnings.append("결제·삭제·전송 가능성이 있는 동작입니다. 실행 결과를 확인한 뒤 사용자가 직접 선택해야 합니다.")

    response = UniversalNavigationObserveResponse(
        request_id=request.request_id,
        session_id=request.session_id,
        status=status,
        screen_fingerprint=observation.screen_fingerprint,
        goal_interpretation=decision.goal_interpretation,
        decision_mode=decision_mode,
        candidates=candidates,
        recommendation=recommendation,
        graph_update=graph_update,
        warnings=warnings,
    )
    return _attach_performance(
        request=request,
        response=response,
        observation=observation,
        repository=repository,
        request_started=request_started,
        timing=timing,
    )


def _attach_performance(
    *,
    request: UniversalNavigationObserveRequest,
    response: UniversalNavigationObserveResponse,
    observation: ObservationResult,
    repository: UniversalNavigationGraphRepository,
    request_started: float,
    timing: dict[str, float],
) -> UniversalNavigationObserveResponse:
    client = request.client_timing
    source = "server_runtime" if client is None else client.measurement_source
    if client is None and ".gym." in request.app_package:
        source = "synthetic"
    route_id = "" if response.discovered_route is None else response.discovered_route.route_id
    target_function = response.goal_interpretation
    if response.discovered_route is not None:
        target_function = response.discovered_route.target_function
    elif response.recommendation is not None:
        target_function = response.recommendation.target_function
    selected_risk = "low" if response.recommendation is None else response.recommendation.risk_level
    failure_type = ""
    if response.phase == "stopped":
        failure_type = response.failure_reason or "exploration_stopped"
    result = repository.performance.record_stage(
        session_id=request.session_id,
        app_package=request.app_package,
        app_version=request.app_version,
        locale=request.locale,
        goal_key=fingerprint_goal(request.goal_text),
        target_function=target_function,
        start_screen_fingerprint=response.screen_fingerprint,
        current_screen_fingerprint=response.screen_fingerprint,
        destination_screen_fingerprint=(response.screen_fingerprint if response.phase == "destination_reached" else ""),
        decision_mode=response.decision_mode,
        phase=response.phase,
        action=response.automation.action,
        safe_to_execute=response.automation.safe_to_execute,
        selected_risk_level=selected_risk,
        selected_element_key=response.automation.selected_element_key or "",
        route_id=route_id,
        failure_type=failure_type,
        measurement=StageMeasurement(
            measurement_source=source,
            server_total_ms=(time.perf_counter() - request_started) * 1000,
            model_decision_ms=timing["model_decision_ms"],
            db_lookup_ms=timing["db_lookup_ms"],
            screen_analysis_ms=timing["screen_analysis_ms"],
            screen_capture_ms=0.0 if client is None else client.screen_capture_ms,
            action_execution_ms=0.0 if client is None else client.action_execution_ms,
            ui_settle_ms=0.0 if client is None else client.ui_settle_ms,
            external_wait_ms=0.0 if client is None else client.external_wait_ms,
            exploration_elapsed_ms=None if client is None else client.exploration_elapsed_ms,
        ),
        executed_recommendation_id=observation.executed_recommendation_id or "",
        executed_transition_outcome=observation.executed_transition_outcome or "",
    )
    return response.model_copy(
        update={"performance": UniversalNavigationPerformance.model_validate(result.payload())}
    )


def extract_navigation_candidates(
    request: UniversalNavigationObserveRequest,
) -> list[UniversalNavigationCandidate]:
    candidates: list[UniversalNavigationCandidate] = []
    seen_keys: set[str] = set()
    children_by_parent: dict[str, list] = {}
    for item in request.screen.elements:
        if item.parent_id:
            children_by_parent.setdefault(item.parent_id, []).append(item)
    labeled_native_clickables = tuple(
        item
        for item in request.screen.elements
        if item.view_id != "exitguide:ocr"
        and item.clickable
        and item.enabled
        and item.visible
        and not item.password
        and (
            sanitize_text(item.text or item.content_description)
            or _descendant_label(item.id, children_by_parent)
        )
    )
    for element in request.screen.elements:
        if not element.clickable or not element.enabled or not element.visible or element.password:
            continue
        if element.view_id == "exitguide:ocr" and _ocr_duplicates_static_native_text(
            element,
            request.screen.elements,
        ):
            # ML Kit also returns ordinary accessibility headings as bounded
            # OCR lines.  Those orphan OCR rows used to become synthetic
            # buttons even though Android had already told us the matching
            # native text was not clickable.  Treat the native semantics as
            # authoritative so headings such as "Memberships and channels"
            # cannot outrank the real subscription card beneath them.
            continue
        if element.view_id == "exitguide:ocr" and any(
            _ocr_is_owned_by_clickable(element.bounds, owner.bounds)
            for owner in labeled_native_clickables
        ):
            # OCR sometimes loses the parent id even though its rectangle is
            # fully inside a readable native card.  Keep the stable native
            # card and discard the fragile coordinate child; otherwise text
            # such as ``개인 멤버십`` can replace the actionable
            # ``YouTube Premium ...`` row and miss after the UI settles.
            continue
        structural_only = False
        # Some custom-drawn Android controls expose a stale or promotional
        # accessibility description while their visible label is different.
        # On-device OCR children are explicitly tagged, so visible text takes
        # precedence without weakening ordinary accessibility semantics.
        direct_label = sanitize_text(element.text or element.content_description)
        descendant_label = _descendant_label(element.id, children_by_parent)
        ocr_label = _ocr_descendant_label(element.id, children_by_parent, element.bounds)
        # OCR is allowed to replace a stale label exposed directly by a
        # custom-drawn card. When the clickable container has a real readable
        # child, however, keep that child label. ML Kit can merge an entire
        # bottom navigation row into one OCR line whose centre happens to fall
        # inside a single tab; using that line would make the tab look like all
        # of its siblings and send the explorer to the wrong destination.
        if direct_label:
            label = _prefer_trustworthy_direct_label(direct_label, ocr_label)
        elif descendant_label:
            label = descendant_label
        else:
            label = ocr_label or sanitize_text(_view_id_label(element.view_id))
        if not label:
            label = _structural_label(element, request.screen.elements)
            structural_only = True
        if not label:
            continue
        key = _element_key(
            element.view_id,
            element.role,
            label,
            element.parent_id,
            discriminator=(
                _relative_geometry_discriminator(element, request.screen.elements)
                if structural_only
                else ""
            ),
        )
        # Accessibility trees can contain several genuinely unlabeled icons
        # in the same coarse screen region (for example search, notifications,
        # and settings in one top bar).  Their positional fallback labels are
        # identical, so a semantic-only key used to discard every icon after
        # the first.  Keep each control available to the safe explorer.  The
        # element id is used only as a last-resort, current-screen tie breaker;
        # it is never exposed as an inferred icon meaning.
        if key in seen_keys and structural_only:
            key = _element_key(
                element.view_id,
                element.role,
                label,
                element.parent_id,
                discriminator=(
                    f"{_relative_geometry_discriminator(element, request.screen.elements)}|"
                    f"{sanitize_text(element.id)}"
                ),
            )
        if key in seen_keys:
            continue
        seen_keys.add(key)
        risk_level, risk_reason = _risk_for_label(label)
        candidates.append(
            UniversalNavigationCandidate(
                element_id=element.id,
                element_key=key,
                label=label,
                role=element.role,
                risk_level=risk_level,
                risk_reason=risk_reason,
            )
        )
    return candidates[:100]


def _android_control_demonstrations(
    settings: Settings,
    request: UniversalNavigationObserveRequest,
    candidates: list[UniversalNavigationCandidate],
) -> list[AndroidControlEvidence]:
    raw_path = settings.android_control_index_path.strip()
    if not raw_path or settings.android_control_retrieval_top_k <= 0:
        return []
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = get_resource_root() / path
    if not path.is_file():
        return []
    visible_text = " | ".join(
        sanitize_text(element.text or element.content_description)
        for element in request.screen.elements
        if element.visible and not element.password and (element.text or element.content_description)
    )[:3000]
    try:
        return AndroidControlIndex(path).search(
            goal_text=request.goal_text,
            candidate_labels=[candidate.label for candidate in candidates],
            screen_text=visible_text,
            limit=settings.android_control_retrieval_top_k,
        )
    except (OSError, sqlite3.Error, ValueError):
        return []


def _conservative_screen_state_evidence(
    request: UniversalNavigationObserveRequest,
) -> tuple[str, ...]:
    """Map high-precision transient/mismatch UI text to catalog sentinels."""

    values = [request.screen.window_title]
    values.extend(
        value
        for element in request.screen.elements
        if element.visible
        for value in (element.text, element.content_description)
        if value
    )
    normalized_values = tuple(
        " ".join(sanitize_text(value).casefold().split()).strip(" .!?:;…")
        for value in values
        if value
    )
    evidence: list[str] = []
    for sentinel, phrases in CONSERVATIVE_SCREEN_STATES:
        matched = False
        for phrase in phrases:
            normalized_phrase = phrase.casefold()
            phrase_is_single_token = " " not in normalized_phrase
            for value in normalized_values:
                if phrase_is_single_token:
                    matched = value == normalized_phrase
                else:
                    matched = (
                        normalized_phrase in value
                        and len(value) <= max(72, len(normalized_phrase) + 32)
                    )
                if matched:
                    break
            if matched:
                break
        if matched:
            evidence.append(sentinel)
    return tuple(evidence)


def _has_safe_reauthentication_gateway(
    request: UniversalNavigationObserveRequest,
    candidates: list[UniversalNavigationCandidate],
) -> bool:
    if any(
        element.visible
        and (
            element.password
            or element.role.casefold()
            in {
                "input",
                "text_field",
                "textfield",
                "edittext",
                "textbox",
                "searchbox",
            }
        )
        for element in request.screen.elements
    ):
        return False
    elements = {element.id: element for element in request.screen.elements}
    return any(
        candidate.risk_level == "low"
        and _looks_like_reauthentication_candidate(candidate.label)
        and (element := elements.get(candidate.element_id)) is not None
        and element.visible
        and element.enabled
        and element.clickable
        and not element.checkable
        and not element.selected
        and not element.password
        for candidate in candidates
    )


def _requires_low_evidence_stop(
    *,
    catalog_plan,
    goal_plan,
    request: UniversalNavigationObserveRequest,
    candidates: list[UniversalNavigationCandidate],
    catalog: NavigationFunctionCatalog,
) -> bool:
    """Stop generic or barely-concrete routing unless a safe exact UI target exists."""

    if catalog_plan.intent == GOAL_GOVERNANCE_BLOCKED_INTENT:
        return False
    # Curated legacy consumer intents (subscription cancellation, privacy,
    # refunds, and similar flows) remain available when the larger catalog has
    # no concrete match.  Only truly generic navigation stops here.
    if catalog_plan.intent == "generic_navigation":
        return goal_plan.intent == "generic_navigation"
    if catalog_plan.confidence >= max(0.40, GOAL_CONCRETE_SCORE_FLOOR):
        return False
    return not _has_exact_visible_safe_terminal(
        catalog_plan=catalog_plan,
        request=request,
        candidates=candidates,
        catalog=catalog,
    )


def _has_exact_visible_safe_terminal(
    *,
    catalog_plan,
    request: UniversalNavigationObserveRequest,
    candidates: list[UniversalNavigationCandidate],
    catalog: NavigationFunctionCatalog,
) -> bool:
    """Preserve an exact, enabled, read-only terminal despite a low goal score."""

    terminal = catalog_plan.terminal_function
    definition = catalog.function(terminal) if terminal else None
    if (
        definition is None
        or not definition.terminal
        or definition.state_changing
        or definition.risk_level != "low"
        or definition.automation_policy == "never_auto"
        or definition.stop_policy not in {"continue", "at_destination"}
    ):
        return False
    enabled_by_id = {
        element.id: bool(element.enabled)
        for element in request.screen.elements
        if element.visible
    }
    for candidate in candidates:
        if not enabled_by_id.get(candidate.element_id, False) or candidate.risk_level != "low":
            continue
        matches = catalog.match_candidate(
            label=candidate.label,
            role=candidate.role,
            locale=request.locale,
            enabled=True,
            limit=4,
        )
        if any(
            match.function_id == terminal
            and match.alias_score >= 0.98
            and match.negative_evidence == ()
            for match in matches
        ):
            return True
    return False


def _provider_for(settings: Settings) -> NavigationDecisionProvider:
    provider_name = settings.navigation_agent_provider.strip().lower()
    if provider_name == "exaone":
        return ExaoneNavigationDecisionProvider(settings)
    return DeterministicNavigationDecisionProvider()


def _apply_confidence_gate(
    decision: AgentDecision,
    *,
    goal_text: str,
    request: UniversalNavigationObserveRequest,
    candidates: list[UniversalNavigationCandidate],
    demonstrations: list[AndroidControlEvidence],
    min_confidence: float,
    min_margin: float,
) -> tuple[AgentDecision, str | None]:
    if decision.goal_reached or decision.selected_element_id is None:
        return decision, None
    ranked = rank_candidates(
        goal_text=goal_text,
        request=request,
        candidates=candidates,
        demonstrations=demonstrations,
    )
    selected = next(
        (item for item in ranked if item[1].element_id == decision.selected_element_id),
        None,
    )
    if selected is None:
        return _uncertain_decision(decision, "선택 후보가 현재 의미 순위에 없습니다."), "선택 근거가 없습니다."
    selected_score = selected[0]
    if decision.confidence < max(0.0, min(1.0, min_confidence)):
        reason = f"모델 확신도 {decision.confidence:.2f}가 기준 {min_confidence:.2f}보다 낮습니다."
        return _uncertain_decision(decision, reason), reason
    if selected_score < 0.24:
        reason = f"화면 문맥 기반 독립 점수 {selected_score:.2f}가 너무 낮습니다."
        return _uncertain_decision(decision, reason), reason
    if ranked and ranked[0][1].element_id != decision.selected_element_id:
        difference = ranked[0][0] - selected_score
        if difference >= max(0.12, min_margin):
            reason = (
                f"'{ranked[0][1].label}'이(가) '{selected[1].label}'보다 "
                f"독립 근거가 {difference:.2f} 높습니다."
            )
            return _uncertain_decision(decision, reason), reason
    if len(ranked) >= 2 and ranked[0][1].element_id == decision.selected_element_id:
        margin = ranked[0][0] - ranked[1][0]
        if margin < max(0.0, min_margin):
            reason = f"상위 두 후보의 점수 차이가 {margin:.2f}로 구분 기준보다 작습니다."
            return _uncertain_decision(decision, reason), reason
    return decision, None


def _uncertain_decision(decision: AgentDecision, reason: str) -> AgentDecision:
    return AgentDecision(
        goal_interpretation=decision.goal_interpretation,
        target_function=decision.target_function,
        selected_element_id=None,
        reason=sanitize_text(reason),
        expected_next_screen="",
        instruction="현재 후보를 확실하게 구분하지 못했습니다. 화면의 계정·설정 메뉴를 확인하거나 스크롤해 주세요.",
        confidence=0.0,
        goal_reached=False,
        requires_user_confirmation=False,
    )


def _decision_from_cache(
    cached: StoredAction | None,
    candidates: list[UniversalNavigationCandidate],
    goal_text: str,
) -> AgentDecision | None:
    if cached is None:
        return None
    current = next((candidate for candidate in candidates if candidate.element_key == cached.element_key), None)
    if current is None:
        semantic_matches = sorted(
            (
                (_text_similarity(cached.label, candidate.label), candidate)
                for candidate in candidates
                if candidate.role.lower() == cached.role.lower()
            ),
            key=lambda item: item[0],
            reverse=True,
        )
        if not semantic_matches or semantic_matches[0][0] < 0.86:
            return None
        best_score, current = semantic_matches[0]
        if len(semantic_matches) > 1 and best_score - semantic_matches[1][0] < 0.08:
            return None
    return AgentDecision(
        goal_interpretation=sanitize_text(goal_text),
        target_function="이전에 성공한 기능 경로 재사용",
        selected_element_id=current.element_id,
        reason="같은 목적과 화면에서 사용자가 이전에 성공한 선택입니다.",
        expected_next_screen="이전에 관찰한 다음 기능 화면",
        instruction=f"‘{current.label}’ 메뉴를 눌러 주세요.",
        confidence=0.93,
        goal_reached=False,
        requires_user_confirmation=current.risk_level in {"medium", "high", "blocked"},
    )


def _guard_exaone_decision(
    decision: AgentDecision,
    *,
    goal_text: str,
    request: UniversalNavigationObserveRequest,
    candidates: list[UniversalNavigationCandidate],
    graph_hints: list[dict[str, object]],
    demonstrations: list[AndroidControlEvidence],
) -> tuple[AgentDecision, str | None]:
    """Reject unstable model choices only when local screen evidence is stronger.

    K-EXAONE remains the primary reasoner for novel labels. The deterministic
    provider acts as a narrow semantic safety rail: it fills an unjustified
    empty answer, rejects an unsupported completion claim, or replaces a choice
    whose local intent score is materially weaker than another visible button.
    """
    baseline = DeterministicNavigationDecisionProvider().decide(
        goal_text=goal_text,
        request=request,
        candidates=candidates,
        graph_hints=graph_hints,
        demonstrations=demonstrations,
    )
    if decision.goal_reached and not baseline.goal_reached:
        return baseline, "현재 화면에 목적 완료를 입증하는 문구가 없습니다."
    if decision.goal_reached or baseline.selected_element_id is None:
        return decision, None

    baseline_candidate = next(
        (candidate for candidate in candidates if candidate.element_id == baseline.selected_element_id),
        None,
    )
    if baseline_candidate is None:
        return decision, None
    ranked = rank_candidates(
        goal_text=goal_text,
        request=request,
        candidates=candidates,
        demonstrations=demonstrations,
    )
    scores = {candidate.element_id: score for score, candidate, _ in ranked}
    baseline_score = scores.get(baseline_candidate.element_id, 0.0)

    if decision.selected_element_id is None:
        if baseline_score >= 0.28:
            return baseline, "빈 선택보다 목적과 직접 연결되는 현재 화면 후보가 있습니다."
        return decision, None

    selected_candidate = next(
        (candidate for candidate in candidates if candidate.element_id == decision.selected_element_id),
        None,
    )
    if selected_candidate is None:
        return decision, None
    if selected_candidate.element_id == baseline_candidate.element_id:
        if decision.confidence < 0.55 and baseline_score >= 0.50:
            return baseline, "모델과 독립 기능 판단이 같은 후보를 가리키지만 모델 확신도가 낮아 독립 점수를 사용했습니다."
        return decision, None
    selected_score = scores.get(selected_candidate.element_id, 0.0)
    # The catalog score is built from independently curated aliases and
    # positive/negative context. A seven-point gap is already meaningful and
    # matches the normal candidate-margin gate used by the API.
    if baseline_score - selected_score >= 0.07:
        return baseline, (
            f"'{baseline_candidate.label}'의 목적 연관도가 "
            f"'{selected_candidate.label}'보다 명확히 높습니다."
        )
    return decision, None


def _system_prompt() -> str:
    return (
        "You are K-EXAONE acting as ExitGuideLab's read-only Android navigation decision engine. "
        "You MUST call recommend_navigation_action exactly once and never answer with ordinary text. "
        "당신은 ExitGuideLab의 읽기 전용 Android 내비게이션 판단기입니다. "
        "앱별 사전 경로를 가정하지 말고 현재 화면에 실제로 존재하는 후보만 사용하세요. "
        "AndroidControl 시연은 버튼 단어를 복사하는 정답지가 아니라 목적을 중간 기능으로 분해하는 참고 근거입니다. "
        "버튼 이름이 목적 단어와 같아도 화면 위치·주변 문맥·예상 다음 기능이 다르면 선택하지 마세요. "
        "예를 들어 동영상 홈의 콘텐츠 '구독' 탭은 Premium 결제 구독 관리 메뉴가 아닙니다. "
        "사용자를 대신해 클릭하지 않으며, recommend_navigation_action 도구로 안내할 후보 하나 또는 목적 완료 상태를 반환하세요. "
        "결제·삭제·송금·전송·권한 변경 같은 상태 변경은 숨기지 말고 사용자 확인을 요구하세요. "
        "현재 근거가 부족하면 selected_element_id를 빈 문자열로 반환하세요."
    )


def _build_prompt(
    goal_text: str,
    request: UniversalNavigationObserveRequest,
    candidates: list[UniversalNavigationCandidate],
    graph_hints: list[dict[str, object]],
    demonstrations: list[AndroidControlEvidence],
) -> str:
    visible_text = [
        sanitize_text(element.text or element.content_description)
        for element in request.screen.elements
        if element.visible and not element.password and (element.text or element.content_description)
    ][:80]
    plan = infer_goal_plan(goal_text)
    contexts = candidate_contexts(
        request=request,
        candidates=candidates,
        demonstrations=demonstrations,
        plan=plan,
    )
    payload = {
        "user_goal": sanitize_text(goal_text),
        "goal_plan": plan.prompt_payload(),
        "app_package": request.app_package,
        "activity_name": sanitize_text(request.screen.activity_name),
        "window_title": sanitize_text(request.screen.window_title),
        "visible_text": visible_text,
        "action_candidates": [contexts[candidate.element_id].prompt_payload(candidate) for candidate in candidates],
        "android_control_demonstrations": [item.prompt_payload() for item in demonstrations],
        "previously_observed_transitions": graph_hints,
        "rules": [
            "selected_element_id must be one of action_candidates.element_id or an empty string",
            "choose by the candidate's inferred function and expected next screen, not surface word overlap",
            "treat AndroidControl demonstrations as cross-app functional priors, never as a guaranteed route",
            "avoid any candidate whose inferred_functions intersects goal_plan.avoid_functions",
            "prefer a low-risk candidate that advances one required intermediate function",
            "goal_reached is true only when the visible screen proves completion",
            "return an empty selection when independent semantic evidence is weak or the top candidates are ambiguous",
            "never claim that an action was executed",
        ],
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _recommendation_tool(candidate_ids: list[str]) -> dict[str, Any]:
    selected_schema: dict[str, Any] = {"type": "string"}
    if candidate_ids:
        selected_schema["enum"] = ["", *candidate_ids]
    return {
        "type": "function",
        "function": {
            "name": RECOMMEND_NAVIGATION_TOOL,
            "description": "현재 화면에서 사용자에게 안내할 다음 기능 메뉴를 선택합니다. 실제 클릭은 수행하지 않습니다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "goal_interpretation": {"type": "string"},
                    "target_function": {"type": "string"},
                    "selected_element_id": selected_schema,
                    "reason": {"type": "string"},
                    "expected_next_screen": {"type": "string"},
                    "instruction": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "goal_reached": {"type": "boolean"},
                    "requires_user_confirmation": {"type": "boolean"},
                },
                "required": [
                    "goal_interpretation",
                    "target_function",
                    "selected_element_id",
                    "reason",
                    "expected_next_screen",
                    "instruction",
                    "confidence",
                    "goal_reached",
                    "requires_user_confirmation",
                ],
                "additionalProperties": False,
            },
        },
    }


def _tool_arguments(message: dict[str, Any]) -> dict[str, Any]:
    tool_calls = message.get("tool_calls")
    if tool_calls is not None and tool_calls != []:
        if not isinstance(tool_calls, list):
            raise ValueError("tool_calls must be a list")
        if len(tool_calls) != 1:
            raise ValueError("K-EXAONE must return exactly one tool call")
        tool_call = tool_calls[0]
        if not isinstance(tool_call, dict):
            raise ValueError("tool call must be an object")
        if "type" in tool_call and tool_call["type"] != "function":
            raise ValueError("tool call type must be function")
        function = tool_call.get("function")
        if not isinstance(function, dict):
            raise ValueError("tool call function is missing")
        if function.get("name") != RECOMMEND_NAVIGATION_TOOL:
            raise ValueError(f"unexpected tool function: {function.get('name')!r}")
        if "arguments" not in function:
            raise ValueError("tool call arguments are missing")
        return _coerce_recommendation_arguments(function["arguments"])

    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("tool call arguments are missing")
    return _coerce_recommendation_arguments(content)


def _coerce_recommendation_arguments(value: object) -> dict[str, Any]:
    if isinstance(value, str):
        payload = _parse_single_json_object(value)
    elif isinstance(value, dict):
        payload = value
    else:
        raise ValueError("tool call arguments must be a JSON object or an encoded JSON object")
    return _unwrap_recommendation_wrapper(payload)


def _parse_single_json_object(value: str) -> dict[str, Any]:
    """Decode exactly one object, accepting only known transport wrappers.

    Some Hermes deployments repeat a harmless ``</tool_call>`` transport
    sentinel in ``arguments`` or place the pseudo call in an exact
    ``<tool_call>``/Markdown JSON wrapper.  Those wrappers are stripped
    explicitly.  ``raw_decode`` plus the empty-tail check rejects a second
    object and all other trailing output.
    """

    stripped = value.strip()
    fence_match = JSON_FENCE_PATTERN.fullmatch(stripped)
    if stripped.startswith("```"):
        if fence_match is None:
            raise ValueError("malformed or unsupported JSON fence")
        stripped = fence_match.group("body").strip()

    tag_match = TOOL_CALL_TAG_PATTERN.fullmatch(stripped)
    if stripped.startswith("<tool_call>"):
        if tag_match is None:
            raise ValueError("malformed tool_call wrapper")
        stripped = tag_match.group("body").strip()
    elif stripped.endswith("</tool_call>"):
        stripped = stripped[: -len("</tool_call>")].rstrip()

    def reject_nonfinite(constant: str) -> None:
        raise ValueError(f"non-finite JSON number is not allowed: {constant}")

    decoder = json.JSONDecoder(parse_constant=reject_nonfinite)
    try:
        payload, end = decoder.raw_decode(stripped)
    except json.JSONDecodeError as exc:
        raise ValueError(f"tool call arguments are not valid JSON: {exc.msg}") from exc
    if stripped[end:].strip():
        raise ValueError("tool call arguments contain trailing data or a second JSON value")
    if not isinstance(payload, dict):
        raise ValueError("tool call arguments must decode to one JSON object")
    return payload


def _unwrap_recommendation_wrapper(payload: dict[str, Any]) -> dict[str, Any]:
    """Accept direct arguments or an exact wrapper for our sole Hermes tool."""

    keys = set(payload)
    if keys == {RECOMMEND_NAVIGATION_TOOL}:
        arguments = payload[RECOMMEND_NAVIGATION_TOOL]
        if not isinstance(arguments, dict):
            raise ValueError(f"{RECOMMEND_NAVIGATION_TOOL} wrapper must contain an object")
        return arguments
    if keys == {"name", "arguments"}:
        if payload["name"] != RECOMMEND_NAVIGATION_TOOL:
            raise ValueError(f"unexpected tool function: {payload['name']!r}")
        arguments = payload["arguments"]
        if isinstance(arguments, str):
            return _parse_single_json_object(arguments)
        if not isinstance(arguments, dict):
            raise ValueError("wrapped tool arguments must be an object or encoded object")
        return arguments
    if keys & {"name", "arguments", "function", "tool", "tool_calls"}:
        raise ValueError("unsupported or non-exact tool-call wrapper")
    return payload


def _decision_from_arguments(arguments: dict[str, Any]) -> AgentDecision:
    if not isinstance(arguments, dict):
        raise ValueError("navigation decision arguments must be an object")
    fields = set(arguments)
    missing = sorted(DECISION_REQUIRED_FIELDS - fields)
    unexpected = sorted(fields - DECISION_REQUIRED_FIELDS)
    if missing:
        raise ValueError(f"navigation decision is missing required fields: {', '.join(missing)}")
    if unexpected:
        raise ValueError(f"navigation decision has unexpected fields: {', '.join(unexpected)}")
    for field in DECISION_STRING_FIELDS:
        if type(arguments[field]) is not str:
            raise ValueError(f"navigation decision field {field} must be a string")
    for field in DECISION_BOOLEAN_FIELDS:
        if type(arguments[field]) is not bool:
            raise ValueError(f"navigation decision field {field} must be a boolean")
    confidence = arguments["confidence"]
    if type(confidence) not in {int, float} or not math.isfinite(float(confidence)):
        raise ValueError("navigation decision field confidence must be a finite number")

    return AgentDecision(
        goal_interpretation=sanitize_text(arguments["goal_interpretation"]),
        target_function=sanitize_text(arguments["target_function"]),
        selected_element_id=arguments["selected_element_id"].strip() or None,
        reason=sanitize_text(arguments["reason"]),
        expected_next_screen=sanitize_text(arguments["expected_next_screen"]),
        instruction=sanitize_text(arguments["instruction"]),
        confidence=float(confidence),
        goal_reached=arguments["goal_reached"],
        requires_user_confirmation=arguments["requires_user_confirmation"],
    )


def _validate_selected_element(decision: AgentDecision, candidate_ids: list[str]) -> None:
    if decision.selected_element_id is not None and decision.selected_element_id not in candidate_ids:
        raise ValueError("selected_element_id is not in the current candidate allowlist")
    if not 0.0 <= decision.confidence <= 1.0:
        raise ValueError("confidence is outside the 0-1 range")
    if decision.goal_reached and decision.selected_element_id is not None:
        raise ValueError("a completed goal cannot also select a next action")


def _candidate_score(goal_text: str, candidate: UniversalNavigationCandidate) -> float:
    goal = sanitize_text(goal_text).lower()
    label = candidate.label.lower()
    score = _text_similarity(goal, label)
    for triggers, hints in INTENT_HINTS:
        if not any(trigger in goal for trigger in triggers):
            continue
        for index, hint in enumerate(hints):
            if hint in label:
                score = max(score, 0.88 - min(index, 6) * 0.07)
    if any(gateway in label for gateway in GENERIC_GATEWAYS):
        score = max(score, 0.32)
    if candidate.role.lower() in {"button", "menu", "menuitem", "tab"}:
        score += 0.04
    if candidate.risk_level == "medium" and not _shares_risk_intent(goal, label):
        score -= 0.18
    if candidate.risk_level == "high" and not _shares_risk_intent(goal, label):
        score -= 0.35
    return max(0.0, min(1.0, score))


def _deterministic_goal_reached(goal_text: str, request: UniversalNavigationObserveRequest) -> bool:
    goal = sanitize_text(goal_text).lower()
    for element in request.screen.elements:
        if not element.visible or element.clickable or element.password:
            continue
        label = sanitize_text(element.text or element.content_description).lower()
        if FINAL_STATE_PATTERN.search(label) and _text_similarity(goal, label) >= 0.3:
            return True
        if FINAL_STATE_PATTERN.search(label) and any(
            token in goal and token in label
            for token in ("해지", "구독", "알림", "마케팅", "탈퇴", "삭제", "결제", "환불", "취소")
        ):
            return True
    return False


def _risk_for_label(label: str) -> tuple[str, str | None]:
    normalized = label.lower()
    # These are read-only hubs despite containing words such as "purchase".
    # Treating the noun as a purchase action blocks the very screen that users
    # must traverse before reaching a separately guarded final action.
    if any(phrase in normalized for phrase in SAFE_NAVIGATION_RISK_PHRASES):
        return "low", None
    if any(token in normalized for token in HIGH_RISK_TOKENS):
        return "high", "결제·삭제·송금·전송처럼 되돌리기 어려운 상태 변경 가능성이 있습니다."
    if any(token in normalized for token in MEDIUM_RISK_TOKENS):
        return "medium", "계정이나 서비스 상태를 변경할 수 있어 사용자의 확인이 필요합니다."
    return "low", None


def _shares_risk_intent(goal: str, label: str) -> bool:
    risk_terms = ("해지", "취소", "삭제", "탈퇴", "결제", "구매", "송금", "전송", "동의", "허용")
    if any(term in goal and term in label for term in risk_terms):
        return True
    return any(
        any(trigger in goal for trigger in triggers) and any(hint in label for hint in hints)
        for triggers, hints in INTENT_HINTS
    )


def _text_similarity(left: str, right: str) -> float:
    normalized_left = _normalize(left)
    normalized_right = _normalize(right)
    if not normalized_left or not normalized_right:
        return 0.0
    if normalized_left == normalized_right:
        return 1.0
    if normalized_left in normalized_right or normalized_right in normalized_left:
        return 0.9
    left_tokens = set(TOKEN_PATTERN.findall(left.lower()))
    right_tokens = set(TOKEN_PATTERN.findall(right.lower()))
    token_score = len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))
    sequence_score = SequenceMatcher(None, normalized_left, normalized_right).ratio()
    return max(token_score, sequence_score)


def _normalize(value: str) -> str:
    return "".join(TOKEN_PATTERN.findall(value.lower()))


def _target_function(goal_text: str, label: str) -> str:
    return f"{sanitize_text(goal_text)} 목적을 위한 {sanitize_text(label)} 기능 탐색"


def _view_id_label(view_id: str | None) -> str:
    value = (view_id or "").split("/")[-1]
    return value.replace("_", " ").replace("-", " ")


def _structural_label(element, elements) -> str:
    """Give unlabeled clickable icons a stable, inspectable fallback label.

    Accessibility trees sometimes expose a gear/overflow icon as a clickable
    ImageView with no text, content description, or resource id. Ignoring it
    makes the entire submenu unreachable, so retain it as a positional
    navigation hypothesis. It is still subject to the low-risk exploration
    guard and is never treated as a final state-changing control.
    """
    if not element.bounds or len(element.bounds) != 4:
        return "이름 없는 아이콘"
    max_right = max((item.bounds[2] for item in elements if item.bounds and len(item.bounds) == 4), default=1080)
    max_bottom = max((item.bounds[3] for item in elements if item.bounds and len(item.bounds) == 4), default=2400)
    left, top, right, bottom = element.bounds
    center_x = (left + right) / 2
    center_y = (top + bottom) / 2
    horizontal = "왼쪽" if center_x <= max_right * 0.33 else "오른쪽" if center_x >= max_right * 0.67 else "가운데"
    vertical = "상단" if center_y <= max_bottom * 0.25 else "하단" if center_y >= max_bottom * 0.75 else "중앙"
    return f"이름 없는 {vertical} {horizontal} 아이콘"


def _descendant_label(element_id: str, children_by_parent: dict[str, list]) -> str:
    """Resolve the visible label nested inside a clickable row/container."""
    queue = list(children_by_parent.get(element_id, ()))
    visited: set[str] = set()
    while queue and len(visited) < 24:
        child = queue.pop(0)
        if child.id in visited:
            continue
        visited.add(child.id)
        if child.view_id == "exitguide:ocr":
            continue
        label = sanitize_text(child.text or child.content_description or _view_id_label(child.view_id))
        if label:
            return label
        queue.extend(children_by_parent.get(child.id, ()))
    return ""


def _ocr_descendant_label(
    element_id: str,
    children_by_parent: dict[str, list],
    element_bounds: list[int] | tuple[int, int, int, int] | None = None,
) -> str:
    """Prefer text visibly rendered inside a clickable custom control."""
    queue = list(children_by_parent.get(element_id, ()))
    visited: set[str] = set()
    labels: list[str] = []
    while queue and len(visited) < 32 and len(labels) < 3:
        child = queue.pop(0)
        if child.id in visited:
            continue
        visited.add(child.id)
        if child.view_id == "exitguide:ocr":
            if not _ocr_is_owned_by_clickable(child.bounds, element_bounds):
                continue
            label = sanitize_text(child.text or child.content_description)
            if label and label not in labels:
                labels.append(label)
        queue.extend(children_by_parent.get(child.id, ()))
    return " ".join(labels)


def _prefer_trustworthy_direct_label(direct_label: str, ocr_label: str) -> str:
    """Keep a native label when OCR is only a noisy reading of that label.

    Accessibility text is generally more exact than OCR.  OCR remains useful
    for custom-drawn controls whose accessibility description is stale or
    promotional, so a clearly different visible OCR label may still replace
    the native one.  This comparison is deliberately language-agnostic and
    bounded to the two labels already associated with the same clickable
    control by geometry.
    """

    if not ocr_label:
        return direct_label
    direct_semantics = "".join(
        character.casefold()
        for character in direct_label
        if unicodedata.category(character) != "Cf"
    )
    if (
        ("프로필" in direct_semantics and any(
            marker in direct_semantics for marker in ("관리", "변경")
        ))
        or (
            "profile" in direct_semantics
            and any(
                marker in direct_semantics
                for marker in ("manage", "change", "switch")
            )
        )
    ):
        # A profile header commonly renders the user's display name, while
        # Accessibility describes the actual action (change/manage profile).
        # OCR is visually accurate but semantically weaker in this case and
        # must not replace the navigation meaning with personal text.
        return direct_label
    similarity = _text_similarity(direct_label, ocr_label)
    direct_compact = "".join(direct_label.split())
    ocr_compact = "".join(ocr_label.split())
    if similarity >= 0.72:
        return direct_label
    if (
        similarity >= 0.50
        and max(len(direct_compact), len(ocr_compact)) <= 16
        and abs(len(direct_compact) - len(ocr_compact)) <= 2
    ):
        # One corrupted Hangul syllable can halve the generic similarity of a
        # short label (``선물하기`` -> ``서무하기``).  For compact controls,
        # the native accessibility description is still the more trustworthy
        # source; clearly different visible text continues to use OCR.
        return direct_label
    return ocr_label


def _ocr_is_owned_by_clickable(
    ocr_bounds: list[int] | tuple[int, int, int, int] | None,
    clickable_bounds: list[int] | tuple[int, int, int, int] | None,
) -> bool:
    """Reject OCR rows that merely cross a clickable tab at their centre.

    ML Kit often emits one line for an entire bottom navigation row. The
    Android client associates OCR with the control under the line centre, so
    verify that most of the OCR rectangle actually belongs to that control
    before allowing it to replace the accessibility label.
    """
    if not ocr_bounds or len(ocr_bounds) != 4 or not clickable_bounds or len(clickable_bounds) != 4:
        return True
    ocr_left, ocr_top, ocr_right, ocr_bottom = ocr_bounds
    owner_left, owner_top, owner_right, owner_bottom = clickable_bounds
    ocr_width = max(1, ocr_right - ocr_left)
    ocr_height = max(1, ocr_bottom - ocr_top)
    intersection_width = max(0, min(ocr_right, owner_right) - max(ocr_left, owner_left))
    intersection_height = max(0, min(ocr_bottom, owner_bottom) - max(ocr_top, owner_top))
    overlap = (intersection_width * intersection_height) / (ocr_width * ocr_height)
    return overlap >= 0.68


def _ocr_duplicates_static_native_text(ocr_element, elements) -> bool:
    """Return whether OCR merely duplicated a native non-clickable label.

    Coordinate OCR remains available for genuinely custom-rendered controls.
    It is discarded only when a visible native node exposes essentially the
    same text in the same rectangle and explicitly reports that it is static.
    """

    ocr_label = sanitize_text(ocr_element.text or ocr_element.content_description)
    if not ocr_label or not ocr_element.bounds or len(ocr_element.bounds) != 4:
        return False
    ocr_compact = "".join(ocr_label.casefold().split())
    if len(ocr_compact) < 2:
        return False
    for native in elements:
        if (
            native.id == ocr_element.id
            or native.view_id == "exitguide:ocr"
            or not native.visible
            or not native.enabled
            or native.clickable
            or native.checkable
            or native.password
            or sanitize_text(native.role).casefold()
            in {
                "button",
                "imagebutton",
                "image_button",
                "menuitem",
                "tab",
            }
        ):
            continue
        native_label = sanitize_text(native.text or native.content_description)
        if not native_label:
            continue
        native_compact = "".join(native_label.casefold().split())
        text_matches = bool(
            _text_similarity(ocr_label, native_label) >= 0.84
            or (
                min(len(ocr_compact), len(native_compact)) >= 4
                and (
                    ocr_compact in native_compact
                    or native_compact in ocr_compact
                )
            )
        )
        if text_matches and _ocr_is_owned_by_clickable(
            ocr_element.bounds,
            native.bounds,
        ):
            return True
    return False


def _relative_geometry_discriminator(element, elements) -> str:
    """Return a non-semantic, scale-independent identity for an unlabeled control.

    Geometry is deliberately *not* used to claim that an icon is a gear.  It
    only prevents sibling controls with the same structural fallback label
    from collapsing into one candidate.  Quantization tolerates small layout
    shifts while allowing a stale cached route to fall back when the UI moves
    materially.
    """

    if not element.bounds or len(element.bounds) != 4:
        return f"id:{sanitize_text(element.id)}"
    max_right = max(
        (item.bounds[2] for item in elements if item.bounds and len(item.bounds) == 4),
        default=max(1, element.bounds[2]),
    )
    max_bottom = max(
        (item.bounds[3] for item in elements if item.bounds and len(item.bounds) == 4),
        default=max(1, element.bounds[3]),
    )
    left, top, right, bottom = element.bounds

    def bucket(value: float, extent: int) -> int:
        return max(0, min(31, int(round((value / max(1, extent)) * 31))))

    return ":".join(
        str(value)
        for value in (
            bucket((left + right) / 2, max_right),
            bucket((top + bottom) / 2, max_bottom),
            bucket(max(1, right - left), max_right),
            bucket(max(1, bottom - top), max_bottom),
        )
    )


def _element_key(
    view_id: str | None,
    role: str,
    label: str,
    parent_id: str | None,
    *,
    discriminator: str = "",
) -> str:
    payload = (
        f"{sanitize_text(view_id)}|{role.lower()}|{_normalize(label)}|"
        f"{parent_id or ''}|{discriminator}"
    )
    return f"ue_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}"


def _recommendation_id(
    request: UniversalNavigationObserveRequest,
    screen_fingerprint: str,
    selected_element_id: str | None,
) -> str:
    payload = f"{request.request_id}|{request.session_id}|{screen_fingerprint}|{selected_element_id or 'complete'}"
    return f"ur_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}"


def _exaone_headers(settings: Settings) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {settings.exaone_api_key}",
        "Content-Type": "application/json",
    }
    if settings.exaone_team:
        headers["X-Friendli-Team"] = settings.exaone_team
    return headers

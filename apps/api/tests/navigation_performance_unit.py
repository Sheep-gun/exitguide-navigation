import sqlite3
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.navigation_performance import (
    NavigationPerformanceStore,
    StageMeasurement,
    plan_real_device_import,
)
from app.services.universal_navigation_graph import UniversalNavigationGraphRepository


def main() -> None:
    with TemporaryDirectory(ignore_cleanup_errors=True) as temporary_directory:
        database_path = Path(temporary_directory) / "performance.sqlite"
        store = NavigationPerformanceStore(database_path, minimum_samples=3)
        _record_route(store, "fast-wrong", [900.0, 1_000.0, 1_100.0], correct=False)
        _record_route(store, "slow-safe", [7_000.0, 8_000.0, 9_000.0], correct=True)
        _record_route(store, "fast-safe", [2_500.0, 3_000.0, 3_500.0], correct=True)
        _record_route(
            store,
            "loading-heavy",
            [18_000.0, 20_000.0, 22_000.0],
            correct=True,
            external_wait_ms=17_000.0,
        )
        _record_route(store, "new-fast", [1_500.0], correct=True)
        _record_route(
            store,
            "runtime-only-fast",
            [500.0, 600.0, 700.0, 800.0],
            correct=True,
            validate=False,
        )

        ranked = store.ranked_route_ids(
            app_package="com.exitguide.performance",
            app_version="1.0",
            locale="ko-KR",
            target_function="subscription.cancel.entry",
            start_screen_fingerprint="us_1111111111111111",
        )
        assert ranked == ["fast-safe", "slow-safe", "loading-heavy"], ranked
        assert "fast-wrong" not in ranked
        assert "new-fast" not in ranked
        assert "runtime-only-fast" not in ranked
        assert store.ranked_route_ids(
            app_package="com.exitguide.performance",
            app_version="2.0",
            locale="ko-KR",
            target_function="subscription.cancel.entry",
            start_screen_fingerprint="us_1111111111111111",
        ) == []
        synthetic_summary = store.summary(measurement_source="synthetic")
        assert synthetic_summary["outcome_session_count"] == 17
        assert synthetic_summary["timing_session_count"] == 14
        assert synthetic_summary["trusted_session_count"] == 13
        assert synthetic_summary["destination_accuracy"] == round(10 / 13, 6)

        with sqlite3.connect(database_path) as connection:
            tables = {
                row[0]
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            }
            assert {
                "navigation_sessions",
                "navigation_stage_timings",
                "graph_edge_performance",
                "route_performance",
                "app_version_signatures",
                "route_rankings",
            }.issubset(tables)
            fast = connection.execute(
                "SELECT p50_time_to_destination_ms FROM route_performance WHERE route_id = 'fast-safe'"
            ).fetchone()
            wrong = connection.execute(
                "SELECT eligible FROM route_performance WHERE route_id = 'fast-wrong'"
            ).fetchone()
            new = connection.execute(
                "SELECT under_sampled, eligible FROM route_performance WHERE route_id = 'new-fast'"
            ).fetchone()
            runtime_only = connection.execute(
                """
                SELECT timing_sample_count, trusted_sample_count, under_sampled, eligible
                FROM route_performance WHERE route_id = 'runtime-only-fast'
                """
            ).fetchone()
            loading = connection.execute(
                """
                SELECT p50_time_to_destination_ms, p50_controllable_time_ms
                FROM route_performance WHERE route_id = 'loading-heavy'
                """
            ).fetchone()
            assert fast is not None and round(float(fast[0])) == 3000
            assert wrong is not None and int(wrong[0]) == 0
            assert new is not None and tuple(map(int, new)) == (1, 0)
            assert runtime_only is not None and tuple(map(int, runtime_only)) == (4, 0, 1, 0)
            assert loading is not None and float(loading[0]) == 20_000.0
            assert float(loading[1]) < 2_000.0

        # Every tenth selection checks a verified backup without randomizing
        # normal requests. This keeps alternate routes fresh.
        for _ in range(8):
            store.ranked_route_ids(
                app_package="com.exitguide.performance",
                app_version="1.0",
                locale="ko-KR",
                target_function="subscription.cancel.entry",
                start_screen_fingerprint="us_1111111111111111",
            )
        backup_probe = store.ranked_route_ids(
            app_package="com.exitguide.performance",
            app_version="1.0",
            locale="ko-KR",
            target_function="subscription.cancel.entry",
            start_screen_fingerprint="us_1111111111111111",
        )
        assert backup_probe[0] == "slow-safe", backup_probe

        # If the fastest verified route becomes stale after an app update,
        # the next safe verified route must take over immediately.
        store.invalidate_route("fast-safe")
        recovered = store.ranked_route_ids(
            app_package="com.exitguide.performance",
            app_version="1.0",
            locale="ko-KR",
            target_function="subscription.cancel.entry",
            start_screen_fingerprint="us_1111111111111111",
        )
        assert recovered[0] == "slow-safe", recovered

        imported = store.import_real_device_log(
            {
                "schema_version": 1,
                "measurement_source": "real_device_gold",
                "sessions": [
                    {
                        "session_id": "device-gold-1",
                        "app_package": "com.exitguide.performance",
                        "app_version": "1.0",
                        "locale": "ko-KR",
                        "goal_key": "f" * 16,
                        "target_function": "subscription.cancel.entry",
                        "start_screen_fingerprint": "us_1111111111111111",
                        "destination_screen_fingerprint": "us_2222222222222222",
                        "route_id": "fast-safe",
                        "time_to_destination_ms": 2800,
                        "destination_correct": True,
                        "safe_stop": True,
                        "route_reused": True,
                        "click_count": 2,
                        "stages": [],
                    }
                ],
            }
        )
        assert imported["imported_sessions"] == 1
        real_summary = store.summary(measurement_source="real_device_gold")
        assert real_summary["session_count"] == 1
        assert real_summary["trusted_session_count"] == 1
        assert real_summary["time_to_destination_p50_ms"] == 2800.0
        with sqlite3.connect(database_path) as connection:
            source = connection.execute(
                "SELECT measurement_source FROM route_performance WHERE route_id = 'fast-safe'"
            ).fetchone()
            assert source is not None and source[0] == "real_device_gold"
        try:
            store.record_client_completion(
                session_id="device-gold-1",
                time_to_confirmed_destination_ms=1.0,
                measurement_source="real_device",
            )
        except ValueError as error:
            assert "immutable" in str(error)
        else:
            raise AssertionError("public timing path modified a trusted gold session")
        downgrade_payload = {
            "measurement_source": "real_device",
            "sessions": [_import_session_payload("device-gold-1", route_id="fast-safe")],
        }
        try:
            store.import_real_device_log(downgrade_payload)
        except ValueError as error:
            assert "cannot overwrite trusted" in str(error)
        else:
            raise AssertionError("timing-only import downgraded trusted provenance")

        # A non-gold real-device import is timing evidence only, even if the
        # client claims destination correctness in every record.
        timing_payload = {
            "schema_version": 1,
            "measurement_source": "real_device",
            "sessions": [
                _import_session_payload(f"client-timing-{index}", route_id="client-only")
                for index in range(3)
            ],
        }
        plan = plan_real_device_import(timing_payload)
        assert plan.verification_level == "runtime_inferred"
        first_import = store.import_real_device_plan(plan)
        second_import = store.import_real_device_plan(plan)
        assert first_import["atomic"] is True and second_import["idempotent"] is True
        with sqlite3.connect(database_path) as connection:
            timing_row = connection.execute(
                """
                SELECT timing_sample_count, trusted_sample_count, under_sampled, eligible
                FROM route_performance WHERE route_id = 'client-only'
                """
            ).fetchone()
            session_count = connection.execute(
                "SELECT COUNT(*) FROM navigation_sessions WHERE session_id LIKE 'client-timing-%'"
            ).fetchone()[0]
        assert timing_row is not None and tuple(map(int, timing_row)) == (3, 0, 1, 0)
        assert session_count == 3
        timing_summary = store.summary(measurement_source="real_device")
        assert timing_summary["timing_session_count"] == 3
        assert timing_summary["trusted_session_count"] == 0
        assert timing_summary["destination_accuracy"] == 0.0

        # The whole payload is planned before BEGIN IMMEDIATE, so a late invalid
        # record cannot leave the earlier valid record partially imported.
        malformed_payload = {
            "measurement_source": "real_device_gold",
            "sessions": [
                _import_session_payload("atomic-valid", route_id="atomic-route"),
                {"session_id": "atomic-invalid"},
            ],
        }
        try:
            store.import_real_device_log(malformed_payload)
        except ValueError as error:
            assert "missing device log fields" in str(error)
        else:
            raise AssertionError("partially invalid batch was imported")
        assert store.session("atomic-valid") is None

        try:
            store.apply_validation(
                session_id="client-timing-0",
                destination_correct=True,
                safe_stop=True,
                verification_level="runtime_inferred",
            )
        except ValueError as error:
            assert "provenance" in str(error)
        else:
            raise AssertionError("runtime-inferred correctness was accepted as trusted validation")

        try:
            store.import_real_device_log(
                {
                    "measurement_source": "real_device_gold",
                    "email": "private@example.com",
                    "sessions": [],
                }
            )
        except ValueError as error:
            assert "privacy-sensitive" in str(error)
        else:
            raise AssertionError("privacy-sensitive device log was accepted")

    assert_route_lifecycle_requires_explicit_review()
    assert_verified_candidate_is_provisional_and_version_scoped()
    assert_missing_app_version_can_only_be_filled_once_for_clean_session()
    assert_session_keeps_origin_app_during_cross_app_navigation()
    assert_semantic_wrong_navigation_outcomes_are_counted()

    print("navigation performance checks ok")


def _record_route(
    store: NavigationPerformanceStore,
    route_id: str,
    times: list[float],
    *,
    correct: bool,
    external_wait_ms: float = 0.0,
    validate: bool = True,
    start_index: int = 0,
) -> None:
    for index, elapsed_ms in enumerate(times):
        session_id = f"{route_id}-{index + start_index}"
        store.record_stage(
            session_id=session_id,
            app_package="com.exitguide.performance",
            app_version="1.0",
            locale="ko-KR",
            goal_key="a" * 16,
            target_function="subscription.cancel.entry",
            start_screen_fingerprint="us_1111111111111111",
            current_screen_fingerprint="us_2222222222222222",
            destination_screen_fingerprint="us_2222222222222222",
            decision_mode="route_cache",
            phase="destination_reached",
            action="stop",
            safe_to_execute=False,
            selected_risk_level="medium",
            selected_element_key="ue_terminal",
            route_id=route_id,
            failure_type="",
            measurement=StageMeasurement(
                measurement_source="synthetic",
                server_total_ms=10.0,
                external_wait_ms=external_wait_ms,
                exploration_elapsed_ms=elapsed_ms,
            ),
        )
        if validate:
            store.apply_validation(
                session_id=session_id,
                destination_correct=correct,
                safe_stop=True,
                wrong_clicks=0 if correct else 1,
                failure_type="" if correct else "wrong_menu",
            )


def assert_session_keeps_origin_app_during_cross_app_navigation() -> None:
    with TemporaryDirectory(ignore_cleanup_errors=True) as temporary_directory:
        database_path = Path(temporary_directory) / "cross-app-performance.sqlite"
        store = NavigationPerformanceStore(database_path)
        stage = {
            "session_id": "cross-app-session",
            "app_version": "1.0",
            "locale": "ko-KR",
            "goal_key": "a" * 16,
            "target_function": "subscription.cancel.entry",
            "start_screen_fingerprint": "us_1111111111111111",
            "destination_screen_fingerprint": "",
            "decision_mode": "deterministic_fallback",
            "phase": "exploring",
            "action": "stop",
            "safe_to_execute": False,
            "selected_risk_level": "medium",
            "selected_element_key": "",
            "route_id": "",
            "failure_type": "",
            "measurement": StageMeasurement(measurement_source="synthetic"),
        }
        origin_package = "com.google.android.youtube"
        store.record_stage(
            app_package=origin_package,
            current_screen_fingerprint="us_1111111111111111",
            **stage,
        )
        store.record_stage(
            app_package="com.sec.android.app.sbrowser",
            current_screen_fingerprint="us_2222222222222222",
            **stage,
        )

        with sqlite3.connect(database_path) as connection:
            row = connection.execute(
                """
                SELECT sessions.app_key, signatures.app_key, signatures.app_package
                FROM navigation_sessions AS sessions
                JOIN app_version_signatures AS signatures
                  ON signatures.version_signature = sessions.version_signature
                WHERE sessions.session_id = ?
                """,
                ("cross-app-session",),
            ).fetchone()
        origin_app_key = hashlib.sha256(
            f"{origin_package}|1.0|ko-kr".encode("utf-8")
        ).hexdigest()[:20]
        assert row == (origin_app_key, origin_app_key, origin_package), row


def assert_semantic_wrong_navigation_outcomes_are_counted() -> None:
    with TemporaryDirectory(ignore_cleanup_errors=True) as temporary_directory:
        database_path = Path(temporary_directory) / "semantic-outcomes.sqlite"
        store = NavigationPerformanceStore(database_path)
        common = {
            "session_id": "semantic-wrong-session",
            "app_package": "com.exitguide.performance",
            "app_version": "1.0",
            "locale": "ko-KR",
            "goal_key": "b" * 16,
            "target_function": "notification.settings",
            "start_screen_fingerprint": "us_1111111111111111",
            "destination_screen_fingerprint": "",
            "decision_mode": "function_graph_exploration",
            "phase": "exploring",
            "action": "back",
            "safe_to_execute": True,
            "selected_risk_level": "low",
            "selected_element_key": "",
            "route_id": "",
            "failure_type": "",
            "measurement": StageMeasurement(measurement_source="synthetic"),
        }
        first = store.record_stage(
            current_screen_fingerprint="us_2222222222222222",
            executed_recommendation_id="recommendation-off-target",
            executed_transition_outcome="off_target",
            **common,
        )
        second = store.record_stage(
            current_screen_fingerprint="us_3333333333333333",
            executed_recommendation_id="recommendation-dead-end",
            executed_transition_outcome="dead_end_branch",
            **common,
        )
        duplicate = store.record_stage(
            current_screen_fingerprint="us_3333333333333333",
            executed_recommendation_id="recommendation-dead-end",
            executed_transition_outcome="dead_end_branch",
            **common,
        )

        assert (first.wrong_guidance_delta, first.wrong_click_delta) == (1, 1)
        assert (second.wrong_guidance_delta, second.wrong_click_delta) == (1, 1)
        assert (duplicate.wrong_guidance_delta, duplicate.wrong_click_delta) == (0, 0)
        with sqlite3.connect(database_path) as connection:
            session_counts = connection.execute(
                """
                SELECT wrong_guidance_count, wrong_click_count
                FROM navigation_sessions WHERE session_id = ?
                """,
                ("semantic-wrong-session",),
            ).fetchone()
            outcomes = connection.execute(
                """
                SELECT outcome, wrong_guidance, wrong_click
                FROM navigation_instruction_outcomes
                WHERE session_id = ? ORDER BY outcome
                """,
                ("semantic-wrong-session",),
            ).fetchall()
        assert session_counts == (2, 2), session_counts
        assert outcomes == [
            ("dead_end_branch", 1, 1),
            ("off_target", 1, 1),
        ], outcomes


def _import_session_payload(session_id: str, *, route_id: str) -> dict[str, object]:
    return {
        "session_id": session_id,
        "app_package": "com.exitguide.performance",
        "app_version": "1.0",
        "locale": "ko-KR",
        "goal_key": "c" * 16,
        "target_function": "subscription.cancel.entry",
        "start_screen_fingerprint": "us_1111111111111111",
        "destination_screen_fingerprint": "us_2222222222222222",
        "route_id": route_id,
        "time_to_destination_ms": 1200.0,
        "destination_correct": True,
        "safe_stop": True,
        "route_reused": True,
        "click_count": 2,
        "stages": [],
    }


def assert_route_lifecycle_requires_explicit_review() -> None:
    with TemporaryDirectory(ignore_cleanup_errors=True) as temporary_directory:
        database_path = Path(temporary_directory) / "route-lifecycle.sqlite"
        repository = UniversalNavigationGraphRepository(database_path)
        app_package = "com.exitguide.performance"
        app_version = "1.0"
        locale = "ko-KR"
        app_key = hashlib.sha256(
            f"{app_package}|{app_version}|{locale.lower()}".encode("utf-8")
        ).hexdigest()[:20]
        connection = sqlite3.connect(database_path)
        try:
            connection.execute(
                """
                INSERT INTO universal_apps (
                  app_key, app_package, app_version, locale, first_seen_at, last_seen_at
                ) VALUES (?, ?, ?, ?, 'test', 'test')
                """,
                (app_key, app_package, app_version, locale),
            )
            connection.commit()
        finally:
            connection.close()
        route = repository.save_route(
            app_package=app_package,
            app_version=app_version,
            locale=locale,
            goal_text="구독 해지",
            target_function="subscription.cancel.entry",
            start_screen_fingerprint="us_1111111111111111",
            destination_screen_fingerprint="us_2222222222222222",
            steps=[
                {
                    "ordinal": 0,
                    "from_screen_fingerprint": "us_1111111111111111",
                    "element_key": "ue_subscription",
                    "label": "구독 관리",
                    "function_ids": ["subscription.management.entry"],
                    "expected_to_screen_fingerprint": "us_2222222222222222",
                    "terminal": False,
                    "confidence": 0.9,
                }
            ],
            confidence=0.9,
        )
        assert route.lifecycle_status == "shadow" and route.provisional is True
        with sqlite3.connect(database_path) as connection:
            app_function_row = connection.execute(
                """
                SELECT function_domain, target_function, lifecycle_status,
                  lifecycle_priority, is_serving, step_count
                FROM universal_app_function_routes WHERE route_id = ?
                """,
                (route.route_id,),
            ).fetchone()
        assert app_function_row == (
            "subscription",
            "subscription.cancel.entry",
            "shadow",
            0,
            0,
            1,
        )
        assert repository.route_action(
            app_package=app_package,
            app_version=app_version,
            locale=locale,
            target_function="subscription.cancel.entry",
            screen_fingerprint="us_1111111111111111",
        ) is None


        _record_route(repository.performance, route.route_id, [1000.0, 1100.0], correct=True)
        under_sampled = repository.route(route.route_id)
        assert under_sampled is not None
        assert under_sampled.lifecycle_status == "shadow" and under_sampled.provisional is True
        assert repository.route_action(
            app_package=app_package,
            app_version=app_version,
            locale=locale,
            target_function="subscription.cancel.entry",
            screen_fingerprint="us_1111111111111111",
        ) is None

        # Even after enough clean benchmark-gold evidence makes the route
        # performance-eligible, validation must not promote its lifecycle.
        _record_route(
            repository.performance,
            route.route_id,
            [1200.0],
            correct=True,
            start_index=2,
        )
        benchmark_validated = repository.route(route.route_id)
        assert benchmark_validated is not None
        assert (
            benchmark_validated.lifecycle_status == "shadow"
            and benchmark_validated.provisional is True
        )
        assert repository.route_action(
            app_package=app_package,
            app_version=app_version,
            locale=locale,
            target_function="subscription.cancel.entry",
            screen_fingerprint="us_1111111111111111",
        ) is None

        with sqlite3.connect(database_path) as connection:
            performance = connection.execute(
                """
                SELECT trusted_sample_count, success_count, failure_count,
                  wrong_click_count, eligible, under_sampled
                FROM route_performance WHERE route_id = ?
                """,
                (route.route_id,),
            ).fetchone()
        assert performance == (3, 3, 0, 0, 1, 0), performance

        # Human-gold correction is also performance evidence only. A clean
        # human review must leave the candidate shadow/provisional.
        repository.performance.apply_validation(
            session_id=f"{route.route_id}-0",
            destination_correct=True,
            safe_stop=True,
            wrong_clicks=0,
            failure_type="",
            verification_level="human_gold",
        )
        human_validated = repository.route(route.route_id)
        assert human_validated is not None
        assert human_validated.lifecycle_status == "shadow" and human_validated.provisional is True
        assert repository.route_action(
            app_package=app_package,
            app_version=app_version,
            locale=locale,
            target_function="subscription.cancel.entry",
            screen_fingerprint="us_1111111111111111",
        ) is None

        # A successful destination with a session-level wrong click updates
        # performance truth and serving eligibility, but still does not make
        # an implicit lifecycle rejection. This mirrors the Baemin regression:
        # the wrong click can be outside the saved candidate route steps.
        repository.performance.apply_validation(
            session_id=f"{route.route_id}-0",
            destination_correct=True,
            safe_stop=True,
            wrong_clicks=1,
            failure_type="wrong_menu_before_saved_route",
            verification_level="benchmark_gold",
        )
        validated_with_wrong_click = repository.route(route.route_id)
        assert validated_with_wrong_click is not None
        assert (
            validated_with_wrong_click.lifecycle_status == "shadow"
            and validated_with_wrong_click.provisional is True
        )
        with sqlite3.connect(database_path) as connection:
            performance = connection.execute(
                """
                SELECT success_count, failure_count, wrong_click_count, eligible
                FROM route_performance WHERE route_id = ?
                """,
                (route.route_id,),
            ).fetchone()
        assert performance == (2, 1, 1, 0), performance
        assert repository.route_action(
            app_package=app_package,
            app_version=app_version,
            locale=locale,
            target_function="subscription.cancel.entry",
            screen_fingerprint="us_1111111111111111",
        ) is None

        # Correcting performance truth still does not approve the candidate.
        repository.performance.apply_validation(
            session_id=f"{route.route_id}-0",
            destination_correct=True,
            safe_stop=True,
            wrong_clicks=0,
            failure_type="",
            verification_level="human_gold",
        )
        corrected = repository.route(route.route_id)
        assert corrected is not None
        assert corrected.lifecycle_status == "shadow" and corrected.provisional is True

        # Lifecycle serving requires a separate, explicit approval action.
        approved = repository.approve_route(route.route_id)
        assert approved.lifecycle_status == "approved" and approved.provisional is False
        with sqlite3.connect(database_path) as connection:
            approved_index = connection.execute(
                """
                SELECT lifecycle_status, lifecycle_priority, is_serving
                FROM universal_app_function_routes WHERE route_id = ?
                """,
                (route.route_id,),
            ).fetchone()
        assert approved_index == ("approved", 2, 1)
        assert repository.route_action(
            app_package=app_package,
            app_version=app_version,
            locale=locale,
            target_function="subscription.cancel.entry",
            screen_fingerprint="us_1111111111111111",
        ) is not None

        # Explicit invalidation remains the separate lifecycle operation.
        repository.invalidate_route(route.route_id)
        stale = repository.route(route.route_id)
        assert stale is not None and stale.lifecycle_status == "stale"
        with sqlite3.connect(database_path) as connection:
            stale_index = connection.execute(
                """
                SELECT lifecycle_status, lifecycle_priority, is_serving
                FROM universal_app_function_routes WHERE route_id = ?
                """,
                (route.route_id,),
            ).fetchone()
        assert stale_index == ("stale", 0, 0)
        assert repository.route_action(
            app_package=app_package,
            app_version=app_version,
            locale=locale,
            target_function="subscription.cancel.entry",
            screen_fingerprint="us_1111111111111111",
        ) is None


def assert_verified_candidate_is_provisional_and_version_scoped() -> None:
    with TemporaryDirectory(ignore_cleanup_errors=True) as temporary_directory:
        database_path = Path(temporary_directory) / "verified-candidate.sqlite"
        repository = UniversalNavigationGraphRepository(database_path)
        app_package = "com.exitguide.performance"
        app_version = "1.0"
        locale = "ko-KR"
        app_key = hashlib.sha256(
            f"{app_package}|{app_version}|{locale.lower()}".encode("utf-8")
        ).hexdigest()[:20]
        connection = sqlite3.connect(database_path)
        try:
            connection.execute(
                """
                INSERT INTO universal_apps (
                  app_key, app_package, app_version, locale, first_seen_at, last_seen_at
                ) VALUES (?, ?, ?, ?, 'test', 'test')
                """,
                (app_key, app_package, app_version, locale),
            )
            connection.commit()
        finally:
            connection.close()
        route = repository.save_route(
            app_package=app_package,
            app_version=app_version,
            locale=locale,
            goal_text="구독 해지",
            target_function="subscription.cancel.entry",
            start_screen_fingerprint="us_1111111111111111",
            destination_screen_fingerprint="us_2222222222222222",
            steps=[
                {
                    "ordinal": 0,
                    "from_screen_fingerprint": "us_1111111111111111",
                    "element_key": "ue_subscription",
                    "label": "구독 관리",
                    "function_ids": ["subscription.management.entry"],
                    "role": "button",
                    "risk_level": "low",
                    "expected_to_screen_fingerprint": "us_2222222222222222",
                    "terminal": False,
                    "confidence": 0.9,
                }
            ],
            confidence=0.9,
        )
        _record_route(repository.performance, route.route_id, [900.0], correct=True)
        verified = repository.verify_route_candidate(route.route_id)
        assert verified.lifecycle_status == "verified_candidate"
        assert verified.provisional is True
        match = repository.route_action(
            app_package=app_package,
            app_version=app_version,
            locale=locale,
            target_function="subscription.cancel.entry",
            screen_fingerprint="us_1111111111111111",
        )
        assert match is not None and match[0].route_id == route.route_id
        assert repository.route_action(
            app_package=app_package,
            app_version="2.0",
            locale=locale,
            target_function="subscription.cancel.entry",
            screen_fingerprint="us_1111111111111111",
        ) is None


def assert_missing_app_version_can_only_be_filled_once_for_clean_session() -> None:
    with TemporaryDirectory(ignore_cleanup_errors=True) as temporary_directory:
        database_path = Path(temporary_directory) / "missing-version.sqlite"
        repository = UniversalNavigationGraphRepository(database_path)
        session_id = "legacy-clean-session"
        app_package = "com.sampleapp"
        locale = "ko-KR"
        repository.ensure_app_scope(app_package, "", locale)
        repository.performance.record_stage(
            session_id=session_id,
            app_package=app_package,
            app_version="",
            locale=locale,
            goal_key="d" * 16,
            target_function="notification.settings",
            start_screen_fingerprint="us_1111111111111111",
            current_screen_fingerprint="us_2222222222222222",
            destination_screen_fingerprint="us_2222222222222222",
            decision_mode="function_graph_exploration",
            phase="destination_reached",
            action="stop",
            safe_to_execute=False,
            selected_risk_level="medium",
            selected_element_key="ue_notification",
            route_id="",
            failure_type="",
            measurement=StageMeasurement(
                measurement_source="real_device",
                server_total_ms=10.0,
                exploration_elapsed_ms=1000.0,
            ),
        )
        repository.performance.apply_validation(
            session_id=session_id,
            destination_correct=True,
            safe_stop=True,
            unsafe_clicks=0,
            wrong_clicks=0,
            verification_level="human_gold",
        )
        assert repository.bind_session_missing_app_version(session_id, "16.16.0") == (
            app_package,
            "16.16.0",
            locale,
        )
        with sqlite3.connect(database_path) as connection:
            rebound = connection.execute(
                """
                SELECT apps.app_version, navigation.version_signature
                FROM navigation_sessions AS navigation
                JOIN universal_apps AS apps ON apps.app_key = navigation.app_key
                WHERE navigation.session_id = ?
                """,
                (session_id,),
            ).fetchone()
        assert rebound is not None and rebound[0] == "16.16.0"
        assert str(rebound[1]).startswith("avs_")
        try:
            repository.bind_session_missing_app_version(session_id, "16.17.0")
        except ValueError as error:
            assert "cannot be overwritten" in str(error)
        else:
            raise AssertionError("an existing app version was overwritten")


if __name__ == "__main__":
    main()

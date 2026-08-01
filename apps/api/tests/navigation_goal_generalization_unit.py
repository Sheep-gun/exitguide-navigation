import json
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.navigation_function_catalog import NavigationFunctionCatalog
from app.services.navigation_goal_generalization import evaluate_independent_goals


ROOT = Path(__file__).resolve().parents[3]
CATALOG_PATH = ROOT / "fixtures" / "navigation" / "function-catalog.v1.json"
GYM_ROOT = ROOT / "fixtures" / "navigation" / "db-gym"


def main() -> None:
    productivity_fixture = GYM_ROOT / "public-productivity-system.v1.json"
    productivity_report = evaluate_independent_goals(
        catalog_path=CATALOG_PATH,
        fixture_paths=[productivity_fixture],
    )
    assert productivity_report["total"] == 55
    assert productivity_report["correct"] == 55
    assert productivity_report["accuracy"] == 1.0
    assert productivity_report["generic_rate"] == 0.0

    fixture = GYM_ROOT / "alias-collision-adversarial.v2.json"
    report = evaluate_independent_goals(catalog_path=CATALOG_PATH, fixture_paths=[fixture])
    assert report["catalog_derived"] is False
    assert report["independent_source_accuracy_claim"] is True
    assert report["unseen_holdout_accuracy_claim"] is False
    assert report["total"] == 75
    assert report["correct"] == 75
    assert report["accuracy"] == 1.0
    assert report["generic_rate"] == 0.0

    with TemporaryDirectory() as temporary_directory:
        catalog = NavigationFunctionCatalog(
            Path(temporary_directory) / "catalog.sqlite",
            CATALOG_PATH,
        )
        # Independently worded probes make sure the catalog learned reusable
        # consequence/domain cues, not the 55 frozen benchmark sentences.
        semantic_probes = (
            ("v3_email_archive", "Keep this receipt out of my inbox without deleting the mail"),
            ("v3_email_swipe_actions", "Set a right swipe on mail to archive rather than delete"),
            ("v3_email_signature", "Change the signature added to mail I send from my phone"),
            ("v3_email_vacation_responder", "Let people who email know I am away automatically"),
            ("v3_email_sync", "Sync new mail automatically for this account"),
            ("v3_email_labels", "Open the Gmail label sync and notification choices"),
            ("v3_email_filters", "Automatically apply a label to mail from this sender"),
            ("v3_email_scheduled", "Review scheduled mail waiting to be sent later"),
            ("v3_email_spam", "Review mail the service marked as spam"),
            ("v3_email_forwarding", "Route incoming mail to a second mailbox automatically"),
            ("v3_email_send", "Send the written mail to its recipient"),
            ("v3_calendar_event_create", "Put a new appointment on my calendar"),
            ("v3_calendar_event_edit", "Change the start time of an existing event"),
            ("v3_calendar_event_delete", "Remove an event from the calendar"),
            ("v3_calendar_rsvp", "Respond that I will attend the invited event"),
            ("v3_calendar_notifications", "Make the calendar warn me earlier about an event"),
            ("v3_calendar_shared_calendars", "Choose a shared calendar for a new event"),
            ("v3_maps_directions", "Show directions and estimated time from my current location"),
            ("v3_maps_offline_maps", "Prepare a map I can use without internet"),
            ("v3_maps_saved_lists", "Open my collection of saved places"),
            ("v3_maps_location_sharing", "Show my family my live location for a limited time"),
            ("v3_maps_trip_progress_sharing", "Let a friend see my ETA while navigating"),
            ("v3_maps_incognito", "Use Maps without saving this search history"),
            ("v3_maps_location_history", "Open the Maps timeline of places I visited"),
            ("v3_maps_avoid_options", "Make this route avoid a toll road"),
            ("v3_maps_report_issue", "Send a correction for wrong road information on the map"),
            ("v3_android_notification_history", "Find an alert dismissed earlier today"),
            ("v3_android_privacy_dashboard", "List apps that recently used camera permission"),
            ("v3_android_bluetooth", "Open the system list of nearby Bluetooth accessories"),
            ("v3_android_hotspot", "Share phone data with my laptop through hotspot"),
            ("v3_android_vpn", "Let me choose one of the Android VPN profiles"),
            ("android_app_notifications", "Open notification controls for one noisy app"),
            ("android_notification_categories", "Find one conversation's notification type in the app"),
            ("android_change_permission", "Review camera permission for this app and let me decide"),
            ("v4_android_backup_device_backup", "Control whether this phone backs up to a Google Account"),
            ("v4_android_backup_backup_account", "Switch the Google Account where this backup is stored"),
            ("v4_android_backup_restore_device", "During setup choose a previous backup to restore"),
            ("v4_android_backup_backup_details", "Review backup contents including app data and call history"),
            ("v4_android_backup_manual_backup", "Make a fresh phone backup now before final upload"),
            ("v4_android_backup_transfer_setup", "Transfer data from an old device during new phone setup"),
            ("v4_android_safety_emergency_info", "Put medical emergency information on the lock screen"),
            ("v4_android_safety_emergency_contacts", "Review the people listed as emergency contacts"),
            ("v4_android_safety_sos", "Configure the power button to call for help in an emergency"),
            ("v4_android_safety_safety_check", "Set a safety check timer while walking alone"),
            ("v4_android_safety_crisis_alerts", "Show nearby crisis alerts in the Safety app"),
        )
        assert len(semantic_probes) == 45
        for expected_intent, goal in semantic_probes:
            plan = catalog.plan_goal(goal)
            assert plan.intent == expected_intent, (goal, expected_intent, plan)

        derived_path = Path(temporary_directory) / "derived.json"
        derived_path.write_text(
            json.dumps({"catalog_derived": True, "cases": []}),
            encoding="utf-8",
        )
        try:
            evaluate_independent_goals(catalog_path=CATALOG_PATH, fixture_paths=[derived_path])
        except ValueError as exc:
            assert "not marked independent" in str(exc)
        else:
            raise AssertionError("catalog-derived fixture should have been rejected")
    print(
        "navigation independent goal generalization checks ok: "
        "productivity=55/55 semantic_probes=45/45 alias_collision=75/75"
    )


if __name__ == "__main__":
    main()

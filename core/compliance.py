# core/compliance.py
import yaml
from pathlib import Path
from datetime import datetime, timedelta
from functools import lru_cache

from models.schema import TransactionContext, AgentDecision, ComplianceResult

# Gap 1: Define a set of all actions that touch the customer
CUSTOMER_FACING_ACTIONS = {"send_reminder", "offer_alt_method"}

@lru_cache(maxsize=None) # Gap 5: Cache the YAML read so it only happens once per run
def load_bucket_rules() -> dict:
    config_path = Path(__file__).parent.parent / "config" / "bucket_rules.yaml"
    with open(config_path, "r") as f:
        return yaml.safe_load(f).get("rules", {})

def get_next_available_window(current_time: datetime) -> datetime:
    """Calculates the next safe 8 AM window for communication."""
    if current_time.hour >= 21:
        next_day = current_time + timedelta(days=1)
        return next_day.replace(hour=8, minute=0, second=0, microsecond=0)
    elif current_time.hour < 8:
        return current_time.replace(hour=8, minute=0, second=0, microsecond=0)
    return current_time

def verify_decision(transaction: TransactionContext, decision: AgentDecision) -> ComplianceResult:
    """
    Checks the LLM's decision against hard compliance rules.
    Returns a strongly typed ComplianceResult.
    """
    action = decision.action_selected
    scheduled_for = decision.scheduled_for

    # Gap 3: The Absolute Veto (checked before anything else)
    if transaction.opted_out:
        return ComplianceResult(
            is_compliant=False,
            reason="Absolute Veto: Customer explicitly opted out. All automated recovery blocked.",
            final_action="stop"
        )

    rules = load_bucket_rules()
    bucket = transaction.failure_details.root_cause_bucket
    bucket_config = rules.get(bucket, {})
    
    allowed_actions = bucket_config.get("allowed_actions", ["stop", "escalate_human"])
    max_retries = bucket_config.get("max_retries", 3)
    max_reminders = bucket_config.get("max_reminders", 2)

    # Rule Check: Is the action allowed for this bucket?
    if action not in allowed_actions:
        return ComplianceResult(
            is_compliant=False,
            reason=f"Rule Violation: {action} is not permitted for {bucket}.",
            final_action="stop"
        )

    # Gap 4: Precise Limit Checks
    if action in ["retry_immediate", "retry_scheduled"]:
        if transaction.failure_details.retry_count >= max_retries:
            return ComplianceResult(
                is_compliant=False,
                reason=f"Limit Exceeded: Max bank retries ({max_retries}) reached.",
                final_action="escalate_human"
            )
    elif action in CUSTOMER_FACING_ACTIONS:
        if transaction.failure_details.reminder_count >= max_reminders:
            return ComplianceResult(
                is_compliant=False,
                reason=f"Limit Exceeded: Max customer nudges ({max_reminders}) reached.",
                final_action="escalate_human"
            )

    # Gap 1: Broad DND Check
    if action in CUSTOMER_FACING_ACTIONS and transaction.dnd_active:
        return ComplianceResult(
            is_compliant=False,
            reason="Compliance Violation: Customer is on DND registry. Communication blocked.",
            final_action="stop"
        )

    # Gap 2: Safe Time-of-Day Rescheduling
    if action in CUSTOMER_FACING_ACTIONS:
        current_time = datetime.now() # In production, use transaction timezone
        if current_time.hour < 8 or current_time.hour >= 21:
            safe_time = get_next_available_window(current_time)
            return ComplianceResult(
                is_compliant=False,
                reason=f"Time Violation: Cannot contact outside 8 AM - 9 PM. Rescheduled nudge to {safe_time.isoformat()}.",
                final_action=action,        # We keep the LLM's intended action type
                scheduled_for=safe_time     # We just override WHEN it happens
            )

    # Passed all checks
    return ComplianceResult(
        is_compliant=True,
        reason="All compliance checks passed.",
        final_action=action,
        scheduled_for=scheduled_for
    )
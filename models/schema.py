from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime

class FailureDetails(BaseModel):
    root_cause_bucket: Literal["A_Technical", "B_Recoverable_Customer", "C_Hard_Decline"]
    specific_error: str
    retry_count: int = 0
    reminder_count: int = 0

class TransactionContext(BaseModel):
    transaction_id: str
    customer_id: str
    amount_inr: float
    failure_details: FailureDetails
    dnd_active: bool
    opted_out: bool
    
class AgentDecision(BaseModel):
    llm_reasoning: str = Field(description="Step-by-step reasoning for the chosen action based on the rules.")
    action_selected: Literal[
        "retry_immediate", 
        "retry_scheduled", 
        "send_reminder", 
        "offer_alt_method", 
        "escalate_human", 
        "stop"
    ]
    scheduled_for: Optional[datetime] = Field(None, description="ISO8601 timestamp if scheduling a future action.")
    
class ComplianceResult(BaseModel):
    is_compliant: bool
    reason: str
    final_action: str
    scheduled_for: Optional[datetime] = None

class AuditRecord(BaseModel):
    transaction_id: str
    timestamp: datetime
    state_snapshot: FailureDetails
    decision: AgentDecision
    dnd_passed: bool
    status: str
import os
import json
from pathlib import Path
import google.generativeai as genai
from dotenv import load_dotenv

from models.schema import TransactionContext, AgentDecision

# Load environment variables
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

def load_system_prompt() -> str:
    """Reads the system prompt from the prompts directory."""
    prompt_path = Path(__file__).parent.parent / "prompts" / "decision_engine_prompt.md"
    try:
        with open(prompt_path, "r") as f:
            return f.read()
    except FileNotFoundError:
        # Fallback if file isn't created yet for testing
        return "You are a payment recovery routing AI. Output valid JSON only."

def evaluate_transaction(transaction: TransactionContext) -> AgentDecision:
    """
    Passes the failed transaction to Gemini and forces it to return 
    a structured AgentDecision object.
    """
    system_prompt = load_system_prompt()
    
    # We use gemini-1.5-flash because routing tasks require speed, not deep creative reasoning
    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        system_instruction=system_prompt
    )

    try:
        # Convert the Pydantic model to a JSON string for the prompt
        user_message = transaction.model_dump_json()

        response = model.generate_content(
            user_message,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                response_schema=AgentDecision,
                temperature=0.0,  # 0.0 forces deterministic, non-creative routing
            )
        )
        
        # Parse the guaranteed JSON string back into our Pydantic model
        decision = AgentDecision.model_validate_json(response.text)
        return decision

    except Exception as e:
        # Fallback for API timeouts or unexpected errors - fail safe!
        print(f" LLM Error on {transaction.transaction_id}: {str(e)}")
        return AgentDecision(
            llm_reasoning="Fallback due to LLM failure. Defaulting to safe stop.",
            action_selected="stop",
            scheduled_for=None
        )

# Quick local test block
if __name__ == "__main__":
    from models.schema import FailureDetails
    
    # Dummy transaction to test the pipeline locally
    test_txn = TransactionContext(
        transaction_id="txn_123",
        customer_id="cust_999",
        amount_inr=1500.0,
        failure_details=FailureDetails(
            root_cause_bucket="B_Recoverable_Customer",
            specific_error="insufficient_funds",
            previous_attempts=0
        ),
        dnd_active=False
    )
    
    print("Calling Gemini...")
    result = evaluate_transaction(test_txn)
    print("\nDecision Result:")
    print(result.model_dump_json(indent=2))
from typing import TypedDict, List, Optional

class AgentState(TypedDict, total=False):
    # inputs
    gmail_message_id: str

    # parsed email
    subject: str
    sender: str
    body: str

    # retrieval
    retrieved_chunks: List[str]
    retrieved_context: str

    # outputs
    draft: str
    confidence: float
    done: bool

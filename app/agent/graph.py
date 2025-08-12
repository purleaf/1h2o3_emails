import os, base64
from typing import Dict
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver    
from langgraph.checkpoint.memory import InMemorySaver  
from langchain_openai import ChatOpenAI

from .state import AgentState
from .kb import top_k
from gmail.gmail_utils import gmail_authentication

# --- helpers: Gmail fetch + draft + labels ---

def gmail_fetch_plaintext(gmail_id: str) -> Dict[str, str]:
    """Return {'subject','from','body'} for a Gmail message."""
    service = gmail_authentication()
    msg = service.users().messages().get(userId="me", id=gmail_id, format="full").execute()

    headers = {h["name"].lower(): h["value"] for h in msg["payload"].get("headers", [])}
    subject = headers.get("subject", "")
    sender = headers.get("from", "")

    # naive body extract: plain text in the top-level body or first part
    body = ""
    payload = msg.get("payload", {})
    if "data" in payload.get("body", {}):
        body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", "ignore")
    else:
        for part in payload.get("parts", []) or []:
            if part.get("mimeType", "").startswith("text/plain") and "data" in part.get("body", {}):
                body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", "ignore")
                break

    return {"subject": subject, "from": sender, "body": body}

def gmail_create_draft_and_label(gmail_id: str, draft_text: str, add_label_name: str = "AGENT_DRAFTED", mark_read=True) -> str:
    """Create a Gmail draft reply to the thread and add label; returns draftId."""
    from email.mime.text import MIMEText
    import base64

    service = gmail_authentication()

    # Ensure label exists (get or create)
    labels = service.users().labels().list(userId="me").execute().get("labels", [])
    name_to_id = {l["name"]: l["id"] for l in labels}
    if add_label_name not in name_to_id:
        lbl = service.users().labels().create(userId="me", body={
            "name": add_label_name,
            "labelListVisibility": "labelShow",
            "messageListVisibility": "show"
        }).execute()
        name_to_id[add_label_name] = lbl["id"]
    label_id = name_to_id[add_label_name]

    # Build a reply draft
    msg_meta = service.users().messages().get(userId="me", id=gmail_id, format="metadata").execute()
    thread_id = msg_meta["threadId"]

    mime = MIMEText(draft_text, _subtype="plain", _charset="utf-8")
    mime["In-Reply-To"] = msg_meta["id"]
    raw = base64.urlsafe_b64encode(mime.as_bytes()).decode("utf-8")

    draft = service.users().drafts().create(userId="me", body={
        "message": {"raw": raw, "threadId": thread_id}
    }).execute()
    draft_id = draft["id"]

    # Add label + optionally mark as read
    modify_body = {"addLabelIds": [label_id]}
    if mark_read:
        modify_body["removeLabelIds"] = ["UNREAD"]
    service.users().messages().modify(userId="me", id=gmail_id, body=modify_body).execute()

    return draft_id

# --- Nodes ---

def parse_email_node(state: AgentState) -> AgentState:
    info = gmail_fetch_plaintext(state["gmail_message_id"])
    return {
        **state,
        "subject": info["subject"],
        "sender": info["from"],
        "body": info["body"],
    }

def retrieve_node(state: AgentState) -> AgentState:
    body = state.get("body", "")
    subj = state.get("subject", "")
    q = (subj + "\n" + body).strip()
    chunks = top_k(q, k=3) if q else []
    ctx = "\n\n".join(chunks) if chunks else ""
    return {**state, "retrieved_chunks": chunks, "retrieved_context": ctx}

def draft_node(state: AgentState) -> AgentState:
    """Hello-world draft: uses GPT to generate a concise draft using retrieved context."""
    llm = ChatOpenAI(model=os.getenv("LLM_MODEL", "gpt-4.1"), temperature=0.2)
    prompt = f"""You draft concise, professional replies about spare parts.
If confident, include 1-2 product links from the provided context.
If not confident, ask for model/serial/part number.

Subject: {state.get("subject","")}
From: {state.get("sender","")}
Email body:
{state.get("body","")}

Retrieved context (may be empty):
{state.get("retrieved_context","")}

Return ONLY the draft body text (no JSON, no preface).
"""
    out = llm.invoke(prompt).content.strip()
    # simple confidence heuristic for now
    ####################################
    ####################################
    ####################################
    conf = 0.7 if "http" in out or state.get("retrieved_context") else 0.5
    return {**state, "draft": out, "confidence": conf}
    ####################################
    ####################################
    ####################################
def save_node(state: AgentState) -> AgentState:
    draft_id = gmail_create_draft_and_label(
        state["gmail_message_id"],
        state.get("draft",""),
        add_label_name=os.getenv("DRAFT_LABEL", "AGENT_DRAFTED"),
        mark_read=True  # per your preference
    )
    return {**state, "done": True}

# --- Graph ---

def build_graph(sqlite_path: str = "/app/data/sqlite/checkpoints.db", use_memory=True):
    builder = StateGraph(AgentState)
    builder.add_node("parse", parse_email_node)
    builder.add_node("retrieve", retrieve_node)
    builder.add_node("draft", draft_node)
    builder.add_node("save", save_node)

    builder.set_entry_point("parse")
    builder.add_edge("parse", "retrieve")
    builder.add_edge("retrieve", "draft")
    builder.add_edge("draft", "save")
    builder.add_edge("save", END)

    os.makedirs(os.path.dirname(sqlite_path), exist_ok=True)
    memory = SqliteSaver.from_conn_string(f"sqlite:///{sqlite_path}")
    if use_memory:
        checkpointer = InMemorySaver()                         # quick dev only
    else:
        checkpointer = SqliteSaver.from_conn_string(sqlite_path)

    return builder.compile(checkpointer=checkpointer)

import os, json
from typing import List
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS

DATA_DIR = os.getenv("DATA_DIR", "/app/data")
FAISS_DIR = os.path.join(DATA_DIR, "faiss")
FAISS_INDEX = os.path.join(FAISS_DIR, "index")
EMBED_MODEL = os.getenv("EMBED_MODEL", "text-embedding-3-small")

def _emb() -> OpenAIEmbeddings:
    
    return OpenAIEmbeddings(model=EMBED_MODEL)

def load_or_create() -> FAISS:
    os.makedirs(FAISS_DIR, exist_ok=True)
    if os.path.exists(FAISS_INDEX):
        return FAISS.load_local(FAISS_INDEX, _emb(), allow_dangerous_deserialization=True)
    # create empty
    return FAISS.from_texts(["Hello KB"], _emb())  # tiny seed so retriever initializes

def persist(vs: FAISS):
    vs.save_local(FAISS_INDEX)

def add_texts(texts: List[str]) -> int:
    vs = load_or_create()
    vs.add_texts(texts)
    persist(vs)
    return len(texts)

def top_k(query: str, k: int = 3) -> List[str]:
    vs = load_or_create()
    docs = vs.similarity_search(query, k=k)
    return [d.page_content for d in docs]

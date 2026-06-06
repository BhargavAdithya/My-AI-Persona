import os
from sentence_transformers import SentenceTransformer
import chromadb

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VECTOR_DIR = os.path.join(BASE_DIR, "vector_db")

print(f"[VectorStore] Loading from: {VECTOR_DIR}")

embedding_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

client = chromadb.PersistentClient(path=VECTOR_DIR)

collection = client.get_or_create_collection(name="candidate_knowledge")


def embed_query(text: str) -> list[float]:
    return embedding_model.encode([text])[0].tolist()


def get_collection():
    return collection
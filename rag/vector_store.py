import os
import chromadb
from sentence_transformers import SentenceTransformer

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

embedding_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

client = chromadb.PersistentClient(path=os.path.join(BASE_DIR, "vector_db"))

collection = client.get_or_create_collection(name="candidate_knowledge")


def embed_query(text: str) -> list[float]:
    return embedding_model.encode([text])[0].tolist()


def get_collection():
    return collection
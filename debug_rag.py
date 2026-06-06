import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rag.vector_store import get_collection, embed_query

collection = get_collection()

# Check total chunks stored
count = collection.count()
print(f"\n✅ Total chunks in vector DB: {count}")

# Check what sources are stored
results = collection.get(include=["metadatas"], limit=1000)
sources = set()
for meta in results["metadatas"]:
    sources.add(meta.get("source", "unknown"))

print(f"\n📁 Unique sources ({len(sources)}):")
for s in sorted(sources):
    print(f"   {s}")

# Test retrieval for each project
test_queries = [
    "LandCoverClassification project",
    "floravision plant detection",
    "TALENTSCOUT recruitment",
    "hospital management system",
    "expense management",
    "lulc-dl land use",
    "education degree college",
    "skills programming languages",
]

print("\n🔍 Retrieval test:")
for query in test_queries:
    embedding = embed_query(query)
    res = collection.query(
        query_embeddings=[embedding],
        n_results=3,
        include=["documents", "metadatas", "distances"]
    )
    print(f"\n  Query: '{query}'")
    for doc, meta, dist in zip(
        res["documents"][0],
        res["metadatas"][0],
        res["distances"][0]
    ):
        print(f"    [{dist:.3f}] {meta.get('source','?')[:80]}")
        print(f"           {doc[:100].strip()}...")
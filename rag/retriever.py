import os
from rag.vector_store import get_collection, embed_query

REPO_KEYWORDS = {
    "LandCoverClassification": [
        "landcover", "land cover", "land-cover", "lulc classification",
        "sentinel", "satellite imagery", "remote sensing", "ndvi", "ndwi",
        "segmentation", "multispectral"
    ],
    "floravision": [
        "floravision", "flora", "plant", "flower", "garden",
        "nursery", "aglaonema", "trending plants", "o2 plants"
    ],
    "hospital-management": [
        "hospital", "medical", "patient", "doctor", "appointment",
        "healthcare", "clinic", "nurse", "role-based"
    ],
    "Expenese-Management": [
        "expense", "expenese", "budget", "finance", "money",
        "approval", "currency", "ocr", "receipt", "reimbursement"
    ],
    "lulc-dl": [
        "lulc", "lulc-dl", "land use", "land-use", "deep learning model",
        "unet", "segmentation model", "satellite"
    ],
    "TALENTSCOUT": [
        "talentscout", "talent scout", "talent", "scout",
        "recruitment", "hiring", "resume screening", "candidate",
        "interview questions", "job"
    ],
}


def retrieve(query: str, n_results: int = 8) -> list[dict]:
    collection = get_collection()
    query_embedding = embed_query(query)

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=n_results,
        include=["documents", "metadatas", "distances"]
    )

    retrieved = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0]
    ):
        retrieved.append({
            "content": doc,
            "source": meta.get("source", "unknown"),
            "distance": dist
        })

    return retrieved


def detect_repo(query: str) -> str | None:
    query_lower = query.lower()
    for repo, keywords in REPO_KEYWORDS.items():
        if any(kw in query_lower for kw in keywords):
            return repo
    return None


def retrieve_for_query(query: str, n_results: int = 8) -> list[dict]:
    """
    Smart retrieval:
    1. Detects if query targets a specific repo
    2. If yes: fetches ALL chunks from that repo's README + key files
       then fills remaining slots with general semantic search
    3. If no: pure semantic search across all sources
    """
    collection = get_collection()
    matched_repo = detect_repo(query)

    if matched_repo:
        # Get ALL chunks from this repo directly by metadata filter
        try:
            all_docs = collection.get(
                include=["documents", "metadatas"]
            )

            repo_chunks = []
            for doc, meta in zip(all_docs["documents"], all_docs["metadatas"]):
                source = meta.get("source", "")
                if matched_repo.lower() in source.lower():
                    repo_chunks.append({
                        "content": doc,
                        "source": source,
                        "distance": 0.0
                    })

            # Prioritise README and commits for this repo
            readme_chunks = [c for c in repo_chunks if "readme" in c["source"].lower()]
            commit_chunks = [c for c in repo_chunks if "commits" in c["source"].lower()]
            code_chunks   = [c for c in repo_chunks if c not in readme_chunks and c not in commit_chunks]

            # Build ordered list: readme first, then commits, then code
            ordered = readme_chunks + commit_chunks + code_chunks

            # Also run semantic search to catch resume mentions of this repo
            semantic = retrieve(query, n_results=4)
            semantic_filtered = [
                c for c in semantic
                if matched_repo.lower() not in c["source"].lower()
            ]

            combined = ordered[:6] + semantic_filtered[:2]
            return combined[:n_results]

        except Exception as e:
            print(f"[Retriever] Repo filter failed: {e}")
            return retrieve(query, n_results=n_results)

    # No specific repo detected — semantic search
    return retrieve(query, n_results=n_results)


def format_context(chunks: list[dict]) -> str:
    parts = []
    seen = set()

    for i, chunk in enumerate(chunks, 1):
        content = chunk["content"].strip()
        if not content or content in seen:
            continue
        seen.add(content)

        source = chunk["source"]
        # Shorten path to repo/filename only
        source = source.replace("\\", "/")
        if "github_repos" in source:
            parts_list = source.split("github_repos/")
            source = parts_list[-1] if len(parts_list) > 1 else source
        elif "commits" in source:
            source = os.path.basename(source)
        elif "resume" in source.lower():
            source = "resume.pdf"

        parts.append(f"[{source}]\n{content}")

    return "\n\n---\n\n".join(parts)
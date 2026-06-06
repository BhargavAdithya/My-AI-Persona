import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from voice_agent.voice import app
from fastapi.responses import JSONResponse

@app.get("/debug")
async def debug():
    """Check if vector DB is loaded and has data."""
    try:
        from rag.vector_store import get_collection
        collection = get_collection()
        count = collection.count()
        
        # Check if data files exist
        base = os.path.dirname(os.path.abspath(__file__))
        resume_exists = os.path.exists(os.path.join(base, "data", "resume"))
        commits_exists = os.path.exists(os.path.join(base, "data", "commits"))
        repos_exists = os.path.exists(os.path.join(base, "data", "github_repos"))
        vector_db_exists = os.path.exists(os.path.join(base, "vector_db"))

        return JSONResponse({
            "vector_db_chunks": count,
            "vector_db_exists": vector_db_exists,
            "resume_dir_exists": resume_exists,
            "commits_dir_exists": commits_exists,
            "repos_dir_exists": repos_exists,
            "cwd": os.getcwd(),
            "base_dir": base
        })
    except Exception as e:
        return JSONResponse({"error": str(e)})
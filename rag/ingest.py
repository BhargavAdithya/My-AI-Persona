import os
from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer
import chromadb

# ==========================
# PATHS
# ==========================

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

RESUME_DIR = os.path.join(BASE_DIR, "data", "resume")
REPOS_DIR = os.path.join(BASE_DIR, "data", "github_repos")
COMMITS_DIR = os.path.join(BASE_DIR, "data", "commits")

# ==========================
# LOAD MODEL
# ==========================

embedding_model = SentenceTransformer(
    "sentence-transformers/all-MiniLM-L6-v2"
)

# ==========================
# CHROMA
# ==========================

client = chromadb.PersistentClient(
    path=os.path.join(BASE_DIR, "vector_db")
)

collection = client.get_or_create_collection(
    name="candidate_knowledge"
)

# ==========================
# LOAD DOCUMENTS
# ==========================

documents = []

# Resume
for file in os.listdir(RESUME_DIR):

    if file.endswith(".pdf"):

        pdf_path = os.path.join(RESUME_DIR, file)

        reader = PdfReader(pdf_path)

        text = ""

        for page in reader.pages:
            text += page.extract_text() + "\n"

        documents.append(
            {
                "source": file,
                "content": text
            }
        )

# Commit Files
for file in os.listdir(COMMITS_DIR):

    if file.endswith(".txt"):

        path = os.path.join(COMMITS_DIR, file)

        with open(path, "r", encoding="utf-8", errors="ignore") as f:

            documents.append(
                {
                    "source": file,
                    "content": f.read()
                }
            )

# GitHub Repositories
for repo in os.listdir(REPOS_DIR):

    repo_path = os.path.join(REPOS_DIR, repo)

    for root, dirs, files in os.walk(repo_path):

        dirs[:] = [
            d for d in dirs
            if d not in [
                ".git",
                "__pycache__",
                "node_modules",
                ".next",
                "venv",
                ".venv",
                "build",
                "dist"
            ]
        ]

        for file in files:

            if file.endswith((
                ".md",
                ".txt",
                ".py",
                ".js",
                ".jsx",
                ".ts",
                ".tsx",
                ".json"
            )):

                file_path = os.path.join(root, file)
                print(file_path)

                try:

                    with open(
                        file_path,
                        "r",
                        encoding="utf-8",
                        errors="ignore"
                    ) as f:
                        
                        content = f.read()

                        if len(content.strip()) > 0:

                            documents.append(
                                {
                                    "source": file_path,
                                    "content": content
                                }
                            )

                except Exception as e:
                    print(f"Skipped {file_path}: {e}")

print(f"Loaded {len(documents)} documents")

# ==========================
# CHUNKING
# ==========================

splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200
)

chunks = []

for doc in documents:

    split_text = splitter.split_text(
        doc["content"]
    )

    for chunk in split_text:

        chunks.append(
            {
                "source": doc["source"],
                "content": chunk
            }
        )

print(f"Created {len(chunks)} chunks")

# ==========================
# EMBEDDINGS
# ==========================

texts = [c["content"] for c in chunks]

embeddings = embedding_model.encode(
    texts,
    show_progress_bar=True
)

# ==========================
# STORE
# ==========================

for i, (chunk, embedding) in enumerate(
    zip(chunks, embeddings)
):

    collection.add(
        ids=[f"doc_{i}"],
        embeddings=[embedding.tolist()],
        documents=[chunk["content"]],
        metadatas=[
            {
                "source": chunk["source"]
            }
        ]
    )

print("Vector database created successfully.")
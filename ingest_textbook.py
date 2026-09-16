import os
import json
from langchain_ollama import OllamaEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document

# Embedding engine
MODEL_EMBED = "bge-m3"
embeddings = OllamaEmbeddings(model=MODEL_EMBED)

def ingest_from_json():
    # Remove existing database to avoid conflicts
    import shutil
    persist_directory = "data/chroma_db"
    if os.path.exists(persist_directory):
        print(f"🗑️ Removing existing database: {persist_directory}")
        shutil.rmtree(persist_directory)

    # Load lesson_1_database.json
    db_path = "lesson_1_database.json"
    if not os.path.exists(db_path):
        print(f"❌ Error: Could not find {db_path}")
        return

    print(f"📖 Loading {db_path}...")
    with open(db_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    pages = data.get("pages", {})
    book_metadata = data.get("book_metadata", {})

    print(f"📚 Book: {book_metadata.get('lesson', 'Unknown')}")
    print(f"📄 Pages to process: {len(pages)}")

    documents_pool = []
    for page_key, page_data in pages.items():
        page_number = page_data.get("page_number", 0)
        raw_text = page_data.get("raw_text", "")
        
        # Use page number as the label (e.g., "44", "45", etc.)
        page_label = str(page_number)
        
        if not raw_text:
            print(f"  ⚠️ Skipping page {page_number}: no raw_text")
            continue

        doc_node = Document(
            page_content=raw_text.strip(),
            metadata={
                "page_label": page_label,
                "page_key": page_key,
                "source": db_path
            }
        )
        documents_pool.append(doc_node)

    if not documents_pool:
        print("⚠️ Warning: No valid pages found in JSON file.")
        return

    print(f"🧠 Indexing {len(documents_pool)} pages into Chroma database using {MODEL_EMBED}...")
    
    vector_db = Chroma.from_documents(
        documents=documents_pool,
        embedding=embeddings,
        persist_directory=persist_directory
    )
    print(f"✅ Success! Vector database created inside: {persist_directory}")

if __name__ == "__main__":
    ingest_from_json()

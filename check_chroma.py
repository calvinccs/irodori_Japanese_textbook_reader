import os
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings

CHROMA_PATH = "data/chroma_db"
MODEL_EMBED = "bge-m3"

print("🔍 Scanning local data directory...")
if not os.path.exists(CHROMA_PATH):
    print("❌ ERROR: The 'data/chroma_db' folder does not exist on your drive!")
else:
    print("✅ Found 'data/chroma_db' folder.")
    embeddings = OllamaEmbeddings(model=MODEL_EMBED)
    
    try:
        db = Chroma(persist_directory=CHROMA_PATH, embedding_function=embeddings)
        data = db.get()
        
        total_chunks = len(data.get("documents", []))
        print(f"📊 Total database records found: {total_chunks}")
        
        if total_chunks > 0:
            print("\n🏷️  Available Page Labels in your database:")
            labels = set(meta.get("page_label") for meta in data.get("metadatas", []) if "page_label" in meta)
            for idx, label in enumerate(sorted(list(labels)), 1):
                print(f"  {idx}. {label}")
        else:
            print("⚠️ WARNING: The database is completely empty. Run your ingestion script!")
            
    except Exception as e:
        print(f"❌ DATABASE ERROR: {e}")

# Yuki-sensei Tutor - Feedback & Improvement Log

## Session: 2026-09-08

### Feedback Received

#### 1. RAG Quality Issues
- **Problem**: RAG contains incomplete page information
- **Cause**: Images and tables in PDFs make text extraction difficult
- **Current State**: Page dropdown selection and content loading works correctly, but extracted text is incomplete

#### 2. Response Speed
- **Problem**: Chat replies take a long time to generate
- **Possible Causes**:
  - Qwen 3.6-35B is a large model (35B parameters)
  - Long context windows from textbook content
  - Ollama embedding model overhead

### Potential Improvements

#### RAG Quality
- [ ] Improve PDF parsing to better extract tables and text around images
- [ ] Add image descriptions using a vision model for page images
- [ ] Chunk pages into smaller sections (by dialogue, vocabulary, etc.) for more precise retrieval
- [ ] Consider using a different parsing library (e.g., pdfplumber with table extraction)

#### Response Speed
- [ ] Use a smaller/faster model in LM Studio
- [ ] Reduce the context window or add response time limits
- [ ] Cache the initial greeting response to avoid regenerating it
- [ ] Check if the Ollama embedding model is causing slowdowns
- [ ] Implement response streaming for better perceived performance

#### UI/UX
- [ ] Add loading indicators for RAG retrieval
- [ ] Show page preview/thumbnail when selecting from dropdown
- [ ] Add pagination or page grouping for large textbooks

---

*Add new feedback entries below with date and description*
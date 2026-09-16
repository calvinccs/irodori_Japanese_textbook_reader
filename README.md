# Yuki-sensei: Just-In-Time Japanese Language Tutor

An interactive, AI-powered Japanese language tutor built with Streamlit and Qwen2.5-VL. This application uses a **Just-In-Time page-matching architecture** — no pre-extracted PDF database needed. Pages are analyzed on-the-fly when dropped into the app.

## 🌟 Features

*   **Just-In-Time Page Analysis**: Drop any textbook page image → Qwen2.5-VL instantly extracts vocabulary, dialogue, grammar, and audio tags.
*   **Split-Screen Layout**: Left panel for page viewing, right panel for interactive chat.
*   **Roleplay Conversations**: Yuki-sensei auto-initializes as a dialogue partner from the page content.
*   **Streaming Responses**: Real-time token streaming for fast perceived performance.
*   **Text-Only Chat History**: Heavy image data is stripped after initial analysis to keep the local model fast.
*   **Multilingual Support**: Responses include Japanese script (Kanji/Kana), Romaji, and English translations.

## 🛠️ Tech Stack

*   **Frontend**: [Streamlit](https://streamlit.io/)
*   **Vision LLM**: [Qwen2.5-VL](https://ollama.com/library/qwen2.5-vl) via LM Studio
*   **API**: OpenAI-compatible REST API (via `requests`)
*   **Language**: Python 3.12+
*   **Dependency Manager**: [uv](https://github.com/astral-sh/uv)

## 🚀 Getting Started

### Prerequisites

*   Python 3.12+
*   [uv](https://github.com/astral-sh/uv) (recommended for dependency management)
*   [LM Studio](https://lmstudio.ai/) with **Qwen2.5-VL** loaded
    *   LM Studio is running on `http://localhost:7749` (default)

### Installation & Setup

1.  **Clone the repository:**
    ```bash
    git clone <repository_url>
    cd irodori_graph_tutor
    ```

2.  **Install dependencies using `uv`:**
    ```bash
    uv sync
    ```

3.  **Run the application:**
    ```bash
    streamlit run app.py
    ```

4.  **Drop a textbook page image** into the left panel to start learning!

## 📐 Architecture

```
User drops page image → Base64 encode → Qwen2.5-VL (LM Studio)
                                        ↓
                              Structured JSON extraction
                              (vocab, dialogue, grammar, tags)
                                        ↓
                              Context injected into chat system prompt
                                        ↓
                              Text-only streaming conversation
                              (images stripped after init)
```

## ⚙️ Configuration

Edit these values at the top of `app.py` if needed:

| Variable | Default | Description |
|----------|---------|-------------|
| `LM_STUDIO_URL` | `http://localhost:7749/v1/chat/completions` | LM Studio API endpoint |
| `LM_STUDIO_MODEL` | `qwen2.5-vl-7b-instruct` | Model name in LM Studio |
| `MAX_CHAT_HISTORY` | `30` | Max chat messages to retain |

"""
Yuki-sensei: Just-In-Time Japanese Language Tutor
=================================================
A split-screen desktop app for interactive Japanese learning with Qwen2.5-VL
via LM Studio. Pages are analyzed on-the-fly — no pre-extracted database needed.

Usage:
    streamlit run app.py

LM Studio must be running at http://localhost:7749/v1 with Qwen2.5-VL loaded.
"""

import streamlit as st
import base64
import os
import json
import requests
import re
import io
import fitz  # PyMuPDF
from PIL import Image

# ============================================================
# CONFIGURATION
# ============================================================
LM_STUDIO_URL = "http://localhost:7749/v1/chat/completions"
LM_STUDIO_MODEL = "qwen2.5-vl-7b-instruct"
MAX_CHAT_HISTORY = 30
AUDIO_BASE_DIR = "/mnt/C4F2195BF2195352/projects/irodori_materials"

# Default textbook PDF paths (in order of preference)
DEFAULT_PDF_PATHS = [
    "japanese_textbook.pdf",
    os.path.join("..", "irodori_materials", "A1.pdf"),
    os.path.join("irodori_materials", "A1.pdf"),
]

# Find first existing PDF
DEFAULT_PDF = None
for p in DEFAULT_PDF_PATHS:
    if os.path.exists(p):
        DEFAULT_PDF = os.path.abspath(p)
        break
if not DEFAULT_PDF:
    DEFAULT_PDF = os.path.join(AUDIO_BASE_DIR, "A1.pdf")  # fallback

# ============================================================
# AUDIO LOOKUP HELPER
# ============================================================
def find_audio_track(track_id: str, pdf_path: str = "") -> list[str]:
    """Find MP3 files for a given track ID in the PDF-specific audio directory.

    Determines the target directory dynamically from the PDF filename.
    e.g. A1.pdf -> audio_A1, A2-1.pdf -> audio_A2-1

    Args:
        track_id: Track ID like '01-34'
        pdf_path: Path to the active PDF (used to derive the audio directory)

    Returns:
        List of absolute file paths to matching MP3 files.
    """
    # Derive audio directory from PDF filename
    if pdf_path:
        pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]
        target_dir = os.path.join(AUDIO_BASE_DIR, f"audio_{pdf_name}")
    else:
        target_dir = AUDIO_BASE_DIR

    # Only search the specific audio directory (no recursion into subfolders)
    bracket_pattern = re.compile(rf"\[{re.escape(track_id)}\]", re.IGNORECASE)
    found_files = []

    try:
        for filename in os.listdir(target_dir):
            if filename.lower().endswith(".mp3") and bracket_pattern.search(filename):
                found_files.append(os.path.join(target_dir, filename))
    except FileNotFoundError:
        pass

    return found_files


def find_video_track(track_id: str, pdf_path: str = "") -> str | None:
    """Find an MP4 video file for a given track ID in the PDF-specific video directory.

    Determines the target directory dynamically from the PDF filename.
    e.g. A1.pdf -> video_A1, A2-1.pdf -> video_A2-1

    Args:
        track_id: Track ID like '01-34'
        pdf_path: Path to the active PDF (used to derive the video directory)

    Returns:
        Absolute file path to the matching MP4 file, or None if not found.
    """
    # Derive video directory from PDF filename
    if pdf_path:
        pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]
        target_dir = os.path.join(AUDIO_BASE_DIR, f"video_{pdf_name}")
    else:
        target_dir = AUDIO_BASE_DIR

    # Only search the specific video directory (no recursion)
    bracket_pattern = re.compile(rf"\[{re.escape(track_id)}\]", re.IGNORECASE)
    found_files = []

    try:
        for filename in os.listdir(target_dir):
            if filename.lower().endswith(".mp4") and bracket_pattern.search(filename):
                found_files.append(os.path.join(target_dir, filename))
    except FileNotFoundError:
        pass

    # Return the first match (or None if none found)
    return found_files[0] if found_files else None


def parse_audio_tags_from_analysis(page_info: dict) -> list[str]:
    """Extract unique audio track IDs from the page analysis result.

    Uses strict \\b\\d{2}-\\d{2}\\b regex to find exactly MM-NN format IDs.
    Handles both list format ['01-34', '01-35'] and string format '01-34, 01-35'.
    """
    TRACK_ID_PATTERN = re.compile(r"\b\d{2}-\d{2}\b")

    tags = page_info.get("audio_tags", [])
    if isinstance(tags, str):
        # Split comma-separated string first
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    elif not isinstance(tags, list):
        tags = []

    # Normalize: extract only valid MM-NN track IDs using strict word-boundary regex
    normalized = []
    for tag in tags:
        match = TRACK_ID_PATTERN.search(str(tag))
        if match:
            normalized.append(match.group(0))
        elif tag.strip():
            normalized.append(tag.strip())

    return list(dict.fromkeys(normalized))  # Deduplicate while preserving order


def render_pdf_page_to_image(pdf_path: str, page_number: int) -> bytes:
    """Render a single PDF page to a PNG image at 2.5x scale for crystal-clear UI display.
    
    Args:
        pdf_path: Path to the PDF file
        page_number: 1-based page number to render
    
    Returns:
        PNG image bytes
    """
    doc = fitz.open(pdf_path)
    
    # Clamp page number
    if page_number < 1:
        page_number = 1
    if page_number > doc.page_count:
        page_number = doc.page_count
    
    page = doc[page_number - 1]
    
    # Render at 2.5x scale (~200 DPI) — sharp enough for tiny Furigana characters
    zoom = 2.5
    matrix = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=matrix)
    # Convert to PNG bytes (no scaling — raw, uncompressed for the UI viewer)
    img_data = pix.tobytes("png")

    doc.close()
    return img_data



def get_rendered_image_bytes(pdf_path: str, page_number: int) -> bytes | None:
    """Get rendered page bytes, with caching via session state."""
    cache_key = f"pdf_page_{pdf_path}_{page_number}"
    if cache_key not in st.session_state:
        try:
            st.session_state[cache_key] = render_pdf_page_to_image(pdf_path, page_number)
        except Exception:
            st.session_state[cache_key] = None
    return st.session_state[cache_key]

def get_ai_ready_image_bytes(pdf_path: str, page_number: int) -> bytes | None:
    """Render a PDF page and downscale it for AI/VLM ingestion.

    Produces a high-res image in memory (cached), then caps the longest edge
    at 1024px to keep the base64 payload lightweight for Qwen2.5-VL.

    Args:
        pdf_path: Path to the PDF file
        page_number: 1-based page number to render

    Returns:
        Downscaled PNG image bytes, or None on failure
    """
    # Render high-res page (cached via get_rendered_image_bytes)
    high_res_bytes = get_rendered_image_bytes(pdf_path, page_number)
    if high_res_bytes is None:
        return None

    # Decode, resize, re-encode
    img = Image.open(io.BytesIO(high_res_bytes))
    max_edge = max(img.width, img.height)
    if max_edge > 1024:
        scale = 1024 / max_edge
        new_w = int(img.width * scale)
        new_h = int(img.height * scale)
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ============================================================
# INITIALIZATION
# ============================================================
st.set_page_config(
    page_title="Yuki-sensei: JIT Japanese Tutor",
    page_icon="\U0001f1ef\U0001f1f5",
    layout="wide",
)

st.title("\U0001f1ef\U0001f1f5 Yuki-sensei: Just-In-Time Japanese Tutor")
st.caption(
    "Browse your textbook on the left \u2192 Click '[\u2728 Learn This Page]' \u2192 Yuki-sensei analyzes it and starts a roleplay conversation."
)

# ============================================================
# SESSION STATE
# ============================================================
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "page_info" not in st.session_state:
    st.session_state.page_info = None
if "image_analyzed" not in st.session_state:
    st.session_state.image_analyzed = False
if "current_page_label" not in st.session_state:
    st.session_state.current_page_label = None
if "audio_files" not in st.session_state:
    st.session_state.audio_files = {}
if "pdf_path" not in st.session_state:
    st.session_state.pdf_path = DEFAULT_PDF
if "current_page" not in st.session_state:
    st.session_state.current_page = 44

# ============================================================
# PDF PATH CONFIGURATION
# ============================================================
with st.container():
    st.subheader("\U0001f4c1 Textbook PDF")
    pdf_path = st.text_input(
        "PDF Path",
        value=st.session_state.pdf_path,
        help="Path to your Japanese textbook PDF. Defaults to japanese_textbook.pdf in this folder.",
    )
    if pdf_path and pdf_path != st.session_state.pdf_path:
        st.session_state.pdf_path = pdf_path
        st.session_state.current_page = 44
        st.rerun()
    
    # Validate PDF
    if pdf_path and os.path.exists(pdf_path):
        try:
            doc = fitz.open(pdf_path)
            total_pages = doc.page_count
            doc.close()
            st.success(f"\u2705 PDF loaded: {os.path.basename(pdf_path)} ({total_pages} pages)")
        except Exception as e:
            st.error(f"\u274c Invalid PDF: {e}")
            total_pages = 0
    elif pdf_path:
        st.warning(f"\u274c File not found: {pdf_path}")
        total_pages = 0
    else:
        st.info("Enter a PDF path above to get started.")
        total_pages = 0


# ============================================================
# SYSTEM PROMPTS
# ============================================================
PAGE_ANALYSIS_SYSTEM_PROMPT = (
    "You are a supportive, patient Japanese tutor for a beginner/intermediate student.\n\n"
    "When given an image of a Japanese language textbook page, extract and "
    "structure the following information:\n\n"
    "1. **Topic** – Main theme of the page.\n"
    "2. **Vocabulary** – Key words with Japanese (Kanji/Kana), Romaji, English.\n"
    "3. **Dialogue** – Conversations with speaker labels, Romaji, translations.\n"
    "4. **Grammar** – Rules and explanations covered.\n"
    "5. **Audio Tags** – Any audio track references found on the page. Use the format MM-NN (two-digit chapter-two-digit track), e.g. 01-34. These correspond to audio files named like X_[01-34]_name.mp3.\n"
    "6. **Exercises** – Practice activities mentioned.\n\n"
    "IMPORTANT RESPONSE RULES:\n"
    "- Never write a response completely in Japanese. Always provide an English translation right below your Japanese sentences.\n"
    "- Use Romaji brackets for complex Kanji so the student can read it (e.g., 漢字【かんじ】).\n"
    "- Keep your questions simple. Ask the student to repeat a basic vocabulary word or fill in a single missing particle from the textbook page, rather than asking for open-ended explanations.\n\n"
    "Return ONLY a valid JSON object with these keys: "
    "'topic', 'vocabulary', 'dialogue', 'grammar', 'audio_tags', 'exercises'. "
    "Do NOT include markdown code fences or any text outside the JSON."
)

ROLEPLAY_SYSTEM_PROMPT = (
    "You are 'Yuki-sensei', a supportive and patient Japanese tutor for a beginner/intermediate student.\n\n"
    "You are roleplaying a conversation with a student using material from "
    "a specific textbook page.\n\n"
    "RULES:\n"
    "- Always stay in character as the dialogue partner from the textbook.\n"
    "- Never write a response completely in Japanese. Always provide an English translation right below your Japanese sentences.\n"
    "- Use Romaji brackets for complex Kanji so the student can read it (e.g., 漢字【かんじ】).\n"
    "- Keep your questions simple. Ask the student to repeat a basic vocabulary word or fill in a single missing particle from the textbook page, rather than asking for open-ended explanations.\n"
    "- Encourage the student to respond in Japanese.\n"
    "- Provide corrections gently when needed.\n"
    "- Include Romaji and English translations in parentheses when helpful.\n"
    "- Keep responses brief (under 3 sentences).\n"
    "- Never break character or mention that you're an AI.\n"
    "- Always reference the vocabulary and grammar from the current page.\n"
    "- Make the conversation natural and interactive.\n\n"
    "Current page context:\n"
    "{page_context}\n\n"
    "Begin the roleplay by introducing yourself as a character from the "
    "dialogue and inviting the student to practice."
)

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def encode_image_to_base64(image_path: str) -> str:
    """Encode an image file to a base64 data URI string."""
    with open(image_path, "rb") as img_file:
        return base64.b64encode(img_file.read()).decode("utf-8")


def analyze_page_with_vl(image_path: str):
    """Send page image to Qwen2.5-VL via LM Studio for structured analysis."""
    base64_image = encode_image_to_base64(image_path)

    messages = [
        {
            "role": "system",
            "content": PAGE_ANALYSIS_SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_image}"
                    },
                },
                {
                    "type": "text",
                    "text": "Analyze this Japanese textbook page and extract all key information.",
                },
            ],
        },
    ]

    try:
        resp = requests.post(
            LM_STUDIO_URL,
            json={
                "model": LM_STUDIO_MODEL,
                "messages": messages,
                "temperature": 0.0,
                "max_tokens": 800,
            },
            timeout=60,
        )
        resp.raise_for_status()
        result = resp.json()
        return result["choices"][0]["message"]["content"]
    except requests.exceptions.ConnectionError:
        return None
    except Exception:
        return None


def analyze_page_with_vl_from_bytes(base64_image: str):
    """Send page image (already base64-encoded) to Qwen2.5-VL via LM Studio for structured analysis."""
    messages = [
        {
            "role": "system",
            "content": PAGE_ANALYSIS_SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{base64_image}"
                    },
                },
                {
                    "type": "text",
                    "text": "Analyze this Japanese textbook page and extract all key information.",
                },
            ],
        },
    ]

    try:
        resp = requests.post(
            LM_STUDIO_URL,
            json={
                "model": LM_STUDIO_MODEL,
                "messages": messages,
                "temperature": 0.0,
                "max_tokens": 800,
            },
            timeout=60,
        )
        resp.raise_for_status()
        result = resp.json()
        return result["choices"][0]["message"]["content"]
    except requests.exceptions.ConnectionError:
        return None
    except Exception:
        return None


def parse_analysis_result(text: str):
    """Parse the JSON analysis result from Qwen2.5-VL output."""
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            json_str = text[start:end]
            return json.loads(json_str)
        return None
    except (json.JSONDecodeError, ValueError):
        return None


def build_page_context(page_info: dict) -> str:
    """Format page info into a readable context string for the chat system prompt."""
    if not page_info:
        return "No page context available."

    lines = ["--- Active Page Context ---"]
    lines.append(f"Topic: {page_info.get('topic', 'N/A')}")
    lines.append("")

    vocab = page_info.get("vocabulary", [])
    if vocab:
        lines.append("Key Vocabulary:")
        for item in vocab:
            if isinstance(item, dict):
                jp = item.get("jp", "")
                romaji = item.get("romaji", "")
                en = item.get("en", "")
                lines.append(f"  \\• {jp} ({romaji}): {en}")
            else:
                lines.append(f"  \\• {item}")
        lines.append("")

    dialogue = page_info.get("dialogue", [])
    if dialogue:
        lines.append("Dialogue:")
        for item in dialogue:
            if isinstance(item, dict):
                speaker = item.get("speaker", "")
                jp = item.get("jp", "")
                lines.append(f"  \\• {speaker}: {jp}")
            else:
                lines.append(f"  \\• {item}")
        lines.append("")

    grammar = page_info.get("grammar", [])
    if grammar:
        lines.append("Grammar Points:")
        for item in grammar:
            if isinstance(item, dict):
                point = item.get("point", "")
                explanation = item.get("explanation", "")
                lines.append(f"  \\• {point}: {explanation}")
            else:
                lines.append(f"  \\• {item}")
        lines.append("")

    audio_tags = page_info.get("audio_tags", [])
    if audio_tags:
        lines.append(f"Audio Tags: {', '.join(audio_tags)}")
        lines.append("")

    lines.append("--- End Context ---")
    return "\\n".join(lines)


def send_chat_message(user_message: str, include_image: bool = False, image_path=None, image_b64=None):
    """Send a chat message to Qwen2.5-VL via LM Studio. Returns the assistant response."""
    messages = [
        {
            "role": "system",
            "content": ROLEPLAY_SYSTEM_PROMPT.format(
                page_context=build_page_context(st.session_state.page_info)
            ),
        }
    ]

    # Add text-only chat history (images stripped after initial analysis)
    for msg in st.session_state.chat_history:
        messages.append({"role": msg["role"], "content": msg["content"]})

    # First user message after page analysis includes the image
    if include_image:
        if image_b64:
            b64_image = image_b64
        elif image_path:
            b64_image = encode_image_to_base64(image_path)
        else:
            b64_image = None

        if b64_image:
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64_image}"},
                        },
                        {"type": "text", "text": user_message},
                    ],
                }
            )
        else:
            messages.append({"role": "user", "content": user_message})
    else:
        messages.append({"role": "user", "content": user_message})

    try:
        resp = requests.post(
            LM_STUDIO_URL,
            json={
                "model": LM_STUDIO_MODEL,
                "messages": messages,
                "temperature": 0.0,
                "max_tokens": 800,
                "stream": True,
            },
            timeout=60,
            stream=True,
        )
        resp.raise_for_status()

        full_response = ""
        for line in resp.iter_lines(decode_unicode=False):
            if not line:
                continue
            line_str = line.decode("utf-8")
            if line_str.startswith("data: "):
                data_str = line_str[6:]
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        full_response += content
                except json.JSONDecodeError:
                    continue

        return full_response
    except requests.exceptions.ConnectionError:
        return (
            "\u26a0\ufe0f Cannot connect to LM Studio. "
            "Please ensure LM Studio is running at `http://localhost:7749/v1` "
            "with Qwen2.5-VL loaded."
        )
    except Exception as exc:
        return f"\u26a0\ufe0f Error: {exc}"


# ============================================================
# LAYOUT: SPLIT-SCREEN
# ============================================================
left_col, right_col = st.columns([2, 1], gap="large")

# ============================================================
# LEFT PANEL: PDF PAGE VIEWER
# ============================================================
with left_col:
    st.header("\U0001f4c4 Textbook Page")

    # --- Navigation bar ---
    col_prev, col_page_num, col_next, col_learn = st.columns([1, 2, 1, 1.5], gap="small")

    with col_prev:
        if st.button("\u25c0 Previous", key="btn_prev"):
            st.session_state.current_page = max(1, st.session_state.current_page - 1)
            st.rerun()
    with col_page_num:
        page_input = st.number_input(
            "Page",
            min_value=1,
            max_value=total_pages if total_pages > 0 else 9999,
            value=st.session_state.current_page,
            key="page_number_input",
            label_visibility="collapsed",
        )
        if page_input != st.session_state.current_page:
            st.session_state.current_page = page_input
            st.rerun()
    with col_next:
        if st.button("Next \u25b6", key="btn_next"):
            st.session_state.current_page = min(total_pages, st.session_state.current_page + 1)
            st.rerun()
    with col_learn:
        learned = st.button("\u2728 Learn This Page", type="primary", key="btn_learn")

    # --- Page image viewer ---
    if pdf_path and total_pages > 0:
        rendered_img = get_rendered_image_bytes(pdf_path, st.session_state.current_page)
        if rendered_img is not None:
            st.image(rendered_img, use_container_width=True, caption=f"Page {st.session_state.current_page}")
        else:
            st.error("Failed to render this page.")

        # --- Learn button handler ---
        if learned:
            page_img_bytes = get_ai_ready_image_bytes(pdf_path, st.session_state.current_page)
            if page_img_bytes:
                b64_image = base64.b64encode(page_img_bytes).decode("utf-8")
                st.session_state.chat_history = []
                st.session_state.page_info = None
                st.session_state.audio_files = {}
                st.session_state.image_analyzed = False
                st.session_state.current_page_label = f"page_{st.session_state.current_page}"

                with st.spinner("\U0001f50d Yuki-sensei is analyzing the page..."):
                    analysis_text = analyze_page_with_vl_from_bytes(b64_image)

                if analysis_text:
                    page_info = parse_analysis_result(analysis_text) or {"topic": "Unknown"}
                    st.session_state.page_info = page_info
                    st.session_state.image_analyzed = True

                    audio_tags = parse_audio_tags_from_analysis(page_info)
                    st.session_state.audio_files = {}
                    if audio_tags:
                        for tag in audio_tags:
                            matches = find_audio_track(tag, pdf_path)
                            st.session_state.audio_files[tag] = matches if matches else []

                    st.subheader("\U0001f4cb Extracted Information")
                    with st.expander("\U0001f4d6 Topic", expanded=True):
                        st.write(page_info.get("topic", "N/A"))
                    with st.expander("\U0001f4da Vocabulary"):
                        vocab = page_info.get("vocabulary", [])
                        if vocab:
                            for item in vocab:
                                if isinstance(item, dict):
                                    st.write(f"**{item.get('jp', '')}** ({item.get('romaji', '')}): {item.get('en', '')}")
                                else:
                                    st.write(item)
                        else:
                            st.write("No vocabulary extracted.")
                    with st.expander("\U0001f4ac Dialogue"):
                        dialogue = page_info.get("dialogue", [])
                        if dialogue:
                            for item in dialogue:
                                if isinstance(item, dict):
                                    st.write(f"**{item.get('speaker', '')}:** {item.get('jp', '')}")
                                else:
                                    st.write(item)
                        else:
                            st.write("No dialogue extracted.")
                    with st.expander("\U0001f4d0 Grammar"):
                        grammar = page_info.get("grammar", [])
                        if grammar:
                            for item in grammar:
                                if isinstance(item, dict):
                                    st.write(f"**{item.get('point', '')}:** {item.get('explanation', '')}")
                                else:
                                    st.write(item)
                        else:
                            st.write("No grammar points extracted.")
                    with st.expander("\U0001f3b5 Audio Tags"):
                        tags = page_info.get("audio_tags", [])
                        st.write(", ".join(tags) if tags else "No audio tags found.")

                    with st.spinner("\U0001f916 Initializing conversation..."):
                        initial_msg = send_chat_message(
                            "Please start the roleplay based on this page. Introduce yourself as a character from the dialogue and invite the student to practice.",
                            include_image=True,
                            image_b64=b64_image,
                        )
                    if initial_msg:
                        st.session_state.chat_history.append({"role": "assistant", "content": initial_msg})
                        st.toast("\u2705 Page analyzed! Conversation started.", icon="\U0001f389")
                else:
                    st.error("\u274c Failed to analyze the page. Is LM Studio running at `http://localhost:7749/v1`?")
            else:
                st.error("Could not render the page image for analysis.")
    else:
        st.info("\U0001f446 Enter a valid PDF path above to get started!")


# ============================================================
# RIGHT PANEL: ACTIVE CHAT WINDOW
# ============================================================
with right_col:
    st.header("\U0001f4ac Yuki-sensei Chat")

    if st.session_state.chat_history:
        # Display chat messages
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])

        # Render audio players for any found tracks on this page
        audio_files = st.session_state.get("audio_files", {})
        if audio_files:
            st.divider()
            st.subheader("\U0001f3a7 Audio Tracks for This Page")
            
            for track_id, files in audio_files.items():
                st.markdown(f"**Track {track_id}**")
                if files:
                    for i, filepath in enumerate(files):
                        filename = os.path.basename(filepath)
                        # Stream the file via Streamlit's static file serving
                        st.audio(filepath, format="audio/mpeg", start_time=0)
                        if i < len(files) - 1:
                            st.caption(f"Match: {filename}")
                else:
                    st.warning(f"No MP3 file found for track ID `[ {track_id} ]`")
                st.markdown("---")

        # --- Manually requested audio tracks (user override) ---
        manual_audio = st.session_state.get("manual_audio_tracks", {})
        if manual_audio:
            st.divider()
            st.subheader("\U0001f3b6 Manually Requested Audio")
            for track_id, files in manual_audio.items():
                if files:
                    st.markdown(f"**Track {track_id}**")
                    st.audio(files[0], format="audio/mpeg", start_time=0)
                else:
                    st.warning(f"Track `{track_id}` not found in audio directory")
                st.markdown("---")

        # Chat input
        if user_input := st.chat_input("Practice with Yuki-sensei..."):
            with st.chat_message("user"):
                st.write(user_input)

            st.session_state.chat_history.append(
                {"role": "user", "content": user_input}
            )

            # --- Manual audio track override ---
            # Scan user message for MM-NN track pattern
            TRACK_PATTERN = re.compile(r"\b\d{2}-\d{2}\b")
            track_matches = TRACK_PATTERN.findall(user_input)

            if track_matches:
                # Derive audio directory from the currently loaded PDF
                current_pdf = st.session_state.get("pdf_path", "")
                for track_id in track_matches:
                    found_files = find_audio_track(track_id, current_pdf)
                    if found_files:
                        # Store for rendering below (avoids inline HTML issues)
                        if "manual_audio_tracks" not in st.session_state:
                            st.session_state.manual_audio_tracks = {}
                        st.session_state.manual_audio_tracks[track_id] = found_files
                    else:
                        # Fallback: Yuki-sensei acknowledges the missing track
                        fallback_msg = (
                            f"I noticed you requested track `{track_id}`, "
                            f"but I couldn't locate it in the audio directory for this book."
                        )
                        st.session_state.chat_history.append(
                            {"role": "assistant", "content": fallback_msg}
                        )

            # --- Manual video track override ---
            # Scan user message for video track references
            video_matches = TRACK_PATTERN.findall(user_input)
            video_inject = ""
            if video_matches:
                current_pdf = st.session_state.get("pdf_path", "")
                for track_id in video_matches:
                    video_path = find_video_track(track_id, current_pdf)
                    if video_path:
                        video_html = (
                            f'\n\n<video width="100%" controls style="border-radius: 8px; margin-top: 10px; max-width: 420px; border: 1px solid #ddd;"><source src="file://{video_path}" type="video/mp4">Your browser does not support the video tag.</video>'
                        )
                        video_inject += video_html
                    else:
                        video_fallback = (
                            f"I couldn't find a video clip for track `{track_id}` in the video directory for this book."
                        )
                        st.session_state.chat_history.append(
                            {"role": "assistant", "content": video_fallback}
                        )

            with st.chat_message("assistant"):
                message_placeholder = st.empty()
                full_response = send_chat_message(user_input, include_image=False)
                # Append video player(s) to Yuki-sensei's response if found
                if video_inject:
                    full_response += video_inject
                message_placeholder.markdown(full_response)

            st.session_state.chat_history.append(
                {"role": "assistant", "content": full_response}
            )
    else:
        st.info("\U0001f4c4 Browse to a page in the left panel and click '[\u2728 Learn This Page]' to start a conversation!")

    # Clear chat button
    if st.session_state.chat_history:
        if st.button("\U0001f5d1\ufe0f Clear Chat", type="primary"):
            st.session_state.chat_history = []
            st.rerun()

# ============================================================
# FOOTER
# ============================================================
st.caption(
    "Powered by Qwen2.5-VL via LM Studio \u2022 Yuki-sensei JIT Japanese Tutor"
)

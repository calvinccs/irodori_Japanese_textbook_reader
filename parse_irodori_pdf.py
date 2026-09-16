import os
import re
import pymupdf

def extract_and_group_by_printed_page(pdf_path):
    txt_output_path = "data/irodori_sample.txt"
    
    if not os.path.exists(pdf_path):
        print(f"❌ Error: Could not find PDF at {pdf_path}")
        return

    os.makedirs(os.path.dirname(txt_output_path), exist_ok=True)
    print(f"📖 Opening {os.path.basename(pdf_path)} with printed-page grouping...")
    
    doc = pymupdf.open(pdf_path)
    
    # We will accumulate all clean blocks from across the document first
    raw_blocks_list = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        blocks = page.get_text("blocks", sort=True)
        for b in blocks:
            text = b[4].strip()
            if len(text) > 1:  # Filter out empty artifacts
                raw_blocks_list.append(text)

    # Reconstruct the text flow to analyze it
    full_text_flow = "\n\n".join(raw_blocks_list)
    
    # Match strings like "入門　この教材の使い方 - 1" or "入門 L1 - 6" at the start of a line
    # Regex breakdown: Start of line -> any characters -> optional space -> dash -> space -> digits -> end of line
    page_marker_pattern = r"(^.+?\s*-\s*\d+$)"
    
    # Split the full text into sections using our structural page marker match
    # Using re.split with a capture group preserves the header text in the resulting list
    tokens = re.split(page_marker_pattern, full_text_flow, flags=re.MULTILINE)

    print("🧩 Grouping content under page headers...")
    
    formatted_payload = ""
    # The first token is any text before the very first page marker header (usually empty)
    current_header = "Introductory Material"
    
    for token in tokens:
        token_clean = token.strip()
        if not token_clean:
            continue
            
        # If this token matches our page marker regex, update the active structural label
        if re.match(r"^.+?\s*-\s*\d+$", token_clean):
            current_header = token_clean
        else:
            # Clean up spacing within the text content block
            content_clean = re.sub(r'\n+', '\n', token_clean)
            
            # Append it to our structured textbook output block using the captured header string
            formatted_payload += (
                f"\n\n---LESSON_START:{current_header}---\n"
                f"Content:\n{content_clean}\n"
                f"Practice Directive: Use this material from section '{current_header}' to guide the student. Roleplay matching exercises interactively as Yuki-sensei.\n"
                f"---LESSON_END:{current_header}---\n"
            )

    print(f"✍️ Writing grouped page blocks into {txt_output_path}...")
    with open(txt_output_path, "w", encoding="utf-8") as f:
        f.write(formatted_payload.strip())

    print("✅ Success! The textbook text file has been structured by custom page labels.")

if __name__ == "__main__":
    # ⚠️ DROP THE PATH TO YOUR ACTUAL TEXTBOOK PDF HERE
    TARGET_PDF = r"/home/calvin/Documents/projects/irodori_materials/A1.pdf" 
    extract_and_group_by_printed_page(TARGET_PDF)

import streamlit as st
import os
import io
import time
from google import genai
from google.genai import types
import docx
from ebooklib import epub

# Initialize Streamlit Page Configuration
st.set_page_config(page_title="Document to EPUB Translator", page_icon="🌐", layout="centered")
st.title("🌐 AI Document to EPUB Translator (Gemini 3.6)")
st.write("Translate large `.txt` or `.docx` files to English using Gemini 3.6 Flash and download as `.epub`.")

# -----------------------------------------------------------------------------
# 1. Session State Initialization (Ensures repetitive runs work flawlessly)
# -----------------------------------------------------------------------------
if "translated_text" not in st.session_state:
    st.session_state.translated_text = None
if "file_hash" not in st.session_state:
    st.session_state.file_hash = None

# -----------------------------------------------------------------------------
# 2. Text Extraction Utilities
# -----------------------------------------------------------------------------
def extract_text_from_docx(file_bytes):
    """Extracts raw text from an uploaded DOCX file bytes."""
    doc = docx.Document(io.BytesIO(file_bytes))
    full_text = []
    for para in doc.paragraphs:
        full_text.append(para.text)
    return "\n".join(full_text)

def chunk_text(text, max_chars=12000):
    """Splits text into larger chunks by paragraphs leveraging Gemini 3.6's massive token capacity."""
    paragraphs = text.split("\n")
    chunks = []
    current_chunk = []
    current_length = 0
    
    for para in paragraphs:
        if current_length + len(para) > max_chars:
            chunks.append("\n".join(current_chunk))
            current_chunk = [para]
            current_length = len(para)
        else:
            current_chunk.append(para)
            current_length += len(para) + 1
            
    if current_chunk:
        chunks.append("\n".join(current_chunk))
    return chunks

# -----------------------------------------------------------------------------
# 3. EPUB Generation Utility
# -----------------------------------------------------------------------------
def create_epub(translated_text, title="Translated Book"):
    """Packages raw text into a standard valid EPUB file format."""
    book = epub.EpubBook()
    book.set_identifier("gemini_trans_id_12345")
    book.set_title(title)
    book.set_language("en")
    
    # Create main chapter
    c1 = epub.EpubHtml(title="Translated Content", file_name="chap_1.xhtml", lang="en")
    
    # Format plain text paragraphs to HTML blocks safely
    html_content = "<html><body>"
    for para in translated_text.split("\n"):
        if para.strip():
            html_content += f"<p>{para.strip()}</p>"
    html_content += "</body></html>"
    
    c1.content = html_content
    book.add_item(c1)
    
    # Core EPUB structure requirements
    book.toc = (epub.Link("chap_1.xhtml", "Translated Content", "translated_content"),)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", c1]
    
    # Write to memory buffer
    epub_buffer = io.BytesIO()
    epub.write_epub(epub_buffer, book, {})
    epub_buffer.seek(0)
    return epub_buffer

# -----------------------------------------------------------------------------
# 4. Core UI & Translation Logic
# -----------------------------------------------------------------------------
# Sidebar API Configuration
st.sidebar.header("🔑 API Configuration")
api_key = st.sidebar.text_input("Enter Gemini API Key", type="password", help="Get a free key from Google AI Studio")

# Main File Uploader (Supports files up to and beyond 2MB)
uploaded_file = st.file_uploader("Upload your document", type=["txt", "docx"])

if uploaded_file is not None:
    # Reset session token state if a completely new file is dropped in
    current_file_id = f"{uploaded_file.name}_{uploaded_file.size}"
    if st.session_state.file_hash != current_file_id:
        st.session_state.translated_text = None
        st.session_state.file_hash = current_file_id

    # Read and parse file
    file_bytes = uploaded_file.read()
    if uploaded_file.name.endswith(".txt"):
        try:
            raw_text = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            raw_text = file_bytes.decode("latin-1")
    else:
        raw_text = extract_text_from_docx(file_bytes)
        
    word_count = len(raw_text.split())
    st.info(f"📄 File loaded successfully. Total approximate words: **{word_count:,}**")

    # Translation Trigger Button
    if st.button("🚀 Translate to English"):
        if not api_key:
            st.error("Please enter your Gemini API Key in the sidebar first!")
        else:
            try:
                # Initialize official modern Google GenAI Client
                client = genai.Client(api_key=api_key)
                
                # Gemini 3.6 Flash features optimal processing for huge datasets
                chunks = chunk_text(raw_text, max_chars=12000)
                total_chunks = len(chunks)
                
                translated_chunks = []
                
                # UI Progress Trackers
                progress_bar = st.progress(0.0)
                status_text = st.empty()
                
                for idx, chunk in enumerate(chunks):
                    if not chunk.strip():
                        continue
                        
                    status_text.text(f"Translating section {idx + 1} of {total_chunks}...")
                    
                    # Target the flagship Gemini 3.6 Flash Engine
                    # Note: temperature is deprecated in 3.6+ and has been cleanly removed here
                    response = client.models.generate_content(
                        model='gemini-3.6-flash',
                        contents=chunk,
                        config=types.GenerateContentConfig(
                            system_instruction="You are a professional book translator. Translate the provided source text directly into natural, accurate, fluent literary English. Retain all original paragraph separations. Output ONLY the translated text without adding any personal commentary, notes, introduction, or explanations.",
                        )
                    )
                    
                    translated_chunks.append(response.text)
                    
                    # Update active UI progress bar dynamically
                    progress_bar.progress((idx + 1) / total_chunks)
                    # Short protective break to prevent hitting rate limits
                    time.sleep(0.4)
                    
                st.session_state.translated_text = "\n".join(translated_chunks)
                status_text.text("✅ Translation completed successfully!")
                st.success("Your document has been translated!")
                
            except Exception as e:
                st.error(f"An error occurred during translation: {str(e)}")

    # -----------------------------------------------------------------------------
    # 5. File Download Action (Persists across repeated operations via Session State)
    # -----------------------------------------------------------------------------
    if st.session_state.translated_text:
        st.subheader("📥 Download Translated Document")
        
        # Build clean filename
        original_name = uploaded_file.name.rsplit('.', 1)[0]
        epub_filename = f"{original_name}_translated.epub"
        
        # Compile EPUB container
        with st.spinner("Generating EPUB file payload..."):
            epub_data = create_epub(st.session_state.translated_text, title=original_name)
            
        st.download_button(
            label="💾 Download as EPUB",
            data=epub_data,
            file_name=epub_filename,
            mime="application/epub+zip"
        )

import streamlit as st
import os
import io
import time
import asyncio
from google import genai
from google.genai import types
import docx
from ebooklib import epub

# Initialize Streamlit Page Configuration
st.set_page_config(page_title="Fast Document Translator", page_icon="⚡", layout="centered")
st.title("⚡ High-Velocity Document to EPUB Translator")
st.write("Optimized for Gemini 3.6 Flash rate limits to translate 26k+ words in seconds.")

# -----------------------------------------------------------------------------
# 1. Session State Initialization
# -----------------------------------------------------------------------------
if "translated_text" not in st.session_state:
    st.session_state.translated_text = None
if "file_hash" not in st.session_state:
    st.session_state.file_hash = None

# -----------------------------------------------------------------------------
# 2. Text Extraction Utilities
# -----------------------------------------------------------------------------
def extract_text_from_docx(file_bytes):
    doc = docx.Document(io.BytesIO(file_bytes))
    full_text = [para.text for para in doc.paragraphs]
    return "\n".join(full_text)

def chunk_text(text, max_chars=60000):
    """Increased to 60k characters. Reduces 55 chunks down to 2-3 massive chunks to avoid rate limits."""
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
    book = epub.EpubBook()
    book.set_identifier("gemini_trans_fast_999")
    book.set_title(title)
    book.set_language("en")
    
    c1 = epub.EpubHtml(title="Translated Content", file_name="chap_1.xhtml", lang="en")
    
    html_content = "<html><body>"
    for para in translated_text.split("\n"):
        if para.strip():
            html_content += f"<p>{para.strip()}</p>"
    html_content += "</body></html>"
    
    c1.content = html_content
    book.add_item(c1)
    book.toc = (epub.Link("chap_1.xhtml", "Translated Content", "translated_content"),)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", c1]
    
    epub_buffer = io.BytesIO()
    epub.write_epub(epub_buffer, book, {})
    epub_buffer.seek(0)
    return epub_buffer

# -----------------------------------------------------------------------------
# 4. Async Translation Worker (Optimized for Free Tiers)
# -----------------------------------------------------------------------------
async def translate_chunk_async(client, chunk, idx, total_chunks, progress_tracker):
    if not chunk.strip():
        return idx, ""
        
    # Small staggered delay to keep free API keys safe from instant rejection
    await asyncio.sleep(idx * 0.5) 
    
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.models.generate_content(
                model='gemini-3.6-flash',
                contents=chunk,
                config=types.GenerateContentConfig(
                    system_instruction="You are a professional book translator. Translate the provided source text directly into natural, accurate, fluent literary English. Retain all original paragraph separations. Output ONLY the translated text without adding any personal commentary.",
                )
            )
        )
        progress_tracker["completed"] += 1
        progress_tracker["bar"].progress(progress_tracker["completed"] / total_chunks)
        progress_tracker["text"].text(f"🚀 Processing mega-section {progress_tracker['completed']} of {total_chunks}...")
        
        return idx, response.text
    except Exception as e:
        return idx, f"[Error translating block {idx}: {str(e)}]"

async def main_translation_orchestrator(client, chunks):
    total_chunks = len(chunks)
    progress_tracker = {
        "completed": 0,
        "bar": st.progress(0.0),
        "text": st.empty()
    }
    
    tasks = [translate_chunk_async(client, chunk, i, total_chunks, progress_tracker) for i, chunk in enumerate(chunks)]
    results = await asyncio.gather(*tasks)
    results.sort(key=lambda x: x)
    return [text for idx, text in results]

# -----------------------------------------------------------------------------
# 5. UI Layout
# -----------------------------------------------------------------------------
st.sidebar.header("🔑 API Configuration")
api_key = st.sidebar.text_input("Enter Gemini API Key", type="password")

uploaded_file = st.file_uploader("Upload your document", type=["txt", "docx"])

if uploaded_file is not None:
    current_file_id = f"{uploaded_file.name}_{uploaded_file.size}"
    if st.session_state.file_hash != current_file_id:
        st.session_state.translated_text = None
        st.session_state.file_hash = current_file_id

    file_bytes = uploaded_file.read()
    if uploaded_file.name.endswith(".txt"):
        try:
            raw_text = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            raw_text = file_bytes.decode("latin-1")
    else:
        raw_text = extract_text_from_docx(file_bytes)
        
    word_count = len(raw_text.split())
    st.info(f"📄 File loaded successfully. Total words: **{word_count:,}**")

    if st.button("⚡ Start High-Speed Translation"):
        if not api_key:
            st.error("Please enter your Gemini API Key first!")
        else:
            try:
                client = genai.Client(api_key=api_key)
                
                # Generates much fewer chunks to maximize speed under free API limits
                chunks = chunk_text(raw_text, max_chars=60000)
                
                translated_list = asyncio.run(main_translation_orchestrator(client, chunks))
                st.session_state.translated_text = "\n".join(translated_list)
                st.success("🎉 Translation completed in record time!")
            except Exception as e:
                st.error(f"An error occurred: {str(e)}")

    if st.session_state.translated_text:
        st.subheader("📥 Download Translated Document")
        original_name = uploaded_file.name.rsplit('.', 1)
        epub_filename = f"{original_name}_translated.epub"
        
        with st.spinner("Generating EPUB file payload..."):
            epub_data = create_epub(st.session_state.translated_text, title=original_name)
            
        st.download_button(
            label="💾 Download as EPUB",
            data=epub_data,
            file_name=epub_filename,
            mime="application/epub+zip"
        )

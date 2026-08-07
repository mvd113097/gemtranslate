import streamlit as st
import io
import asyncio
import html
from google import genai
from google.genai import types
import docx
from ebooklib import epub

# -----------------------------------------------------------------------------
# PAGE CONFIG
# -----------------------------------------------------------------------------
st.set_page_config(page_title="Fast Translator", page_icon="⚡")
st.title("⚡ Fast TXT/DOCX → English → EPUB")

# -----------------------------------------------------------------------------
# SESSION STATE
# -----------------------------------------------------------------------------
if "translated_text" not in st.session_state:
    st.session_state.translated_text = None
if "file_hash" not in st.session_state:
    st.session_state.file_hash = None

# -----------------------------------------------------------------------------
# TEXT EXTRACTION
# -----------------------------------------------------------------------------
def extract_text_from_docx(file_bytes):
    doc = docx.Document(io.BytesIO(file_bytes))
    return "\n".join([p.text for p in doc.paragraphs])

# -----------------------------------------------------------------------------
# CHUNKING (SAFE SIZE)
# -----------------------------------------------------------------------------
def chunk_text(text, max_chars=30000):
    paragraphs = text.split("\n")
    chunks = []
    current = []
    length = 0

    for para in paragraphs:
        if length + len(para) > max_chars:
            chunks.append("\n".join(current))
            current = [para]
            length = len(para)
        else:
            current.append(para)
            length += len(para)

    if current:
        chunks.append("\n".join(current))

    return chunks

# -----------------------------------------------------------------------------
# EPUB CREATION (FIXED)
# -----------------------------------------------------------------------------
def create_epub(translated_text, title="Translated Book"):
    title = str(title)

    book = epub.EpubBook()
    book.set_identifier("id123456")
    book.set_title(title)
    book.set_language("en")
    book.add_author("Auto Translator")

    c1 = epub.EpubHtml(
        title="Chapter 1",
        file_name="chap_1.xhtml",
        lang="en"
    )

    content = "<html><body>"

    for para in translated_text.split("\n"):
        if para.strip():
            safe = html.escape(para.strip())
            content += f"<p>{safe}</p>"

    content += "</body></html>"

    c1.content = content
    book.add_item(c1)

    book.toc = (epub.Link("chap_1.xhtml", "Content", "c1"),)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    book.spine = ["nav", c1]

    buffer = io.BytesIO()
    epub.write_epub(buffer, book)
    buffer.seek(0)

    return buffer

# -----------------------------------------------------------------------------
# TRANSLATION
# -----------------------------------------------------------------------------
async def translate_chunk(client, chunk):
    loop = asyncio.get_event_loop()

    response = await loop.run_in_executor(
        None,
        lambda: client.models.generate_content(
            model="gemini-1.5-flash",
            contents=chunk,
            config=types.GenerateContentConfig(
                system_instruction=(
                    "Translate to natural fluent English. "
                    "Keep paragraphs. No comments."
                )
            )
        )
    )

    return response.text

async def translate_all(client, chunks):
    tasks = [translate_chunk(client, c) for c in chunks]
    results = await asyncio.gather(*tasks)
    return "\n".join(results)

# -----------------------------------------------------------------------------
# UI
# -----------------------------------------------------------------------------
st.sidebar.header("🔑 API Key")
api_key = st.sidebar.text_input("Gemini API Key", type="password")

file = st.file_uploader("Upload TXT or DOCX", type=["txt", "docx"])

if file:
    file_id = f"{file.name}_{file.size}"

    if st.session_state.file_hash != file_id:
        st.session_state.translated_text = None
        st.session_state.file_hash = file_id

    data = file.read()

    if file.name.endswith(".txt"):
        try:
            raw_text = data.decode("utf-8")
        except:
            raw_text = data.decode("latin-1")
    else:
        raw_text = extract_text_from_docx(data)

    st.info(f"Words: {len(raw_text.split()):,}")

    if st.button("⚡ Translate"):
        if not api_key:
            st.error("Enter API key")
        else:
            try:
                client = genai.Client(api_key=api_key)

                chunks = chunk_text(raw_text)
                st.write(f"Chunks: {len(chunks)}")

                with st.spinner("Translating..."):
                    result = asyncio.run(translate_all(client, chunks))

                st.session_state.translated_text = result
                st.success("Done!")

            except Exception as e:
                st.error(str(e))

# -----------------------------------------------------------------------------
# DOWNLOAD
# -----------------------------------------------------------------------------
if st.session_state.translated_text:
    st.subheader("📥 Download")

    base_name = file.name.rsplit(".", 1)[0]
    epub_name = f"{base_name}_translated.epub"

    epub_file = create_epub(
        st.session_state.translated_text,
        title=base_name
    )

    st.download_button(
        "💾 Download EPUB",
        data=epub_file,
        file_name=epub_name,
        mime="application/epub+zip"
    )

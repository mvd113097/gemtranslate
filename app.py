import streamlit as st
import os
import io
import time
from google import genai
import docx
from ebooklib import epub

# ------------------ CONFIG ------------------
st.set_page_config(page_title="Fast Translator", page_icon="⚡")

st.title("⚡ Fast TXT/DOCX → English → EPUB")

# ------------------ API KEY ------------------
API_KEY = "YOUR_API_KEY_HERE"  # 🔥 PUT YOUR GEMINI API KEY HERE

client = genai.Client(api_key=API_KEY)

# ------------------ FUNCTIONS ------------------

def read_txt(file):
    return file.read().decode("utf-8", errors="ignore")

def read_docx(file):
    doc = docx.Document(file)
    return "\n".join([p.text for p in doc.paragraphs])

def split_text(text, max_chars=4000):
    return [text[i:i+max_chars] for i in range(0, len(text), max_chars)]

def translate_chunk(chunk):
    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=f"Translate the following text to English. Keep names consistent:\n\n{chunk}"
        )
        return response.text
    except Exception as e:
        return f"\n[ERROR: {e}]\n"

def create_epub(title, content):
    book = epub.EpubBook()
    book.set_title(title)
    book.set_language("en")

    chapter = epub.EpubHtml(title="Chapter", file_name="chap_1.xhtml")
    chapter.content = f"<h1>{title}</h1><p>{content.replace(chr(10), '<br>')}</p>"

    book.add_item(chapter)
    book.toc = (epub.Link("chap_1.xhtml", "Chapter", "chap1"),)

    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    style = 'BODY { font-family: Arial; }'
    nav_css = epub.EpubItem(uid="style_nav", file_name="style/nav.css", media_type="text/css", content=style)

    book.add_item(nav_css)
    book.spine = ["nav", chapter]

    buffer = io.BytesIO()
    epub.write_epub(buffer, book)
    return buffer

# ------------------ UI ------------------

uploaded_file = st.file_uploader("Upload TXT or DOCX", type=["txt", "docx"])

if uploaded_file:
    if uploaded_file.name.endswith(".txt"):
        text = read_txt(uploaded_file)
    else:
        text = read_docx(uploaded_file)

    st.info(f"Words: {len(text.split()):,}")

    if st.button("⚡ Translate"):
        chunks = split_text(text)
        st.write(f"Chunks: {len(chunks)}")

        translated_text = ""

        progress = st.progress(0)

        for i, chunk in enumerate(chunks):
            result = translate_chunk(chunk)
            translated_text += result + "\n"

            progress.progress((i + 1) / len(chunks))
            time.sleep(1)  # prevents rate limit

        st.success("✅ Translation Complete!")

        epub_file = create_epub("Translated Book", translated_text)

        st.download_button(
            label="📥 Download EPUB",
            data=epub_file,
            file_name="translated.epub",
            mime="application/epub+zip"
        )

"""S-09 匯出渲染：txt/md/docx 三格式；docx 可重開且有標題；無 PDF（NG-3）。"""
import io

import pytest

from services.export import render

SAMPLE = "# 週會記錄\n\n## 討論事項\n- 重點一\n- 重點二\n\n## 決議\n指派日班。\n"


def test_md_passthrough():
    data, media, ext = render(SAMPLE, "md")
    assert ext == "md" and media.startswith("text/markdown")
    assert data.decode("utf-8") == SAMPLE


def test_txt_strips_markdown():
    data, media, ext = render(SAMPLE, "txt")
    assert ext == "txt" and media.startswith("text/plain")
    text = data.decode("utf-8")
    assert "#" not in text and "週會記錄" in text and "・重點一" in text


def test_docx_opens_with_headings():
    from docx import Document
    data, media, ext = render(SAMPLE, "docx")
    assert ext == "docx" and "wordprocessingml" in media
    doc = Document(io.BytesIO(data))
    texts = [p.text for p in doc.paragraphs]
    assert "週會記錄" in texts and "討論事項" in texts and "決議" in texts


def test_title_prepended_when_missing():
    data, _, _ = render("純內容無標題", "md", title="補上的標題")
    assert data.decode("utf-8").startswith("# 補上的標題")


def test_pdf_rejected():
    with pytest.raises(ValueError):
        render(SAMPLE, "pdf")


def test_unknown_fmt_rejected():
    with pytest.raises(ValueError):
        render(SAMPLE, "rtf")

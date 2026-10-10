"""Outline the legacy DOCX report (headings + table captions) via stdlib zip."""

import re
import sys
import zipfile
from pathlib import Path

DOCX = Path(r"D:\ISB\Legislative Preparedness\MGLA_Legislative_Preparedness_Report.docx")


def main():
    tries, text = 0, None
    while tries < 4:
        try:
            with zipfile.ZipFile(DOCX) as zf:
                xml = zf.read("word/document.xml").decode("utf-8")
            break
        except OSError:
            tries += 1
            import time
            time.sleep(15)
    else:
        print("DOCX unreadable after retries")
        return 1
    paras = re.findall(r"<w:p[^>]*>(.*?)</w:p>", xml, re.S)
    texts = []
    for para in paras:
        style = re.search(r'w:val="([^"]+)"', para[:600])
        words = re.findall(r"<w:t[^>]*>(.*?)</w:t>", para, re.S)
        content = "".join(words).strip()
        if content:
            texts.append((style.group(1) if style else "", content))
    print(f"paragraphs: {len(texts)}")
    for style, content in texts:
        if "Heading" in style or re.match(r"^(Part|Chapter|Appendix)\b", content, re.I):
            print(f"[{style}] {content[:110]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

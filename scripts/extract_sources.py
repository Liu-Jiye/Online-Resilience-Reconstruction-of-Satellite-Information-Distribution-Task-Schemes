import argparse
import csv
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORD = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
MATH = '{http://schemas.openxmlformats.org/officeDocument/2006/math}'


def extract_docx(path):
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read('word/document.xml'))
    paragraphs = []
    for paragraph in root.iter(WORD + 'p'):
        pieces = []
        for node in paragraph.iter():
            if node.tag in (WORD + 't', MATH + 't'):
                pieces.append(node.text or '')
            elif node.tag == WORD + 'tab':
                pieces.append('\t')
            elif node.tag == WORD + 'br':
                pieces.append('\n')
        paragraphs.append(''.join(pieces))
    return '\n\n'.join(paragraphs)


def extract_pdf(path):
    import fitz

    with fitz.open(path) as document:
        return '\n\n'.join(
            f'## 原文件物理页 {index}\n\n{page.get_text()}'
            for index, page in enumerate(document, 1)
        )


def main():
    parser = argparse.ArgumentParser(description='Regenerate searchable source indexes, not experiments')
    parser.add_argument('--docx-only', action='store_true')
    arguments = parser.parse_args()
    with (ROOT / 'archive/manifest.csv').open(encoding='utf-8-sig', newline='') as stream:
        records = list(csv.DictReader(stream))
    for record in records:
        source = ROOT / record['repository_path']
        if arguments.docx_only and source.suffix.lower() != '.docx':
            continue
        body = extract_docx(source) if source.suffix.lower() == '.docx' else extract_pdf(source)
        destination = ROOT / record['text_index']
        destination.parent.mkdir(parents=True, exist_ok=True)
        heading = f'# {record["source_id"]} {source.name}\n\n'
        notice = '自动提取文本，仅供搜索；公式、图片和表格请核对原文件。\n\n'
        normalized = '\n'.join(line.rstrip() for line in body.splitlines()).strip()
        destination.write_text(heading + notice + normalized + '\n', encoding='utf-8')
        print(f'Indexed {record["source_id"]}: {destination.relative_to(ROOT)}')


if __name__ == '__main__':
    main()

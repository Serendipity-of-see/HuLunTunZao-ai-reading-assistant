import re
from typing import List, Tuple


# 章节标题正则（匹配 "第X章"、"Chapter X"、"第X回" 等）
CHAPTER_PATTERNS = [
    re.compile(r'^第[零一二三四五六七八九十百千万\d]+[章节回卷]', re.MULTILINE),
    re.compile(r'^Chapter\s+\d+', re.MULTILINE | re.IGNORECASE),
    re.compile(r'^\d+[\.\s、]', re.MULTILINE),  # 纯数字标题
]

# 句末标点
SENTENCE_ENDS = re.compile(r'[。！？…；](?![」』"\'"])')


def split_chapters(text: str) -> List[Tuple[str, str, int]]:
    """
    将全文按章节切分。
    返回: [(标题, 正文, 章节序号), ...]
    若未检测到章节标记，整文作为一章。
    """
    chapters = []
    matches = []
    for pattern in CHAPTER_PATTERNS:
        for m in pattern.finditer(text):
            matches.append((m.start(), m.group().strip()))

    if not matches:
        return [("第一章", text.strip(), 1)]

    matches.sort(key=lambda x: x[0])

    for i, (start, title) in enumerate(matches):
        end = matches[i + 1][0] if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        # 去掉标题行本身
        if body.startswith(title):
            body = body[len(title):].strip()
        chapters.append((title, body, i + 1))

    return chapters


def split_sentences(text: str) -> List[str]:
    """
    按句末标点分句，合并对话（"xxx说："+后续引号内容）。
    返回: [句子1, 句子2, ...]
    """
    # 先在句末标点处分隔
    raw_parts = []
    last_end = 0
    for m in SENTENCE_ENDS.finditer(text):
        raw_parts.append(text[last_end:m.end()])
        last_end = m.end()
    if last_end < len(text):
        raw_parts.append(text[last_end:])

    # 对话合并：如果前句以「说：」「道：」等结尾，与后句的引号内容合并
    dialogue_connectors = re.compile(r'(说|道|问|答|喊|叫|嚷|骂|吼)(：|:)["\'""]\s*$')
    merged = []
    i = 0
    while i < len(raw_parts):
        current = raw_parts[i].strip()
        if not current:
            i += 1
            continue
        if dialogue_connectors.search(current) and i + 1 < len(raw_parts):
            current = current + raw_parts[i + 1].strip()
            i += 2
        else:
            i += 1
        merged.append(current)

    return merged


def parse_book(file_path: str) -> dict:
    """
    解析 TXT 文件，返回结构化数据。
    返回: {
        "chapters": [{"title": str, "index": int, "atoms": [str, ...]}, ...],
        "total_chars": int,
        "total_atoms": int
    }
    """
    # 尝试多种编码
    content = None
    for enc in ['utf-8', 'gbk', 'gb2312', 'gb18030']:
        try:
            with open(file_path, 'r', encoding=enc) as f:
                content = f.read()
            break
        except (UnicodeDecodeError, UnicodeError):
            continue

    if content is None:
        raise ValueError(f"无法识别文件编码: {file_path}")

    total_chars = len(content)
    chapters = split_chapters(content)

    result_chapters = []
    total_atoms = 0
    for title, body, idx in chapters:
        atoms = split_sentences(body)
        # 过滤过短的句子（纯空格、纯标点）
        atoms = [a.strip() for a in atoms if len(a.strip()) > 1]
        total_atoms += len(atoms)
        result_chapters.append({
            "title": title,
            "index": idx,
            "atoms": atoms,
        })

    return {
        "chapters": result_chapters,
        "total_chars": total_chars,
        "total_atoms": total_atoms,
    }

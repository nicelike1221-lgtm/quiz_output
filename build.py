#!/usr/bin/env python3
"""
Build static quiz pages from Feishu Bitable or local JSON files.

Environment variables for Feishu mode:
  FEISHU_APP_ID       Feishu app ID
  FEISHU_APP_SECRET   Feishu app secret
  FEISHU_APP_TOKEN    Feishu Bitable app token
  FEISHU_QUIZ_TABLE   Table ID for quizzes metadata
  FEISHU_QUEST_TABLE  Table ID for questions

If Feishu credentials are not set, the script falls back to local *_quiz.json files.
"""

import json
import os
import re
import sys
import html as html_module
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
TEMPLATE_PATH = ROOT / "template.html"
OUTPUT_DIR = ROOT / "docs"


def slugify(text: str) -> str:
    """Create a URL-friendly slug from text."""
    text = text.strip()
    text = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "quiz"


def load_template() -> str:
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Template not found: {TEMPLATE_PATH}")
    return TEMPLATE_PATH.read_text(encoding="utf-8")


def render_quiz_page(template: str, quiz_data: dict, slug: str) -> str:
    """Render a single quiz HTML page."""
    title = quiz_data.get("meta", {}).get("title", "Quiz")
    quiz_json = json.dumps(quiz_data, ensure_ascii=False, indent=2)
    page = template.replace("{{QUIZ_DATA}}", quiz_json)
    page = page.replace("{{PAGE_TITLE}}", html_module.escape(title))
    return page


def build_index_page(quizzes: list) -> str:
    """Render the site index page with a clean list style."""

    def guess_tag(title: str) -> tuple:
        t = title.lower()
        if "多选" in t:
            return "多选", "multi"
        if "单选" in t:
            return "单选", "single"
        if "判断" in t:
            return "判断", "judge"
        return "练习", "single"

    rows = []
    for quiz in quizzes:
        meta = quiz["data"].get("meta", {})
        title = meta.get("title", quiz["slug"])
        tag, tag_class = guess_tag(title)
        rows.append(
            f"""
            <a href="quiz/{quiz['slug']}.html" class="quiz-row">
                <span class="icon">📄</span>
                <span class="title">{html_module.escape(title)}</span>
                <span class="tag tag-{tag_class}">{tag}</span>
            </a>
            """
        )

    rows_html = "\n".join(rows) if rows else "<p>暂无试卷</p>"

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>民法刷题</title>
<style>
:root {{
  --bg: #f0f2f5;
  --card-bg: #fff;
  --text: #1a1a2e;
  --muted: #8892b0;
  --single: #4f6ef7;
  --multi: #f59e0b;
  --judge: #10b981;
  --radius: 16px;
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.6;
  min-height: 100vh;
}}
.container {{ max-width: 720px; margin: 0 auto; padding: 40px 16px; }}
.card {{
  background: var(--card-bg);
  border-radius: var(--radius);
  padding: 40px 32px;
  box-shadow: 0 4px 20px rgba(0,0,0,.05);
}}
header {{ text-align: center; margin-bottom: 36px; }}
header h1 {{ font-size: 1.8em; font-weight: 700; display: inline-flex; align-items: center; gap: 10px; }}
header h1 .logo {{ font-size: 1.2em; }}
header p {{ color: var(--muted); margin-top: 8px; font-size: .95em; }}
.divider {{ height: 1px; background: #eef1ff; margin: 24px 0; }}
.quiz-row {{
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  border-radius: 12px;
  text-decoration: none;
  color: inherit;
  transition: background .15s;
}}
.quiz-row:hover {{ background: #f8faff; }}
.quiz-row .icon {{ font-size: 1.3em; }}
.quiz-row .title {{ flex: 1; font-weight: 500; font-size: 1.05em; }}
.quiz-row .tag {{
  font-size: .75em;
  padding: 4px 12px;
  border-radius: 12px;
  font-weight: 600;
  color: #fff;
}}
.tag-single {{ background: var(--single); }}
.tag-multi {{ background: var(--multi); }}
.tag-judge {{ background: var(--judge); }}
footer {{
  text-align: center;
  color: var(--muted);
  font-size: .85em;
  margin-top: 32px;
}}
footer .bulb {{ margin-right: 4px; }}
</style>
</head>
<body>
<div class="container">
  <div class="card">
    <header>
      <h1><span class="logo">📚</span>民法刷题</h1>
      <p>选择以下题目开始练习</p>
    </header>
    <div class="divider"></div>
    <div class="quiz-list">
      {rows_html}
    </div>
  </div>
  <footer>
    <p><span class="bulb">💡</span>点击题目开始刷题 · 数据来自飞书多维表格</p>
  </footer>
</div>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Local JSON mode
# ---------------------------------------------------------------------------

def load_from_local() -> list:
    """Load quizzes from *_quiz.json files in the repo."""
    quizzes = []
    for json_file in sorted(ROOT.rglob("*_quiz.json")):
        # Skip files inside docs/
        if "docs" in json_file.parts:
            continue
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"[warn] Skip invalid JSON {json_file}: {e}", file=sys.stderr)
            continue
        slug = slugify(json_file.stem.replace("_quiz", ""))
        quizzes.append({"slug": slug, "data": data, "source": "local"})
    return quizzes


# ---------------------------------------------------------------------------
# Feishu Bitable mode
# ---------------------------------------------------------------------------

FEISHU_TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
FEISHU_RECORDS_URL = "https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records"


def get_tenant_access_token(app_id: str, app_secret: str) -> str:
    resp = requests.post(
        FEISHU_TOKEN_URL,
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Feishu token error: {data}")
    return data["tenant_access_token"]


def list_all_records(token: str, app_token: str, table_id: str) -> list:
    headers = {"Authorization": f"Bearer {token}"}
    records = []
    page_token = None
    while True:
        params = {"page_size": 500}
        if page_token:
            params["page_token"] = page_token
        resp = requests.get(
            FEISHU_RECORDS_URL.format(app_token=app_token, table_id=table_id),
            headers=headers,
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Feishu records error: {data}")
        payload = data.get("data", {})
        records.extend(payload.get("items", []))
        if not payload.get("has_more"):
            break
        page_token = payload.get("page_token")
    return records


def field_to_str(value) -> str:
    """Convert a Feishu field value to string, handling list types."""
    if value is None:
        return ""
    if isinstance(value, list):
        return "".join(str(x).strip() for x in value if str(x).strip())
    return str(value).strip()


def parse_options_from_field(raw):
    """Accept options as a list, newline-separated, pipe-separated,
    or a single line with A/B/C/D prefixes."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        # 1) Newline-separated
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if len(lines) > 1:
            return lines
        # 2) Pipe-separated
        if "|" in text:
            return [part.strip() for part in text.split("|") if part.strip()]
        # 3) Single line with option prefixes like "A. xxx B. yyy C. zzz"
        # Split before each "A. ", "B. ", "C. ", "D. " etc.
        parts = re.split(r"(?=\b[A-Z]\.\s)", text)
        parts = [p.strip() for p in parts if p.strip()]
        if len(parts) > 1:
            return parts
        return lines
    return []


def parse_quiz_meta(records: list) -> list:
    quizzes = []
    for r in records:
        fields = r.get("fields", {})
        enabled = fields.get("enabled", True)
        if isinstance(enabled, str):
            enabled = enabled.lower() in ("true", "是", "yes", "1")
        if not enabled:
            continue
        quiz_id = field_to_str(fields.get("quiz_id", ""))
        title = field_to_str(fields.get("title", ""))
        if not quiz_id or not title:
            continue
        quizzes.append({
            "quiz_id": quiz_id,
            "title": title,
            "source": field_to_str(fields.get("source", "")),
            "slug": slugify(field_to_str(fields.get("slug", "")) or quiz_id),
        })
    return quizzes


def parse_questions(records: list) -> list:
    questions = []
    for r in records:
        fields = r.get("fields", {})
        quiz_id = field_to_str(fields.get("quiz_id", ""))
        stem = field_to_str(fields.get("stem", ""))
        if not quiz_id or not stem:
            continue
        qid = fields.get("id")
        try:
            qid = int(qid)
        except (TypeError, ValueError):
            qid = 0

        # Try dedicated option columns first, then a generic "options" field.
        options = []
        for i in range(8):
            key = f"option_{chr(ord('A') + i)}"
            if key in fields and fields[key]:
                options.append(field_to_str(fields[key]))
        if not options:
            options = parse_options_from_field(fields.get("options"))

        questions.append({
            "quiz_id": quiz_id,
            "id": qid,
            "type": field_to_str(fields.get("type", "single_choice")),
            "stem": stem,
            "options": options,
            "answer": field_to_str(fields.get("answer", "")),
            "explanation": field_to_str(fields.get("explanation", "")),
        })
    # Stable ordering by id
    questions.sort(key=lambda q: q["id"])
    return questions


def load_from_feishu() -> list:
    app_id = os.environ.get("FEISHU_APP_ID")
    app_secret = os.environ.get("FEISHU_APP_SECRET")
    app_token = os.environ.get("FEISHU_APP_TOKEN")
    quiz_table = os.environ.get("FEISHU_QUIZ_TABLE")
    question_table = os.environ.get("FEISHU_QUEST_TABLE")

    if not all([app_id, app_secret, app_token, quiz_table, question_table]):
        raise RuntimeError("Missing Feishu environment variables")

    token = get_tenant_access_token(app_id, app_secret)
    quiz_records = list_all_records(token, app_token, quiz_table)
    question_records = list_all_records(token, app_token, question_table)

    quizzes_meta = parse_quiz_meta(quiz_records)
    all_questions = parse_questions(question_records)

    quizzes = []
    for meta in quizzes_meta:
        qid = meta["quiz_id"]
        questions = [q for q in all_questions if q["quiz_id"] == qid]
        if not questions:
            print(f"[warn] No questions found for quiz {qid}", file=sys.stderr)
            continue
        data = {
            "meta": {
                "title": meta["title"],
                "source": meta["source"],
                "total_questions": len(questions),
            },
            "questions": [
                {
                    "id": q["id"],
                    "type": q["type"],
                    "stem": q["stem"],
                    "options": q["options"],
                    "answer": q["answer"],
                    "explanation": q["explanation"],
                }
                for q in questions
            ],
        }
        quizzes.append({"slug": meta["slug"], "data": data, "source": "feishu"})
    return quizzes


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    template = load_template()

    # Prefer Feishu if credentials are present; otherwise fall back to local JSON.
    if os.environ.get("FEISHU_APP_ID"):
        try:
            quizzes = load_from_feishu()
            print(f"Loaded {len(quizzes)} quizzes from Feishu")
        except Exception as e:
            print(f"[warn] Feishu failed ({e}); falling back to local JSON", file=sys.stderr)
            quizzes = load_from_local()
    else:
        quizzes = load_from_local()
        print(f"Loaded {len(quizzes)} quizzes from local JSON")

    if not quizzes:
        print("[error] No quizzes found", file=sys.stderr)
        sys.exit(1)

    OUTPUT_DIR.mkdir(exist_ok=True)
    (OUTPUT_DIR / "quiz").mkdir(exist_ok=True)

    for quiz in quizzes:
        page = render_quiz_page(template, quiz["data"], quiz["slug"])
        out_path = OUTPUT_DIR / "quiz" / f"{quiz['slug']}.html"
        out_path.write_text(page, encoding="utf-8")
        print(f"Generated: {out_path}")

    index_page = build_index_page(quizzes)
    (OUTPUT_DIR / "index.html").write_text(index_page, encoding="utf-8")
    print(f"Generated: {OUTPUT_DIR / 'index.html'}")


if __name__ == "__main__":
    main()

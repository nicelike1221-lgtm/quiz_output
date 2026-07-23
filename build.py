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
    """Render the site index page."""
    cards = []
    for quiz in quizzes:
        meta = quiz["data"].get("meta", {})
        title = meta.get("title", quiz["slug"])
        total = meta.get("total_questions", len(quiz["data"].get("questions", [])))
        source = meta.get("source", "")
        cards.append(
            f"""
            <a href="quiz/{quiz['slug']}.html" class="quiz-card">
                <h3>{html_module.escape(title)}</h3>
                <p class="meta">共 {total} 题 · {html_module.escape(source)}</p>
                <span class="btn">开始刷题</span>
            </a>
            """
        )

    cards_html = "\n".join(cards) if cards else "<p>暂无试卷</p>"

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>法考真题刷题</title>
<style>
:root {{
  --bg: #f0f2f5;
  --card-bg: #fff;
  --text: #1a1a2e;
  --muted: #8892b0;
  --accent: #4f6ef7;
  --accent-light: #eef1ff;
  --border: #e5e7eb;
  --radius: 12px;
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.6;
  min-height: 100vh;
}}
.container {{ max-width: 860px; margin: 0 auto; padding: 24px 16px; }}
header {{
  background: var(--card-bg);
  border-radius: var(--radius);
  padding: 32px 24px;
  margin-bottom: 20px;
  text-align: center;
  box-shadow: 0 1px 3px rgba(0,0,0,.06);
}}
header h1 {{ font-size: 1.6em; font-weight: 700; }}
header p {{ color: var(--muted); margin-top: 8px; }}
.grid {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
}}
.quiz-card {{
  display: block;
  background: var(--card-bg);
  border-radius: var(--radius);
  padding: 24px;
  text-decoration: none;
  color: inherit;
  box-shadow: 0 1px 3px rgba(0,0,0,.06);
  transition: transform .15s, box-shadow .15s;
}}
.quiz-card:hover {{
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0,0,0,.08);
}}
.quiz-card h3 {{ font-size: 1.1em; margin-bottom: 8px; }}
.quiz-card .meta {{
  font-size: .85em;
  color: var(--muted);
  margin-bottom: 16px;
}}
.quiz-card .btn {{
  display: inline-block;
  padding: 8px 16px;
  background: var(--accent);
  color: #fff;
  border-radius: 20px;
  font-size: .85em;
  font-weight: 500;
}}
footer {{
  text-align: center;
  color: var(--muted);
  font-size: .8em;
  margin-top: 32px;
}}
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>法考真题刷题</h1>
    <p>选择一套试卷，开始练习</p>
  </header>
  <div class="grid">
    {cards_html}
  </div>
  <footer>
    <p>数据源自飞书多维表格 · 自动构建于 GitHub Pages</p>
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


def parse_options_from_field(raw):
    """Accept options as a list or newline-separated string."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    if isinstance(raw, str):
        return [line.strip() for line in raw.splitlines() if line.strip()]
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
        quiz_id = str(fields.get("quiz_id", "")).strip()
        title = str(fields.get("title", "")).strip()
        if not quiz_id or not title:
            continue
        quizzes.append({
            "quiz_id": quiz_id,
            "title": title,
            "source": str(fields.get("source", "")).strip(),
            "slug": slugify(str(fields.get("slug", "")).strip() or quiz_id),
        })
    return quizzes


def parse_questions(records: list) -> list:
    questions = []
    for r in records:
        fields = r.get("fields", {})
        quiz_id = str(fields.get("quiz_id", "")).strip()
        stem = str(fields.get("stem", "")).strip()
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
                options.append(str(fields[key]).strip())
        if not options:
            options = parse_options_from_field(fields.get("options"))

        questions.append({
            "quiz_id": quiz_id,
            "id": qid,
            "type": str(fields.get("type", "single_choice")).strip(),
            "stem": stem,
            "options": options,
            "answer": str(fields.get("answer", "")).strip(),
            "explanation": str(fields.get("explanation", "")).strip(),
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

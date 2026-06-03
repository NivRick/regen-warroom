"""
再生醫療戰情室 — 資料抓取腳本 v4
資料來源：
  台灣市場   → TWSE MOPS RSS、Google News、NewsAPI
  臨床突破   → PubMed、ClinicalTrials.gov API v2、GEN News、Nature Biotechnology
  亞太合作   → Google News、BioPharma Dive、FierceBiotech（過濾）
  法規動態   → FDA RSS、Google News（法規關鍵字）
  資金動向   → STAT News、FierceBiotech、BioPharma Dive、EndPoints News、Google News
  醫療旅遊   → Google News RSS
翻譯策略：
  預設       → Google Translate 非官方 API（免費、不需 Key）
  升級版     → Gemini Flash（免費額度 1500次/天，設定 GEMINI_API_KEY 環境變數）
過濾策略：
  只保留 30 天內的資料（超過 30 天自動丟棄）
"""

import json
import os
import re
import time
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
NEWSAPI_KEY   = os.environ.get("NEWSAPI_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# ── 醫療術語白話對照表（確保翻譯一致性）──
GLOSSARY = {
    r"\bCAR[-\s]?T\b":            "CAR-T細胞療法",
    r"\bCAR NK\b":                 "CAR-NK自然殺手細胞療法",
    r"\bstem cell(?:s)?\b":       "幹細胞",
    r"\bgene therapy\b":          "基因療法",
    r"\bcell therapy\b":          "細胞治療",
    r"\bregenerative medicine\b": "再生醫療",
    r"\bclinical trial(?:s)?\b":  "臨床試驗",
    r"\bphase (?:I|1)\b":         "第一期試驗",
    r"\bphase (?:II|2)\b":        "第二期試驗",
    r"\bphase (?:III|3)\b":       "第三期試驗",
    r"\bFDA\b":                   "美國食藥局（FDA）",
    r"\bEMA\b":                   "歐洲藥品管理局（EMA）",
    r"\bPMDA\b":                  "日本藥品局（PMDA）",
    r"\biPSC(?:s)?\b":            "誘導型多能幹細胞（iPSC）",
    r"\bexosome(?:s)?\b":         "外泌體",
    r"\bmRNA\b":                  "信使RNA（mRNA）",
    r"\bCRISPR\b":                "基因剪輯技術（CRISPR）",
    r"\borganoid(?:s)?\b":        "類器官",
    r"\btissue engineering\b":    "組織工程",
    r"\bscaffold(?:s)?\b":        "生物支架",
    r"\bautologous\b":            "自體（取自患者本人）",
    r"\ballogeneic\b":            "異體（取自捐贈者）",
    r"\bin vivo\b":               "體內實驗",
    r"\bin vitro\b":              "體外實驗",
    r"\bplacebo\b":               "安慰劑",
    r"\bbiomarker(?:s)?\b":       "生物標記",
    r"\bimmunotherapy\b":         "免疫療法",
    r"\bchimeric antigen receptor\b": "嵌合抗原受體",
    r"\bSeriesA\b":               "A輪融資",
    r"\bSeries A\b":              "A輪融資",
    r"\bSeries B\b":              "B輪融資",
    r"\bSeries C\b":              "C輪融資",
    r"\bIPO\b":                   "首次公開上市（IPO）",
    r"\bventure capital\b":       "創投資金",
}
TODAY  = datetime.now(timezone.utc).strftime("%Y-%m-%d")
CUTOFF = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")  # 30 天前


# ════════════════════════════════════════════════
# 翻譯模組
# ════════════════════════════════════════════════

def is_english(text):
    """判斷文字是否主要為英文（ASCII 字母佔比 > 65%）"""
    if not text:
        return False
    alpha = [c for c in text if c.isalpha()]
    if not alpha:
        return False
    ascii_alpha = [c for c in alpha if ord(c) < 128]
    return (len(ascii_alpha) / len(alpha)) > 0.65


def apply_glossary(text):
    """套用術語對照表，讓翻譯結果更一致"""
    for pattern, replacement in GLOSSARY.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def google_translate(text, target="zh-TW"):
    """Google Translate 非官方 API（免費）"""
    if not text or len(text.strip()) < 3:
        return text
    try:
        text = text[:600]
        encoded = urllib.parse.quote(text)
        url = (
            f"https://translate.googleapis.com/translate_a/single"
            f"?client=gtx&sl=auto&tl={target}&dt=t&q={encoded}"
        )
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://translate.google.com",
        })
        with urllib.request.urlopen(req, timeout=12) as r:
            result = json.loads(r.read())
        translated = "".join(
            seg[0] for seg in result[0] if seg and seg[0]
        )
        return translated.strip()
    except Exception:
        return text   # 失敗保留原文


# 依序嘗試的 Gemini 模型（舊的被淘汰時自動換下一個）
GEMINI_MODELS = [
    "gemini-2.0-flash",
    "gemini-2.5-flash",
    "gemini-1.5-flash",
    "gemini-2.0-flash-lite",
]
_gemini_model = None   # 快取已確認可用的模型


def _find_gemini_model():
    """找到第一個可用的 Gemini 模型"""
    global _gemini_model
    if _gemini_model:
        return _gemini_model
    for model in GEMINI_MODELS:
        try:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/"
                f"models/{model}:generateContent?key={GEMINI_API_KEY}"
            )
            payload = json.dumps({
                "contents": [{"parts": [{"text": "Hi"}]}],
                "generationConfig": {"maxOutputTokens": 5},
            }).encode()
            req = urllib.request.Request(
                url, data=payload, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                r.read()
            _gemini_model = model
            print(f"    Gemini 模型確認：{model}")
            return model
        except Exception:
            continue
    return None


BATCH_SIZE  = 8   # 每次 Gemini API 翻譯幾筆（8筆≈800 tokens，安全範圍）
BATCH_DELAY = 7   # 批次間隔秒數（10 RPM → 每 6 秒一次，7秒保守）


def gemini_translate_batch(pairs):
    """批次翻譯 [(title, summary), ...] → [(zh_title, zh_summary), ...]
    一次 API call 翻多筆，大幅減少請求次數。"""
    model = _find_gemini_model()
    if not model:
        return [(None, None)] * len(pairs)

    # 組合輸入（摘要為空時，標記請自動生成）
    lines = []
    for i, (t, s) in enumerate(pairs, 1):
        lines.append(f"[{i}] 標題：{t[:200]}")
        if s and s.strip():
            lines.append(f"    摘要：{s[:150]}")
        else:
            lines.append(f"    摘要：（空白，請根據標題自動生成50字以內的繁體中文白話摘要）")

    prompt = f"""你是台灣資深生醫產業分析師。請將以下英文生醫新聞翻譯成繁體中文白話。

翻譯規則：
1. 使用台灣慣用術語（細胞治療、基因療法、幹細胞、臨床試驗、核准、募資）
2. 英文縮寫保留並加括號說明，例如：嵌合抗原受體T細胞療法（CAR-T）
3. 用台灣商業媒體的口語風格，避免艱澀學術語句
4. 金額改為「億美元」「萬美元」
5. 摘要標記為「空白，請自動生成」時，根據標題自行撰寫50字以內的重點摘要
6. 嚴格按照輸出格式，不要加任何說明

輸出格式（必須完全遵守）：
[1] 標題：xxx
    摘要：xxx
[2] 標題：xxx
    摘要：xxx

待翻譯內容：
{chr(10).join(lines)}"""

    try:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/"
            f"models/{model}:generateContent?key={GEMINI_API_KEY}"
        )
        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 2000},
        }).encode()
        req = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=40) as r:
            result = json.loads(r.read())
        raw = result["candidates"][0]["content"]["parts"][0]["text"].strip()

        # 解析輸出
        outputs = [(None, None)] * len(pairs)
        cur_idx, cur_title, cur_summary = None, None, ""
        for line in raw.splitlines():
            m = re.match(r'\[(\d+)\]\s*標題[：:]\s*(.+)', line)
            if m:
                if cur_idx is not None:
                    outputs[cur_idx] = (cur_title, cur_summary.strip())
                cur_idx    = int(m.group(1)) - 1
                cur_title  = m.group(2).strip()
                cur_summary = ""
            elif re.match(r'\s*摘要[：:]\s*', line) and cur_idx is not None:
                cur_summary = re.sub(r'^\s*摘要[：:]\s*', '', line).strip()
        if cur_idx is not None:
            outputs[cur_idx] = (cur_title, cur_summary.strip())

        return outputs
    except Exception as e:
        print(f"    Gemini 批次翻譯失敗: {e}")
        return [(None, None)] * len(pairs)


def translate_items(items, module_label=""):
    """翻譯整個模組，英文 → 繁體中文白話"""
    eng_indices = [(i, it) for i, it in enumerate(items) if is_english(it.get("title", ""))]
    if not eng_indices:
        return items

    mode = "Gemini 批次" if GEMINI_API_KEY else "Google Translate"
    print(f"    翻譯 {len(eng_indices)} 筆英文內容 ({mode})...")

    if GEMINI_API_KEY:
        # ── Gemini 批次翻譯 ──
        for batch_start in range(0, len(eng_indices), BATCH_SIZE):
            batch = eng_indices[batch_start:batch_start + BATCH_SIZE]
            pairs = [(it.get("title",""), it.get("summary","")) for _, it in batch]
            results = gemini_translate_batch(pairs)

            for (orig_i, item), (zh_title, zh_summary) in zip(batch, results):
                if zh_title:
                    items[orig_i]["title"]   = zh_title
                    items[orig_i]["summary"] = zh_summary or ""
                    items[orig_i]["lang"]    = "zh-TW"
                else:
                    # 單筆降級到 Google Translate
                    items[orig_i]["title"] = apply_glossary(google_translate(item["title"]))
                    if item.get("summary") and is_english(item["summary"]):
                        items[orig_i]["summary"] = apply_glossary(google_translate(item["summary"]))
                    items[orig_i]["lang"] = "zh-TW"

            remaining = len(eng_indices) - batch_start - BATCH_SIZE
            if remaining > 0:
                print(f"      還剩 {remaining} 筆，等待 {BATCH_DELAY} 秒...")
                time.sleep(BATCH_DELAY)
    else:
        # ── Google Translate 逐筆翻譯 ──
        for orig_i, item in eng_indices:
            items[orig_i]["title"] = apply_glossary(google_translate(item.get("title","")))
            if item.get("summary") and is_english(item["summary"]):
                time.sleep(0.15)
                items[orig_i]["summary"] = apply_glossary(google_translate(item["summary"]))
            items[orig_i]["lang"] = "zh-TW"
            time.sleep(0.15)

    return items


# ════════════════════════════════════════════════
# 基礎工具
# ════════════════════════════════════════════════

def fetch_url(url, timeout=20):
    headers = {
        "User-Agent": "RegenIntel/2.0 (research aggregator; contact: research@regen-intel.local)",
        "Accept": "application/json, application/xml, text/xml, */*",
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        # 嘗試 UTF-8，失敗則 latin-1
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw.decode("latin-1", errors="replace")


def save_json(filename, module_id, items):
    """去重 → 過濾日期 → 翻譯 → 排序 → 儲存"""
    # 1. 去重 + 日期過濾
    seen_titles = set()
    cleaned = []
    for item in items:
        title_key = (item.get("title") or "")[:60].lower().strip()
        if not title_key or title_key in seen_titles:
            continue
        seen_titles.add(title_key)
        fixed = clamp_date(item.get("date", ""))
        if fixed is None:
            continue
        item["date"] = fixed
        cleaned.append(item)

    # 2. 翻譯英文內容 → 繁體中文白話
    cleaned = translate_items(cleaned, module_id)

    # 3. 排序（新到舊）、取前 50 筆
    cleaned.sort(key=lambda x: x.get("date", ""), reverse=True)

    data = {
        "module": module_id,
        "updated": datetime.now(timezone.utc).isoformat(),
        "items": cleaned[:50],
    }
    path = DATA_DIR / filename
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✓ {filename}: {len(cleaned)} 筆（上限 50，30天內）")


def clamp_date(date_str):
    if not date_str:
        return TODAY
    if date_str > TODAY:
        return TODAY        # 未來日期 → 今天
    if date_str < CUTOFF:
        return None         # 超過 2 年 → 丟棄
    return date_str


def parse_rfc_date(s):
    """RFC 2822 → YYYY-MM-DD"""
    if not s:
        return TODAY
    months = {
        "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04",
        "May": "05", "Jun": "06", "Jul": "07", "Aug": "08",
        "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12",
    }
    m = re.search(r"(\d{1,2})\s+(\w{3})\s+(\d{4})", s)
    if m:
        day = m.group(1).zfill(2)
        mon = months.get(m.group(2), "01")
        year = m.group(3)
        return f"{year}-{mon}-{day}"
    return TODAY


def strip_html(text):
    text = re.sub(r"<[^>]+>", "", text)
    for ent, ch in [("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"),
                    ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'")]:
        text = text.replace(ent, ch)
    text = re.sub(r"&#\d+;", "", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def clean_text(text):
    return re.sub(r"\s+", " ", str(text)).strip()


def split_google_title(title, fallback_source):
    """「新聞標題 - 媒體名稱」→ (title, source)"""
    parts = title.rsplit(" - ", 1)
    if len(parts) == 2 and 2 <= len(parts[1]) <= 45:
        return parts[0].strip(), parts[1].strip()
    return title.strip(), fallback_source


def parse_rss_feed(url, source_name, limit=12, kw_filter=None):
    """通用 RSS 解析器，支援關鍵字過濾"""
    xml = fetch_url(url)
    root = ET.fromstring(xml)
    results = []
    for item in list(root.iter("item"))[:limit * 3]:   # 多抓再過濾
        if len(results) >= limit:
            break
        raw_title = (item.findtext("title") or "").strip()
        desc = strip_html((item.findtext("description") or "").strip())
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()

        title, real_source = split_google_title(raw_title, source_name)

        # 關鍵字過濾
        if kw_filter:
            combined = (title + desc).lower()
            if not any(kw.lower() in combined for kw in kw_filter):
                continue

        # 清理 description（Google News 常常是 title 的重複）
        clean_desc = desc
        if title.lower()[:40] in clean_desc.lower():
            clean_desc = re.sub(re.escape(title[:40]), "", clean_desc, flags=re.IGNORECASE)
        clean_desc = clean_desc.strip(" -–—\xa0")
        if len(clean_desc) < 25:
            clean_desc = ""

        if title:
            results.append({
                "title": title,
                "summary": clean_desc[:250],
                "source": real_source,
                "date": parse_rfc_date(pub),
                "url": link,
            })
    return results


def google_news_rss(query, lang="en", country="US", limit=8):
    encoded = urllib.parse.quote(query)
    ceid = f"{country}:{lang}"
    url = f"https://news.google.com/rss/search?q={encoded}&hl={lang}&gl={country}&ceid={ceid}"
    return parse_rss_feed(url, "Google News", limit)


def dedup(items):
    seen, out = set(), []
    for item in items:
        key = (item.get("title") or "")[:55].lower()
        if key and key not in seen:
            seen.add(key)
            out.append(item)
    return out


# ════════════════════════════════════════════════
# 1. 台灣市場
# ════════════════════════════════════════════════
def fetch_taiwan_market():
    print("📍 台灣市場...")
    items = []
    kw = [
        "再生醫療", "細胞治療", "幹細胞", "基因治療", "CAR-T", "外泌體", "iPSC",
        "生技", "訊聯", "長聖", "北極星", "亞果", "宣捷", "尖端醫",
        "臍帶血", "免疫細胞", "異體", "自體",
    ]

    # ── GeneOnline 台灣生技專業媒體（繁體中文，最重要來源）──
    try:
        items += parse_rss_feed(
            "https://geneonline.news/feed/",
            "GeneOnline", limit=20, kw_filter=kw
        )
        print(f"    GeneOnline: {len(items)} 筆")
    except Exception as e:
        print(f"  GeneOnline: {e}")

    # ── TWSE MOPS 重大訊息 ──
    try:
        xml = fetch_url("https://mops.twse.com.tw/mops/rss/news_rss.xml")
        root = ET.fromstring(xml)
        for it in root.iter("item"):
            title = (it.findtext("title") or "").strip()
            desc  = strip_html((it.findtext("description") or ""))
            if any(k in title + desc for k in kw):
                items.append({
                    "title": title, "summary": desc[:200],
                    "source": "TWSE MOPS",
                    "date": parse_rfc_date(it.findtext("pubDate") or ""),
                    "url": (it.findtext("link") or ""),
                })
    except Exception as e:
        print(f"  MOPS: {e}")

    # ── 鉅亨網生技醫療 ──
    try:
        items += parse_rss_feed(
            "https://www.cnyes.com/rss/cat/tw_stock_news",
            "鉅亨網", limit=15, kw_filter=kw
        )
    except Exception as e:
        print(f"  鉅亨網: {e}")

    # ── 工商時報生技 ──
    try:
        items += parse_rss_feed(
            "https://ctee.com.tw/feed",
            "工商時報", limit=15, kw_filter=kw
        )
    except Exception as e:
        print(f"  工商時報: {e}")

    # ── 經濟日報 ──
    try:
        items += parse_rss_feed(
            "https://money.udn.com/rssfeed/news/1/5612?ch=money",
            "經濟日報", limit=15, kw_filter=kw
        )
    except Exception as e:
        print(f"  經濟日報: {e}")

    # ── 中央社生技健康 ──
    try:
        items += parse_rss_feed(
            "https://feeds.feedburner.com/cna/Zozw",
            "中央社", limit=15, kw_filter=kw
        )
    except Exception as e:
        print(f"  中央社: {e}")

    # ── 生技中心 (DCB) 新聞 ──
    try:
        items += parse_rss_feed(
            "https://www.dcb.org.tw/news/rss",
            "生技中心", limit=10, kw_filter=kw
        )
    except Exception as e:
        print(f"  生技中心: {e}")

    # ── Google News 台灣中文（多組關鍵字廣撒）──
    for q in [
        "再生醫療 台灣",
        "細胞治療 台灣 臨床",
        "幹細胞 台灣 生技",
        "基因治療 台灣 衛福部",
        "CAR-T 台灣",
        "訊聯 長聖 亞果 宣捷",
        "生技股 再生醫療 上市",
        "台灣 免疫細胞 治療 核准",
    ]:
        try:
            items += google_news_rss(q, lang="zh-TW", country="TW", limit=8)
        except Exception as e:
            print(f"  GNews TW ({q[:10]}): {e}")

    # ── NewsAPI（若有金鑰）──
    if NEWSAPI_KEY:
        try:
            q = urllib.parse.quote("再生醫療 OR 細胞治療 台灣")
            url = (f"https://newsapi.org/v2/everything?q={q}&language=zh"
                   f"&sortBy=publishedAt&pageSize=20&apiKey={NEWSAPI_KEY}")
            data = json.loads(fetch_url(url))
            for a in data.get("articles", []):
                items.append({
                    "title": a.get("title", ""),
                    "summary": a.get("description") or "",
                    "source": a.get("source", {}).get("name", "NewsAPI"),
                    "date": (a.get("publishedAt") or "")[:10],
                    "url": a.get("url", ""),
                })
        except Exception as e:
            print(f"  NewsAPI: {e}")

    save_json("taiwan-market.json", "taiwan", dedup(items))


# ════════════════════════════════════════════════
# 2. 全球臨床突破
#    來源：PubMed + ClinicalTrials.gov + GEN News + Nature Biotechnology
# ════════════════════════════════════════════════
def fetch_global_research():
    print("🔬 全球臨床突破...")
    items = []

    # ── PubMed ──
    try:
        query = urllib.parse.quote(
            "(regenerative medicine[Title/Abstract] OR cell therapy[Title/Abstract] OR "
            "stem cell therapy[Title/Abstract] OR CAR-T[Title/Abstract] OR "
            "gene therapy[Title/Abstract] OR exosome therapy[Title/Abstract] OR "
            "iPSC[Title/Abstract] OR organoid[Title/Abstract] OR "
            "tissue engineering[Title/Abstract])"
        )
        mindate = CUTOFF.replace("-", "/")
        maxdate = TODAY.replace("-", "/")
        search_url = (
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
            f"?db=pubmed&term={query}&retmax=40&sort=pub+date&retmode=json"
            f"&datetype=pdat&mindate={mindate}&maxdate={maxdate}"
        )
        ids = json.loads(fetch_url(search_url)).get("esearchresult", {}).get("idlist", [])

        if ids:
            id_str = ",".join(ids[:20])
            xml = fetch_url(
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
                f"?db=pubmed&id={id_str}&retmode=xml&rettype=abstract"
            )
            root = ET.fromstring(xml)
            month_map = {
                "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04",
                "May": "05", "Jun": "06", "Jul": "07", "Aug": "08",
                "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12",
            }
            for art in root.findall(".//PubmedArticle"):
                def txt(path):
                    el = art.find(path)
                    return (el.text or "") if el is not None else ""
                title    = clean_text(txt(".//ArticleTitle"))
                abstract = clean_text(txt(".//AbstractText"))
                pmid     = txt(".//PMID")
                year     = txt(".//PubDate/Year") or TODAY[:4]
                month    = txt(".//PubDate/Month")
                mon_num  = month_map.get(month, month.zfill(2) if month.isdigit() else "01")
                items.append({
                    "title": title,
                    "summary": abstract[:300] + ("..." if len(abstract) > 300 else ""),
                    "source": "PubMed",
                    "date": f"{year}-{mon_num}-01",
                    "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
                })
    except Exception as e:
        print(f"  PubMed: {e}")

    # ── ClinicalTrials.gov API v2 ──
    try:
        params = urllib.parse.urlencode({
            "query.cond": "regenerative medicine OR cell therapy OR gene therapy OR CAR-T OR stem cell OR iPSC OR exosome",
            "filter.advanced": f"AREA[StartDate]RANGE[{CUTOFF},MAX]",
            "pageSize": 20,
            "format": "json",
            "fields": "NCTId,BriefTitle,OverallStatus,StartDate,LeadSponsorName,LocationCountry,Phase,BriefSummary",
        })
        ct_data = json.loads(fetch_url(f"https://clinicaltrials.gov/api/v2/studies?{params}"))
        for study in ct_data.get("studies", []):
            proto = study.get("protocolSection", {})
            ident = proto.get("identificationModule", {})
            status = proto.get("statusModule", {})
            desc = proto.get("descriptionModule", {})
            sponsor = proto.get("sponsorCollaboratorsModule", {})
            design = proto.get("designModule", {})

            nct_id = ident.get("nctId", "")
            title  = ident.get("briefTitle", "")
            phase  = ", ".join(design.get("phases", [])) or "N/A"
            overall_status = status.get("overallStatus", "")
            start_date = status.get("startDateStruct", {}).get("date", "")[:10] or TODAY
            summary = desc.get("briefSummary", "")[:250]
            lead_sponsor = sponsor.get("leadSponsor", {}).get("name", "")
            countries = proto.get("contactsLocationsModule", {})
            country_list = list({
                loc.get("country", "")
                for loc in countries.get("locations", [])
                if loc.get("country")
            })[:3]

            items.append({
                "title": f"[{phase}] {title}",
                "summary": f"狀態：{overall_status}｜主辦：{lead_sponsor}｜{summary}",
                "source": f"ClinicalTrials.gov｜{', '.join(country_list) or 'Global'}",
                "date": start_date,
                "url": f"https://clinicaltrials.gov/study/{nct_id}" if nct_id else "",
            })
    except Exception as e:
        print(f"  ClinicalTrials.gov: {e}")

    # ── GEN (Genetic Engineering & Biotechnology News) ──
    REGEN_KW = [
        "cell therapy", "gene therapy", "regenerative", "CAR-T", "stem cell",
        "exosome", "mRNA therapy", "CRISPR", "clinical trial", "iPSC",
        "tissue engineering", "scaffold", "organoid",
    ]
    try:
        items += parse_rss_feed(
            "https://www.genengnews.com/feed/",
            "GEN News", limit=10, kw_filter=REGEN_KW
        )
    except Exception as e:
        print(f"  GEN News: {e}")

    # ── Nature Biotechnology ──
    try:
        items += parse_rss_feed(
            "https://www.nature.com/nbt.rss",
            "Nature Biotechnology", limit=8, kw_filter=REGEN_KW
        )
    except Exception as e:
        print(f"  Nature Biotech: {e}")

    # ── BioSpace ──
    try:
        items += parse_rss_feed(
            "https://www.biospace.com/news/feed/",
            "BioSpace", limit=10, kw_filter=REGEN_KW
        )
    except Exception as e:
        print(f"  BioSpace: {e}")

    # ── EndPoints News ──
    try:
        items += parse_rss_feed(
            "https://endpts.com/feed/",
            "EndPoints News", limit=10, kw_filter=REGEN_KW
        )
    except Exception as e:
        print(f"  EndPoints News: {e}")

    # ── Google News 補充（近期研究）──
    for q in [
        "cell therapy clinical trial results 2026",
        "gene therapy breakthrough FDA approval 2026",
        "CAR-T stem cell exosome research 2026",
    ]:
        try:
            items += google_news_rss(q, limit=6)
        except Exception as e:
            print(f"  GNews research: {e}")

    save_json("global-research.json", "research", dedup(items))


# ════════════════════════════════════════════════
# 3. 海外機構亞太合作
#    來源：Google News + BioPharma Dive + FierceBiotech（過濾）
# ════════════════════════════════════════════════
def fetch_asia_pacific():
    print("🌏 亞太合作...")
    items = []
    APAC_KW = [
        "Asia", "Japan", "Korea", "Singapore", "Taiwan", "China", "APAC",
        "Asia Pacific", "東南亞", "亞太", "日本", "韓國",
    ]

    # Google News 英文
    for q in [
        "regenerative medicine Asia Pacific collaboration 2025 2026",
        "cell therapy Japan Korea Singapore clinical partnership",
        "gene therapy APAC investment deal",
    ]:
        try:
            items += google_news_rss(q, limit=8)
        except Exception as e:
            print(f"  GNews APAC: {e}")

    # Google News 中文
    for q in ["再生醫療 亞太 合作 日本 韓國", "細胞治療 海外 合作 台灣"]:
        try:
            items += google_news_rss(q, lang="zh-TW", country="TW", limit=6)
        except Exception as e:
            print(f"  GNews TW APAC: {e}")

    # BioPharma Dive（APAC 過濾）
    try:
        items += parse_rss_feed(
            "https://www.biopharmadive.com/feeds/news/",
            "BioPharma Dive", limit=8, kw_filter=APAC_KW
        )
    except Exception as e:
        print(f"  BioPharma Dive: {e}")

    # FierceBiotech（APAC 過濾）
    try:
        items += parse_rss_feed(
            "https://www.fiercebiotech.com/rss/xml",
            "FierceBiotech", limit=8, kw_filter=APAC_KW
        )
    except Exception as e:
        print(f"  FierceBiotech: {e}")

    save_json("asia-pacific.json", "apac", dedup(items))


# ════════════════════════════════════════════════
# 4. 法規動態
#    來源：FDA RSS + Google News（台灣、日本 PMDA、EMA）
# ════════════════════════════════════════════════
def fetch_regulations():
    print("⚖️  法規動態...")
    items = []
    REGEN_KW = [
        "cell therapy", "gene therapy", "regenerative", "CAR-T", "stem cell",
        "tissue engineering", "biologics", "ATMP", "approval", "clearance",
        "再生醫療", "細胞治療", "基因治療", "核准", "法規",
    ]

    # FDA RSS feeds
    for feed_url, source in [
        ("https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/biologics/rss.xml", "FDA Biologics"),
        ("https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/pressreleases/rss.xml", "FDA Press Releases"),
        ("https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/fda-approvals-safety-alerts/rss.xml", "FDA Approvals"),
    ]:
        try:
            items += parse_rss_feed(feed_url, source, limit=8, kw_filter=REGEN_KW)
        except Exception as e:
            print(f"  {source}: {e}")

    # Google News — 台灣法規
    for q in ["再生醫療法 台灣 衛福部 食藥署", "細胞治療 台灣 法規 核准"]:
        try:
            items += google_news_rss(q, lang="zh-TW", country="TW", limit=6)
        except Exception as e:
            print(f"  GNews TW 法規: {e}")

    # Google News — 日本 PMDA / EMA
    for q in [
        "PMDA Japan regenerative medicine approval 2025 2026",
        "EMA cell gene therapy approval 2025 2026",
    ]:
        try:
            items += google_news_rss(q, limit=6)
        except Exception as e:
            print(f"  GNews 法規 Intl: {e}")

    # GEN News（法規過濾）
    try:
        items += parse_rss_feed(
            "https://www.genengnews.com/feed/",
            "GEN News", limit=6,
            kw_filter=["FDA", "EMA", "PMDA", "approved", "approval", "regulatory", "clearance"]
        )
    except Exception as e:
        print(f"  GEN News 法規: {e}")

    save_json("regulations.json", "regulation", dedup(items))


# ════════════════════════════════════════════════
# 5. 市場資金動向
#    來源：STAT News + FierceBiotech + BioPharma Dive + Google News
# ════════════════════════════════════════════════
def fetch_funding():
    print("💰 資金動向...")
    items = []
    FUNDING_KW = [
        "raises", "funding", "Series A", "Series B", "Series C", "IPO",
        "merger", "acquisition", "deal", "investment", "venture", "million",
        "billion", "募資", "投資", "上市", "合併", "收購",
        "cell therapy", "gene therapy", "regenerative", "CAR-T", "stem cell",
    ]

    # STAT News（科學+商業）
    try:
        items += parse_rss_feed(
            "https://www.statnews.com/feed/",
            "STAT News", limit=12, kw_filter=FUNDING_KW
        )
    except Exception as e:
        print(f"  STAT News: {e}")

    # FierceBiotech
    try:
        items += parse_rss_feed(
            "https://www.fiercebiotech.com/rss/xml",
            "FierceBiotech", limit=12, kw_filter=FUNDING_KW
        )
    except Exception as e:
        print(f"  FierceBiotech: {e}")

    # BioPharma Dive
    try:
        items += parse_rss_feed(
            "https://www.biopharmadive.com/feeds/news/",
            "BioPharma Dive", limit=10, kw_filter=FUNDING_KW
        )
    except Exception as e:
        print(f"  BioPharma Dive: {e}")

    # EndPoints News（資金/交易）
    try:
        items += parse_rss_feed(
            "https://endpts.com/feed/",
            "EndPoints News", limit=10, kw_filter=FUNDING_KW
        )
    except Exception as e:
        print(f"  EndPoints News 資金: {e}")

    # BioSpace（募資新聞）
    try:
        items += parse_rss_feed(
            "https://www.biospace.com/news/feed/",
            "BioSpace", limit=8, kw_filter=FUNDING_KW
        )
    except Exception as e:
        print(f"  BioSpace 資金: {e}")

    # Google News
    for q in [
        "regenerative medicine biotech funding raises million 2025 2026",
        "cell therapy gene therapy IPO Series funding",
        "再生醫療 生技 投資 募資 上市",
    ]:
        try:
            items += google_news_rss(q, limit=6)
        except Exception as e:
            print(f"  GNews 資金: {e}")

    save_json("funding.json", "funding", dedup(items))


# ════════════════════════════════════════════════
# 6. 醫療旅遊
#    來源：Google News RSS
# ════════════════════════════════════════════════
def fetch_medical_tourism():
    print("✈️  醫療旅遊...")
    items = []

    for q in [
        "medical tourism regenerative medicine stem cell treatment clinic 2025 2026",
        "cell therapy medical travel Japan Korea Thailand Taiwan",
        "longevity clinic stem cell anti-aging treatment abroad",
        "再生醫療 醫療旅遊 幹細胞 治療 海外 日本 泰國",
    ]:
        try:
            items += google_news_rss(q, limit=7)
        except Exception as e:
            print(f"  GNews 旅遊: {e}")

    save_json("medical-tourism.json", "tourism", dedup(items))


# ════════════════════════════════════════════════
# 7. 競爭動態
#    追蹤全球大廠與台灣競爭者的最新動態
# ════════════════════════════════════════════════
def fetch_competitors():
    print("🎯 競爭動態...")
    items = []

    # 全球主要競爭者（CAR-T / 基因治療 / 再生醫療大廠）
    GLOBAL_QUERIES = [
        "Novartis Kymriah CAR-T cell therapy",
        "Gilead Kite Yescarta cell therapy approval",
        "Bristol Myers Squibb Breyanzi Lisocabtagene",
        "Legend Biotech Ciltacel BCMA myeloma",
        "bluebird bio gene therapy FDA",
        "Fate Therapeutics iPSC NK cell",
        "Intellia Therapeutics CRISPR in vivo",
        "Vertex Editas CRISPR sickle cell thalassemia",
        "Regeneron gene therapy ocular",
        "Johnson Johnson Janssen cell therapy",
    ]
    for q in GLOBAL_QUERIES:
        try:
            items += google_news_rss(q, limit=4)
        except Exception as e:
            print(f"  GNews 全球對手: {e}")

    # 台灣競爭者
    TW_QUERIES = [
        "震泰生技 細胞治療 臨床",
        "訊聯生物科技 幹細胞 CAR-T",
        "長聖國際生技 臨床試驗 核准",
        "醣基生醫 糖鏈工程",
        "亞果生醫 軟骨 幹細胞",
        "宣捷生技 臍帶血 幹細胞",
        "震泰 訊聯 長聖 再生醫療 台灣",
    ]
    for q in TW_QUERIES:
        try:
            items += google_news_rss(q, lang="zh-TW", country="TW", limit=4)
        except Exception as e:
            print(f"  GNews TW 對手: {e}")

    # 競爭動態英文資訊（BioSpace / EndPoints）
    COMP_KW = [
        "Novartis", "Gilead", "Kite", "Bristol Myers", "Legend Biotech",
        "bluebird", "Fate Therapeutics", "Intellia", "Editas", "Vertex",
        "CAR-T", "cell therapy approval", "gene therapy IND",
    ]
    for feed_url, src in [
        ("https://endpts.com/feed/", "EndPoints News"),
        ("https://www.biospace.com/news/feed/", "BioSpace"),
    ]:
        try:
            items += parse_rss_feed(feed_url, src, limit=8, kw_filter=COMP_KW)
        except Exception as e:
            print(f"  {src} 競爭: {e}")

    save_json("competitors.json", "competitor", dedup(items))


# ════════════════════════════════════════════════
# 8. 台灣再生醫療股票（TWSE + OTC 收盤資料）
#    來源：statementdog.com/taiex/29-regenerative-medicine-industry
#    格式：(股票代碼, 公司名稱, 產業層級)
# ════════════════════════════════════════════════
STOCK_WATCHLIST = [
    # ── 上游：幹細胞收集儲存 ──
    ("1784", "訊聯",     "上游"),
    ("4170", "鑫品生醫", "上游"),
    ("4186", "尖端醫",   "上游"),
    ("6461", "益得",     "上游"),
    ("6712", "長聖",     "上游"),
    ("6794", "向榮生技", "上游"),
    ("6838", "台新藥",   "上游"),
    ("6891", "樂迦再生", "上游"),
    ("6892", "台寶生醫", "上游"),
    ("6704", "國璽幹細胞","上游"),
    ("4724", "宣捷",     "上游"),
    ("6973", "永立榮",   "上游"),
    ("6986", "和迅",     "上游"),
    # ── 中游：幹細胞開發 ──
    ("6748", "亞果生醫", "中游"),
    ("6879", "大江基因", "中游"),
    ("6976", "育世博",   "中游"),
    ("6949", "沛爾生醫", "中游"),
    # ── 下游：臨床/移植/治療 ──
    ("3118", "進階",     "下游"),
    ("3224", "三顧",     "下游"),
    ("6550", "北極星藥", "下游"),
    ("6662", "樂斯科",   "下游"),
    ("6814", "路迦生醫", "下游"),
    ("6939", "啟弘生技", "下游"),
    # 7xxx 興櫃（光晟/通用/仲恩/富禾/思必瑞特/訊聯智藥/海昌/寶泰/宇越）另有 ESB API 支援
]


def fetch_stocks():
    """
    三市場全覆蓋：TWSE 上市 + OTC 上櫃 + 興櫃 ESB
    只需 3 個 API call，涵蓋再生醫療族群所有掛牌公司。
    """
    print("📈 台灣再生醫療股票（TWSE + OTC + 興櫃 全量）...")
    roc_today = f"{int(TODAY[:4])-1911}/{TODAY[5:7]}/{TODAY[8:10]}"

    # ── 1. TWSE 上市全量 ──
    twse_map: dict = {}
    try:
        rows = json.loads(fetch_url(
            "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
        ))
        for s in rows:
            code = s.get("Code", "").strip()
            if code:
                twse_map[code] = s
        print(f"  TWSE 上市: {len(twse_map)} 支")
    except Exception as e:
        print(f"  TWSE API 失敗: {e}")

    # ── 2. OTC 上櫃全量 ──
    otc_map: dict = {}
    try:
        rows = json.loads(fetch_url(
            "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes"
        ))
        for s in rows:
            code = s.get("SecuritiesCompanyCode", "").strip()
            if code:
                otc_map[code] = s
        print(f"  OTC 上櫃:  {len(otc_map)} 支")
    except Exception as e:
        print(f"  OTC API 失敗: {e}")

    # ── 3. 興櫃 ESB 全量 ──
    # API: SecuritiesCompanyCode / CompanyName / LatestPrice / PreviousAveragePrice
    esb_map: dict = {}
    try:
        rows = json.loads(fetch_url(
            "https://www.tpex.org.tw/openapi/v1/tpex_esb_latest_statistics"
        ))
        seen = set()
        for s in rows:
            code = s.get("SecuritiesCompanyCode", "").strip()
            if code and code not in seen:
                esb_map[code] = s
                seen.add(code)
        print(f"  興櫃 ESB:  {len(esb_map)} 支")
    except Exception as e:
        print(f"  ESB API 失敗: {e}")

    # ── 逐支對照 watchlist ──
    results = []
    for code, name, tier in STOCK_WATCHLIST:
        market = None
        entry  = None
        if code in twse_map:
            market, entry = "TWSE", twse_map[code]
        elif code in otc_map:
            market, entry = "OTC", otc_map[code]
        elif code in esb_map:
            market, entry = "ESB", esb_map[code]

        if not entry:
            print(f"  ⚠ {code} {name}：三市場均查無資料（停牌/未上市）")
            continue

        # ── 解析各市場格式 ──
        if market == "TWSE":
            # ClosingPrice / Change / Date("1150603")
            close_str  = str(entry.get("ClosingPrice", "0")).replace(",", "").strip()
            change_raw = str(entry.get("Change", "0")).replace(",", "").strip()
            raw_date   = str(entry.get("Date", ""))
            date_disp  = (f"{raw_date[:3]}/{raw_date[3:5]}/{raw_date[5:7]}"
                          if len(raw_date) == 7 else raw_date)

        elif market == "OTC":
            # Close / Change("+0.24" / "-0.19")
            close_str  = str(entry.get("Close", "0")).replace(",", "").strip()
            change_raw = str(entry.get("Change", "0")).replace(",", "").strip()
            date_disp  = roc_today

        else:  # ESB 興櫃
            # LatestPrice / PreviousAveragePrice（純數字）
            latest = float(entry.get("LatestPrice", 0) or 0)
            prev   = float(entry.get("PreviousAveragePrice", 0) or 0)
            # 當日無成交（LatestPrice=0）→ 用前日均價顯示，漲跌=0
            if latest == 0:
                latest = prev
            close_str  = f"{latest:.2f}"
            change_raw = f"{latest - prev:.2f}"
            date_disp  = roc_today

        try:
            close_f  = float(close_str)
            change_f = float(change_raw)   # "+0.24"/"-0.19"/"-0.11" Python 均可解析
            prev_p   = close_f - change_f
            pct      = round(change_f / prev_p * 100, 2) if prev_p else 0.0
        except (ValueError, ZeroDivisionError):
            close_f = change_f = pct = 0.0

        results.append({
            "code":       code,
            "name":       name,
            "tier":       tier,
            "close":      close_str,
            "change":     f"+{change_f:.2f}" if change_f > 0 else f"{change_f:.2f}",
            "change_pct": pct,
            "date":       date_disp,
            "market":     market,
        })

    path = DATA_DIR / "stocks.json"
    path.write_text(
        json.dumps({"updated": datetime.now(timezone.utc).isoformat(), "stocks": results},
                   ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"  ✓ stocks.json: {len(results)}/{len(STOCK_WATCHLIST)} 支成功")


# ════════════════════════════════════════════════
# 主程式
# ════════════════════════════════════════════════
if __name__ == "__main__":
    DATA_DIR.mkdir(exist_ok=True)
    print(f"=== 再生醫療戰情室 資料更新開始 ({TODAY}) ===\n")

    fetch_taiwan_market()
    fetch_global_research()
    fetch_asia_pacific()
    fetch_regulations()
    fetch_funding()
    fetch_medical_tourism()
    fetch_competitors()
    fetch_stocks()

    print(f"\n=== 更新完成 {datetime.now(timezone.utc).strftime('%H:%M UTC')} ===")

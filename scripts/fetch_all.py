"""
再生醫療戰情室 — 資料抓取腳本 v3
資料來源：
  台灣市場   → TWSE MOPS RSS、Google News、NewsAPI
  臨床突破   → PubMed、ClinicalTrials.gov API v2、GEN News、Nature Biotechnology
  亞太合作   → Google News、BioPharma Dive、FierceBiotech（過濾）
  法規動態   → FDA RSS、Google News（法規關鍵字）
  資金動向   → STAT News、FierceBiotech、BioPharma Dive、Google News
  醫療旅遊   → Google News RSS
翻譯策略：
  預設       → Google Translate 非官方 API（免費、不需 Key）
  升級版     → Gemini 1.5 Flash（免費額度 1500次/天，設定 GEMINI_API_KEY 環境變數）
"""

import json
import os
import re
import time
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
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
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
CUTOFF = f"{int(TODAY[:4]) - 2}{TODAY[4:]}"   # 2 年前作為最舊門檻


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


def gemini_translate(title, summary):
    """Gemini：翻譯 + 白話化（自動選用可用模型）"""
    if not GEMINI_API_KEY:
        return None, None

    model = _find_gemini_model()
    if not model:
        return None, None

    prompt = f"""你是台灣資深生醫產業分析師，請將以下英文生醫新聞翻譯成繁體中文。

規則：
1. 使用台灣慣用術語（細胞治療、基因療法、幹細胞、臨床試驗、核准、募資）
2. 專有名詞保留英文縮寫並加括號，例如：嵌合抗原受體T細胞療法（CAR-T）
3. 把艱澀學術句改寫成台灣商業媒體的口語風格
4. 金額單位改為「億美元」「萬美元」等台灣讀者習慣的說法
5. 只輸出翻譯，不要加任何說明或標題

【標題】{title}
【摘要】{summary if summary else "（無）"}

請依序輸出：
標題翻譯：（一行）
摘要翻譯：（若無摘要則輸出空行）"""

    try:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/"
            f"models/{model}:generateContent?key={GEMINI_API_KEY}"
        )
        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 400},
        }).encode()
        req = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            result = json.loads(r.read())
        raw = result["candidates"][0]["content"]["parts"][0]["text"].strip()

        title_zh, summary_zh = "", ""
        for line in raw.splitlines():
            if line.startswith("標題翻譯："):
                title_zh = line.replace("標題翻譯：", "").strip()
            elif line.startswith("摘要翻譯："):
                summary_zh = line.replace("摘要翻譯：", "").strip()
        return title_zh or None, summary_zh or None
    except Exception as e:
        print(f"    Gemini 翻譯失敗: {e}")
        return None, None


def translate_items(items, module_label=""):
    """翻譯整個模組的 items，英文 → 繁體中文白話"""
    total = sum(1 for it in items if is_english(it.get("title", "")))
    if total == 0:
        return items

    print(f"    翻譯 {total} 筆英文內容 ({'Gemini' if GEMINI_API_KEY else 'Google Translate'})...")

    translated = []
    for item in items:
        title   = item.get("title", "")
        summary = item.get("summary", "")

        if not is_english(title):
            translated.append(item)
            continue

        if GEMINI_API_KEY:
            # Gemini：翻譯 + 白話化（一次搞定）
            t_title, t_summary = gemini_translate(title, summary)
            if t_title:
                item["title"]   = t_title
                item["summary"] = t_summary or ""
                item["lang"]    = "zh-TW"
            else:
                # Gemini 失敗 → 降級 Google Translate
                item["title"]   = apply_glossary(google_translate(title))
                if summary and is_english(summary):
                    item["summary"] = apply_glossary(google_translate(summary))
                item["lang"] = "zh-TW"
            time.sleep(0.5)   # Gemini rate limit
        else:
            # Google Translate：翻譯後套用術語表
            item["title"] = apply_glossary(google_translate(title))
            if summary and is_english(summary):
                time.sleep(0.15)
                item["summary"] = apply_glossary(google_translate(summary))
            item["lang"] = "zh-TW"
            time.sleep(0.15)

        translated.append(item)

    return translated


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

    # 3. 排序（新到舊）、取前 30 筆
    cleaned.sort(key=lambda x: x.get("date", ""), reverse=True)

    data = {
        "module": module_id,
        "updated": datetime.now(timezone.utc).isoformat(),
        "items": cleaned[:30],
    }
    path = DATA_DIR / filename
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✓ {filename}: {len(cleaned)} 筆（上限 30）")


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
    kw = ["再生醫療", "細胞治療", "幹細胞", "基因治療", "CAR-T", "外泌體", "iPSC"]

    # TWSE MOPS
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

    # NewsAPI（若有金鑰）
    if NEWSAPI_KEY and len(items) < 8:
        try:
            q = urllib.parse.quote("再生醫療 OR 細胞治療 台灣")
            url = (f"https://newsapi.org/v2/everything?q={q}&language=zh"
                   f"&sortBy=publishedAt&pageSize=15&apiKey={NEWSAPI_KEY}")
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

    # Google News 中文台灣
    for q in ["再生醫療 台灣 生技", "細胞治療 台灣 臨床", "基因治療 台灣 上市"]:
        try:
            items += google_news_rss(q, lang="zh-TW", country="TW", limit=6)
        except Exception as e:
            print(f"  GNews TW: {e}")

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
            "gene therapy[Title/Abstract] OR exosome therapy[Title/Abstract]) "
            "AND (\"clinical trial\"[PT] OR \"phase 1\"[Title/Abstract] OR "
            "\"phase 2\"[Title/Abstract] OR \"phase 3\"[Title/Abstract])"
        )
        search_url = (
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
            f"?db=pubmed&term={query}&retmax=25&sort=pub+date&retmode=json"
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
            "query.cond": "regenerative medicine OR cell therapy OR gene therapy OR CAR-T OR stem cell",
            "filter.advanced": "AREA[StartDate]RANGE[2024-01-01,MAX]",
            "pageSize": 15,
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

    print(f"\n=== 更新完成 {datetime.now(timezone.utc).strftime('%H:%M UTC')} ===")

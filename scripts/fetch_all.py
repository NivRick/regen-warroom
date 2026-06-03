"""
再生醫療戰情室 — 資料抓取腳本
執行方式：python scripts/fetch_all.py
需要環境變數：NEWSAPI_KEY（可選，有更好）
免費資料來源：PubMed、FDA RSS、Google News RSS、TWSE MOPS
"""

import json
import os
import re
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
NEWSAPI_KEY = os.environ.get("NEWSAPI_KEY", "")


def fetch_url(url, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": "RegenIntel/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def save_json(filename, module_id, items):
    # 過濾：移除超過 2 年的舊資料，修正未來日期
    cleaned = []
    for item in items:
        fixed_date = clamp_date(item.get("date", ""))
        if fixed_date is None:
            continue  # 超過 2 年，丟棄
        item["date"] = fixed_date
        cleaned.append(item)

    # 依日期排序（新到舊），最多保留 30 筆
    cleaned.sort(key=lambda x: x.get("date", ""), reverse=True)

    data = {
        "module": module_id,
        "updated": datetime.now(timezone.utc).isoformat(),
        "items": cleaned[:30],
    }
    path = DATA_DIR / filename
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✓ {filename}: {len(items)} 筆")


# ────────────────────────────────────────────
# 1. 台灣市場 — TWSE MOPS 重大訊息
# ────────────────────────────────────────────
def fetch_taiwan_market():
    print("台灣市場（TWSE MOPS）...")
    items = []
    keywords = ["再生醫療", "細胞治療", "幹細胞", "基因治療", "CAR-T"]

    try:
        # MOPS 重大訊息 RSS
        url = "https://mops.twse.com.tw/mops/rss/news_rss.xml"
        xml = fetch_url(url)
        root = ET.fromstring(xml)
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            desc = (item.findtext("description") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub = (item.findtext("pubDate") or "").strip()

            full_text = title + desc
            if any(kw in full_text for kw in keywords):
                date_str = parse_rfc_date(pub)
                items.append({
                    "title": title,
                    "summary": desc[:200] if desc else "",
                    "source": "TWSE MOPS 重大訊息",
                    "date": date_str,
                    "url": link,
                })
    except Exception as e:
        print(f"    MOPS RSS 失敗: {e}")

    # 補充：NewsAPI（若有金鑰）
    if NEWSAPI_KEY and len(items) < 10:
        try:
            q = urllib.parse.quote("再生醫療 OR 細胞治療 台灣")
            url = f"https://newsapi.org/v2/everything?q={q}&language=zh&sortBy=publishedAt&pageSize=20&apiKey={NEWSAPI_KEY}"
            data = json.loads(fetch_url(url))
            for a in data.get("articles", []):
                items.append({
                    "title": a.get("title", ""),
                    "summary": a.get("description", "") or "",
                    "source": a.get("source", {}).get("name", "新聞"),
                    "date": (a.get("publishedAt", "") or "")[:10],
                    "url": a.get("url", ""),
                })
        except Exception as e:
            print(f"    NewsAPI 失敗: {e}")

    # Google News RSS 備用
    if len(items) < 5:
        try:
            q = urllib.parse.quote("再生醫療 台灣 上市")
            url = f"https://news.google.com/rss/search?q={q}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
            items += parse_google_rss(url, "Google News", 10)
        except Exception as e:
            print(f"    Google News 失敗: {e}")

    save_json("taiwan-market.json", "taiwan", items)


# ────────────────────────────────────────────
# 2. 全球臨床突破 — PubMed API
# ────────────────────────────────────────────
def fetch_global_research():
    print("全球臨床突破（PubMed）...")
    items = []
    query = urllib.parse.quote(
        '(regenerative medicine[Title/Abstract] OR cell therapy[Title/Abstract] OR '
        'stem cell therapy[Title/Abstract] OR CAR-T[Title/Abstract] OR '
        'gene therapy[Title/Abstract]) AND ("clinical trial"[PT] OR "clinical study"[PT])'
    )
    try:
        # esearch
        search_url = (
            f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
            f"?db=pubmed&term={query}&retmax=20&sort=pub+date&retmode=json"
        )
        search_data = json.loads(fetch_url(search_url))
        ids = search_data.get("esearchresult", {}).get("idlist", [])

        if ids:
            # efetch
            id_str = ",".join(ids[:15])
            fetch_url2 = (
                f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
                f"?db=pubmed&id={id_str}&retmode=xml&rettype=abstract"
            )
            xml = fetch_url(fetch_url2)
            root = ET.fromstring(xml)

            for article in root.findall(".//PubmedArticle"):
                title_el = article.find(".//ArticleTitle")
                abstract_el = article.find(".//AbstractText")
                pmid_el = article.find(".//PMID")
                year_el = article.find(".//PubDate/Year")
                month_el = article.find(".//PubDate/Month")

                title = (title_el.text or "") if title_el is not None else ""
                abstract = (abstract_el.text or "") if abstract_el is not None else ""
                pmid = (pmid_el.text or "") if pmid_el is not None else ""
                year = (year_el.text or "2025") if year_el is not None else "2025"
                month = (month_el.text or "01") if month_el is not None else "01"
                # 月份文字轉數字
                month_map = {"Jan":"01","Feb":"02","Mar":"03","Apr":"04","May":"05","Jun":"06",
                             "Jul":"07","Aug":"08","Sep":"09","Oct":"10","Nov":"11","Dec":"12"}
                month_num = month_map.get(month, month.zfill(2) if month.isdigit() else "01")

                items.append({
                    "title": clean_text(title),
                    "summary": clean_text(abstract[:300] + "..." if len(abstract) > 300 else abstract),
                    "source": "PubMed",
                    "date": f"{year}-{month_num}-01",
                    "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
                })
    except Exception as e:
        print(f"    PubMed 失敗: {e}")

    # Google Scholar RSS 備用
    if len(items) < 5:
        try:
            q = urllib.parse.quote("regenerative medicine clinical trial 2025")
            url = f"https://news.google.com/rss/search?q={q}&hl=en&gl=US&ceid=US:en"
            items += parse_google_rss(url, "Google News", 10)
        except Exception as e:
            print(f"    備用 RSS 失敗: {e}")

    save_json("global-research.json", "research", items)


# ────────────────────────────────────────────
# 3. 海外機構亞太合作 — Google News RSS
# ────────────────────────────────────────────
def fetch_asia_pacific():
    print("亞太合作動態（Google News RSS）...")
    items = []
    queries = [
        "regenerative medicine Asia Pacific collaboration 2025",
        "cell therapy Japan Korea Singapore clinical",
        "再生醫療 亞太 合作 日本 韓國",
    ]
    for q in queries:
        try:
            encoded = urllib.parse.quote(q)
            url = f"https://news.google.com/rss/search?q={encoded}&hl=en&gl=US&ceid=US:en"
            items += parse_google_rss(url, "Google News", 8)
        except Exception as e:
            print(f"    查詢失敗 ({q[:30]}...): {e}")

    # 去重
    seen = set()
    unique = []
    for item in items:
        key = item["title"][:50]
        if key not in seen:
            seen.add(key)
            unique.append(item)

    save_json("asia-pacific.json", "apac", unique)


# ────────────────────────────────────────────
# 4. 法規動態 — FDA RSS + WHO + 台灣衛福部
# ────────────────────────────────────────────
def fetch_regulations():
    print("法規動態（FDA / WHO / 台灣）...")
    items = []

    # FDA 新聞 RSS
    fda_feeds = [
        ("https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/biologics/rss.xml", "FDA Biologics"),
        ("https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/pressreleases/rss.xml", "FDA Press"),
    ]
    for feed_url, source in fda_feeds:
        try:
            xml = fetch_url(feed_url)
            root = ET.fromstring(xml)
            regen_kw = ["cell therapy", "gene therapy", "regenerative", "CAR-T", "stem cell", "tissue"]
            for item in root.iter("item"):
                title = (item.findtext("title") or "").strip()
                desc = (item.findtext("description") or "").strip()
                link = (item.findtext("link") or "").strip()
                pub = (item.findtext("pubDate") or "").strip()
                if any(kw in (title + desc).lower() for kw in regen_kw):
                    items.append({
                        "title": title,
                        "summary": strip_html(desc[:250]),
                        "source": source,
                        "date": parse_rfc_date(pub),
                        "url": link,
                    })
        except Exception as e:
            print(f"    {source} 失敗: {e}")

    # Google News — 台灣法規
    try:
        q = urllib.parse.quote("再生醫療法 台灣 衛福部 細胞治療 法規")
        url = f"https://news.google.com/rss/search?q={q}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        items += parse_google_rss(url, "台灣法規新聞", 8)
    except Exception as e:
        print(f"    台灣法規 RSS 失敗: {e}")

    # Google News — 日本 PMDA
    try:
        q = urllib.parse.quote("PMDA Japan regenerative medicine approval 2025")
        url = f"https://news.google.com/rss/search?q={q}&hl=en&gl=JP&ceid=JP:en"
        items += parse_google_rss(url, "日本 PMDA", 5)
    except Exception as e:
        print(f"    PMDA RSS 失敗: {e}")

    save_json("regulations.json", "regulation", items)


# ────────────────────────────────────────────
# 5. 市場資金動向 — Google News RSS
# ────────────────────────────────────────────
def fetch_funding():
    print("市場資金動向（Google News RSS）...")
    items = []
    queries = [
        "regenerative medicine funding investment 2025 million",
        "cell therapy biotech IPO Series funding 2025",
        "gene therapy venture capital deal 2025",
        "再生醫療 投資 募資 上市",
    ]
    for q in queries:
        try:
            encoded = urllib.parse.quote(q)
            url = f"https://news.google.com/rss/search?q={encoded}&hl=en&gl=US&ceid=US:en"
            items += parse_google_rss(url, "Google News", 7)
        except Exception as e:
            print(f"    查詢失敗: {e}")

    seen = set()
    unique = []
    for item in items:
        key = item["title"][:50]
        if key not in seen:
            seen.add(key)
            unique.append(item)

    save_json("funding.json", "funding", unique)


# ────────────────────────────────────────────
# 6. 醫療旅遊 — Google News RSS
# ────────────────────────────────────────────
def fetch_medical_tourism():
    print("國際再生醫療旅遊（Google News RSS）...")
    items = []
    queries = [
        "medical tourism regenerative medicine stem cell treatment 2025",
        "cell therapy medical travel Asia Japan Korea Thailand",
        "再生醫療 醫療旅遊 幹細胞 治療 海外",
    ]
    for q in queries:
        try:
            encoded = urllib.parse.quote(q)
            url = f"https://news.google.com/rss/search?q={encoded}&hl=en&gl=US&ceid=US:en"
            items += parse_google_rss(url, "Google News", 7)
        except Exception as e:
            print(f"    查詢失敗: {e}")

    seen = set()
    unique = []
    for item in items:
        key = item["title"][:50]
        if key not in seen:
            seen.add(key)
            unique.append(item)

    save_json("medical-tourism.json", "tourism", unique)


# ────────────────────────────────────────────
# 工具函數
# ────────────────────────────────────────────
def parse_google_rss(url, source_name, limit=10):
    xml = fetch_url(url)
    root = ET.fromstring(xml)
    results = []
    for item in list(root.iter("item"))[:limit]:
        raw_title = (item.findtext("title") or "").strip()
        desc = strip_html((item.findtext("description") or "").strip())
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()

        # Google News title 格式：「新聞標題 - 媒體名稱」，拆出乾淨標題與真實來源
        title, real_source = split_google_title(raw_title, source_name)

        # Google News description 通常重複 title，去除後無實質內容，留空即可
        clean_desc = desc.replace(raw_title, "").strip(" -–—\xa0")
        # 若描述和標題幾乎相同就清空
        if len(clean_desc) < 20 or clean_desc.lower() in title.lower():
            clean_desc = ""

        if title:
            results.append({
                "title": title,
                "summary": clean_desc[:200],
                "source": real_source,
                "date": parse_rfc_date(pub),
                "url": link,
            })
    return results


def split_google_title(title, fallback_source):
    """拆解 Google News 標題格式：'新聞標題 - 媒體名稱'"""
    # 從最後一個 ' - ' 切開
    parts = title.rsplit(" - ", 1)
    if len(parts) == 2 and len(parts[1]) < 40:
        return parts[0].strip(), parts[1].strip()
    return title.strip(), fallback_source


def parse_rfc_date(s):
    """解析 RFC 2822 日期字串，回傳 YYYY-MM-DD，並過濾未來日期"""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if not s:
        return today
    months = {"Jan":"01","Feb":"02","Mar":"03","Apr":"04","May":"05","Jun":"06",
               "Jul":"07","Aug":"08","Sep":"09","Oct":"10","Nov":"11","Dec":"12"}
    m = re.search(r"(\d{1,2})\s+(\w{3})\s+(\d{4})", s)
    if m:
        day, mon, year = m.group(1).zfill(2), months.get(m.group(2), "01"), m.group(3)
        date_str = f"{year}-{mon}-{day}"
        # 未來日期 → 改用今天；超過 18 個月的舊資料 → 保留但標記
        if date_str > today:
            return today
        return date_str
    return today


def clamp_date(date_str):
    """將超出合理範圍的日期修正：未來日期→今天，超過2年→放棄該筆"""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cutoff = f"{int(today[:4])-2}{today[4:]}"  # 2年前
    if date_str > today:
        return today
    if date_str < cutoff:
        return None  # 回傳 None 表示此筆應過濾掉
    return date_str


def strip_html(text):
    text = re.sub(r"<[^>]+>", "", text)
    # 解碼常見 HTML entities
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    text = re.sub(r"&#\d+;", "", text)   # 移除數字 entity
    return re.sub(r"\s{2,}", " ", text).strip()


def clean_text(text):
    return re.sub(r"\s+", " ", text).strip()


# ────────────────────────────────────────────
# 主程式
# ────────────────────────────────────────────
if __name__ == "__main__":
    DATA_DIR.mkdir(exist_ok=True)
    print("=== 再生醫療戰情室 資料更新開始 ===\n")

    fetch_taiwan_market()
    fetch_global_research()
    fetch_asia_pacific()
    fetch_regulations()
    fetch_funding()
    fetch_medical_tourism()

    print("\n=== 更新完成 ===")
    print(f"時間：{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")

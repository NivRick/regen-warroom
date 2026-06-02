# 再生醫療戰情室 (Regen Intel War Room)

手機優先、密碼保護的再生醫療情報監控網頁，部署在 GitHub Pages，完全免費。

## 快速部署步驟

### 1. 建立 GitHub Repository

1. 在 GitHub 建立一個新的 **公開 (public)** repository（例如 `regen-warroom`）
2. 將此資料夾的所有檔案上傳，或使用 git push：

```bash
cd regen-warroom
git init
git add .
git commit -m "init: 再生醫療戰情室"
git remote add origin https://github.com/你的帳號/regen-warroom.git
git push -u origin main
```

### 2. 開啟 GitHub Pages

1. 進入 repository → **Settings** → **Pages**
2. Source 選 **Deploy from a branch**
3. Branch 選 **main**，資料夾選 **/ (root)**
4. 儲存後等約 2 分鐘，網址會顯示在頁面上

### 3. 設定 NEWSAPI_KEY（可選，可提升台灣新聞品質）

1. 前往 [newsapi.org](https://newsapi.org) 免費註冊，取得 API Key
2. 進入 repository → **Settings** → **Secrets and variables** → **Actions**
3. 點 **New repository secret**，名稱填 `NEWSAPI_KEY`，值貼上 Key

### 4. 首次手動執行資料抓取

1. 進入 repository → **Actions**
2. 點左側 **抓取再生醫療情報資料**
3. 點 **Run workflow** → **Run workflow**
4. 等約 30 秒完成，重新整理網頁即可看到真實資料

---

## 預設密碼

```
regen2025
```

> 若要修改密碼：在 `app.js` 第 4 行換成新密碼的 SHA-256 hash 值。
> 可用 `python3 -c "import hashlib; print(hashlib.sha256('新密碼'.encode()).hexdigest())"` 取得 hash。

---

## 資料來源（完全免費）

| 模組 | 來源 |
|------|------|
| 台灣市場 | TWSE MOPS RSS、Google News、NewsAPI |
| 臨床突破 | PubMed E-utilities API（免費） |
| 亞太合作 | Google News RSS |
| 法規動態 | FDA RSS Feed、Google News |
| 資金動向 | Google News RSS |
| 醫療旅遊 | Google News RSS |

---

## 自動更新排程

GitHub Actions 每天自動執行 **兩次**：
- 台灣時間 **早上 7:00**
- 台灣時間 **晚上 7:00**

---

## 本地端測試

```bash
# 測試資料抓取腳本
python scripts/fetch_all.py

# 啟動本地伺服器
python -m http.server 8080
# 瀏覽 http://localhost:8080
```

<div align="center">

# 📖 Novel Ranking Scanner

[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Qidian%20%7C%20Fanqie-orange)]()

**Automated ranking scraper for Qidian & Fanqie Novel. Analyze genre trends, title patterns, synopsis hooks, author levels, and more — all in a structured Markdown report.**

[🇨🇳 中文](README.md)

</div>

---

## ✨ Features

| Feature | Description |
|:---|:---|
| 🏆 **Dual Platform** | Scrape 8 core rankings from Qidian (起点) and Fanqie (番茄) in one command |
| 📊 **7-Dimension Analysis** | Genre distribution, title patterns, synopsis hooks, author levels, word count, cross-rank overlap, newbie cases |
| 📝 **Smart Report** | Auto-generated Markdown report with rank portraits, highlight books, and actionable writing tips |
| 🔄 **Checkpoint Resume** | Per-book detail caching — resume from where you left off |
| 🛡️ **Anti-Scraping** | UA rotation, random delays, 403 backoff, font decryption (Fanqie PUA mapping) |
| 🏷️ **Cross-Rank Dedup** | Books appearing on multiple rankings are merged with `rankAppearances` preserved |

<details>
<summary><strong>🗂️ Supported Rankings</strong></summary>

### Qidian (起点中文网)

| Rank | Key | Description |
|:---|:---|:---|
| Sanjiang | `sanjiang` | Editorial picks for rising new books |
| Strong Rec | `strong` | Editor's strong recommendations |
| New Book | `newbook` | Newly published books |
| Bestseller | `hotsales` | VIP subscription bestsellers |

### Fanqie (番茄小说)

| Rank | Key | Description |
|:---|:---|:---|
| Male Read | `male_read` | Male channel popular reads |
| Male New | `male_new` | Male channel new books |
| Female Read | `female_read` | Female channel popular reads |
| Female New | `female_new` | Female channel new books |

</details>

---

## 🚀 Quick Start

### Installation

```bash
git clone https://github.com/Beat1ngHeart/Novel-Ranking-Scanner.git
cd Novel-Ranking-Scanner
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### One-Command Scan

```bash
# Qidian full pipeline
python main.py full --strategy mobile

# Fanqie full pipeline
python main.py full --site fanqie --pages 1
```

### Quick Test

```bash
# Qidian: 1 page per rank, limit 20 books
python main.py full --strategy mobile --pages 1 --limit 20

# Fanqie: 1 page per rank, limit 20 books
python main.py full --site fanqie --pages 1 --limit 20
```

---

## 📋 Step-by-Step

<details>
<summary><strong>Qidian</strong></summary>

```bash
python main.py scrape --strategy mobile          # 1. Scrape rankings
python main.py detail --limit 50                 # 2. Fetch book details
python main.py filter --months 6 --max-level 5   # 3. Filter by date & level
python main.py analyze                           # 4. Run analysis
python main.py report                            # 5. Generate report
```

</details>

<details>
<summary><strong>Fanqie</strong></summary>

```bash
python main.py scrape --site fanqie --pages 1    # 1. Scrape rankings
python main.py detail --site fanqie              # 2. Reuse ranking details (skippable)
python main.py filter --site fanqie              # 3. Filter
python main.py analyze --site fanqie             # 4. Analyze
python main.py report --site fanqie              # 5. Generate report
```

</details>

<details>
<summary><strong>Advanced Usage</strong></summary>

```bash
# Scrape specific rankings only
python main.py scrape --rankings sanjiang strong --strategy mobile
python main.py scrape --site fanqie --rankings male_read female_new --pages 1

# Run specific analysis dimensions only
python main.py analyze --analyses genre title crossrank

# Use a proxy
python main.py full --proxy socks5://localhost:1080

# Verbose logging
python main.py full -v
```

</details>

---

## 📂 Output Structure

```
output/
├── raw/          # Raw ranking JSON snapshots
├── details/      # Per-book detail cache
├── analysis/     # Filter & analysis results
├── reports/      # Final Markdown reports
└── debug/        # HTML dumps on parse failure
```

---

## 📊 Report Preview

The generated Markdown report includes:

> **1. Overview** — Hot genres, newbie percentage, word count maturity
> **2. Rank Portraits** — Per-rank genre breakdown, word count, top books
> **3. Highlight Books** — Top 12 books table
> **4. Genre Distribution** — Overall & cross-rank comparison
> **5. Title Analysis** — Length, keywords, structural patterns
> **6. Synopsis Analysis** — Hook types, first-sentence patterns
> **7. Author Level** — Level distribution, newbie stats
> **8. Word Count** — Range distribution
> **9. Actionable Observations** — Data-driven writing suggestions
> **10. Per-Book Archive** — Full field dump for every book

---

## ⚠️ Notes

<details>
<summary><strong>Anti-Scraping & Limitations</strong></summary>

- Qidian desktop pages often return challenge pages; prefer `--strategy mobile`
- Fanqie encodes some fields with font-face PUA Unicode — auto-decoded and flagged as `fontEncrypted: true`
- Control request frequency: validate with `--pages` and `--limit` before scaling up
- If results are empty, check `output/debug/` HTML and adjust selectors

</details>

<details>
<summary><strong>Run Tests</strong></summary>

```bash
python3 -m unittest discover -s tests
```

</details>

---

## 📁 Project Structure

```
Novel-Ranking-Scanner/
├── main.py                  # CLI entry point
├── config.py                # Constants & configuration
├── session.py               # HTTP session & retry logic
├── requirements.txt         # Dependencies
├── scraper/
│   ├── ranking.py           # Qidian ranking scraper
│   ├── detail.py            # Qidian detail scraper
│   └── fanqie.py            # Fanqie ranking scraper
├── analysis/
│   ├── filter.py            # Date & level filtering
│   ├── genre.py             # Genre distribution
│   ├── title.py             # Title pattern analysis
│   ├── synopsis.py          # Synopsis hook analysis
│   ├── author.py            # Author level distribution
│   ├── wordcount.py         # Word count distribution
│   ├── cross_rank.py        # Cross-rank overlap
│   └── ranks.py             # Rank ordering utility
├── report/
│   └── markdown.py          # Markdown report generator
└── tests/                   # Unit tests
```

---

## 📄 License

MIT License — for educational and research purposes only. Respect platform Terms of Service.

---

<div align="center">

**Built with ❤️ for web novel writers**

[⬆ Back to top](#-novel-ranking-scanner) · [🇨🇳 中文](README.md)

</div>

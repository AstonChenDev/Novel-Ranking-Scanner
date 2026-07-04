<div align="center">

# 📖 小说排行榜扫榜工具

### Novel Ranking Scanner

[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Qidian%20%7C%20Fanqie-orange)]()

**自动抓取起点中文网 · 番茄小说榜单数据，多维度分析题材趋势，生成结构化报告，为网文选题提供数据支撑。**

*Scrape ranking data from Qidian & Fanqie Novel, analyze genre trends across multiple dimensions, and generate actionable reports for web novel writers.*

[中文](#-快速开始--quick-start) · [English](#-quick-start)

</div>

---

## ✨ 功能亮点 · Features

| 功能 | 说明 |
|:---|:---|
| 🏆 **双平台覆盖** | 起点中文网 + 番茄小说，8 个核心榜单一键扫榜 |
| 📊 **7 维分析** | 分类分布、标题模式、简介开篇、作者等级、字数分布、跨榜上榜、新人案例 |
| 📝 **智能报告** | 自动生成 Markdown 报告，含榜单画像、重点书目、可执行写作建议 |
| 🔄 **断点续跑** | 详情页单书缓存，中断后无需重头开始 |
| 🛡️ **反爬保护** | UA 轮换、随机延迟、403 退避、字体解密（番茄 PUA 映射） |
| 🏷️ **跨榜去重** | 同一本书多榜上榜时保留 `rankAppearances`，总体按书去重 |

<details>
<summary><strong>🗂️ 支持的榜单 · Supported Rankings</strong></summary>

### 起点中文网 (Qidian)

| 榜单 | Key | 说明 |
|:---|:---|:---|
| 三江推荐 | `sanjiang` | 编辑推荐的上升期新书 |
| 强推榜 | `strong` | 编辑强推的重点书 |
| 新书榜 | `newbook` | 新发布书籍排名 |
| 畅销榜 | `hotsales` | VIP 畅销书 |

### 番茄小说 (Fanqie)

| 榜单 | Key | 说明 |
|:---|:---|:---|
| 男频阅读榜 | `male_read` | 男频热门阅读 |
| 男频新书榜 | `male_new` | 男频新书 |
| 女频阅读榜 | `female_read` | 女频热门阅读 |
| 女频新书榜 | `female_new` | 女频新书 |

</details>

---

## 🚀 快速开始 · Quick Start

### 安装 · Installation

```bash
# 克隆仓库 · Clone the repo
git clone https://github.com/Beat1ngHeart/Novel-Ranking-Scanner.git
cd Novel-Ranking-Scanner

# 创建虚拟环境 · Create virtual environment
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 安装依赖 · Install dependencies
pip install -r requirements.txt
```

### 一键扫榜 · One-Command Scan

```bash
# 起点完整流水线 · Qidian full pipeline
python main.py full --strategy mobile

# 番茄完整流水线 · Fanqie full pipeline
python main.py full --site fanqie --pages 1
```

### 快速测试 · Quick Test

```bash
# 起点：每榜 1 页，限 20 本 · Qidian: 1 page per rank, limit 20
python main.py full --strategy mobile --pages 1 --limit 20

# 番茄：每榜 1 页，限 20 本 · Fanqie: 1 page per rank, limit 20
python main.py full --site fanqie --pages 1 --limit 20
```

---

## 📋 分步运行 · Step-by-Step

<details>
<summary><strong>起点 · Qidian</strong></summary>

```bash
python main.py scrape --strategy mobile          # 1. 抓取榜单
python main.py detail --limit 50                 # 2. 获取详情
python main.py filter --months 6 --max-level 5   # 3. 筛选
python main.py analyze                           # 4. 分析
python main.py report                            # 5. 生成报告
```

</details>

<details>
<summary><strong>番茄 · Fanqie</strong></summary>

```bash
python main.py scrape --site fanqie --pages 1    # 1. 抓取榜单
python main.py detail --site fanqie              # 2. 复用榜单详情（可跳过）
python main.py filter --site fanqie              # 3. 筛选
python main.py analyze --site fanqie             # 4. 分析
python main.py report --site fanqie              # 5. 生成报告
```

</details>

<details>
<summary><strong>高级用法 · Advanced Usage</strong></summary>

```bash
# 只抓指定榜单 · Scrape specific rankings only
python main.py scrape --rankings sanjiang strong --strategy mobile
python main.py scrape --site fanqie --rankings male_read female_new --pages 1

# 只运行指定分析维度 · Run specific analyses only
python main.py analyze --analyses genre title crossrank

# 使用代理 · Use proxy
python main.py full --proxy socks5://localhost:1080

# 详细日志 · Verbose logging
python main.py full -v
```

</details>

---

## 📂 输出目录 · Output Structure

```
output/
├── raw/          # 榜单原始 JSON · Raw ranking JSON
├── details/      # 单书详情缓存 · Per-book detail cache
├── analysis/     # 筛选 & 分析结果 · Filter & analysis results
├── reports/      # Markdown 报告 · Final Markdown reports
└── debug/        # 解析失败时的 HTML · Debug HTML dumps
```

---

## 📊 报告示例 · Report Preview

生成的 Markdown 报告包含以下章节：

> **1. 概览** — 热门分类、新人占比、字数成熟度
> **2. 榜单画像** — 每个榜单的分类、字数、Top 书目
> **3. 重点书目速览** — Top 12 书目表格
> **4. 分类分布** — 总体 & 跨榜对比
> **5. 标题分析** — 长度、关键词、结构模式
> **6. 简介开篇** — 开篇类型、首句特征
> **7. 作者等级** — 等级分布、新人占比
> **8. 字数分布** — 区间统计
> **9. 可执行观察** — 基于数据的写作建议
> **10. 逐本书籍档案** — 每本书的完整字段

---

## ⚠️ 注意事项 · Notes

<details>
<summary><strong>反爬与限制 · Anti-Scraping</strong></summary>

- 起点桌面端页面容易返回探测页，建议优先使用 `--strategy mobile`
- 番茄部分字段使用字体加密（PUA Unicode），程序会自动解码并标记 `fontEncrypted: true`
- 请控制抓取频率，用 `--pages` 和 `--limit` 小范围验证后再扩大规模
- 若抓取结果突然为空，检查 `output/debug/` 中的 HTML 并调整选择器

</details>

<details>
<summary><strong>运行测试 · Run Tests</strong></summary>

```bash
python3 -m unittest discover -s tests
```

</details>

---

## 📁 项目结构 · Project Structure

```
小说扫榜/
├── main.py                  # CLI 入口 · CLI entry point
├── config.py                # 常量配置 · Constants & config
├── session.py               # HTTP 会话管理 · Session & retry
├── requirements.txt         # 依赖 · Dependencies
├── scraper/
│   ├── ranking.py           # 起点榜单爬取 · Qidian ranking scraper
│   ├── detail.py            # 起点详情爬取 · Qidian detail scraper
│   └── fanqie.py            # 番茄榜单爬取 · Fanqie ranking scraper
├── analysis/
│   ├── filter.py            # 筛选逻辑 · Filtering
│   ├── genre.py             # 分类分布 · Genre distribution
│   ├── title.py             # 标题分析 · Title analysis
│   ├── synopsis.py          # 简介分析 · Synopsis analysis
│   ├── author.py            # 作者等级 · Author level
│   ├── wordcount.py         # 字数分布 · Word count
│   ├── cross_rank.py        # 跨榜上榜 · Cross-rank
│   └── ranks.py             # 榜单排序 · Rank ordering
├── report/
│   └── markdown.py          # 报告生成 · Report generator
└── tests/                   # 单元测试 · Unit tests
```

---

## 📄 License

MIT License — 仅供学习研究，请勿用于商业爬虫或侵犯平台权益。

*For educational and research purposes only. Respect platform Terms of Service.*

---

<div align="center">

**Built with ❤️ for web novel writers**

[⬆ Back to top](#-小说排行榜扫榜工具)

</div>

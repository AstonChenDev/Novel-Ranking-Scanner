<div align="center">

# 📖 小说排行榜扫榜工具

[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-5%20sources-orange)]()

**自动抓取起点、番茄、红果、抖音和快手榜单数据，生成可验证的完整快照，为网文与短剧选题提供数据支撑。**

[🇺🇸 English](README_EN.md)

</div>

---

## ✨ 功能亮点

| 功能 | 说明 |
|:---|:---|
| 🏆 **五平台覆盖** | 起点、番茄、红果、抖音、快手榜单使用统一快照协议 |
| 📊 **7 维分析** | 分类分布、标题模式、简介开篇、作者等级、字数分布、跨榜上榜、新人案例 |
| 📝 **智能报告** | 自动生成 Markdown 报告，含榜单画像、重点书目、可执行写作建议 |
| 🔄 **断点续跑** | 详情页单书缓存，中断后无需重头开始 |
| 🛡️ **反爬保护** | UA 轮换、随机延迟、403 退避、字体解密（番茄 PUA 映射） |
| 🏷️ **跨榜去重** | 同一本书多榜上榜时保留 `rankAppearances`，总体按书去重 |

<details>
<summary><strong>🗂️ 支持的榜单</strong></summary>

### 起点中文网

| 榜单 | Key | 说明 |
|:---|:---|:---|
| 三江推荐 | `sanjiang` | 编辑推荐的上升期新书 |
| 强推榜 | `strong` | 编辑强推的重点书 |
| 新书榜 | `newbook` | 新发布书籍排名 |
| 畅销榜 | `hotsales` | VIP 畅销书 |

### 番茄小说

| 榜单 | Key | 说明 |
|:---|:---|:---|
| 男频阅读榜 | `male_read` | 男频热门阅读 |
| 男频新书榜 | `male_new` | 男频新书 |
| 女频阅读榜 | `female_read` | 女频热门阅读 |
| 女频新书榜 | `female_new` | 女频新书 |

### 短剧平台

| 平台 | 榜单 | 完整性口径 |
|:---|:---|:---|
| 红果 | 总热播、真人、AI、漫剧 | 官网每榜 5 页，共 100 部；按 `totalPages` 完整翻页 |
| 抖音 | 热播、漫剧、新剧、互动、必看 | 每页最多 15 部；按 `has_more/offset` 抓到末页 |
| 快手 | 全网热播、推荐、热播、真人、漫剧、必看及 8 个题材榜 | 接口一次返回平台定义的完整 Top 19～50 |

短剧字段统一保留排名、简介、封面、题材、内容形态、热度、播放、收藏、点赞、评分、集数、
时长、账号/出品方、付费/独播状态、平台标签和在榜天数；上游没有的字段为 `null`，不会伪造成 `0`。

</details>

---

## 🚀 快速开始

### 安装

```bash
git clone https://github.com/Beat1ngHeart/Novel-Ranking-Scanner.git
cd Novel-Ranking-Scanner
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 一键扫榜

```bash
# 起点完整流水线
python main.py full --strategy mobile

# 番茄完整流水线
python main.py full --site fanqie --pages 2

# 短剧榜单（完整翻页）
python main.py scrape --site hongguo
python main.py scrape --site douyin
python main.py scrape --site kuaishou
```

### 快速测试

```bash
# 起点：每榜 1 页，限 20 本
python main.py full --strategy mobile --pages 1 --limit 20

# 番茄：每榜 1 页，限 20 本
python main.py full --site fanqie --pages 2 --limit 20
```

---

## 📋 分步运行

<details>
<summary><strong>起点</strong></summary>

```bash
python main.py scrape --strategy mobile          # 1. 抓取榜单
python main.py detail --limit 50                 # 2. 获取详情
python main.py filter --months 6 --max-level 5   # 3. 筛选
python main.py analyze                           # 4. 分析
python main.py report                            # 5. 生成报告
```

</details>

<details>
<summary><strong>番茄</strong></summary>

```bash
python main.py scrape --site fanqie --pages 2    # 1. 抓取完整分类榜
python main.py detail --site fanqie              # 2. 复用榜单详情（可跳过）
python main.py filter --site fanqie              # 3. 筛选
python main.py analyze --site fanqie             # 4. 分析
python main.py report --site fanqie              # 5. 生成报告
```

</details>

<details>
<summary><strong>提交到独立采集写入服务</strong></summary>

`ingest` 不会改变现有的抓榜命令。它把最新榜单快照转换为跨平台的批量导入协议；
同一本书出现在多个榜单时会保留多条榜单关系。服务端 URL 和 token 可以通过环境变量
`RANK_INGEST_URL`、`RANK_INGEST_TOKEN` 提供，也可以用命令行参数覆盖。

```bash
# 先抓榜，再检查规范化 JSON（不发请求）
python main.py scrape --site fanqie --pages 2
python main.py ingest --site fanqie --dry-run --output /tmp/rank-ingestion.json

# 推送最新快照；失败会自动重试，最终失败返回非零退出码
export RANK_INGEST_URL=http://127.0.0.1:19501/internal/v1/rank-snapshots
export RANK_INGEST_TOKEN='replace-with-internal-token'
python main.py ingest --site fanqie --retries 4

# 也可以直接推送指定快照，`push` 是 `ingest` 的别名
python main.py push --input output/raw/all_rankings_20260919_080000.json
```

协议顶层包含 `schema_version`、`source` 和 `books`。每个书籍行使用稳定的
`site`、`book_id`、`rank_type`、`rank_scope_key`、`rank_position` 等字段，并保留无法预知的平台特有
字段到 `extra`，方便将来接入其他平台；`rank_scope_key` 是分类/分区的稳定 ID，不能用展示分类名代替。
服务端按“平台 + 榜型 + 维度 + 日期”保存快照，同一本书仍按“平台 + 书籍 ID”复用正文采集任务。

</details>

### 每日调度

项目根目录的 `run_daily_rank_sync.sh` 默认只抓番茄，再导入独立采集服务；正文由常驻 worker 消费，日榜命令不重复启动 worker。
请由外部 cron、systemd timer 或容器调度器每天调用，令牌通过 `EXTERNAL_RANK_INGESTION_TOKEN` 或 `RANK_ENV_FILE` 提供。
每次只导入本批次新文件，不回退历史快照。需要多平台时显式设置，例如
`RANK_SITES=fanqie,hongguo,douyin,kuaishou`；默认仍只运行番茄。

番茄已使用官网的 `offset/limit` API：每页50本，普通分类榜100本只需两页。`--pages` 是安全上限，
如果配置页数不足上游总数，会明确失败，不发布不完整榜单。旧 HTML 只含前10本，不能用 `?page=` 翻页。

<details>
<summary><strong>高级用法</strong></summary>

```bash
# 只抓指定榜单
python main.py scrape --rankings sanjiang strong --strategy mobile
python main.py scrape --site fanqie --rankings male_read female_new --pages 1

# 只运行指定分析维度
python main.py analyze --analyses genre title crossrank

# 使用代理
python main.py full --proxy socks5://localhost:1080

# 详细日志
python main.py full -v
```

</details>

---

## 📂 输出目录

```
output/
├── raw/          # 榜单原始 JSON
├── details/      # 单书详情缓存
├── analysis/     # 筛选 & 分析结果
├── reports/      # Markdown 报告
└── debug/        # 解析失败时的 HTML
```

---

## 📊 报告示例

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

## ⚠️ 注意事项

<details>
<summary><strong>反爬与限制</strong></summary>

- 起点桌面端页面容易返回探测页，建议优先使用 `--strategy mobile`
- 番茄部分字段使用字体加密（PUA Unicode），程序会自动解码并标记 `fontEncrypted: true`
- 请控制抓取频率，用 `--pages` 和 `--limit` 小范围验证后再扩大规模
- 若抓取结果突然为空，检查 `output/debug/` 中的 HTML 并调整选择器

</details>

<details>
<summary><strong>运行测试</strong></summary>

```bash
python3 -m unittest discover -s tests
```

</details>

---

## 📁 项目结构

```
小说扫榜/
├── main.py                  # CLI 入口
├── config.py                # 常量配置
├── session.py               # HTTP 会话管理
├── requirements.txt         # 依赖
├── scraper/
│   ├── ranking.py           # 起点榜单爬取
│   ├── detail.py            # 起点详情爬取
│   ├── fanqie.py            # 番茄榜单爬取
│   └── short_drama.py       # 红果、抖音、快手短剧榜单与完整性保护
├── analysis/
│   ├── filter.py            # 筛选逻辑
│   ├── genre.py             # 分类分布
│   ├── title.py             # 标题分析
│   ├── synopsis.py          # 简介分析
│   ├── author.py            # 作者等级
│   ├── wordcount.py         # 字数分布
│   ├── cross_rank.py        # 跨榜上榜
│   └── ranks.py             # 榜单排序
├── report/
│   └── markdown.py          # 报告生成
└── tests/                   # 单元测试
```

---

## 📄 License

MIT License — 仅供学习研究，请勿用于商业爬虫或侵犯平台权益。

---

<div align="center">

**Built with ❤️ for web novel writers**

[⬆ 回到顶部](#-小说排行榜扫榜工具) · [🇺🇸 English](README_EN.md)

</div>

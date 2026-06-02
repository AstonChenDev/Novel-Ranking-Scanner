# 起点排行榜扫榜工具

抓取起点中文网榜单数据，补充书籍详情，并从分类、标题、简介、作者等级、字数和跨榜情况生成 Markdown 分析报告。

## 功能

- 支持三江推荐、强推榜、新书榜、畅销榜。
- 支持桌面端页面解析，失败时可降级到移动端接口。
- 详情抓取带单书缓存，可断点续跑。
- 同一本书跨多个榜单时会保留 `rankAppearances`，总体分析按书籍去重，榜单对比按榜单出现计数。
- 报告输出到 `output/reports/`。

## 安装

建议使用 Python 3.9+。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 常用命令

完整流水线：

```bash
python main.py full --strategy mobile
```

快速测试，只抓每榜 1 页并限制详情数量：

```bash
python main.py full --strategy mobile --pages 1 --limit 20
```

分步运行：

```bash
python main.py scrape --strategy mobile
python main.py detail --limit 50
python main.py filter --months 6 --max-level 5
python main.py analyze
python main.py report
```

只分析指定维度：

```bash
python main.py analyze --analyses genre title crossrank
```

## 输出目录

- `output/raw/`: 榜单原始数据和本次抓取快照 `all_rankings_*.json`
- `output/details/`: 单书详情缓存和合并后的 `all_details_*.json`
- `output/analysis/`: 筛选结果和分析 JSON
- `output/reports/`: Markdown 报告
- `output/debug/`: 页面解析失败时保存的 HTML

## 注意

起点页面结构、接口和反爬策略可能变化。若抓取结果突然为空，优先检查 `output/debug/` 中的 HTML，并调整 `scraper/ranking.py` 或 `scraper/detail.py` 的选择器。

当前桌面端页面容易返回探测页，建议优先使用 `--strategy mobile`。移动端 SSR 页面会从页面内嵌 JSON 解析榜单数据。

请控制抓取频率，优先用 `--pages` 和 `--limit` 小范围验证后再扩大规模。

## 测试

```bash
PYTHONPYCACHEPREFIX=/private/tmp/qidian_pycache python3 -m unittest discover -s tests
```

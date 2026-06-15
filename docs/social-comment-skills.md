# 国内高赞内容与评论 Skill 调研

更新时间：2026-06-15

## 当前可用结论

没有找到一个可以“免登录、免授权、稳定聚合微博/抖音/B站/小红书高赞文章视频及其高赞评论”的单一 skill。

可用能力需要拆开看：

| 能力 | 当前结论 | 适合程度 |
| --- | --- | --- |
| 小红书搜索、读笔记、读评论 | 已有 `xiaohongshu-cli` skill，可搜索笔记、读取笔记和评论；需要登录态/cookie | 可作为第一个真实评论接入点 |
| B站视频发现 | 可用 B站公开搜索/详情接口校验 BV、标题、UP主、日期、播放、点赞、评论数 | 适合补视频源，不等同于高赞评论 |
| B站评论 | 搜到的 `bilibili-downloader` 更偏下载视频；是否能稳定取评论需另行验证 | 暂不直接推荐 |
| 抖音视频/评论 | 搜到 TikHub API helper，通常依赖第三方 API 服务和 Key | 可评估，但不是免费内置能力 |
| 微博评论 | 搜到 `weibo-cli`，安装量较低，需要验证登录、搜索和评论接口是否可用 | 候选，不作为当前主路径 |
| 全网热榜 | `newsnow` 可覆盖微博/抖音/B站/知乎等热榜，但本机运行缺 `bun`；且它主要给标题和链接，不保证评论 | 适合发现热点，不适合直接拿高赞评论 |

## 已搜索到的 Skill 候选

- `autoclaw-cc/xiaohongshu-mcp-skills@xiaohongshu`：约 2.5K installs，方向是小红书 MCP。
- `jackwener/xiaohongshu-cli@xiaohongshu-cli`：约 948 installs；当前本机已安装同类 skill，可搜索、读取笔记、读取评论。
- `jackwener/weibo-cli@weibo-cli`：约 113 installs；需后续验证。
- `liangdabiao/tikhub_api_skill@tikhub-api-helper`：约 166 installs；偏 TikHub API，通常需要第三方 API Key。
- `serpdownloaders/skills@bilibili-downloader`：约 1.1K installs；偏 B站下载，不等同于评论采集。

## 推荐路线

1. 先接小红书：用 `xiaohongshu-cli` 搜索热点关键词，读取热门笔记和评论，标准化到 `social-opinions`。
2. B站先只做视频源：用公开接口校验视频存在、发布时间、播放量、点赞和评论数；评论抓取另做验证。
3. 抖音走 API 服务评估：如果要稳定拿视频评论，需要 TikHub 这类服务或官方/授权数据源。
4. 微博单独验证 `weibo-cli`：确认能否搜索热点微博并读取评论点赞数后再接入。

## 小红书已接入流程

本仓库已新增两段本地脚本：

- `scripts/collect_xhs_social_comments.py`：只读调用 `xhs search`、`xhs read`、`xhs comments`，输出原始评论、页面可用的 `social-opinions` 和 KOL/热内容 CSV。
- `scripts/apply_social_opinions_to_frontend.py`：把 `xhs-social-opinions.csv` 回灌到 `insights/hotspots-data.js`，页面会展示评论链接、热内容链接、点赞数、评论作者和回复数；默认只更新匹配到的热点，需要全量替换时加 `--replace-existing`。

最小验证命令：

```bash
xhs status --yaml
python3 scripts/collect_xhs_social_comments.py --keywords "外卖大战" --sort popular --search-limit 15 --notes-per-keyword 1 --comments-per-note 5 --min-note-likes 1000 --min-comment-likes 1 --days 500
cp insights/hotspots-data.js /tmp/hotspots-data-xhs-test.js
python3 scripts/apply_social_opinions_to_frontend.py --input /tmp/hotspots-data-xhs-test.js --output /tmp/hotspots-data-xhs-test.js --social-opinions data/social-discovery/生成的-xhs-social-opinions.csv
```

生产使用建议：

- 默认优先用 `--sort latest --days 15` 找近期讨论。
- 如果近期互动量不足，可以临时用 `--sort popular` 复核历史高赞评论，但不要直接把超出采集窗口的旧评论当成本周舆论。
- `data/social-discovery/` 已加入 `.gitignore`；只有经过人工确认的标准化结果才应回灌并发布。
- 小红书搜索会混入红包口令、探店、泛生活内容；脚本已加入噪音词和标题相关性过滤，但最终发布前仍需要抽查来源链接。

## 证据标准

任何评论进入页面前必须具备：

- 平台
- 内容标题
- 内容链接
- 评论正文
- 评论点赞数
- 评论作者或匿名标识
- 抓取/导出时间

如果缺少评论点赞数或内容链接，只能作为“候选舆情”，不能生成高赞评论、公众共识和争议点。

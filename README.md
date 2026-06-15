# 小胡聊商业｜每周商业热点雷达

这是一个静态网页发布包，可直接通过 GitHub Pages 托管。

入口：

- `index.html`
- `insights/weekly-hotspots.html`

更新数据时，重新生成 `insights/hotspots-data.js` 后再发布。

云端采集：

- GitHub Actions：`Collect business hotspots`
- 每日后台自动运行，也可由仓库所有者在 GitHub Actions 手动运行
- 默认使用商业媒体直连采集和免费新闻 RSS 聚合，无需 API 密钥
- 使用 GitHub Models 为每条入选新闻生成差异化的 AI 选题价值分析
- 可选维护 `data/video_sources.csv`，补充抖音/B站视频源链接；只有人工打开确认、日期在采集窗口内且 `verified=yes` 的视频才会展示
- `TAVILY_API_KEY` 仅作为后续可选增强，不是运行必需项

小红书舆论采集：

- 本地使用 `xiaohongshu-cli` 的只读能力，读取搜索结果、笔记互动数和评论
- 原始结果默认输出到 `data/social-discovery/`，该目录已被 `.gitignore` 排除，不会自动发布账号侧数据
- 示例采集命令：
  ```bash
  python3 scripts/collect_xhs_social_comments.py --keywords "外卖大战" --sort popular --days 30
  ```
- 回灌到页面数据：
  ```bash
  python3 scripts/apply_social_opinions_to_frontend.py --social-opinions data/social-discovery/生成的-xhs-social-opinions.csv
  ```
- 这一步依赖本机小红书登录态，不放进 GitHub Actions；确认评论来源和时间后再提交 `insights/hotspots-data.js`

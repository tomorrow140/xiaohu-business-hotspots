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
- 可选维护 `data/video_sources.csv`，补充抖音/B站视频源链接
- `TAVILY_API_KEY` 仅作为后续可选增强，不是运行必需项

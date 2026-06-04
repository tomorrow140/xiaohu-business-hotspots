# 小胡聊商业｜每周商业热点雷达

这是一个静态网页发布包，可直接通过 GitHub Pages 托管。

入口：

- `index.html`
- `insights/weekly-hotspots.html`

更新数据时，重新生成 `insights/hotspots-data.js` 后再发布。

云端采集：

- GitHub Actions：`Collect business hotspots`
- 手动运行或每周一自动运行
- 配置仓库 Secret `TAVILY_API_KEY` 后，优先使用 Tavily 聚合商业媒体

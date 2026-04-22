# 更新日志 / Changelog

本文件记录 DBC2C 的版本更新内容。格式大致遵循 [Keep a Changelog](https://keepachangelog.com/) 约定。

## [Unreleased]

### Added
- **Info 菜单**:新增 `Info` 菜单项,包含 `Changelog` 可查看本文件内容。
- **撤销 / 重做**:
  - 快捷键:`Ctrl+Z` 撤销,`Ctrl+Y` / `Ctrl+Shift+Z` 重做。
  - 入口:`Edit` 菜单新增 `Undo` / `Redo`。
  - 覆盖操作:新增节点(含拖拽 / 树形双击 / 消息批量加入)、删除节点与连线、复制节点、编辑 / 清除接收条件、显示 / 隐藏条件依赖连线、清空画布、节点拖动位置。
  - 历史栈最多 100 步,导入 DBC 或导入 JSON 时会清空历史。

## 已有功能基线

- 解析 DBC(基于 cantools),在左侧以 Node → TX / RX → Message → Signal 树形展示,支持搜索过滤。
- 拖拽或双击把 Signal / 整个 Message 加入右侧画布。
- 画布支持:中键平移、`Ctrl+滚轮` 缩放、网格对齐、节点复制(`Ctrl+D`) / 删除(`Delete` / `Backspace`)、`Ctrl+Shift+F` 适配全部节点、`Ctrl+0` 重置视图。
- 通过右键菜单可为信号配置 `Receive Condition` 并在画布中以虚线连接显示其来源依赖。
- 画布状态导入 / 导出 JSON(`Ctrl+O` / `Ctrl+Shift+O` / `Ctrl+S`)。

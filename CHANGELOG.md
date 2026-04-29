# 更新日志 / Changelog

本文件记录 DBC2C 的版本更新内容。格式大致遵循 [Keep a Changelog](https://keepachangelog.com/) 约定。

## [Unreleased]

### Added
- **未保存状态指示器**:
  - 窗口标题末尾显示 `*` 标记,提示用户存在未保存的更改。
  - 操作触发:新增/删除/复制节点、编辑/清除接收条件、显示/隐藏条件依赖连线、自动布局、节点拖动、撤销/重做。
  - 关闭窗口时弹出保存确认对话框,提供"保存"、"放弃"、"取消"三个选项。
  - 保存、导入DBC、导入JSON后自动清除未保存标记。

### Changed
- **画布 JSON 导出结构升级到 v2(message 分组 + 完整 DBC 属性)**:
  - 顶层字段:`version`、`dbc_file`、`messages`。
  - 相同 `message` 下的信号现在聚合到同一条 `messages[*].signals` 数组里。
  - 每条 message 输出:`name`、`frame_id`、`frame_id_hex`、`length`、`is_extended_frame`、`is_fd`、`senders`、`cycle_time_ms`、`send_type`、`comment`。
  - 每条 signal 输出:`name`、`start_bit`、`length`、`byte_order`、`is_signed`、`is_float`、`factor`、`offset`、`minimum`、`maximum`、`unit`、`initial`、`receivers`、`is_multiplexer`、`multiplexer_ids`、`mux_indicator`、`choices`、`comment`。
  - 每条 signal 追加 `canvas` 子字段,保存该节点在画布上的 `id / node / direction / x / y / condition`。
  - 目的:导出的 JSON 为自包含文档,后续代码生成**只用此 JSON 即可**,无需再读原始 `.dbc`。
- **向后兼容**:仍可载入旧版(v1,`{dbc_file, nodes: [...]}`)格式的画布文件。

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

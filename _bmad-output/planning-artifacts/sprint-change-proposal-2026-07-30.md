# Sprint Change Proposal — 前后端节奏转向：新增 Epic 7 前端集成

- **日期**：2026-07-30
- **作者**：Jianghj（Correct Course 工作流，Incremental 模式）
- **变更规模**：Moderate
- **推荐路径**：Direct Adjustment（Option 1 + 方法论段落修订）
- **落地产物**：`epics.md`、`sprint-status.yaml`

---

## Section 1 · 问题摘要（Issue Summary）

**问题定性**：策略转向（Strategic pivot）。放弃早期「后端先行、前端 later 统一接」的旧节奏，转向「前后端一起走」。

**触发背景**：旧节奏自 Story 1.6/1.7 起自然形成，2.4（2026-07-28）授权「看哪种更好」后成为既定方法论，此后 2.3–3.4 每个 story 都标「app.js 一字节未改」，把前端接线全 defer 到一个从未进入计划的「探索前端集成切片」。

**核心问题（证据）**：
- `prototype/app/app.js`（2374 行）`grep -cE "fetch\(|XMLHttpRequest|localStorage.*token|Authorization"` 命中 **0** —— 确证纯 mock，一个后端接口都没连过。
- Epic 1-3 后端全部 done（`sprint-status.yaml`），后端 `routers/` 齐全（auth/projects/exploration/story/byok/usage/tasks/health），契约就绪但**无消费方**。
- `epics.md` 全文零「前端集成/接线」story —— 约 1.6–3.5 共 7-8 个 story 的接线债从未落入计划。
- 后果：Epic 1-3 全部后端 API **从未经真实前端验证**。

---

## Section 2 · 影响分析（Impact Analysis）

### Epic 影响
- **Epic 1-3**：后端均 done，**无需回退或返工**（不 Rollback，后端没白做）。
- **需新增一个 epic**：现有 E1-6 按用户旅程站点分组，前端接线横跨 E1-E3，无处安放 → 新增 **Epic 7**。
- **Epic 4-6**：仍 backlog，不失效。**4-1 盲测门禁是纯后端评测，与前端集成互不阻塞、可并行。**

### Story 影响
- 新增 Epic 7 下 **7 个 story**（7.1–7.7），覆盖 E1-3 全链前端接线，不改动任何已 done story。

### 产物冲突
- **PRD / MVP**：不砍范围、不改 FR，MVP 完全可达。仅 `epics.md`「方法论前提」段需修订默认交付方式。
- **架构**：无冲突。AR3/AR4/AR5（JWT 双 token / camelCase 边界 / error envelope）反而是 7.1 地基 story 的直接依据。
- **UX**：UX-DR9（错误位对接）→ 7.2/7.3；UX-DR2（BYOK 页须新增）→ 7.4；UX-DR1（文风入口须新增）→ 7.7；UX-DR4/DR5/DR6（探索/设定交互契约）→ 7.5/7.6/7.7 的 AC 来源。
- **CI / 部署 / 基础设施**：无二次影响。

---

## Section 3 · 推荐路径（Recommended Approach）

**选定：Option 1 Direct Adjustment（Hybrid：新 Epic 承载 + 方法论段落修订）**

| 选项 | 结论 | Effort | Risk |
|---|---|---|---|
| Option 1 Direct Adjustment | **采纳** | High | Low |
| Option 2 Rollback | 否决——后端无回退价值 | — | — |
| Option 3 MVP Review | 否决——不缩范围 | — | — |

**理由**：后端不返工，风险最低；新增 Epic 7 末尾追加不打乱已 done 编号与 sprint-status 引用；方法论段落修订把「后端 only」默认改掉，从根源止住债务再生。规模 Moderate（需 backlog 重组、新增 7 story）。

---

## Section 4 · 详细变更提案（Detailed Change Proposals）

### 4.1 Epic 7 骨架

**新增 Epic 7: 前端真实接线与端到端集成**
- 用户能在真实浏览器走通「注册登录→管理作品→探索→出设定圣经」全闭环，数据来自后端而非 mock；把 E1-3 已 done 后端 API 首次接上前端原型，偿还 1.6-3.5 接线债。
- **FRs covered**：无新增 FR（兑现 FR1-FR16 的前端侧，此前仅后端验证）
- **执行时序**：逻辑上介于 Epic 3 与 Epic 4 之间——先还债跑通 E1-E3 闭环，再进入 E4 创作；编号取 7 仅为不打乱已 done 条目与 sprint-status 引用。与 Epic 4-1 盲测门禁（纯后端评测）互不阻塞、可并行。
- **Story 依赖**：7.1 →7.2 →{7.3, 7.4}；7.2 →7.5 →7.6；{7.5,7.6} →7.7

| Story | 标题 | 覆盖 | 关键锚点 |
|---|---|---|---|
| 7.1 | 统一请求工具地基（token / 401→登录 / error envelope / camelCase 边界） | 地基 | AR3, AR4, AR5, UX-DR9 |
| 7.2 | 登录 / 注册接线（真实会话，替换 mock） | FR1 | app.js:246-253, UX-DR9 |
| 7.3 | 作品库接线（列表/新建/重命名/删除/空·失败态/继续创作跳转） | FR2, FR3 | UX-DR9 |
| 7.4 | BYOK 设置页 + 托管用量入口接线（含 UX-DR2 须新增 UI） | FR4 | UX-DR2 |
| 7.5 | 引导探索接线（SSE 问答 / 翻页持久化 / 整理中过渡 / 设定卡弹出） | FR5-8, FR11 | UX-DR4 |
| 7.6 | 自由探索接线（SSE 对话 / 线索区编辑持久化 / 给方向 / 整理门禁） | FR9-11 | UX-DR5 |
| 7.7 | 设定卡 + 文风锚点接线（12 字段 / 编辑升版本 / 确认圣经 / 回到探索丢弃 + UX-DR1 须新增 UI） | FR12-16 | UX-DR1, UX-DR6 |

> 各 story 完整 AC 已在 Incremental review 中逐条确认，最终以写入 `epics.md` 的正文为准。

### 4.2 方法论段落修订（epics.md 方法论前提）
在原段落末尾追加「交付节奏（2026-07-30 修订）」：放弃旧节奏、转向前后端一起走，新 story 默认前后端一起交付，E1-3 接线债由 Epic 7 集中偿还。

### 4.3 Epic 列表 / 总计行 / FR 覆盖图
- Epic 列表段新增 Epic 7 条目。
- 总计行 `Epic 总数：6` → `7`，补 E7 依赖说明。
- FR 覆盖图加备注：Epic 7 不新增 FR，兑现 FR1-FR16 前端侧。

### 4.4 sprint-status.yaml
新增 Epic 7 区块（`epic-7: backlog` + 7 条 `7-x-...: backlog`），更新 `last_updated`，在 SEQUENCING NOTES 补一条前端集成时序说明。

---

## Section 5 · 实施交接（Implementation Handoff）

- **变更分类**：Moderate（backlog 重组 + 新增 7 story，无战略级 replan）。
- **交接对象**：Product Owner / Developer。
- **交付物**：本 Sprint Change Proposal + 更新后的 `epics.md`、`sprint-status.yaml`。
- **后续执行**：Epic 7 可立即开工，7.1 地基为硬前置；建议按 Jflow 逐 story 推进（PRD→TRD→dev 切片）。
- **成功判据**：真实浏览器走通「注册登录→作品库→探索→设定圣经」闭环，数据全部来自后端；E1-3 后端 API 首次获真实前端验证。

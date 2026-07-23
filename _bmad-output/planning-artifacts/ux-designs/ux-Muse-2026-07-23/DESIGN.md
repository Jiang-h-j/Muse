---
name: Muse
description: AI 小说创作伙伴的视觉设计系统 —— editorial / 印刷杂志感 + neo-brutalist 硬阴影的黑白纸张美学
status: draft
created: 2026-07-23
updated: 2026-07-23
project_name: Muse
authority_note: >
  本文件是从已实现原型（prototype/app/styles.css, 3901 行）反向蒸馏的视觉事实结构化镜像。
  与 BMAD-UX 默认「spine 凌驾原型」规则相反：Muse 铁律是「原型 = 唯一事实基准」。
  故本 DESIGN.md 在冲突时【服从】原型代码，不凌驾。token 值均照抄 styles.css，行号可追溯。
sources:
  - prototype/app/styles.css
  - prototype/app/index.html
  - prototype/spec/prototype-spec.md
colors:
  paper: '#f7f7f4'
  white: '#ffffff'
  ink: '#111111'
  ink-2: '#333333'
  sub: '#6e6e6e'
  faint: '#a2a2a2'
  line: '#deded9'
  line-strong: '#111111'
  error: '#a4261d'
  error-bg: '#fff4f2'
  success: '#1f6f49'
  success-bg: '#eef8f2'
  selection: '#e5e5e0'
  ink-hover: '#292929'
  locate-highlight: '#eeeeea'
typography:
  font-sans:
    fontFamily: '"Inter", "Noto Sans SC", -apple-system, sans-serif'
  font-serif:
    fontFamily: '"Noto Serif SC", "Songti SC", serif'
  font-mono:
    fontFamily: '"SFMono-Regular", Consolas, monospace'
  body:
    fontFamily: '{typography.font-sans.fontFamily}'
    fontSize: '14px'
    lineHeight: '1.5'
  display-hero:
    fontFamily: '{typography.font-serif.fontFamily}'
    fontSize: 'clamp(48px, 6.4vw, 96px)'
    fontWeight: '600'
    letterSpacing: '-0.06em'
    lineHeight: '1.12'
  display-page:
    fontFamily: '{typography.font-serif.fontFamily}'
    fontSize: 'clamp(42px, 5vw, 68px)'
    fontWeight: '600'
    letterSpacing: '-0.05em'
    lineHeight: '1.15'
  question:
    fontFamily: '{typography.font-serif.fontFamily}'
    fontSize: 'clamp(24px, 2.9vw, 40px)'
    fontWeight: '600'
    letterSpacing: '-0.03em'
    lineHeight: '1.28'
  prose:
    fontFamily: '{typography.font-serif.fontFamily}'
    fontSize: '17px'
    lineHeight: '2.05'
  overline:
    fontFamily: '{typography.font-mono.fontFamily}'
    fontSize: '10px'
    letterSpacing: '0.1em'
    textTransform: 'uppercase'
  label:
    fontFamily: '{typography.font-sans.fontFamily}'
    fontSize: '12px'
    fontWeight: '600'
  button:
    fontFamily: '{typography.font-sans.fontFamily}'
    fontSize: '12px'
    fontWeight: '600'
rounded:
  control: '2px'
  option-card: '3px'
  dot: '50%'
  DEFAULT: '0'
spacing:
  header-height: '66px'
  header-height-mobile: '60px'
  form-width: '430px'
  reader-width: '720px'
  editor-width: '820px'
  library-width: '1240px'
  archive-width: '1180px'
  modal-padding: '42px'
  card-padding: '26px'
  gutter-inline: 'clamp(24px, 4vw, 64px)'
elevation:
  focus-ring: '0 0 0 3px rgb(0 0 0 / 8%)'
  hard-dropdown: '4px 4px 0 rgb(0 0 0 / 8%)'
  hard-float: '6px 6px 0 rgb(16 16 16 / 8%)'
  hard-modal: '12px 12px 0 rgb(0 0 0 / 18%)'
  hard-dialog: '14px 14px 0 rgb(16 16 16 / 18%)'
components:
  button-primary:
    background: '{colors.ink}'
    color: '{colors.white}'
    border: '1px solid {colors.ink}'
    borderRadius: '{rounded.control}'
    height: '48px'
    fontSize: '{typography.button.fontSize}'
    fontWeight: '600'
    hoverBackground: '{colors.ink-hover}'
    disabledOpacity: '0.6'
  button-secondary:
    background: '{colors.white}'
    color: '{colors.ink}'
    border: '1px solid {colors.line-strong}'
    borderRadius: '{rounded.control}'
    minHeight: '40px'
  button-danger:
    color: '{colors.error}'
    border: '1px solid {colors.error}'
  input:
    background: '{colors.white}'
    border: '1px solid {colors.line-strong}'
    borderRadius: '{rounded.control}'
    height: '48px'
    focusShadow: '{elevation.focus-ring}'
  card:
    background: '{colors.white}'
    border: '1px solid {colors.line-strong}'
    borderRadius: '{rounded.DEFAULT}'
    hoverBackground: '{colors.paper}'
  modal:
    background: '{colors.white}'
    border: '1px solid {colors.line-strong}'
    boxShadow: '{elevation.hard-modal}'
    padding: '{spacing.modal-padding}'
  header:
    height: '{spacing.header-height}'
    borderBottom: '1px solid {colors.line-strong}'
    layout: 'grid 1fr auto 1fr'
---

# Muse — DESIGN.md

> **权威声明**：本文件是原型 `prototype/app/styles.css`（3901 行）视觉事实的结构化镜像，服务于 BMAD 交付物完整性。**与 BMAD-UX 默认规则相反**，Muse 的铁律是"原型 = 唯一事实基准"，因此本文件在与原型代码冲突时**服从原型**，不凌驾。所有 token 照抄自 styles.css，括号内为源行号。

## Brand & Style

Muse 的视觉语言是一套 **editorial / 印刷杂志感叠加 neo-brutalist（新粗野）硬阴影** 的黑白纸张美学：冷静、克制、有版面感——像一本装帧考究的印刷文学刊物被搬上屏幕。它服务于产品主张"让每一个人，成为小说家"，用"纸"的物理隐喻把 AI 生成的抽象过程落成可触摸的创作物。

四条支撑这一姿态的硬事实：

- **黑白纸张色板**：主色是纯黑白灰加一层纸张米色 `{colors.paper}`（styles.css:2），唯一彩色是印刷校样式的深红 `{colors.error}` 与墨绿 `{colors.success}`（styles.css:10-13）——没有品牌蓝、没有渐变主色，是报刊印刷的调性。
- **字体三分工**：衬线体承担标题与正文阅读，等宽体专用于栏目标签 / 编号 / EDITION 字样 / 页码（folio），无衬线做 UI 控件——这正是报纸杂志的排版分工。大量 `uppercase` + 宽字距的 mono 小标签强化栏目感。
- **硬投影**：全站阴影模糊半径恒为 0，只有位移（`Nx Ny 0`），像实体纸片叠放的投影——neo-brutalist 标志手法。
- **纸质装饰母题**：登录页 45° 方形描边、方块 wordmark、大号 serif folio 页码、章节卡以 ±1.4°/1.6° 旋转叠成"牌堆"——全是纸质印刷物的隐喻。

## Colors

色板刻意让 `line-strong` 与 `ink` 同为 `#111`（"强边框 = 主文字色"），这是黑白版面统一感的根源。

| Token | 值 | 用途 | 不用于 |
|---|---|---|---|
| `paper` | `#f7f7f4` | 页面主背景（纸张米色）、聚焦色块衬底 | 卡片/输入框背景（那是 white） |
| `white` | `#ffffff` | 卡片、输入框、模态、浮层背景 | 页面主背景 |
| `ink` | `#111111` | 主文字、主按钮/深色卡片背景、强边框、左强调条 | — |
| `ink-2` | `#333333` | 次级正文（略浅段落文字） | 标题（用 ink） |
| `sub` | `#6e6e6e` | 副文本、说明、标签、占位说明 | 正文主体 |
| `faint` | `#a2a2a2` | 编号、占位符、禁用态、浅色 folio | 需被读清的正文 |
| `line` | `#deded9` | 浅分隔线 / 弱边框 | 主容器/输入框边框 |
| `line-strong` | `#111111` | 强分隔线 / 主边框（= ink） | — |
| `error` | `#a4261d` | 错误态文字 / 边框 | 一般强调 |
| `error-bg` | `#fff4f2` | 错误提示背景 | — |
| `success` | `#1f6f49` | 成功态文字 / 圆点 / 边框 | 一般强调 |
| `success-bg` | `#eef8f2` | 成功提示背景 | — |

**辅助硬编码色**（未收进 `:root` 但语义重要）：选区背景 `selection #e5e5e0`（styles.css:55）；主按钮 hover `ink-hover #292929`（styles.css:449/816）；段落定位高亮 `locate-highlight #eeeeea`（styles.css:3431）。深色"下一章"卡上的弱文字 `#bdbdb7`、分隔线 `#555550`（styles.css:3143/3147）。

**⚠️ 待补缺陷 token**（原型中被引用但 `:root` 未定义，最终会静默回退）：`--sans`（styles.css:2991）、`--line-soft`（styles.css:3480 禁用态边框实际失效）。**无深色模式**、无命名的间距/圆角/阴影 scale token（除颜色与字体外均为硬编码字面量）。

## Typography

基础：`body { font: 14px/1.5 var(--font) }`（styles.css:34）+ 抗锯齿。字体三分工见下。

**展示型 serif 标题**——共同特征 `font-weight:600` + 负字距 + 紧行高，靠 `clamp()` 响应式缩放：

| 角色 | Token | 字号 | 源行号 |
|---|---|---|---|
| 登录主标题 | `display-hero` | `clamp(48px,6.4vw,96px)` | 166 |
| 作品库大标题 | `display-page` | `clamp(42px,5vw,68px)` | 669 |
| 引导大问句 | `question` | `clamp(24px,2.9vw,40px)` | 1707 |
| 章节标题 | — | `clamp(38px,5vw,64px)` | 2463 |

**serif 正文/阅读**：章节正文 `prose` 17px / 行高 2.05（阅读态特意加大行距，styles.css:3361）；章节大纲 18px / 1.8；Agent 消息 `clamp(14px,1.3vw,18px)` / 1.55。

**mono 栏目标签 / 编号**（统一 `uppercase`）：`overline` 10px / 字距 0.1em（styles.css:1244-1253）；`.guided-progress` 字距 0.14em 为全站最宽（styles.css:1699）；消息元信息 9px。

**UI 文字**：`label` 与 `button` 均 12px / 600。字段 label 12px/600（styles.css:389）。

## Layout & Spacing

**无间距 scale token，全部硬编码**，响应式内边距普遍用 `clamp()`。

- **顶栏**：统一高度 `{spacing.header-height}` 66px（移动端 60px），三分栏 `grid 1fr auto 1fr`，底部 1px 强线，左右 padding `{spacing.gutter-inline}`。
- **主内容最大宽度**：表单 430px、阅读器 720px、对话/编辑列 820px、作品库 1240px、归档 1180px。
- **卡片内边距** 20–26px；**模态** 42px；对话框头/身 `26–28px 32px`。
- **网格**：桌面优先，无 min-width 断点，无容器查询。

## Elevation & Depth

阴影语言统一为**硬投影：模糊半径恒 0，只有位移**（`Nx Ny 0 color`），营造实体纸片叠放感。X/Y 偏移永远相等（正 45° 右下投影），偏移量与元素层级严格正相关，透明度 7%–18%（越重的对话框越深）。

| 层级 | Token | 值 | 用于 |
|---|---|---|---|
| 下拉/选项 | `hard-dropdown` | `4px 4px 0 rgb(0 0 0 / 8%)` | 项目菜单、已选选项 |
| 浮层 | `hard-float` | `6px 6px 0 rgb(16 16 16 / 8%)` | 灵感浮层、批注浮层(8px) |
| 模态 | `hard-modal` | `12px 12px 0 rgb(0 0 0 / 18%)` | 新建/模式模态 |
| 大对话框 | `hard-dialog` | `14px 14px 0 rgb(16 16 16 / 18%)` | 设定档、归档对话框 |

**聚焦环**（0 位移 + spread，无模糊）：`focus-ring` `0 0 0 3px rgb(0 0 0 / 8%)`（styles.css:418）。

**"纸衬"聚焦**（用 spread 把背景色向外撑，让编辑态像"在纸上"）：内联可编辑项聚焦 `0 0 0 6px var(--white)` / `0 0 0 8px var(--paper)`（styles.css:2001/2205）；段落选中用左右阴影 `8px 0 0 var(--paper), -8px 0 0 var(--paper)`（styles.css:3425）。

**单侧色条**（用阴影当强调条）：模式卡 hover `inset 4px 0 var(--ink)`；设定档"已更新"项 `-4px 0 0 var(--success)`。

## Shapes

- **切边直角为默认语言**：卡片、模态、导航、徽章一律 0 圆角，边框 `1px solid`（弱 line / 强 line-strong），如印刷版面的分栏切割。
- **微圆角只给可点控件**：按钮/输入 `{rounded.control}` 2px、引导选项卡 `{rounded.option-card}` 3px——软化点击目标又不破坏硬朗基调。
- **圆形只用于状态点与 loading**（`{rounded.dot}` 50%），语义上区隔于"版面"。
- **方块母题**：wordmark 36×36、模式序号 26×26、Agent 头像 24×24、完成勾选 38×38——编号/头像都是实心方块而非圆形，呼应印刷铅字块。
- **旋转装饰**：登录 45° 方框、归档卡 ±1.4°/1.6° 旋转叠放，hover 回正上浮——纸牌物理隐喻。阴影方向恒右下 45°，与"光从左上来"直觉一致。

## Components

**button-primary**（styles.css:433/799）：背景 ink、1px ink 边框、白字、圆角 2px；常两端对齐（文字 + 箭头）；`.submit` 高 48px 全宽，`.primary-button` min-height 40px / 12px / 600。hover 背景 `#292929`；disabled `opacity:0.6` + `cursor:wait`。

**button-secondary**（styles.css:1081）：白底、1px line-strong 边框、12px/600、min-height 40px、圆角 2px。**button-danger**：边框与文字用 error（styles.css:862/1120）。**幽灵/工具按钮**：透明 + sub 色，hover 变 ink 或背景 paper。

**input**（styles.css:403）：白底、1px line-strong、圆角 2px、高 48px、padding `0 14px`、全宽；聚焦 `focus-ring` + `outline:0`。**"无边框写作"文本域**（探索/章节想法输入，styles.css:1768/2506）：无边框或仅底线，行高 1.75、resize vertical，让输入区"隐形"以突出写作。**内联可编辑**（contenteditable）：设定卡 / 线索卡 / 阶段规划，聚焦时用"纸衬"阴影。

**card**（styles.css:1004/3060）：白底、1px line-strong、hover 背景 paper。模式选项卡 min-height 230px + 26×26 黑序号方块 + hover 左内强调条。归档章节卡 min-height 350px + 48px serif 大序号，牌堆布局（±旋转 + `margin-left:-72px` 叠压 + `archive-deal` 发牌入场）。"下一章"深色卡背景 ink / 白字（反相卡）。

**modal / dialog**（styles.css:967/2125）：白底、1px 边框、硬阴影 12–14px、右上 34×34 方形关闭钮；大对话框三段式（头/滚动体/底部动作，各 1px 强线分隔）。遮罩 `rgb(16 16 16 / 28%–56%)`，`body.dialog-open { overflow:hidden }`。**移动端（760px）对话框全屏化**：去边框、去阴影、`height:100vh`。

**header**（styles.css:602/1131）：高 66px、三分栏 `grid 1fr auto 1fr`、底部 1px 强线；活动导航项底部 4px ink 下划线；`.save-state` 含 6px 绿圆点。

**列表项 `.project-row`**（styles.css:694）：5 列网格、底部 1px line、min-height 148px；含 mono 序号 + serif 25px 标题 + 模式徽章 + 状态 + 时间 + 主按钮 + ••• 菜单；整行覆盖点击热区，hover 标题加下划线。

**标签/徽章**：描边小标签 `1px solid line` + sub + 10px；mono overline uppercase 宽字距；状态圆点（3×3 黑方点 / 6px 绿圆点）；计数徽章黑底白字 mono。

## Motion

**8 个 @keyframes**：`frame-in`（45° 方框缩放淡入）、`title-in`（clip-path 逐字揭示）、`rise-in`、`form-in`、`fade-in`、`guided-settle-spin`（loading 转圈）、`archive-deal`（发牌入场，320ms）、`generation-pulse`（生成中方框呼吸，1.2s infinite）。

**登录入场编排**（styles.css:183-213）：统一缓动 `cubic-bezier(0.22,1,0.36,1)`，时长 420–980ms，延迟 80→1020ms 逐个揭示。

**微交互 transition**：引导选项 `border-color/box-shadow/transform` 各 0.16s ease（hover 上浮 1px + 硬阴影 + 箭头位移）；文字按钮 hover 变色 0.15s；折叠区 `grid-template-rows 240ms`（`1fr`↔`0fr`）；折叠箭头 `transform 160ms`（open 时 rotate 45°）。

**无障碍**：`@media (prefers-reduced-motion: reduce)`（styles.css:578）全局 `transition-duration:0.01ms !important` + `scroll-behavior:auto`，并关闭脉冲与发牌动画。

## Do's and Don'ts

**Do**
- 用硬投影（模糊 0、X=Y 正偏移）表达层级；偏移量随层级递增（4→6→8→12→14px）。
- 标题/正文用 serif，标签/编号/页码用 mono uppercase，UI 控件用 sans。
- 卡片/模态/导航保持直角，只给按钮/输入 2px 微圆角。
- 编辑态用"纸衬"spread 阴影，让内联编辑像在纸上写字。
- 主按钮永远 ink 底白字两端对齐；危险动作永远 error 描边。

**Don't**
- 不引入带模糊半径的柔和阴影（会破坏纸片叠放语言）。
- 不加品牌彩色 / 渐变主色（色板只有黑白灰 + 纸色 + 校样红绿）。
- 不给卡片/徽章加圆角（圆形只留给状态点与 loading）。
- 不新增未在 `:root` 定义的 token（`--sans`/`--line-soft` 是现存缺陷，须补定义而非扩散）。
- 不假设深色模式存在（原型无，任何暗色态需先立项）。

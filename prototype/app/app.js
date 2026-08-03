const app = document.querySelector("#app");
// 引导探索的问题库：每题一组预设选项（label 短标签 / value 写入历史的完整答案）。
// 问题偏间接、有画面感，借鉴人格测试——不直接问“你想写什么类型”，而是从倾向推断。
// allowCustom 为 true 的题额外允许用户用一句话自述（目前仅第一题）。
const explorationQuestions = [
  {
    question:
      "先别急着想完整故事。此刻你脑中最先亮起来的，是哪一种画面？",
    allowCustom: true,
    options: [
      { label: "一个人", value: "一个在雨夜里独自收到陌生人来信的人。" },
      { label: "一个场景", value: "一座每天凌晨都会悄悄改变街道位置的城市。" },
      { label: "一件事", value: "所有人在同一个清晨，忘记了同一天发生过的事。" },
      { label: "一种情绪", value: "一种明知身边有什么不对、却说不出哪里不对的不安。" },
    ],
  },
  {
    question: "你更想写一个怎样的主角？",
    options: [
      { label: "主动改变世界的人", value: "一个不肯接受既定事实、执意要亲手改变结局的人。" },
      { label: "被世界推着走的人", value: "一个被卷入远超自己掌控的处境、只能一步步应对的人。" },
      { label: "想守住某样东西的人", value: "一个拼命想守住某个人或某段记忆、不让它被抹去的人。" },
      { label: "在寻找答案的人", value: "一个隐约察觉真相被掩盖、执意要弄清到底发生了什么的人。" },
    ],
  },
  {
    question: "故事里最主要的对抗，来自哪里？",
    options: [
      { label: "人与人", value: "核心冲突来自人与人之间——背叛、争夺，或立场的对立。" },
      { label: "人与规则", value: "核心冲突来自个人与某种制度或规则的对抗。" },
      { label: "人与世界", value: "核心冲突来自人与环境本身——一个会反抗、会改变的世界。" },
      { label: "人与自己", value: "核心冲突来自主角内心——他最大的敌人是自己的记忆或欲望。" },
    ],
  },
  {
    question: "读者合上这本书时，你最想他带走哪种感觉？",
    options: [
      { label: "震撼", value: "希望结尾给读者强烈的震撼与回响，久久不能平静。" },
      { label: "温暖", value: "希望读者读完感到温暖，相信人与人之间仍有微光。" },
      { label: "怅然", value: "希望留下一种怅然若失、意味深长的余味。" },
      { label: "紧张到最后", value: "希望读者一路悬着心，直到最后一页才敢松一口气。" },
    ],
  },
  {
    question: "这个世界离我们的现实有多远？",
    options: [
      { label: "就是现实", value: "故事发生在与现实几乎无异的世界，力量来自人性本身。" },
      { label: "现实里的一点异常", value: "世界基本写实，但藏着一处无法解释的异常规则。" },
      { label: "完全架空", value: "一个拥有自身规则与秩序的完整架空世界。" },
      { label: "熟悉又陌生", value: "像我们的世界，却在某个根本设定上被悄悄改写过。" },
    ],
  },
  {
    question: "如果把故事的气质想成一幅画，它接近哪种光线？",
    options: [
      { label: "冷峻的夜雨", value: "潮湿的旧城、将熄未熄的路灯，冷峻克制的气质。" },
      { label: "明亮的清晨", value: "开阔明亮的清晨光线，节奏轻快、充满可能性。" },
      { label: "黄昏的暖光", value: "黄昏般温暖而略带感伤的光线，适合缓慢的情感。" },
      { label: "无光的深处", value: "几乎没有光的幽闭空间，压抑、悬疑、步步逼近。" },
    ],
  },
];
const seededExplorationHistory = [
  {
    question: explorationQuestions[0].question,
    answer: "一个在雨夜里独自收到陌生人来信的人。",
  },
  {
    question: explorationQuestions[1].question,
    answer: "一个拼命想守住某个人或某段记忆、不让它被抹去的人。",
  },
  {
    question: explorationQuestions[2].question,
    answer: "核心冲突来自主角内心——他最大的敌人是自己的记忆或欲望。",
  },
  {
    question: explorationQuestions[3].question,
    answer: "希望留下一种怅然若失、意味深长的余味。",
  },
  {
    question: explorationQuestions[4].question,
    answer: "世界基本写实，但藏着一处无法解释的异常规则。",
  },
];
const seededFreeConversation = [
  {
    role: "user",
    text: "我想让那封信其实是姐姐多年前写给未来的他，但又不想太早揭晓。",
  },
  {
    role: "agent",
    text: "这个方向会让寻找姐姐同时变成一次对记忆的追查。我们可以先只留下信件年代对不上的破绽，不直接说明写信人。你希望这封信更像求救，还是警告？",
  },
];
let hasPlayedIntro = false;
let createStep = "closed";
let selectedMode = "";
let explorationTitle = "未命名小说";
const startWithConversationPreview =
  new window.URLSearchParams(location.hash.split("?")[1] || "").get("state") ===
  "conversation";
let explorationHistory = startWithConversationPreview
  ? seededExplorationHistory.map((entry) => ({ ...entry }))
  : [];
let freeConversation = startWithConversationPreview
  ? seededFreeConversation.map((entry) => ({ ...entry }))
  : [];
// explorationView：引导探索的翻页指针（“正在看第几题”），可前后翻不删答案。
// 已答题数由 explorationHistory.length 决定，两者解耦以支持问卷式前后翻页。
let explorationView = explorationHistory.length;
// 引导探索答完最后一题后的“整理中”过渡态：遮住后台生成设定的等待，传递“它在认真理解我”的体感。
let guidedSettling = false;
// Story 7.5 引导探索接线态（替换纯 mock/sessionStorage）：
// explorationProjectId：当前探索作品 id（来自路由 exploreMatch，供建会话/落库/settle 用）。
let explorationProjectId = "";
// guidedLoadState：进探索页拉会话 + 回填答案的加载态（loading/ready/error），驱动渲染。
let guidedLoadState = "loading";
// guidedLoadSeq：拉取代次，回调校验代次未变才写状态/DOM（仿 7.3 projectsLoadSeq，防往返赛跑）。
let guidedLoadSeq = 0;
// guidedLoadError：加载失败时的 ApiError（渲染 error 态用）。
let guidedLoadError = null;
// guidedAnswerSaving：某题答案落库在途标志，防重复提交（选项连点 / 自述重复提交）。
let guidedAnswerSaving = false;
// settleAbortController：settle SSE 在途控制器，「回到探索」/切走时 abort。
let settleAbortController = null;
// interpretAbortController：自述作答 interpret SSE 在途控制器，切走/导航离开时 abort（review P1）。
let interpretAbortController = null;
// settleErrorText：settle SSE error 事件的可读提示（渲染在收尾态供重试）。
let settleErrorText = "";
// Story 7.6 自由探索接线态：与引导侧并列，所有数据以 API 返回为准。
let freeClues = [];
let freeLoadState = "loading";
let freeLoadSeq = 0;
let freeLoadError = null;
let freeMessageSending = false;
let freeMessageAbortController = null;
let freeSettlePending = false;
let freeSettleErrorText = "";
let freeClueEditingIds = new Map();
let freeClueFocusedIds = new Set();
let deferredFreeClues = null;
// Story 2.8 消费（Correct Course 替换旧版「给方向」+「≥1条消息」门禁）：自由探索导航状态，
// 完成度/当前问题/就绪位恒以后端 GuidanceStateResponse 为准，前端不本地推断。
let guidanceFields = {};
let guidanceCurrentField = null;
let guidanceCurrentQuestion = null;
let guidanceReadyToSettle = false;
// guidanceSuggestions：null=未请求过；[]=已请求但空（异常兜底）；非空=可点击选项列表。
let guidanceSuggestions = null;
let guidanceSuggestionsLoading = false;
let guidanceSkipping = false;
// guidanceStartingEntry：零对话四入口点击后在途的 entry key，用于禁用四个入口按钮防重复点击。
let guidanceStartingEntry = null;
let customStoryClues = [];
const explorationModeKey = "muse-exploration-mode";
const explorationEntryModeKey = "muse-exploration-entry-mode";
const confirmedStoryProfileKey = "muse-confirmed-story-profile";
let explorationMode =
  window.sessionStorage.getItem(explorationModeKey) || "profile";
// 新建时选择的探索入口：guided（引导探索）或 free（自由探索）
let explorationEntryMode =
  window.sessionStorage.getItem(explorationEntryModeKey) || "guided";
let confirmedStoryProfile = readStoredJson(confirmedStoryProfileKey);
let stagePlanningHistory = [];
let stagePlanningRound = 0;
let stagePlanningDraft = {
  goal: "",
  opening: "",
  conflict: "",
  events: "",
  chapters: "",
};
let currentStagePlan = null;
let chapterCreationState = "input";
let chapterIdea = "";
let chapterReaderPage = 0;
let chapterRevision = 1;
let chapterFeedback = "";
let chapterAgentBusy = false;
let chapterAgentResult = "";
let chapterLastRevisionAction = "";
let chapterAnnotations = [];
let chapterAnnotationTarget = null;
let chapterAnnotationDraft = "";
let chapterAnnotationFocus = null;
let chapterFinalized = false;
let chapterCreationIndex = 0;
let archiveDialogOpen = false;
// UX-ALIGN-01 新增四页的会话级状态（文风锚点 / BYOK 用量 / 阶段交界方向输入）
let styleAnchorTab = "library";
let styleAnchorSelected = null;
let styleAnchorPasteText = "";
let styleAnchorResult = null;
let byokTab = "hosted";
let byokKeyDraft = "";
// Story 7.4 接线态：绑定状态与用量由后端驱动（替换原写死占位）。
let byokBinding = null; // {bound, provider, maskedKey} | null（未拉取/未绑定）
let usageView = null; // {billingPath, quotaApplies, used, quota, remaining, resetAt} | null
let byokLoadState = "loading"; // loading | ready | error
let byokLoadSeq = 0; // 拉取代次，防在途赛跑（仿 7.3 projectsLoadSeq）
let byokReplaceMode = false; // 已绑定态点「更换 Key」后进入重填态（UI 态）
let byokSelectedProvider = "deepseek"; // byok tab 当前选中的 provider（写入用）
let byokSaving = false; // 保存 PUT 在途标志：防 input 监听在途重新 enable 按钮致并发双 PUT
let stageDirectionText = "";
// 通读视图分页：章内按页翻阅（每页若干段），翻过本章末页进入下一章。
let readthroughChapterIndex = 0;
let readthroughPageIndex = 0;
let archiveSelectedChapter = 0;
let archiveSelectedStage = 0;
let archiveCollapsedStages = new Set();
// 归档页默认收起：设定圣经默认折叠；阶段在首次渲染时全部预置为收起（见 renderChapterArchive）。
let archiveProfileCollapsed = true;
let archiveStagesInitialized = false;
const pendingStoryProfileKey = "muse-pending-story-profile";
const restoredStoryProfile = readPendingStoryProfile();
let finalStoryProfile = restoredStoryProfile?.profile || null;
let finalStoryProfileSignature = restoredStoryProfile?.signature || "";
let finalStoryProfileRevision = restoredStoryProfile?.revision || 1;
let pendingStoryProfile = Boolean(restoredStoryProfile?.profile);
let lastProfileChangedFields = restoredStoryProfile?.changedFields || [];
let profileFeedbackStatus = restoredStoryProfile?.feedbackStatus || "";

function readStoredJson(key) {
  try {
    return JSON.parse(window.sessionStorage.getItem(key));
  } catch {
    return null;
  }
}

function readPendingStoryProfile() {
  try {
    return JSON.parse(window.sessionStorage.getItem(pendingStoryProfileKey));
  } catch {
    return null;
  }
}

function persistPendingStoryProfile() {
  if (!pendingStoryProfile || !finalStoryProfile) return;
  window.sessionStorage.setItem(
    pendingStoryProfileKey,
    JSON.stringify({
      profile: finalStoryProfile,
      signature: finalStoryProfileSignature,
      revision: finalStoryProfileRevision,
      changedFields: lastProfileChangedFields,
      feedbackStatus: profileFeedbackStatus,
    }),
  );
}

function clearPendingStoryProfile() {
  window.sessionStorage.removeItem(pendingStoryProfileKey);
}

// 作品库列表：Story 7.3 起由后端 GET /api/projects 真实填充（camelCase），
// 不再硬编码。ProjectResponse 字段：{id, title, mode(guided/free),
// phase(explore/chapter/archive), updatedAt(ISO)}。后端已按 updated_at DESC 排序。
let projects = [];
// 列表加载态：驱动 renderProjects 渲染 loading/ready/empty/error 四态（替换原型
// 靠 ?state= 预览开关的手动切换）。初始 loading，list 回调据结果置 ready/empty/error。
let projectsLoadState = "loading";
// 当前登录用户邮箱：GET /api/auth/me 拉取后缓存，header 展示（替换硬编码 creator@example.com）。
// 邮箱不变，缓存即可；me 失败降级为空串、不阻断作品列表。
let currentUserEmail = "";
// 列表拉取代次：每次 loadProjects 自增并捕获快照，回调时校验代次未变才写状态/DOM。
// 防「离开 #/projects 又回来」两次拉取并发时旧回调覆盖新数据（hashPath 校验只防切走、
// 不防往返；跨账号登出→登录后 hash 仍是 #/projects 同理需代次兜住）。
let projectsLoadSeq = 0;

// phase → 展示文案 + 继续路由的单一数据源（键须与后端英文枚举逐字一致）
const PHASE_META = {
  explore: {
    label: "故事设定",
    continueLabel: "继续设定",
    route: (id) => `#/projects/${id}/explore`,
  },
  chapter: {
    label: "章节创作",
    continueLabel: "阅读草稿",
    route: (id) => `#/projects/${id}/chapters/1`,
  },
  archive: {
    label: "已归档",
    continueLabel: "回到归档",
    route: (id) => `#/projects/${id}/archive`,
  },
};

// ---------------------------------------------------------------------
// 作品库字段适配（Story 7.3）：后端 ProjectResponse 只返 {id,title,mode,phase,updatedAt}，
// 与原型 mock 字段（mode 中文 / updated 预格式化 / attention·detail 副文案）不一一对应，
// 渲染前在此收敛映射。纯函数、无 DOM 依赖，便于 Node vm 回归。
// ---------------------------------------------------------------------

// mode 枚举 → 中文展示（后端 guided/free，原型展示「引导探索/自由探索」）。
// 与 createDialog naming 步骤（selectedMode==="free"?"自由探索":"引导探索"）同一口径。
function projectModeLabel(mode) {
  return mode === "free" ? "自由探索" : "引导探索";
}

// phase → 作品行副文案（受控决策 1）：后端不返 mock 的 attention/detail（真实章节进度
// 归 Epic 4/5，本 story 无数据源）。故用 phase 派生中性文案，不臆造后端字段、不硬编码假进度。
function projectStatusText(phase) {
  if (phase === "chapter") return "创作中";
  if (phase === "archive") return "已归档";
  return "设定进行中";
}

// updatedAt(ISO 8601 UTC，带 Z) → 中文相对时间展示（替换 mock 预格式化的「今天 16:40」）。
// 容错：非法/缺失时间返空串（<time> 留空不崩）。相对规则：今天/昨天/N 天内/更早显日期。
function formatRelativeTime(iso) {
  if (!iso) return "";
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return "";
  const now = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  const hm = `${pad(then.getHours())}:${pad(then.getMinutes())}`;
  const startOfDay = (d) =>
    new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const dayDiff = Math.round((startOfDay(now) - startOfDay(then)) / 86400000);
  if (dayDiff <= 0) return `今天 ${hm}`;
  if (dayDiff === 1) return `昨天 ${hm}`;
  if (dayDiff < 7) return `${dayDiff} 天前`;
  return `${then.getMonth() + 1} 月 ${then.getDate()} 日`;
}

// 作品操作失败（ApiError）→ 可读提示文案（不臆造后端未定义分支，参照 authStateFromError）。
// project_not_found：作品已被删/越权（后端 IDOR 消除，越权也返 404）→ 提示已不存在，调用方刷新列表。
function projectErrorText(err) {
  const code = err && err.code;
  if (code === "project_not_found") return "这本小说已不存在，列表已刷新。";
  if (code === "validation_error") return "输入有误，请检查后重试。";
  return "操作未能完成，请检查网络后稍后重试。";
}

function hashPath() {
  return location.hash.split("?")[0] || "#/login";
}

function queryState() {
  const query = location.hash.split("?")[1] || "";
  return new window.URLSearchParams(query).get("state") || "";
}

function currentMode() {
  return hashPath() === "#/register" ? "register" : "login";
}

function stateMessage(state, mode) {
  const messages = {
    expired: ["error", "会话已过期，请重新登录。登录后会返回你的创作空间。"],
    invalid: [
      "error",
      mode === "login"
        ? "邮箱或密码错误，请检查后重试。"
        : "邀请码无效、已使用或已过期。",
    ],
    locked: ["error", "登录尝试次数过多，请稍后再试。"],
    // 未知/网络/校验类错误的中性兜底（Story 7.2 AC6）：不臆造 expired/invalid，只提示重试。
    failed: ["error", "操作未能完成，请检查网络后稍后重试。"],
  };
  return messages[state] || null;
}

// error envelope code → 登录/注册状态位（Story 7.2 AC6，严格对应后端 code，不臆造）。
// 入参为 7.1 apiFetch 抛出的 ApiError（含 code/detail/status）。映射见 story error code 表：
//   invalid_credentials / invalid_invite → invalid；too_many_attempts → locked；
//   token_invalid(expired) → expired（通常 7.1 已跳转，登录页少见）；其余 → failed 中性兜底。
function authStateFromError(err) {
  const code = err && err.code;
  const detail = (err && err.detail) || {};
  if (code === "invalid_credentials" || code === "invalid_invite") return "invalid";
  if (code === "too_many_attempts") return "locked";
  if (code === "token_invalid" || code === "token_expired") return "expired";
  // 优先按 code 判定；code 不可识别时退到 detail 布尔位（后端已透传）。
  if (detail.invalid) return "invalid";
  if (detail.locked) return "locked";
  if (detail.expired) return "expired";
  return "failed";
}

function renderAuth() {
  const mode = currentMode();
  const state = queryState();
  const isRegister = mode === "register";
  const message = stateMessage(state, mode);
  const playIntro = !hasPlayedIntro;
  document.title = `${isRegister ? "邀请码注册" : "登录"} · Muse`;

  app.innerHTML = `
    <div class="auth-page ${playIntro ? "intro" : ""}">
      <section class="brand-side" aria-labelledby="brand-title">
        <header class="brand-head">
          <div class="wordmark"><span class="wordmark-mark">M</span><span>Muse</span></div>
          <span class="edition">Private beta · 2026</span>
        </header>
        <div class="brand-copy">
          <div class="kicker">AI novel collaboration</div>
          <h1 id="brand-title"><span class="brand-title-line">让每一个人，</span><br /><span class="brand-title-line brand-title-indent">成为小说家。</span></h1>
          <p>你参与设定、选择与修改，Agent 陪你把一个想法，一章章写成小说。</p>
        </div>
        <footer class="brand-foot">
          <div><strong>从一个想法开始</strong><span>NOVEL / DRAFT / IN PROGRESS</span></div>
          <span class="folio">01</span>
        </footer>
      </section>
      <section class="form-side">
        <div class="auth-shell">
          <div class="form-index">Account / ${isRegister ? "Register" : "Login"}</div>
          <h2>${isRegister ? "用邀请码创建账号" : "回到你的创作空间"}</h2>
          <p class="form-intro">${isRegister ? "邀请码仅用于早期创作者注册。" : "继续你正在写的故事。"}</p>
          <div class="tabs" role="tablist" aria-label="账号入口">
            <button class="tab" role="tab" aria-selected="${!isRegister}" data-mode="login">登录</button>
            <button class="tab" role="tab" aria-selected="${isRegister}" data-mode="register">邀请码注册</button>
          </div>
          ${message ? `<div class="message ${message[0]}" role="status">${message[1]}</div>` : ""}
          <form id="auth-form" novalidate>
            ${isRegister ? `<div class="field"><div class="field-head"><label for="invite">邀请码</label><span class="field-note">必填</span></div><input class="input" id="invite" name="invite" autocomplete="off" placeholder="输入你的邀请码" required /></div>` : ""}
            <div class="field"><div class="field-head"><label for="email">邮箱</label></div><input class="input" id="email" name="email" type="email" autocomplete="email" placeholder="name@example.com" required /></div>
            <div class="field"><div class="field-head"><label for="password">密码</label>${isRegister ? `<span class="field-note">至少 8 位</span>` : ""}</div><div class="input-wrap"><input class="input" id="password" name="password" type="password" autocomplete="${isRegister ? "new-password" : "current-password"}" placeholder="输入密码" minlength="8" required /><button class="toggle-password" type="button" aria-label="显示密码">显示</button></div></div>
            <button class="submit" type="submit"><span>${isRegister ? "创建账号" : "登录到创作空间"}</span><span class="submit-arrow">→</span></button>
          </form>
          <p class="privacy-note">登录即表示你同意使用必要的会话 Cookie。我们不会在登录页要求验证码或第三方账号。</p>
          <details class="state-preview"><summary>原型状态预览</summary><div class="preview-links"><button class="preview-link" data-auth-state="expired">会话过期</button><button class="preview-link" data-auth-state="invalid">输入错误</button><button class="preview-link" data-auth-state="locked">频控锁定</button><button class="preview-link" data-auth-state="">清除状态</button></div></details>
        </div>
      </section>
    </div>`;

  bindAuthInteractions();
  if (playIntro) {
    window.requestAnimationFrame(() => {
      hasPlayedIntro = true;
    });
  }
}

function projectRow(project, index) {
  const number = String(index + 1).padStart(2, "0");
  const meta = PHASE_META[project.phase];
  // title 为真实用户输入，须 escapeHtml 防 XSS（mock 期是静态标题不涉及）。
  const title = escapeHtml(project.title || "未命名小说");
  const modeLabel = projectModeLabel(project.mode);
  const statusText = projectStatusText(project.phase);
  const updated = formatRelativeTime(project.updatedAt);
  return `
    <li class="project-row" data-project-id="${project.id}">
      <a class="project-archive-link" href="#/projects/${project.id}/archive" aria-label="查看《${title}》的章节归档"></a>
      <span class="project-number">${number}</span>
      <div class="project-copy">
        <div class="project-title-line"><h2>${title}</h2><span class="project-mode">${modeLabel}</span></div>
        <div class="project-status"><span>${meta?.label ?? project.phase}</span><i></i><strong>${statusText}</strong></div>
      </div>
      <time>${updated}</time>
      <button class="project-primary" data-continue="${project.id}">${meta?.continueLabel ?? "继续"}<span>→</span></button>
      <div class="project-menu-wrap">
        <button class="project-menu-button" aria-label="${title}的更多操作" aria-expanded="false" data-menu="${project.id}">•••</button>
        <div class="project-menu" hidden><button data-rename="${project.id}">重命名</button><button data-delete="${project.id}">删除</button></div>
      </div>
    </li>`;
}

function createDialog() {
  if (createStep === "closed") return "";
  if (createStep === "mode") {
    return `
      <div class="modal-backdrop" data-close-modal>
        <section class="modal create-modal" role="dialog" aria-modal="true" aria-labelledby="create-title">
          <div class="modal-index">New novel / 01</div>
          <h2 id="create-title">从哪里开始？</h2>
          <p class="modal-intro">两种方式最终都会形成同一份故事设定。</p>
          <div class="mode-grid">
            <button class="mode-option" data-create-mode="guided"><span class="mode-number">A</span><strong>引导探索</strong><p>回答一组有启发性的问题，系统带你一步步把想法理清楚。</p><span class="mode-action">开始引导 →</span></button>
            <button class="mode-option" data-create-mode="free"><span class="mode-number">B</span><strong>自由探索</strong><p>直接和 Agent 自由讨论，想到哪聊到哪，边聊边成形。</p><span class="mode-action">自由讨论 →</span></button>
          </div>
          <button class="modal-close" data-close-modal aria-label="关闭">×</button>
        </section>
      </div>`;
  }
  return `
    <div class="modal-backdrop" data-close-modal>
      <section class="modal naming-modal" role="dialog" aria-modal="true" aria-labelledby="naming-title">
        <div class="modal-index">New novel / 02</div>
        <h2 id="naming-title">给它一个名字</h2>
        <p class="modal-intro">暂时没有也没关系，可以稍后再改。</p>
        <label class="naming-label" for="novel-title">小说名称</label>
        <input class="input naming-input" id="novel-title" placeholder="未命名小说" autofocus />
        <div class="naming-meta">创建方式：${selectedMode === "free" ? "自由探索" : "引导探索"}</div>
        <div class="modal-actions"><button class="secondary-button" data-back-mode>返回</button><button class="primary-button" data-create-submit>跳过</button></div>
        <button class="modal-close" data-close-modal aria-label="关闭">×</button>
      </section>
    </div>`;
}

// 作品库渲染（Story 7.3 异步数据驱动）。render() dispatcher 同步调本函数：先按当前
// projectsLoadState 同步绘制（loading/ready/empty/error），若处于 loading 则触发一次
// 真实拉取（loadProjects），拉取回调据结果更新态并重绘。此设计保持 render() 同步、
// 数据真实：进入 #/projects 即 loading→拉取→ready/empty/error。
function renderProjects() {
  document.title = "你的小说 · Muse";
  paintProjects();
  bindProjectInteractions();
  if (projectsLoadState === "loading") {
    loadProjects();
  }
}

// 同步绘制当前态到 DOM（不含数据拉取）。四态：
//   loading — 拉取中占位；ready — 有作品列表 + 新建入口；
//   empty — 空库引导；error — 加载失败 + 重新加载。
function paintProjects() {
  const state = projectsLoadState;
  const email = currentUserEmail
    ? escapeHtml(currentUserEmail)
    : "创作空间";
  let content;
  if (state === "loading") {
    content = `<section class="library-loading" aria-busy="true"><p>正在载入你的作品…</p></section>`;
  } else if (state === "error") {
    content = `<section class="library-error"><strong>暂时无法读取你的作品。</strong><p>连接恢复后可以重新加载，不会影响已经保存的内容。</p><button class="secondary-button" data-reload>重新加载</button></section>`;
  } else if (projects.length) {
    content = `<ol class="project-list">${projects
      .map(projectRow)
      .join(
        "",
      )}<li><button class="new-project" data-new-project><span class="new-number">＋</span><span><strong>开始一本新小说</strong><small>从一个想法，或者一份已经准备好的设定开始。</small></span><span class="new-arrow">→</span></button></li></ol>`;
  } else {
    content = `<section class="empty-library"><div class="empty-lead"><div class="empty-index">First novel / 01</div><h2>你的第一本小说，<br />从这里开始。</h2></div><div class="empty-action"><p>不需要准备好完整故事。可以从一个模糊的想法开始，也可以直接写下已有设定。</p><button class="primary-button" data-new-project>开始一本新小说 <span>→</span></button></div></section>`;
  }
  // 计数：loading/error 时列表未定，显 -- 占位；ready/empty 显真实条数。
  const count =
    state === "loading" || state === "error"
      ? "--"
      : String(projects.length).padStart(2, "0");
  app.innerHTML = `
    <div class="library-page">
      <header class="library-header">
        <a class="wordmark" href="#/projects"><span class="wordmark-mark">M</span><span>Muse</span></a>
        <nav class="library-nav" aria-label="主导航"><a aria-current="page" href="#/projects">作品</a></nav>
        <div class="account"><span>${email}</span><a href="#/settings/model-access">设置</a><a href="#/login" data-logout>退出</a></div>
      </header>
      <main class="library-main">
        <div class="library-heading">
          <div><div class="library-kicker">Library / ${count} novels</div><h1>你的小说</h1><p>继续写下去。作品按照最后更新时间排列。</p></div>
          <span class="library-folio">02</span>
        </div>
        ${content}
      </main>
      ${createDialog()}
    </div>`;
}

// 异步拉取真实作品列表 + 当前用户邮箱（AC1/AC2/AC5）。
// 时序防护：拉取前记录发起时 hash，回调时若已切走（不在 #/projects）则不写 DOM，
// 避免用户快速切页后回调仍覆盖新页面（受控决策 4）。
// 401 由 apiFetch 兜底（自动刷新重放 / 失效跳登录），不在此重复处理。
async function loadProjects() {
  const startedHash = hashPath();
  const seq = ++projectsLoadSeq; // 捕获本次拉取代次
  // 并发拉列表 + 邮箱；邮箱失败不阻断列表（受控决策 3，降级为不显示邮箱）。
  const [listResult, meResult] = await Promise.allSettled([
    projectApi.list(),
    authApi.me(),
  ]);
  // 代次校验：期间又发起过新的 loadProjects（往返/切账号）则本次作废，不写状态/DOM。
  // 兼顾 hash 校验（切到别的页）与代次校验（离开又回来的同页并发）。
  if (seq !== projectsLoadSeq || hashPath() !== startedHash) return;
  // me 成功写邮箱、失败清空（防跨账号残留：A 登出→B 登录 me 偶发失败时不显 A 邮箱）。
  currentUserEmail =
    meResult.status === "fulfilled" && meResult.value
      ? meResult.value.email || ""
      : "";
  if (listResult.status === "fulfilled") {
    projects = Array.isArray(listResult.value) ? listResult.value : [];
    projectsLoadState = projects.length ? "ready" : "empty";
  } else {
    // 列表失败（非 401，401 已被 apiFetch 跳登录消化）→ error 态。
    projectsLoadState = "error";
  }
  renderProjects();
}

function storyClue(label, value = "") {
  const empty = !value;
  return `
    <div class="story-clue">
      <span>${label}</span>
      <div class="story-clue-value${empty ? " is-empty" : ""}" contenteditable="true" role="textbox" aria-label="编辑${label}" data-placeholder="尚未确定">${value || "尚未确定"}</div>
    </div>`;
}

function customStoryClue(clue, index) {
  return `
    <div class="story-clue custom-story-clue">
      <div class="custom-clue-head">
        <input value="${clue.label}" placeholder="设定名称" aria-label="自定义设定名称" data-custom-clue-label="${index}" />
        <button type="button" data-remove-custom-clue="${index}" aria-label="删除这项自定义设定">×</button>
      </div>
      <input class="custom-clue-value-input" value="${clue.value}" placeholder="描述这项设定……" aria-label="自定义设定描述" data-custom-clue-value="${index}" />
    </div>`;
}

// Story 7.5：引导探索 error code → 中文提示映射（仿 7.3 projectErrorText / 7.4 byokErrorText）。
// 判定用 err.code（后端恒字符串，7.1-7.4 已坐实）；SSE error 事件的 data.code 同源可复用。
// token_invalid/token_expired（401）由 apiFetch/apiStream 兜底跳登录，不在此处理。
function explorationErrorText(err) {
  const code = err && err.code;
  switch (code) {
    case "quota_exceeded":
      return "已用完当前免费额度。可到设置页绑定自己的 API Key 后继续。";
    case "generate_failed":
      return "生成失败，请稍后重试。";
    case "settle_failed":
      return "整理故事设定时出错了，请重试。";
    case "settle_empty":
      // 后端空态短路（story_settle_agent settle_empty 400）：材料不足以凝练，引导补充而非误报网络。
      return "聊到的内容还不够整理成设定，请回到上一题多补充一些再试。";
    case "exploration_not_ready":
      return "继续和 Agent 讨论，线索足够时就能整理为故事设定。";
    case "clue_not_deletable":
      return "预设线索不可删除。";
    case "preset_label_immutable":
      return "预设线索的名称不可修改。";
    case "already_settled":
      return "这部作品的设定已经确认，无法重新整理。";
    case "mode_mismatch":
      return "当前作品不是引导模式。";
    case "project_not_found":
      return "找不到这部作品，请回到作品库重试。";
    case "task_not_found":
      return "整理任务已失效，请重新整理。";
    default:
      return "操作未能完成，请检查网络后稍后重试。";
  }
}

// 把后端一条引导答案映射为前端 explorationHistory 项。后端行：
// {questionIndex, question, answer, answerType}；前端项：{question, answer}
// （answer 即用户所选选项 value 或自述凝练文本，翻页高亮按 value 匹配选项、不匹配即自述）。
function guidedAnswerFromBackend(row) {
  return { question: row.question, answer: row.answer };
}

// 统一清理探索页在途异步：所有流都必须在切页、换作品和登出时取消，避免旧项目/旧账号的
// 回调污染当前 DOM。pendingStoryProfile 是会话内展示态，导航离开时保留；logout 另行清除。
function teardownExplorationInflight() {
  if (interpretAbortController) {
    interpretAbortController.abort();
    interpretAbortController = null;
  }
  if (freeMessageAbortController) {
    freeMessageAbortController.abort();
    freeMessageAbortController = null;
  }
  if (settleAbortController) {
    settleAbortController.abort();
    settleAbortController = null;
  }
  guidedAnswerSaving = false;
  freeMessageSending = false;
  freeSettlePending = false;
  // Story 2.8 导航状态的提交门禁（无 AbortController，均是常规 apiFetch）：teardown 后
  // isCurrentFreeExploration 会因代次不匹配丢弃在途回调的状态写入，但 finally 里的门禁
  // 复位同样会被挡住——须在此显式复位，否则重进该项目后按钮永久卡在 disabled。
  guidanceStartingEntry = null;
  guidanceSuggestionsLoading = false;
  guidanceSkipping = false;
  guidedLoadSeq += 1;
  freeLoadSeq += 1;
}

// 进引导探索页：建/取会话（2.2）+ 回填全部已答（2.4）。仿 7.3 loadProjects 异步范式
// （loading→ready/error + hash + 代次时序防护）。失败态非 401（401 由 apiFetch 兜底跳登录）。
function loadGuidedExploration(projectId) {
  // review R2 P2：进页先 abort 上一项目残留的在途 SSE（explore→explore 直接换项目时
  // render 的 !exploreMatch teardown 不触发，须在此清理，防旧流连接悬挂）。
  teardownExplorationInflight();
  explorationProjectId = projectId;
  guidedLoadState = "loading";
  guidedLoadError = null;
  // review P4：进页复位作答门禁——防上一次 interpret 挂流/切走时 guidedAnswerSaving 停在
  // true，重进项目后所有作答被入口 `if (...||guidedAnswerSaving) return` 静默拦截。
  guidedAnswerSaving = false;
  const seq = ++guidedLoadSeq;
  const startedHash = location.hash;
  renderExploration();
  (async () => {
    try {
      // 先建/取会话（get-or-create 幂等），再拉已答。会话建立失败即整体失败态。
      await explorationApi.enter(projectId);
      const answers = await explorationApi.listGuidedAnswers(projectId);
      // 时序防护：用户快速切走 / 往返再进（代次变）时，丢弃过期回调，不写状态/DOM。
      if (seq !== guidedLoadSeq || location.hash !== startedHash) return;
      // 按 questionIndex 定点回填（防稀疏/乱序）；answers 已题位升序。
      const history = [];
      for (const row of answers) {
        history[row.questionIndex] = guidedAnswerFromBackend(row);
      }
      explorationHistory = history;
      // 进页翻页指针落在已答进度处（保持原型 explorationView=已答数语义）。
      explorationView = explorationHistory.length;
      guidedLoadState = "ready";
      renderExploration();
    } catch (err) {
      if (seq !== guidedLoadSeq || location.hash !== startedHash) return;
      // 401 已由 apiFetch 兜底（清 token + 跳登录），此处只会拿到非 401 的 ApiError。
      guidedLoadError = err;
      guidedLoadState = "error";
      renderExploration();
    }
  })();
}

function freeMessageFromBackend(row) {
  return { role: row.role, text: row.content };
}

function isCurrentFreeExploration(projectId, seq, startedHash) {
  return (
    seq === freeLoadSeq &&
    projectId === explorationProjectId &&
    location.hash === startedHash &&
    explorationEntryMode === "free"
  );
}

function loadFreeExploration(projectId) {
  teardownExplorationInflight();
  explorationProjectId = projectId;
  freeLoadState = "loading";
  freeLoadError = null;
  freeSettleErrorText = "";
  const seq = ++freeLoadSeq;
  const startedHash = location.hash;
  renderExploration();
  (async () => {
    try {
      await explorationApi.enter(projectId);
      const [messages, clues, guidance] = await Promise.all([
        explorationApi.listFreeMessages(projectId),
        explorationApi.listClues(projectId),
        explorationApi.getGuidance(projectId),
      ]);
      if (!isCurrentFreeExploration(projectId, seq, startedHash)) return;
      freeConversation = Array.isArray(messages)
        ? messages.map(freeMessageFromBackend)
        : [];
      freeClues = Array.isArray(clues) ? clues : [];
      applyGuidanceState(guidance);
      freeLoadState = "ready";
      renderExploration();
    } catch (err) {
      if (!isCurrentFreeExploration(projectId, seq, startedHash)) return;
      freeLoadError = err;
      freeLoadState = "error";
      renderExploration();
    }
  })();
}

// 把后端 GuidanceStateResponse（Story 2.8）写入前端导航态；currentField 变化即视为新一问，
// 清空上一问的按需思路列表，避免展示与新问题不匹配的旧建议。
function applyGuidanceState(state) {
  const nextField = (state && state.currentField) || null;
  if (nextField !== guidanceCurrentField) guidanceSuggestions = null;
  guidanceFields = (state && state.fields) || {};
  guidanceCurrentField = nextField;
  guidanceCurrentQuestion = (state && state.currentQuestion) || null;
  guidanceReadyToSettle = Boolean(state && state.readyToSettle);
}

function replaceFreeClue(updated) {
  const index = freeClues.findIndex((clue) => clue.id === updated.id);
  if (index === -1) freeClues.push(updated);
  else freeClues[index] = updated;
}

function replaceFreeClues(clues) {
  const next = Array.isArray(clues) ? clues : [];
  if (freeClueFocusedIds.size) {
    deferredFreeClues = next;
    return;
  }
  freeClues = next;
}

function applyDeferredFreeClues() {
  if (!deferredFreeClues || freeClueFocusedIds.size) return false;
  freeClues = deferredFreeClues;
  deferredFreeClues = null;
  return true;
}

function freePresetClue(clue) {
  const value = clue.value || "";
  const empty = !value;
  return `
    <div class="story-clue">
      <span>${escapeHtml(clue.label)}</span>
      <div class="story-clue-value${empty ? " is-empty" : ""}" contenteditable="true" role="textbox" aria-label="编辑${escapeHtml(clue.label)}" data-placeholder="尚未确定" data-free-clue-id="${escapeHtml(clue.id)}" data-free-clue-value="${escapeHtml(value)}">${escapeHtml(value || "尚未确定")}</div>
    </div>`;
}

function freeCustomClue(clue, index) {
  const id = clue.id ? escapeHtml(clue.id) : "";
  return `
    <div class="story-clue custom-story-clue" data-free-custom-index="${index}">
      <div class="custom-clue-head">
        <input value="${escapeHtml(clue.label || "")}" placeholder="设定名称" aria-label="自定义设定名称" data-free-custom-label="${index}" data-free-clue-id="${id}" />
        <button type="button" data-remove-free-custom-clue="${index}" aria-label="删除这项自定义设定">×</button>
      </div>
      <input class="custom-clue-value-input" value="${escapeHtml(clue.value || "")}" placeholder="描述这项设定……" aria-label="自定义设定描述" data-free-custom-value="${index}" data-free-clue-id="${id}" />
    </div>`;
}

function freeCustomDraftClue(draft, index) {
  const disabled = draft.creating ? "disabled" : "";
  return `
    <div class="story-clue custom-story-clue" data-free-draft-index="${index}">
      <div class="custom-clue-head">
        <input value="${escapeHtml(draft.label || "")}" placeholder="设定名称" aria-label="自定义设定名称" data-free-draft-label="${index}" ${disabled} />
        <button type="button" data-remove-free-draft="${index}" aria-label="删除这项自定义设定" ${disabled}>×</button>
      </div>
      <input class="custom-clue-value-input" value="${escapeHtml(draft.value || "")}" placeholder="描述这项设定……" aria-label="自定义设定描述" data-free-draft-value="${index}" ${disabled} />
    </div>`;
}

function freeErrorMarkup() {
  return freeSettleErrorText
    ? `<p class="guided-error" role="alert">${escapeHtml(freeSettleErrorText)}</p>`
    : "";
}

function showFreeInlineError(text) {
  const dialogue = document.querySelector(".explore-dialogue");
  if (!dialogue) return;
  let bar = dialogue.querySelector("[data-free-error]");
  if (!bar) {
    bar = document.createElement("p");
    bar.className = "guided-error";
    bar.setAttribute("data-free-error", "");
    bar.setAttribute("role", "alert");
    dialogue.prepend(bar);
  }
  bar.textContent = text;
}

async function syncFreeMessages(projectId, seq, startedHash) {
  const messages = await explorationApi.listFreeMessages(projectId);
  if (!isCurrentFreeExploration(projectId, seq, startedHash)) return false;
  freeConversation = Array.isArray(messages)
    ? messages.map(freeMessageFromBackend)
    : [];
  return true;
}

async function refreshFreeClues(projectId, seq, startedHash) {
  const clues = await explorationApi.refreshClues(projectId);
  if (!isCurrentFreeExploration(projectId, seq, startedHash)) return false;
  replaceFreeClues(clues);
  return true;
}

async function refreshGuidance(projectId, seq, startedHash) {
  const state = await explorationApi.getGuidance(projectId);
  if (!isCurrentFreeExploration(projectId, seq, startedHash)) return false;
  applyGuidanceState(state);
  return true;
}

// 零对话四入口（AC2/AC3）：点击后调 2.8 的开场问题生成能力，得到导航状态后转入常规
// 「当前具体问题 + 输入框」态。不调用 submitFreeMessage，本操作不产生对话消息。
async function startFreeGuidanceEntry(entry) {
  if (
    guidanceStartingEntry ||
    freeMessageSending ||
    !explorationProjectId ||
    !entry
  )
    return;
  const projectId = explorationProjectId;
  const seq = freeLoadSeq;
  const startedHash = location.hash;
  guidanceStartingEntry = entry;
  renderExploration();
  try {
    const state = await explorationApi.startGuidance(projectId, { entry });
    if (!isCurrentFreeExploration(projectId, seq, startedHash)) return;
    applyGuidanceState(state);
  } catch (err) {
    if (!isCurrentFreeExploration(projectId, seq, startedHash)) return;
    showFreeInlineError(explorationErrorText(err));
  } finally {
    if (!isCurrentFreeExploration(projectId, seq, startedHash)) return;
    guidanceStartingEntry = null;
    renderExploration();
  }
}

// 按需回答思路（AC4）：仅点击时请求，不随每轮自动生成。无当前问题时后端 400
// no_current_question——按中性提示处理，不视为异常错误态。
async function requestGuidanceSuggestions() {
  if (
    guidanceSuggestionsLoading ||
    freeMessageSending ||
    !explorationProjectId ||
    !guidanceCurrentQuestion
  )
    return;
  const projectId = explorationProjectId;
  const seq = freeLoadSeq;
  const startedHash = location.hash;
  guidanceSuggestionsLoading = true;
  renderExploration();
  try {
    const { suggestions } = await explorationApi.suggestGuidance(projectId);
    if (!isCurrentFreeExploration(projectId, seq, startedHash)) return;
    guidanceSuggestions = Array.isArray(suggestions) ? suggestions : [];
  } catch (err) {
    if (!isCurrentFreeExploration(projectId, seq, startedHash)) return;
    if (err && err.code === "no_current_question") {
      guidanceSuggestions = [];
    } else {
      showFreeInlineError(explorationErrorText(err));
    }
  } finally {
    if (!isCurrentFreeExploration(projectId, seq, startedHash)) return;
    guidanceSuggestionsLoading = false;
    renderExploration();
  }
}

// 跳过当前问题（AC4）：标记该字段 skipped，原地刷新导航状态（可能是下一问，也可能是收束
// 态）。不调用 submitFreeMessage、不新增对话消息。
async function skipFreeGuidanceQuestion() {
  if (
    guidanceSkipping ||
    freeMessageSending ||
    !explorationProjectId ||
    !guidanceCurrentQuestion
  )
    return;
  const projectId = explorationProjectId;
  const seq = freeLoadSeq;
  const startedHash = location.hash;
  guidanceSkipping = true;
  renderExploration();
  try {
    const state = await explorationApi.skipGuidance(projectId);
    if (!isCurrentFreeExploration(projectId, seq, startedHash)) return;
    applyGuidanceState(state);
  } catch (err) {
    if (!isCurrentFreeExploration(projectId, seq, startedHash)) return;
    if (err && err.code !== "no_current_question") {
      showFreeInlineError(explorationErrorText(err));
    }
  } finally {
    if (!isCurrentFreeExploration(projectId, seq, startedHash)) return;
    guidanceSkipping = false;
    renderExploration();
  }
}

async function submitFreeMessage(content) {
  const text = String(content || "").trim();
  if (!text || freeMessageSending || !explorationProjectId) return;
  const projectId = explorationProjectId;
  const seq = freeLoadSeq;
  const startedHash = location.hash;
  freeMessageSending = true;
  freeSettleErrorText = "";
  freeConversation = [...freeConversation, { role: "user", text }];
  freeMessageAbortController = new AbortController();
  const signal = freeMessageAbortController.signal;
  let gotTerminal = false;
  let streamError = null;
  let agentText = "";
  let keepEditingDom = false;
  renderExploration();
  try {
    await explorationApi.sendFreeMessage(
      projectId,
      { content: text },
      {
        signal,
        onEvent: (type, data) => {
          if (!isCurrentFreeExploration(projectId, seq, startedHash) || signal.aborted)
            return;
          if (type === "delta" && data && typeof data.text === "string") {
            agentText += data.text;
            const last = freeConversation[freeConversation.length - 1];
            if (last && last.role === "agent" && last.pending) last.text = agentText;
            else freeConversation = [...freeConversation, { role: "agent", text: agentText, pending: true }];
            if (!freeClueFocusedIds.size) renderExploration();
          } else if (type === "done" && data && typeof data.text === "string") {
            gotTerminal = true;
          } else if (type === "error") {
            gotTerminal = true;
            streamError = { code: data && data.code, message: data && data.message };
          }
        },
      },
    );
    if (!isCurrentFreeExploration(projectId, seq, startedHash) || signal.aborted) return;
    if (!gotTerminal) streamError = { code: "generate_failed" };
    if (!streamError) {
      const messagesSynced = await syncFreeMessages(projectId, seq, startedHash);
      if (!messagesSynced) return;
      const cluesRefreshed = await refreshFreeClues(projectId, seq, startedHash);
      if (!cluesRefreshed) return;
      // AC3 第 3 步：后端 stream_free_chat 已在落库后同步调用 guidance_agent.refresh_guidance，
      // 此处重新 GET 一次即可拿到本轮判定后的当前具体问题/完成度/就绪位。失败不影响本轮已
      // 成功的对话与线索（同后端「主链路成功、副作用降级」的容忍粒度），静默保留旧导航态。
      await refreshGuidance(projectId, seq, startedHash).catch(() => false);
      keepEditingDom = freeClueFocusedIds.size > 0;
    } else {
      await syncFreeMessages(projectId, seq, startedHash).catch(() => false);
    }
  } catch (err) {
    if (signal.aborted || !isCurrentFreeExploration(projectId, seq, startedHash)) return;
    streamError = err;
    await syncFreeMessages(projectId, seq, startedHash).catch(() => false);
  } finally {
    if (!isCurrentFreeExploration(projectId, seq, startedHash) || signal.aborted) return;
    freeMessageSending = false;
    freeMessageAbortController = null;
    if (!keepEditingDom) renderExploration();
    if (streamError) showFreeInlineError(explorationErrorText(streamError));
  }
}

async function updateFreeClue(clueId, value, label) {
  if (!clueId) return;
  const pending = freeClueEditingIds.get(clueId);
  if (pending) {
    pending.value = value;
    pending.label = label;
    pending.revision += 1;
    return;
  }
  const projectId = explorationProjectId;
  const seq = freeLoadSeq;
  const startedHash = location.hash;
  const request = { value, label, revision: 0 };
  freeClueEditingIds.set(clueId, request);
  try {
    while (true) {
      const revision = request.revision;
      const body = { value: String(request.value || ""), label: request.label };
      const updated = await explorationApi.editClue(projectId, clueId, body);
      if (!isCurrentFreeExploration(projectId, seq, startedHash)) return;
      replaceFreeClue(updated);
      if (request.revision === revision) {
        renderExploration();
        return;
      }
    }
  } catch (err) {
    if (!isCurrentFreeExploration(projectId, seq, startedHash)) return;
    renderExploration();
    showFreeInlineError(explorationErrorText(err));
  } finally {
    freeClueEditingIds.delete(clueId);
  }
}

async function createFreeCustomClue(draft) {
  const label = String(draft.label || "").trim();
  if (!label || draft.creating) return;
  const projectId = explorationProjectId;
  const seq = freeLoadSeq;
  const startedHash = location.hash;
  const submittedValue = String(draft.value || "");
  const submittedLabel = label;
  draft.creating = true;
  try {
    const created = await explorationApi.createCustomClue(projectId, {
      label: submittedLabel,
      value: submittedValue,
    });
    if (!isCurrentFreeExploration(projectId, seq, startedHash)) return;
    const index = customStoryClues.indexOf(draft);
    if (index !== -1) customStoryClues.splice(index, 1);
    replaceFreeClue(created);
    renderExploration();
  } catch (err) {
    if (!isCurrentFreeExploration(projectId, seq, startedHash)) return;
    draft.creating = false;
    renderExploration();
    showFreeInlineError(explorationErrorText(err));
  }
}

async function deleteFreeCustomClue(clueId) {
  if (!clueId) return;
  const projectId = explorationProjectId;
  const seq = freeLoadSeq;
  const startedHash = location.hash;
  try {
    await explorationApi.deleteClue(projectId, clueId);
    if (!isCurrentFreeExploration(projectId, seq, startedHash)) return;
    freeClues = freeClues.filter((clue) => clue.id !== clueId);
    renderExploration();
  } catch (err) {
    if (!isCurrentFreeExploration(projectId, seq, startedHash)) return;
    showFreeInlineError(explorationErrorText(err));
  }
}

async function startFreeSettleFlow() {
  if (freeSettlePending || !explorationProjectId) return;
  if (settleAbortController) settleAbortController.abort();
  const projectId = explorationProjectId;
  const seq = freeLoadSeq;
  const startedHash = location.hash;
  freeSettlePending = true;
  freeSettleErrorText = "";
  settleAbortController = new AbortController();
  const signal = settleAbortController.signal;
  let gotTerminal = false;
  renderExploration();
  try {
    const { taskId } = await explorationApi.settleFree(projectId);
    if (!isCurrentFreeExploration(projectId, seq, startedHash) || signal.aborted) return;
    await explorationApi.taskEvents(taskId, {
      signal,
      onEvent: (type, data) => {
        if (!isCurrentFreeExploration(projectId, seq, startedHash) || signal.aborted)
          return;
        if (type === "result" && data && data.profile) {
          gotTerminal = true;
          freeSettlePending = false;
          settleAbortController = null;
          openStoryProfileFromBackend(data.profile);
        } else if (type === "error") {
          gotTerminal = true;
          freeSettlePending = false;
          settleAbortController = null;
          freeSettleErrorText = explorationErrorText({ code: data && data.code });
          renderExploration();
        }
      },
    });
    if (
      isCurrentFreeExploration(projectId, seq, startedHash) &&
      !signal.aborted &&
      !gotTerminal
    ) {
      freeSettleErrorText = explorationErrorText({ code: "settle_failed" });
    }
  } catch (err) {
    if (!isCurrentFreeExploration(projectId, seq, startedHash) || signal.aborted)
      return;
    if (err && err.code === "exploration_not_ready") {
      await syncFreeMessages(projectId, seq, startedHash).catch(() => false);
    }
    freeSettleErrorText = explorationErrorText(err);
  } finally {
    if (!isCurrentFreeExploration(projectId, seq, startedHash) || signal.aborted)
      return;
    if (gotTerminal) return;
    freeSettlePending = false;
    settleAbortController = null;
    renderExploration();
  }
}

// 落库一条引导答案（选项 / 自述凝练结果通用）。幂等 upsert：同 questionIndex 覆盖。
// 返回 Promise，调用方据成功/失败推进或提示。questionIndex 用当前翻页位置 explorationView。
function persistGuidedAnswer({ questionIndex, question, answer, answerType }) {
  return explorationApi.saveGuidedAnswer(explorationProjectId, {
    questionIndex,
    question,
    answer,
    answerType,
  });
}

function currentExplorationQuestion() {
  // 返回当前题的完整对象（含 question / options / allowCustom）。
  // 需要题干字符串的调用点应取 .question，需要选项的取 .options。
  return (
    explorationQuestions[explorationView] || {
      question: "接下来，你最想把故事的哪一部分看得更清楚？",
      options: [],
    }
  );
}

// 引导探索提交一题答案（Story 7.5 接线）：分两条路径——
//   · 选项作答（submitGuidedOption）：不调 LLM，直接落库该选项 value。
//   · 自述作答（submitGuidedCustom）：先走 interpret 流式凝练，done 拿凝练答案再落库。
// 两者最终都进 commitGuidedAnswer 共用「乐观写前端 → 落库 → 推进 / 末题 settle」逻辑。
//
// 落库语义（受控决策 3）：先乐观写 explorationHistory[view] 让 UI 即时响应，再异步落库；
// 落库失败提示但保留前端答案（避免用户重打），下次操作或刷新会以后端为准。末题特殊：
// settle 需读到已落库答案，故末题落库成功后才触发 settle。

// 选项作答：question_index=当前翻页位置，answerType=option。
function submitGuidedOption(optionValue) {
  const answer = String(optionValue || "").trim();
  if (!answer || guidedAnswerSaving) return;
  commitGuidedAnswer(answer, "option");
}

// 自述作答：先 interpret 流式凝练（真实 Explorer Agent），done 后以凝练结果落库。
async function submitGuidedCustom(freeText) {
  const text = String(freeText || "").trim();
  if (!text || guidedAnswerSaving) return;
  const questionIndex = explorationView;
  const question = currentExplorationQuestion().question;
  // 锁定提交时的会话身份（review P1）：interpret 是真实 LLM、秒级在途，期间用户可能切走/
  // 新建/登出致 explorationProjectId + guidedLoadSeq 变更。回调完成后须校验未变才 commit，
  // 否则把旧作品答案写进新会话 + 砸当前页面（与 loadGuidedExploration 的 seq 校验同源）。
  const seq = guidedLoadSeq;
  const projectId = explorationProjectId;
  guidedAnswerSaving = true;
  // 在途 interpret 流控制器：切走/导航离开时 abort（P1/P2 统一清理会用到）。
  if (interpretAbortController) interpretAbortController.abort();
  interpretAbortController = new AbortController();
  const signal = interpretAbortController.signal;
  // 就地显「理解中」态：找当前自述表单的提交按钮，禁用 + 改文案（仿 7.3/7.4 按钮 loading）。
  const submitBtn = document.querySelector(
    "[data-guided-custom-form] button[type=submit]",
  );
  const originalLabel = submitBtn ? submitBtn.innerHTML : "";
  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.textContent = "理解中…";
  }
  let interpreted = "";
  let streamError = null;
  try {
    await explorationApi.interpretGuided(
      projectId,
      { question, freeText: text },
      {
        signal,
        onEvent: (type, data) => {
          if (type === "delta" && data && data.text) {
            interpreted += data.text;
          } else if (type === "done" && data && typeof data.text === "string") {
            interpreted = data.text;
          } else if (type === "error") {
            // 流内业务错误（如 quota_exceeded / generate_failed）：记下，流结束后统一提示。
            streamError = new ApiError(
              data && data.code,
              data && data.message,
              undefined,
              undefined,
            );
          }
        },
      },
    );
  } catch (err) {
    // 用户主动 abort（切走/导航）：静默退出，不提示、不 commit、不复位 saving（由清理路径统一处理）。
    if (signal.aborted || (err && err.name === "AbortError")) return;
    // 建流前错误（预检 429/404/…）或网络中断：转可读提示。401 已由 apiStream 兜底跳登录。
    streamError = err;
  }
  // 会话已切换（切走/新建/登出）：丢弃本次结果，不写入已变更的会话态、不砸新页面（review P1）。
  if (signal.aborted || seq !== guidedLoadSeq || projectId !== explorationProjectId) {
    return;
  }
  guidedAnswerSaving = false;
  if (streamError) {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.innerHTML = originalLabel;
    }
    showGuidedInlineError(explorationErrorText(streamError));
    return;
  }
  const answer = interpreted.trim();
  if (!answer) {
    // 空产兜底（后端一般已发 generate_failed，此为双保险）。
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.innerHTML = originalLabel;
    }
    showGuidedInlineError("没能理解这句话，请换个说法再试。");
    return;
  }
  interpretAbortController = null;
  commitGuidedAnswer(answer, "custom", questionIndex);
}

// 共用：乐观写前端 + 落库 + 推进（末题触发 settle）。
// questionIndexOverride 供自述路径传入（异步期间 explorationView 可能已变，锁定提交时的题位）。
function commitGuidedAnswer(answer, answerType, questionIndexOverride) {
  const questionIndex =
    questionIndexOverride === undefined ? explorationView : questionIndexOverride;
  const question =
    explorationQuestions[questionIndex]?.question ||
    currentExplorationQuestion().question;
  const wasAnswered = questionIndex < explorationHistory.length;
  // 乐观写：即时反映到 UI（翻页高亮 / 收尾态）。
  explorationHistory[questionIndex] = { question, answer };
  const isLastQuestion = questionIndex >= explorationQuestions.length - 1;

  if (isLastQuestion) {
    // 末题：先落库（settle 需读到），成功后进整理中过渡 + 触发 settle SSE。
    explorationView = explorationQuestions.length;
    guidedSettling = true;
    settleErrorText = "";
    renderExploration();
    guidedAnswerSaving = true;
    (async () => {
      try {
        await persistGuidedAnswer({
          questionIndex,
          question,
          answer,
          answerType,
        });
        guidedAnswerSaving = false;
        startSettleFlow();
      } catch (err) {
        // 末题落库失败：退出整理中过渡，回收尾态提示重试（不触发 settle）。
        guidedAnswerSaving = false;
        guidedSettling = false;
        settleErrorText = explorationErrorText(err);
        renderExploration();
      }
    })();
    return;
  }

  // 非末题：翻回旧题重选后前进到「已答进度」的下一题；否则前进一题。
  explorationView = wasAnswered
    ? explorationView + 1
    : explorationHistory.length;
  renderExploration();
  // 异步落库（fire-and-forget，非阻塞 UI）：失败仅提示，保留前端答案（受控决策 3）。
  // review P4：非末题落库**不设 guidedAnswerSaving**——该标志仅用于「自述 interpret 在途」
  // 与「末题 settle 落库在途」这两个真需互斥的场景；若非末题落库也占用它（一个 RTT），
  // 会误伤用户对下一题的正常点击（renderExploration 已推进到下一题）。选项落库幂等 upsert
  // （后端 (session_id, question_index) 复合唯一），连点/乱序各写各题位、无害。
  persistGuidedAnswer({ questionIndex, question, answer, answerType }).catch(
    (err) => {
      showGuidedInlineError(explorationErrorText(err));
    },
  );
}

// settle SSE 流：POST settle 拿 taskId → GET /tasks/{id}/events 消费 progress/result/error。
// progress 驱动整理中过渡（本 V1 保持文案态，不显数字）；result 关过渡 + 弹真实设定卡；
// error 退回收尾态提示重试。abort（回到探索/切走）时干净退出。
async function startSettleFlow() {
  // 取消上一个在途 settle（重复触发防御），新建控制器。
  if (settleAbortController) settleAbortController.abort();
  settleAbortController = new AbortController();
  const signal = settleAbortController.signal;
  // 锁定会话身份（review P2）：settle 期间用户切走/进别的项目时，result/error 不该
  // 弹卡或砸到新页面（跨项目污染）。回调与收尾都校验 seq/projectId 未变。
  const seq = guidedLoadSeq;
  const projectId = explorationProjectId;
  const stale = () =>
    signal.aborted || seq !== guidedLoadSeq || projectId !== explorationProjectId;
  let gotTerminal = false; // 是否收到 result/error 终态（review P5：无终态兜底判据）
  try {
    const { taskId } = await explorationApi.settleGuided(projectId);
    if (stale()) return;
    await explorationApi.taskEvents(taskId, {
      signal,
      onEvent: (type, data) => {
        if (stale()) return;
        if (type === "result" && data && data.profile) {
          gotTerminal = true;
          guidedSettling = false;
          settleAbortController = null;
          openStoryProfileFromBackend(data.profile);
        } else if (type === "error") {
          gotTerminal = true;
          guidedSettling = false;
          settleAbortController = null;
          settleErrorText = explorationErrorText({
            code: data && data.code,
          });
          renderExploration();
        }
        // progress：整理中过渡已在显示，V1 不额外更新（保持文案态）。
      },
    });
    // review P5：SSE 流正常结束（await 返回）却没收到 result/error 终态——后端漏发终态 /
    // result 里 profile 缺失（if 判据不满足未置 gotTerminal）/ 只发 progress 就断。此时若不
    // 兜底，guidedSettling 永远为 true、UI 永久卡「整理中」spinner。视作失败退回收尾态可重试。
    if (!stale() && !gotTerminal && guidedSettling) {
      guidedSettling = false;
      settleAbortController = null;
      settleErrorText = explorationErrorText({ code: "settle_failed" });
      renderExploration();
    }
  } catch (err) {
    if (stale()) return; // 用户主动 abort / 已切走，不报错、不砸新页面
    guidedSettling = false;
    settleAbortController = null;
    settleErrorText = explorationErrorText(err);
    renderExploration();
  }
}

// 引导页内联错误提示：在引导 stage 顶部插一条错误条（无遮挡、可被下次渲染清除）。
function showGuidedInlineError(text) {
  const stage = document.querySelector(".guided-stage");
  if (!stage) {
    window.alert(text);
    return;
  }
  let bar = stage.querySelector("[data-guided-error]");
  if (!bar) {
    bar = document.createElement("p");
    bar.className = "guided-error";
    bar.setAttribute("data-guided-error", "");
    bar.setAttribute("role", "alert");
    stage.prepend(bar);
  }
  bar.textContent = text;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function collectStoryDraft() {
  const readClue = (label) => {
    const value = document
      .querySelector(`[aria-label="编辑${label}"]`)
      ?.textContent.trim();
    return value === "尚未确定" ? "" : value || "";
  };
  return {
    opening: readClue("最初的念头"),
    protagonist: readClue("主角"),
    conflict: readClue("核心冲突"),
    atmosphere: readClue("世界与氛围"),
    custom: customStoryClues.filter((clue) => clue.label || clue.value),
  };
}

function buildFinalStoryProfile(draft) {
  const opening = draft.opening || "一个尚待展开的故事念头";
  const protagonist = draft.protagonist || "一位被异常事件推离原有生活的人";
  const conflict = draft.conflict || "主角必须在欲望与代价之间做出选择";
  const atmosphere = draft.atmosphere || "克制、悬而未决，并保留逐步揭示的空间";
  const fields = [
    {
      label: "一句话构想",
      value: `${opening}，并在追寻答案的过程中面对${conflict}。`,
      added: true,
    },
    {
      label: "故事概述",
      value: `故事从“${opening}”展开。${protagonist}被卷入其中，随着线索逐渐显现，${conflict}。故事将以人物选择推动情节，而不是一次性解释全部真相。`,
      added: true,
    },
    { label: "主角", value: protagonist, added: !draft.protagonist },
    { label: "核心冲突", value: conflict, added: !draft.conflict },
    { label: "世界与氛围", value: atmosphere, added: !draft.atmosphere },
    {
      label: "叙事风格",
      value: "以人物视角推进，保持细节感与悬念，让设定通过行动和选择自然显现。",
      added: true,
    },
  ];
  draft.custom.forEach((clue) =>
    fields.push({
      label: clue.label || "自定义设定",
      value: clue.value || "尚待补充",
      added: false,
    }),
  );
  return fields;
}

// Story 7.5：把后端 settle result 的 12 字段候选卡（StoryProfileCard，camelCase）转成
// 设定卡对话框渲染用的 [{label, value}] 结构。主干 7 恒显（缺料后端为空串）；题材特化 4
// 按值非空显（后端按 genre 激活、不匹配为 null）；⑫ 文风锚点非空才显。字段顺序对齐
// [[project_muse_setting_fields]] 的 ①-⑫ 编号。本 story emit-only 展示，不含 revision。
const PROFILE_FIELD_LABELS = [
  ["genre", "题材"],
  ["coreAppeal", "核心吸引力"],
  ["protagonist", "主角"],
  ["mainConflict", "主要冲突"],
  ["worldRules", "关键世界规则"],
  ["overallTone", "整体气质"],
  ["openingHook", "开篇钩子"],
  ["powerSystem", "力量体系"],
  ["goldenFinger", "金手指"],
  ["romanceLine", "感情线"],
  ["factionLandscape", "势力格局"],
  ["styleProfile", "文风锚点"],
];
// 主干 7 字段 key（恒显，即使空串也占位，让用户知道该项待补）。
const PROFILE_TRUNK_KEYS = new Set([
  "genre",
  "coreAppeal",
  "protagonist",
  "mainConflict",
  "worldRules",
  "overallTone",
  "openingHook",
]);

function buildProfileFromBackend(profile) {
  const fields = [];
  for (const [key, label] of PROFILE_FIELD_LABELS) {
    const raw = profile ? profile[key] : undefined;
    const value = typeof raw === "string" ? raw.trim() : "";
    if (PROFILE_TRUNK_KEYS.has(key)) {
      // 主干恒显：空串回落占位文案，提示这项还没聊清楚。
      fields.push({ label, value: value || "（尚未聊到，可继续补充）", added: false });
    } else if (value) {
      // 题材特化 + 文风锚点：仅在后端给了非空值时显（按 genre 激活 / 已锚定文风）。
      fields.push({ label, value, added: false });
    }
  }
  return fields;
}

// 用后端真实候选卡弹出设定卡（替换 mock 的 openStoryProfileDialog 走 buildFinalStoryProfile）。
// 会话内恢复用（AC7）：写 finalStoryProfile + pending 态 + persist 到 sessionStorage。
function openStoryProfileFromBackend(profile) {
  finalStoryProfile = buildProfileFromBackend(profile);
  // signature 用后端 profile 序列化，标识「这份候选卡」；恢复时据此判定是否同一份。
  finalStoryProfileSignature = JSON.stringify(profile);
  finalStoryProfileRevision = 1;
  pendingStoryProfile = true;
  lastProfileChangedFields = [];
  profileFeedbackStatus = "";
  persistPendingStoryProfile();
  mountStoryProfileDialog();
}

function storyProfileDialogMarkup() {
  const items = finalStoryProfile
    .map(
      (
        field,
        index,
      ) => `<section class="profile-result-item ${lastProfileChangedFields.includes(index) ? "is-updated" : ""}">
        <div class="profile-result-label"><span>${String(index + 1).padStart(2, "0")} / ${escapeHtml(field.label)}</span></div>
        <div contenteditable="true" role="textbox" aria-label="编辑${escapeHtml(field.label)}" data-final-profile-field="${index}">${escapeHtml(field.value)}</div>
      </section>`,
    )
    .join("");
  return `<div class="profile-dialog-backdrop">
    <section class="profile-dialog" role="dialog" aria-modal="true" aria-labelledby="profile-dialog-title">
      <header class="profile-dialog-head">
        <div><span>Story profile / v${finalStoryProfileRevision}</span><h2 id="profile-dialog-title">确认故事设定</h2><p>直接编辑设定，或者告诉 Agent 你希望怎样调整。确认后将进入第一章创作。</p></div>
      </header>
      <div class="profile-dialog-body">${items}</div>
      <footer class="profile-dialog-actions">
        <form class="profile-feedback" data-profile-feedback>
          <div class="profile-feedback-copy"><strong>你想调整什么？</strong></div>
          <textarea aria-label="反馈给探索 Agent" placeholder="例如：主角可以更自私一些，但不要让他成为反派。" required></textarea>
          <div class="profile-feedback-submit"><p data-profile-feedback-status aria-live="polite">${escapeHtml(profileFeedbackStatus)}</p><button type="submit">调整</button></div>
        </form>
        <div class="profile-confirm-row"><p data-profile-confirm-note>确认后，这份设定将成为后续故事创作的依据。</p><div class="profile-confirm-actions"><button type="button" data-request-profile-return>回到探索页面</button><button class="primary-button" type="button" data-confirm-profile>确认故事设定 <span>→</span></button></div></div>
        <div class="profile-return-confirm" data-profile-return-confirm hidden><section class="profile-return-panel" role="alertdialog" aria-modal="true" aria-labelledby="profile-return-title"><h3 id="profile-return-title">回到探索页面？</h3><p>返回后，当前设定内容和修改记录都会丢失。</p><div><button type="button" data-cancel-profile-return>取消</button><button class="danger-button" type="button" data-confirm-profile-return>确定返回</button></div></section></div>
      </footer>
    </section>
  </div>`;
}

function closeStoryProfileDialog() {
  document.querySelector(".profile-dialog-backdrop")?.remove();
  document.body.classList.remove("dialog-open");
}

function discardStoryProfileAndReturn() {
  finalStoryProfile = null;
  finalStoryProfileSignature = "";
  finalStoryProfileRevision = 1;
  pendingStoryProfile = false;
  lastProfileChangedFields = [];
  profileFeedbackStatus = "";
  // 复位“整理中”过渡态：否则回到探索页会卡在整理动画上（弹窗由末题触发时留下的态）。
  guidedSettling = false;
  // Story 7.5：abort 在途 settle SSE（若还在整理中被点回到探索）。settle 任务 emit-only
  // 无落库副作用（后端 worker 不写 story_bible），前端丢弃 taskId + 断流即可，不调后端
  // 丢弃端点（已确认设定的真实丢弃 FR15 归 7.7）。
  if (settleAbortController) {
    settleAbortController.abort();
    settleAbortController = null;
  }
  settleErrorText = "";
  clearPendingStoryProfile();
  closeStoryProfileDialog();
  // 回到探索页需重新渲染，回到正常问答界面（收尾态：可翻页修改、可再次整理）。
  renderExploration();
}

function confirmStoryProfileAndEnterChapter() {
  // 确认故事设定：保留已确认设定（归档页与章节上下文依赖）。
  // 阶段规划改为幕后逻辑，确认后直接进入第一章创作，不再展示阶段规划问答页。
  confirmedStoryProfile = finalStoryProfile.map((field) => ({ ...field }));
  window.sessionStorage.setItem(
    confirmedStoryProfileKey,
    JSON.stringify(confirmedStoryProfile),
  );
  // 幕后生成阶段计划，供章节创作页使用；用户看不到这一过程。
  if (!currentStagePlan) currentStagePlan = buildCurrentStagePlan();
  explorationMode = "profile";
  window.sessionStorage.removeItem(explorationModeKey);
  pendingStoryProfile = false;
  clearPendingStoryProfile();
  // 确保第一章从头开始渲染
  chapterCreationState = "input";
  chapterIdea = "";
  closeStoryProfileDialog();
  location.hash = "#/projects/demo/chapters/1";
}

function openStoryProfileDialog({ regenerate = false } = {}) {
  const draft = collectStoryDraft();
  const signature = JSON.stringify(draft);
  if (
    regenerate ||
    !finalStoryProfile ||
    signature !== finalStoryProfileSignature
  ) {
    if (regenerate) finalStoryProfileRevision += 1;
    finalStoryProfile = buildFinalStoryProfile(draft);
    finalStoryProfileSignature = signature;
  }
  pendingStoryProfile = true;
  lastProfileChangedFields = [];
  profileFeedbackStatus = "";
  persistPendingStoryProfile();
  mountStoryProfileDialog();
}

function mountStoryProfileDialog() {
  closeStoryProfileDialog();
  app.insertAdjacentHTML("beforeend", storyProfileDialogMarkup());
  document.body.classList.add("dialog-open");
  bindStoryProfileDialogInteractions();
}

function applyStoryProfileFeedback(feedback) {
  const changed = new Set([1]);
  const includesAny = (...keywords) =>
    keywords.some((keyword) => feedback.includes(keyword));

  if (includesAny("主角", "人物", "自私", "性格", "动机")) {
    changed.add(2);
    finalStoryProfile[2].value = `${finalStoryProfile[2].value} 他会优先保护自己的记忆与利益，但仍保留不愿伤害无辜者的底线。`;
  }
  if (includesAny("冲突", "代价", "悬念", "危险")) {
    changed.add(3);
    finalStoryProfile[3].value = `${finalStoryProfile[3].value} 每一次推进都会带来更具体、且无法轻易撤销的代价。`;
  }
  if (includesAny("世界", "城市", "规则", "氛围")) {
    changed.add(4);
    finalStoryProfile[4].value = `${finalStoryProfile[4].value} 世界规则会先通过反常细节显现，再逐步揭露其边界。`;
  }
  if (includesAny("风格", "节奏", "克制", "视角")) {
    changed.add(5);
    finalStoryProfile[5].value =
      "以人物视角缓慢逼近真相，减少直接解释，让冲突通过选择、停顿与细节自然显现。";
  }
  if (changed.size === 1) {
    changed.add(5);
    finalStoryProfile[5].value =
      "保持人物选择的主动性，让新的调整方向通过场景与行动逐步显现。";
  }

  finalStoryProfile[1].value = `${finalStoryProfile[1].value} 新一轮修订会进一步强化人物选择与故事代价之间的联系。`;
  return [...changed];
}

function bindStoryProfileDialogInteractions() {
  document.querySelectorAll("[data-final-profile-field]").forEach((field) => {
    field.addEventListener("input", () => {
      finalStoryProfile[Number(field.dataset.finalProfileField)].value =
        field.textContent.trim();
      persistPendingStoryProfile();
    });
  });
  document
    .querySelector("[data-profile-feedback]")
    ?.addEventListener("submit", (event) => {
      event.preventDefault();
      const textarea = event.currentTarget.querySelector("textarea");
      const feedback = textarea.value.trim();
      if (!feedback) return;
      const button = event.currentTarget.querySelector("button");
      button.disabled = true;
      button.textContent = "调整中…";
      window.setTimeout(() => {
        lastProfileChangedFields = applyStoryProfileFeedback(feedback);
        finalStoryProfileRevision += 1;
        profileFeedbackStatus = `已根据反馈更新 ${lastProfileChangedFields.length} 项设定。`;
        persistPendingStoryProfile();
        mountStoryProfileDialog();
      }, 520);
    });
  document
    .querySelector("[data-request-profile-return]")
    ?.addEventListener("click", () => {
      const confirmation = document.querySelector(
        "[data-profile-return-confirm]",
      );
      confirmation.hidden = false;
      confirmation.querySelector("[data-cancel-profile-return]").focus();
    });
  document
    .querySelector("[data-cancel-profile-return]")
    ?.addEventListener("click", () => {
      document.querySelector("[data-profile-return-confirm]").hidden = true;
      document.querySelector("[data-request-profile-return]").focus();
    });
  document
    .querySelector("[data-confirm-profile-return]")
    ?.addEventListener("click", discardStoryProfileAndReturn);
  document
    .querySelector("[data-confirm-profile]")
    ?.addEventListener("click", (event) => {
      event.currentTarget.disabled = true;
      event.currentTarget.querySelector("span").textContent = "✓";
      document.querySelector("[data-profile-confirm-note]").textContent =
        "故事设定已确认，正在进入第一章创作。";
      window.setTimeout(confirmStoryProfileAndEnterChapter, 420);
    });
}

function confirmedStoryProfileReference() {
  return `<details class="confirmed-profile-reference">
    <summary><span>查看已确认的故事设定</span><i>＋</i></summary>
    <div>${confirmedStoryProfile
      .map(
        (field) =>
          `<section><span>${escapeHtml(field.label)}</span><p>${escapeHtml(field.value)}</p></section>`,
      )
      .join("")}</div>
  </details>`;
}

function buildCurrentStagePlan() {
  const countMatch = stagePlanningDraft.chapters.match(/\d+/);
  const chapterCount = Math.min(7, Math.max(3, Number(countMatch?.[0]) || 5));
  const templates = [
    {
      title: "打破日常",
      brief:
        stagePlanningDraft.opening ||
        "一件无法忽视的意外把主角从原有生活中拖出来。",
    },
    {
      title: "不存在的证明",
      brief:
        stagePlanningDraft.conflict ||
        "主角第一次试图证明异常，却发现所有证据都在否定他的记忆。",
    },
    {
      title: "代价显现",
      brief:
        stagePlanningDraft.events ||
        "追查开始产生真实代价，主角必须在自保和继续前进之间选择。",
    },
    {
      title: "立场转折",
      brief: "新的线索改变主角对同伴和敌人的判断，迫使他重新选择立场。",
    },
    {
      title: "无法回头的选择",
      brief:
        stagePlanningDraft.goal ||
        "主角作出不可撤销的决定，完成本阶段最重要的状态变化。",
    },
    {
      title: "余波",
      brief: "阶段冲突暂时收束，同时留下足以推动下一阶段的新问题。",
    },
    {
      title: "新的方向",
      brief: "人物带着本阶段的后果走向下一段故事，并显露新的目标。",
    },
  ];
  return {
    goal: stagePlanningDraft.goal,
    conflict: stagePlanningDraft.conflict,
    chapters: templates.slice(0, chapterCount),
  };
}

function renderExploration() {
  // 阶段规划已全程幕后化：即使 sessionStorage 残留旧的 "stage" 值也归位到 profile，
  // 不再存在独立的阶段规划问答页。
  if (explorationMode === "stage") {
    explorationMode = "profile";
    window.sessionStorage.removeItem(explorationModeKey);
  }
  const isGuided = explorationEntryMode !== "free";
  // answeredCount 决定翻页边界；是否“收尾态”由翻页位置决定：
  // 只有翻到最后一题之后的虚拟页（view === 题数）才算完成，避免全答完就把最后一题锁成无法回退的死屏。
  const answeredCount = explorationHistory.length;
  const guidedComplete = explorationView >= explorationQuestions.length;
  const currentQuestionObj = currentExplorationQuestion();

  let mainContent;
  let storyForming = ""; // 引导模式不输出右侧侧边栏；仅自由模式在下方 else 分支构造
  if (isGuided) {
    // Story 7.5：进页建会话 + 回填答案的加载态优先（error 态在 pending 卡恢复时不触发）。
    if (guidedLoadState === "loading") {
      mainContent = `
        <section class="explore-dialogue guided-dialogue" aria-labelledby="explore-title">
          <h1 id="explore-title" class="visually-hidden">引导探索</h1>
          <div class="guided-stage">
            <div class="guided-current" role="status" aria-live="polite">
              <span class="guided-settling-spinner" aria-hidden="true"></span>
              <p class="guided-question">正在准备你的引导探索……</p>
            </div>
          </div>
        </section>`;
    } else if (guidedLoadState === "error") {
      const errText = escapeHtml(explorationErrorText(guidedLoadError));
      mainContent = `
        <section class="explore-dialogue guided-dialogue" aria-labelledby="explore-title">
          <h1 id="explore-title" class="visually-hidden">引导探索</h1>
          <div class="guided-stage">
            <div class="guided-current">
              <p class="guided-question">没能载入引导探索</p>
              <p class="guided-complete-hint">${errText}</p>
            </div>
            <div class="guided-complete-actions">
              <button class="primary-button" type="button" data-guided-reload>重新加载 <span>→</span></button>
            </div>
          </div>
        </section>`;
    } else {
    // 引导探索：纯选项式沉浸问答。用户只点选项（第一题可自述一句话），
    // 一次只聚焦一题，不显示已答历史，也不显示右侧故事线索侧边栏。
    const totalLabel = String(explorationQuestions.length).padStart(2, "0");
    // 底部翻页栏：普通问答态可前后翻页；收尾态提供单独“上一题”回到最后一题；
    // 整理中过渡态不允许翻页，不出栏。位置由 guided-footer-nav 吸附到页面底部。
    let toolbar = "";
    const backBtn = `<button class="guided-nav guided-back" type="button" data-guided-back>← 上一题</button>`;
    const spacer = `<span class="guided-nav-placeholder" aria-hidden="true"></span>`;
    if (guidedSettling) {
      // 整理中过渡态优先：不出任何翻页栏（此时 view 已在收尾页，需避免误命中收尾分支）。
      toolbar = "";
    } else if (guidedComplete) {
      toolbar = `<div class="guided-toolbar">${backBtn}${spacer}</div>`;
    } else {
      const canPrev = explorationView > 0;
      const canNext = explorationView < answeredCount;
      if (canPrev || canNext) {
        const nextBtn = `<button class="guided-nav guided-next" type="button" data-guided-next>下一题 →</button>`;
        toolbar = `<div class="guided-toolbar">${canPrev ? backBtn : spacer}${canNext ? nextBtn : spacer}</div>`;
      }
    }
    let stageInner;
    if (guidedSettling) {
      // 答完最后一题后的“整理中”过渡态：遮住后台生成设定的等待。
      stageInner = `
        <div class="guided-current guided-settling" role="status" aria-live="polite">
          <span class="guided-settling-spinner" aria-hidden="true"></span>
          <p class="guided-question">正在把你的回答整理成一份故事设定……</p>
          <p class="guided-complete-hint">读了你在意的画面、人物与冲突，稍等片刻。</p>
        </div>`;
    } else if (guidedComplete) {
      // 收尾态（翻到最后一题之后的虚拟页）：能整理为故事设定；“上一题”由底部翻页栏承载。
      // Story 7.5：settle 失败时在此显重试提示（settleErrorText）。
      const settleHint = settleErrorText
        ? `<p class="guided-error" role="alert">${escapeHtml(settleErrorText)}</p>`
        : "";
      stageInner = `
        <div class="guided-current is-complete">
          <span class="guided-progress">引导完成 · ${totalLabel} / ${totalLabel}</span>
          <p class="guided-question">这些问题已经把故事的骨架照亮了。</p>
          <p class="guided-complete-hint">如果想修改，可以回到上一题重新选择；准备好了就整理成一份故事设定。</p>
        </div>
        ${settleHint}
        <div class="guided-complete-actions">
          <button class="primary-button guided-finish" type="button" data-guided-finish>整理为故事设定 <span>→</span></button>
        </div>`;
    } else {
      const options = Array.isArray(currentQuestionObj.options)
        ? currentQuestionObj.options
        : [];
      // 翻回已答题时高亮上次所选：按已存答案的 value 匹配当前题的选项。
      const savedAnswer = explorationHistory[explorationView]?.answer || "";
      // 选项卡片：显示短标签 + 完整答案说明，点选即提交本题答案。
      const optionCards = options
        .map((option, index) => {
          const isChosen = savedAnswer && option.value === savedAnswer;
          return `<button class="guided-option${isChosen ? " is-chosen" : ""}" type="button" data-guided-option="${index}"${isChosen ? ' aria-pressed="true"' : ""}>
            <span class="guided-option-index">${String.fromCharCode(65 + index)}</span>
            <span class="guided-option-body"><strong>${escapeHtml(option.label)}</strong><span>${escapeHtml(option.value)}</span></span>
            <span class="guided-option-arrow" aria-hidden="true">${isChosen ? "✓" : "→"}</span>
          </button>`;
        })
        .join("");
      // 第一题（allowCustom）：常驻自述输入框，不必点“都不是”即可看到。
      // 翻回第一题且上次是自述作答（答案不匹配任何选项）时，回填上次输入。
      const savedIsCustom =
        savedAnswer && !options.some((option) => option.value === savedAnswer);
      const customValue = savedIsCustom ? escapeHtml(savedAnswer) : "";
      // 第二题起：折叠的“都不是这些？”出口，点击后就地展开一句话自答。
      const escapeExit = currentQuestionObj.allowCustom
        ? `<form class="guided-custom guided-custom--own" data-guided-custom-form>
            <label for="guided-custom-input">或者，用一句话说出你的念头</label>
            <div class="guided-custom-row">
              <input id="guided-custom-input" type="text" data-guided-custom-input value="${customValue}" placeholder="把此刻脑中最清楚的一点写下来……" autocomplete="off" />
              <button class="primary-button" type="submit">确认 <span>→</span></button>
            </div>
          </form>`
        : `<div class="guided-escape">
            <button class="guided-none-toggle" type="button" data-guided-none-toggle>都不是这些？用一句话自己回答</button>
            <form class="guided-custom guided-custom--none" data-guided-custom-form ${savedIsCustom ? "" : "hidden"}>
              <div class="guided-custom-row">
                <input type="text" data-guided-custom-input value="${customValue}" placeholder="用一句话回答这个问题……" autocomplete="off" />
                <button class="primary-button" type="submit">确认 <span>→</span></button>
              </div>
            </form>
          </div>`;
      stageInner = `
        <div class="guided-current">
          <span class="guided-progress">引导探索 · 问题 ${String(explorationView + 1).padStart(2, "0")} / ${totalLabel}</span>
          <p class="guided-question">${escapeHtml(currentQuestionObj.question)}</p>
        </div>
        <div class="guided-options" role="group" aria-label="选择一个答案">${optionCards}</div>
        ${escapeExit}`;
    }
    mainContent = `
      <section class="explore-dialogue guided-dialogue" aria-labelledby="explore-title">
        <h1 id="explore-title" class="visually-hidden">引导探索</h1>
        <div class="guided-stage">
          ${stageInner}
        </div>
        ${toolbar ? `<div class="guided-footer-nav">${toolbar}</div>` : ""}
      </section>`;
    } // 结束 guidedLoadState ready 分支（Story 7.5）
  } else if (freeLoadState === "loading") {
    mainContent = `
      <section class="explore-dialogue" aria-labelledby="explore-title">
        <h1 id="explore-title" class="visually-hidden">自由探索</h1>
        <div class="guided-stage"><div class="guided-current" role="status" aria-live="polite"><span class="guided-settling-spinner" aria-hidden="true"></span><p class="guided-question">正在准备你的自由探索……</p></div></div>
      </section>`;
  } else if (freeLoadState === "error") {
    mainContent = `
      <section class="explore-dialogue" aria-labelledby="explore-title">
        <h1 id="explore-title" class="visually-hidden">自由探索</h1>
        <div class="guided-stage"><div class="guided-current"><p class="guided-question">没能载入自由探索</p><p class="guided-complete-hint">${escapeHtml(explorationErrorText(freeLoadError))}</p></div><div class="guided-complete-actions"><button class="primary-button" type="button" data-free-reload>重新加载 <span>→</span></button></div></div>
      </section>`;
  } else {
    const hasConversation = freeConversation.length > 0;
    // 零对话起点（AC2）：无对话且导航状态尚无 currentQuestion 时展示四个固定入口；
    // 点击 startGuidance 生成开场问题后即使仍无对话消息，也按「已开始」渲染当前问题 + 常规输入框
    // （幂等重放/刷新恢复见 loadFreeExploration→applyGuidanceState）。
    const showEntryPoints = !hasConversation && !guidanceCurrentQuestion;
    const missingFieldCount = Object.values(guidanceFields).filter(
      (status) => status === "missing",
    ).length;
    const canFinish = !freeMessageSending && guidanceReadyToSettle;
    const formingHint = canFinish
      ? "7 项设定主干已经齐备，可以整理成一份故事设定。"
      : missingFieldCount > 0
        ? `还差 ${missingFieldCount} 项设定主干，继续和 Agent 讨论就能整理为故事设定。`
        : "继续和 Agent 讨论，线索足够时就能整理为故事设定。";
    const presetClues = freeClues
      .filter((clue) => clue.kind === "preset")
      .sort((a, b) => a.displayOrder - b.displayOrder)
      .map(freePresetClue)
      .join("");
    const customClues = freeClues
      .filter((clue) => clue.kind === "custom")
      .map(freeCustomClue)
      .join("");
    const customDrafts = customStoryClues.map(freeCustomDraftClue).join("");
    storyForming = `
    <aside class="story-forming" aria-labelledby="story-forming-title">
      <div class="story-forming-head"><div><span>Living notes / draft</span><h2 id="story-forming-title">美好的故事即将展开</h2></div><strong>01</strong></div>
      <p class="story-forming-intro">Agent 会根据对话整理线索。这里的内容由你决定，也可以直接修改。</p>
      <div class="story-clues">
        ${presetClues}
        ${customClues}
        ${customDrafts}
        <button class="add-story-clue" type="button" data-add-free-custom-clue><span>＋</span> 添加自定义设定</button>
      </div>
      <div class="forming-footer">
        ${freeErrorMarkup()}
        <p>${freeSettlePending ? "正在整理你的故事线索……" : formingHint}</p>
        <button class="finish-exploration" type="button" ${canFinish && !freeSettlePending ? "" : "disabled"}>整理为故事设定 <span>→</span></button>
      </div>
    </aside>`;
    const freeMessages = freeConversation
      .map(
        (entry) => `<article class="conversation-message ${entry.role === "agent" ? "agent-message" : "user-message"}">
          <div class="message-meta"><span>${entry.role === "agent" ? "Agent / 自由讨论" : "你"}</span></div>
          <p>${escapeHtml(entry.text)}</p>
        </article>`,
      )
      .join("");
    // 四个产品固定入口（AC2，不得渲染成/命名为 AI 建议）：entry key 对齐后端
    // GuidanceStartRequest.entry 的 Literal 取值。
    const entryPoints = [
      ["story_idea", "故事想法"],
      ["protagonist", "主角"],
      ["conflict", "核心冲突"],
      ["world", "世界与氛围"],
    ];
    const entryPointsBlock = showEntryPoints
      ? `<div class="guidance-entry-points" role="group" aria-label="你想从哪里开始？">
          ${entryPoints
            .map(
              ([entry, label]) =>
                `<button type="button" class="guidance-entry-button" data-guidance-entry="${entry}" ${guidanceStartingEntry ? "disabled" : ""}>${label}</button>`,
            )
            .join("")}
        </div>`
      : "";
    // 当前具体问题区（AC3/AC4/AC7）：只在导航状态给出 currentQuestion 时展示；按需思路与
    // 跳过是这一区域的两个入口，绑定见 bindExplorationInteractions（Task 10）。
    const suggestionsBlock = guidanceSuggestionsLoading
      ? `<p class="guidance-suggestions-loading">正在想几个思路……</p>`
      : guidanceSuggestions === null
        ? ""
        : guidanceSuggestions.length
          ? `<div class="guidance-suggestions" role="group" aria-label="回答思路">${guidanceSuggestions
              .map(
                (text, index) =>
                  `<button type="button" class="guidance-suggestion-option" data-guidance-suggestion="${index}" ${freeMessageSending ? "disabled" : ""}>${escapeHtml(text)}</button>`,
              )
              .join("")}</div>`
          : `<p class="guidance-suggestions-empty">暂时没想到合适的思路，直接说说你的想法也可以。</p>`;
    const currentQuestionBlock = guidanceCurrentQuestion
      ? `<div class="guidance-current-question" role="status" aria-live="polite">
          <p class="guidance-question-text">${escapeHtml(guidanceCurrentQuestion)}</p>
          <div class="guidance-question-actions">
            <button type="button" class="guidance-suggest-toggle" data-guidance-suggest ${guidanceSuggestionsLoading || freeMessageSending ? "disabled" : ""}>没想好？看看几个思路</button>
            <button type="button" class="guidance-skip" data-guidance-skip ${guidanceSkipping || freeMessageSending ? "disabled" : ""}>先跳过这个问题</button>
          </div>
          ${suggestionsBlock}
        </div>`
      : hasConversation && canFinish
        ? `<div class="guidance-current-question is-complete" role="status" aria-live="polite"><p class="guidance-question-text">7 项设定主干都聊得差不多了，可以在右侧整理为故事设定了。</p></div>`
        : "";
    mainContent = `
      <section class="explore-dialogue" aria-labelledby="explore-title">
        <div class="explore-overline">Free exploration / 自由探索</div>
        <div class="explore-heading"><h1 id="explore-title">把故事聊出来</h1><span>自由探索</span></div>
        <section class="exploration-conversation" aria-label="自由讨论">
          <div class="conversation-scroll" data-conversation-scroll>${freeMessages || '<p class="guided-complete-hint">想到什么都可以先说出来。我们边聊边把人物、冲突和世界一点点理清楚。</p>'}</div>
        </section>
        ${entryPointsBlock}
        ${currentQuestionBlock}
        ${
          showEntryPoints
            ? ""
            : `<form class="explore-response compact-composer" id="explore-response" data-free-mode="true">
          <label for="explore-answer">继续讨论</label>
          <textarea id="explore-answer" placeholder="继续回答，或者和 Agent 讨论其他故事想法……" required ${freeMessageSending ? "disabled" : ""}></textarea>
          <div class="response-actions">
            <button class="primary-button explore-submit" type="submit" ${freeMessageSending ? "disabled" : ""}>${freeMessageSending ? "正在回复…" : "发送"} <span>→</span></button>
          </div>
        </form>`
        }
      </section>`;
  }

  document.title = `${explorationTitle} · ${isGuided ? "引导探索" : "自由探索"} · Muse`;
  app.innerHTML = `
    <div class="explore-page">
      <header class="explore-header">
        <a class="explore-back" href="#/projects">← 作品</a>
        <div class="explore-project"><strong>${escapeHtml(explorationTitle)}</strong><span>${isGuided ? "引导探索" : "自由探索"}</span></div>
        <div class="save-state"><i></i> 已保存</div>
      </header>
      <main class="explore-workbench${isGuided ? " is-guided" : ""}">
        ${mainContent}
        ${storyForming}
      </main>
  </div>`;
  bindExplorationInteractions();
  if (pendingStoryProfile && finalStoryProfile) mountStoryProfileDialog();
}

function bindExplorationInteractions() {
  // —— 引导探索：选项卡片、上一题、都不是、第一题自述、答完显式入口 ——
  document.querySelectorAll("[data-guided-option]").forEach((button) => {
    button.addEventListener("click", () => {
      const options = currentExplorationQuestion().options || [];
      const option = options[Number(button.dataset.guidedOption)];
      if (option) submitGuidedOption(option.value);
    });
  });
  document.querySelector("[data-guided-back]")?.addEventListener("click", () => {
    // 上一题：纯翻页，不删答案（保留已答内容，翻回可见上次选择）。
    if (explorationView > 0) {
      explorationView -= 1;
      renderExploration();
    }
  });
  document.querySelector("[data-guided-next]")?.addEventListener("click", () => {
    // 下一题：仅在后面还有已答过的题时可用，向前翻页不改动答案。
    if (explorationView < explorationHistory.length) {
      explorationView += 1;
      renderExploration();
    }
  });
  document
    .querySelector("[data-guided-none-toggle]")
    ?.addEventListener("click", (event) => {
      // “都不是这些？”：就地展开一句话自答输入框。
      const form = document.querySelector(".guided-custom--none");
      if (!form) return;
      form.hidden = false;
      event.currentTarget.hidden = true;
      form.querySelector("[data-guided-custom-input]")?.focus();
    });
  document.querySelectorAll("[data-guided-custom-form]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      // 自述作答：走真实 Explorer Agent interpret 流式凝练（Story 7.5）。
      submitGuidedCustom(
        event.currentTarget.querySelector("[data-guided-custom-input]")?.value,
      );
    });
  });
  document
    .querySelector("[data-guided-finish]")
    ?.addEventListener("click", () => {
      // 收尾态显式「整理为故事设定」：进整理中过渡 + 触发真实 settle SSE（Story 7.5，
      // 替换原 mock openStoryProfileDialog）。末题作答已自动触发；此按钮供翻回后重新整理。
      guidedSettling = true;
      settleErrorText = "";
      renderExploration();
      startSettleFlow();
    });
  document
    .querySelector("[data-guided-reload]")
    ?.addEventListener("click", () => {
      // 加载失败重试：重新建会话 + 回填（Story 7.5 error 态）。
      if (explorationProjectId) loadGuidedExploration(explorationProjectId);
    });

  // —— 自由探索：真实 SSE 对话、线索 CRUD 与整理门禁 ——
  document
    .querySelector("[data-free-reload]")
    ?.addEventListener("click", () => {
      if (explorationProjectId) loadFreeExploration(explorationProjectId);
    });
  document
    .querySelector(".finish-exploration:not(:disabled)")
    ?.addEventListener("click", () => startFreeSettleFlow());
  document
    .querySelector("[data-add-free-custom-clue]")
    ?.addEventListener("click", () => {
      customStoryClues.push({ label: "", value: "" });
      renderExploration();
      document
        .querySelector(`[data-free-draft-label="${customStoryClues.length - 1}"]`)
        ?.focus();
    });
  document.querySelectorAll("[data-remove-free-draft]").forEach((button) => {
    button.addEventListener("click", () => {
      customStoryClues.splice(Number(button.dataset.removeFreeDraft), 1);
      renderExploration();
    });
  });
  document.querySelectorAll("[data-free-draft-label]").forEach((input) => {
    const focusKey = `draft-${input.dataset.freeDraftLabel}`;
    input.addEventListener("focus", () => freeClueFocusedIds.add(focusKey));
    input.addEventListener("input", (event) => {
      customStoryClues[Number(event.currentTarget.dataset.freeDraftLabel)].label =
        event.currentTarget.value;
    });
    input.addEventListener("blur", (event) => {
      const index = Number(event.currentTarget.dataset.freeDraftLabel);
      freeClueFocusedIds.delete(`draft-${index}`);
      if (applyDeferredFreeClues()) renderExploration();
      const draft = customStoryClues[index];
      if (!draft) return;
      const label = event.currentTarget.value.trim();
      if (!label || draft.creating) return;
      createFreeCustomClue(draft);
    });
  });
  document.querySelectorAll("[data-free-draft-value]").forEach((input) => {
    input.addEventListener("input", (event) => {
      customStoryClues[Number(event.currentTarget.dataset.freeDraftValue)].value =
        event.currentTarget.value;
    });
  });
  document.querySelectorAll("[data-remove-free-custom-clue]").forEach((button) => {
    button.addEventListener("click", () =>
      deleteFreeCustomClue(button.closest("[data-free-custom-index]")?.querySelector("[data-free-clue-id]")?.dataset.freeClueId),
    );
  });
  document.querySelectorAll("[data-free-custom-label]").forEach((input) => {
    input.addEventListener("blur", (event) => {
      const clueId = event.currentTarget.dataset.freeClueId;
      const value = event.currentTarget
        .closest("[data-free-custom-index]")
        ?.querySelector("[data-free-custom-value]")?.value;
      updateFreeClue(clueId, value || "", event.currentTarget.value.trim());
    });
  });
  document.querySelectorAll("[data-free-custom-value]").forEach((input) => {
    input.addEventListener("blur", (event) => {
      const clueId = event.currentTarget.dataset.freeClueId;
      const label = event.currentTarget
        .closest("[data-free-custom-index]")
        ?.querySelector("[data-free-custom-label]")?.value;
      updateFreeClue(clueId, event.currentTarget.value, label || undefined);
    });
  });
  document.querySelectorAll("[data-free-clue-id][contenteditable]").forEach((field) => {
    field.addEventListener("focus", () => {
      freeClueFocusedIds.add(field.dataset.freeClueId);
      if (field.classList.contains("is-empty")) {
        field.textContent = "";
        field.classList.remove("is-empty");
      }
    });
    field.addEventListener("blur", () => {
      const clueId = field.dataset.freeClueId;
      const value = field.textContent.trim();
      if (value !== field.dataset.freeClueValue) {
        updateFreeClue(clueId, value);
      }
      freeClueFocusedIds.delete(clueId);
      if (applyDeferredFreeClues()) renderExploration();
      if (!value) {
        field.textContent = field.dataset.placeholder;
        field.classList.add("is-empty");
      }
    });
  });
  document.querySelectorAll("[data-guidance-entry]").forEach((button) =>
    button.addEventListener("click", () =>
      startFreeGuidanceEntry(button.dataset.guidanceEntry),
    ),
  );
  document
    .querySelector("[data-guidance-suggest]")
    ?.addEventListener("click", () => requestGuidanceSuggestions());
  document.querySelectorAll("[data-guidance-suggestion]").forEach((button) =>
    button.addEventListener("click", () => {
      const index = Number(button.dataset.guidanceSuggestion);
      const text = guidanceSuggestions && guidanceSuggestions[index];
      if (text) submitFreeMessage(text);
    }),
  );
  document
    .querySelector("[data-guidance-skip]")
    ?.addEventListener("click", () => skipFreeGuidanceQuestion());
  document
    .querySelector("#explore-response")
    ?.addEventListener("submit", (event) => {
      event.preventDefault();
      const answer = event.currentTarget.querySelector("#explore-answer").value;
      submitFreeMessage(answer);
    });
  const conversation = document.querySelector("[data-conversation-scroll]");
  if (conversation) conversation.scrollTop = conversation.scrollHeight;
}

function chapterStagePlan() {
  return currentStagePlan || buildCurrentStagePlan();
}

function chapterContextMarkup(stagePlan) {
  if (chapterCreationState === "reading") {
    const isAnnotating = Boolean(chapterAnnotationTarget);
    const annotationCount = String(chapterAnnotations.length).padStart(2, "0");
    const annotationList = chapterAnnotations.length
      ? chapterAnnotations
          .map(
            (annotation, index) =>
              `<li><button type="button" data-locate-annotation data-annotation-page="${annotation.page}" data-annotation-paragraph="${annotation.paragraph}"><span>${String(index + 1).padStart(2, "0")} · 第 ${annotation.page + 1} 页第 ${annotation.paragraph + 1} 段</span><p>${escapeHtml(annotation.text)}</p></button></li>`,
          )
          .join("")
      : '<li class="is-empty">还没有段落批注</li>';
    const feedbackValue = isAnnotating
      ? chapterAnnotationDraft
      : chapterFeedback;
    const canImprove = chapterFeedback.trim() || chapterAnnotations.length;
    return `<aside class="chapter-context chapter-agent-panel" aria-label="章节创作 Agent">
      <div class="chapter-context-head"><span>Chapter editor / Agent</span><strong>V${String(chapterRevision).padStart(2, "0")}</strong></div>
      <div class="chapter-agent-thread" aria-live="polite">
        <article><span>A</span><div><strong>章节编辑 Agent</strong><p>阅读时可以随时告诉我哪里需要调整。我会保留你的创作意图，再改进这一章。</p></div></article>
        ${chapterAgentResult ? `<article class="is-result"><span>A</span><div><strong>${chapterAgentBusy ? "正在处理" : "本轮结果"}</strong><p>${escapeHtml(chapterAgentResult)}</p></div></article>` : ""}
      </div>
      ${
        chapterFinalized
          ? `<section class="chapter-finalized-panel"><span>Chapter final / ${String(chapterCreationIndex + 1).padStart(2, "0")}</span><strong>本章已定稿</strong><p>这一版正文将作为后续章节创作的正式上下文。</p><div>✓</div></section>`
          : `<form class="chapter-feedback-form" data-chapter-feedback-form>
        <div class="chapter-feedback-head">
          <div class="chapter-annotation-summary" tabindex="0" aria-label="本章共有 ${chapterAnnotations.length} 条批注"><span>${annotationCount}</span><div class="chapter-annotation-list"><strong>本章批注</strong><ol>${annotationList}</ol></div></div>
          <label for="chapter-feedback">${isAnnotating ? `批注第 ${chapterAnnotationTarget.paragraph + 1} 段` : "对这一章的点评"}</label>
        </div>
        <textarea id="chapter-feedback" placeholder="${isAnnotating ? "写下对这一段的具体意见……" : "例如：开头再快一点，强化收到来信时的不安感……"}" ${chapterAgentBusy ? "disabled" : ""}>${escapeHtml(feedbackValue)}</textarea>
        ${isAnnotating ? `<p>保存后，这条批注会进入本章的批注列表，并用于后续改进。</p><div class="chapter-feedback-actions"><button type="button" data-cancel-annotation>取消</button><button class="primary-button" type="button" data-save-annotation ${chapterAnnotationDraft.trim() ? "" : "disabled"}>保存批注 <span>→</span></button></div>` : `<p>段落批注和整体点评都会用于“改进本章”；“重新生成”会替换整章。</p><div class="chapter-feedback-actions"><button type="button" data-chapter-revision="regenerate" ${chapterAgentBusy ? "disabled" : ""}>重新生成</button><button class="primary-button" type="button" data-chapter-revision="improve" ${chapterAgentBusy || !canImprove ? "disabled" : ""}>改进本章 <span>→</span></button></div><button class="chapter-finalize-button" type="button" data-finalize-chapter>定稿本章 <span>→</span></button>`}
      </form>`
      }
    </aside>`;
  }
  return `<aside class="chapter-context" aria-label="第一阶段章节安排">
    <div class="chapter-context-head"><span>第一阶段</span><strong>${String(stagePlan.chapters.length).padStart(2, "0")} 章</strong></div>
    <p>阶段计划提供每章的方向；详细章节计划只在准备创作当前章时生成。</p>
    <div class="chapter-context-list">${stagePlan.chapters
      .map(
        (chapter, index) =>
          `<section class="${index === chapterCreationIndex ? "is-current" : ""}"><span>${String(index + 1).padStart(2, "0")}</span><div><strong>${escapeHtml(chapter.title)}</strong><p>${escapeHtml(chapter.brief)}</p></div></section>`,
      )
      .join("")}</div>
  </aside>`;
}

function generatedChapterMarkup(chapter, nextChapter) {
  const chapterNumber = String(chapterCreationIndex + 1).padStart(2, "0");
  const revisedOpening =
    chapterLastRevisionAction === "regenerate"
      ? "旧城的雨从凌晨两点十七分开始倒着落向天空。"
      : chapterLastRevisionAction === "improve"
        ? "雨是在凌晨两点十七分落下来的，比程野记忆中的任何一场雨都更安静。"
        : "雨是在凌晨两点十七分落下来的。";
  const pages = [
    [
      revisedOpening,
      "起初只是细密的一层，贴着窗玻璃缓慢向下爬。程野关掉桌上的台灯，准备离开档案室时，门缝里忽然多出了一只没有署名的信封。纸面已经湿透，边缘却没有留下任何被人捏过的痕迹。",
      "信封里只有一页纸。第一行写着他的名字，第二行写着一个早已被所有人否认的名字——程岚，他失踪了十二年的姐姐。",
      "程野把那张纸翻到背面。那里印着一枚已经停用多年的邮戳，日期却是三天以后。他以为自己看错了，伸手擦过墨迹，指腹沾上一点尚未干透的蓝色。",
      "纸页最下方原本空白的位置渐渐浮出一行小字，像有人正隔着雨夜写给他：不要相信明天醒来的自己。",
    ],
    [
      "走廊尽头传来值班员的脚步声。程野下意识把信藏进外套，可对方经过门口时只是看了他一眼，像往常一样问：“你还在查那个不存在的人？”",
      "这句话他听过太多次。十二年前，程岚的房间在一夜之间变成了储物间，学校的名册里没有她的名字，连父母都坚称自己只有一个孩子。只有程野记得姐姐离开前说，她发现这座城市每天都在悄悄替换一部分过去。",
      "他没有回答值班员，径直走向地下档案库。那枚邮戳属于旧城第七码头的临时邮局，而那间邮局早在九年前的火灾中被拆除。",
      "电梯下降时，楼层数字在负二层和负三层之间闪烁了一下。门打开后，原本封闭的走廊尽头亮着一盏陌生的绿灯。",
      "程野站在门口没有立刻进去。绿光越过他的鞋尖，在地面映出两个人的影子，可整条走廊里分明只有他一个人。",
    ],
    [
      "绿灯下面是一排他从未见过的档案柜。每只抽屉上都贴着日期，最靠近门口的那一格，写的正是三天以后。",
      "程野拉开抽屉，里面只有一张雨水浸过的照片。照片上，他和程岚并肩站在第七码头，身后的电子钟显示着明天凌晨两点十七分。",
      "更让他无法移开视线的是照片右下角。那里站着另一个程野，隔着十二年的雨幕望向镜头，手里握着一只没有署名的信封。",
      "头顶的灯忽然熄灭。黑暗里，有人贴近他的耳边，用程岚的声音轻声说：“你终于还是选择打开了它。”",
      "程野攥紧照片。远处传来整齐的钟声，一共十三下。",
    ],
  ];
  const prose = pages[chapterReaderPage]
    .map((paragraph, index) => {
      const hasAnnotation = chapterAnnotations.some(
        (annotation) =>
          annotation.page === chapterReaderPage &&
          annotation.paragraph === index,
      );
      const isSelected =
        chapterAnnotationTarget?.page === chapterReaderPage &&
        chapterAnnotationTarget?.paragraph === index;
      const isLocated =
        chapterAnnotationFocus?.page === chapterReaderPage &&
        chapterAnnotationFocus?.paragraph === index;
      return `<div class="chapter-paragraph ${hasAnnotation ? "has-annotation" : ""} ${isSelected ? "is-selected" : ""} ${isLocated ? "is-located" : ""}" data-paragraph-position="${chapterReaderPage}:${index}" tabindex="-1">${chapterFinalized ? "" : `<button type="button" class="paragraph-annotation-trigger" data-annotation-page="${chapterReaderPage}" data-annotation-paragraph="${index}" aria-label="给第 ${index + 1} 段添加批注">＋</button>`}<p>${paragraph}</p></div>`;
    })
    .join("");
  const pageNumber = String(chapterReaderPage + 1).padStart(2, "0");
  const pageTotal = String(pages.length).padStart(2, "0");
  return `<article class="chapter-reader" aria-labelledby="chapter-reader-title">
    <div class="chapter-reader-meta"><span>第一阶段 / 第 ${chapterNumber} 章</span><span>${chapterFinalized ? "已定稿" : `草稿 V${chapterRevision}`}</span></div>
    <div class="chapter-title-band">
      <h1 id="chapter-reader-title">${escapeHtml(chapter.title)}</h1>
      ${nextChapter ? `<aside class="chapter-next-preview" aria-label="下一章预告"><span>下一章 / ${String(chapterCreationIndex + 2).padStart(2, "0")}</span><strong>${escapeHtml(nextChapter.title)}</strong><p>${escapeHtml(nextChapter.brief)}</p></aside>` : ""}
    </div>
    <p class="chapter-reader-lead">${escapeHtml(chapter.brief)}</p>
    <div class="chapter-reading-frame">
      <button class="chapter-page-turn is-previous" type="button" data-chapter-page="previous" aria-label="上一页" ${chapterReaderPage === 0 ? "disabled" : ""}>←</button>
      <div class="chapter-prose" aria-live="polite">${prose}</div>
      <button class="chapter-page-turn is-next" type="button" data-chapter-page="next" aria-label="下一页" ${chapterReaderPage === pages.length - 1 ? "disabled" : ""}>→</button>
    </div>
    <footer class="chapter-pagination" aria-label="当前页码"><span><strong>${pageNumber}</strong> / ${pageTotal}</span></footer>
  </article>`;
}

function renderChapterCreation() {
  const stagePlan = chapterStagePlan();
  const chapter = stagePlan.chapters[chapterCreationIndex];
  const chapterNumber = String(chapterCreationIndex + 1).padStart(2, "0");
  document.title = `${chapter.title} · 第 ${chapterCreationIndex + 1} 章 · Muse`;
  let mainContent;
  if (chapterCreationState === "input") {
    mainContent = `<section class="chapter-entry" aria-labelledby="chapter-title">
      <div class="chapter-overline">Chapter creation / ${chapterNumber}</div>
      <div class="chapter-heading"><div><span>第 ${chapterNumber} 章</span><h1 id="chapter-title">${escapeHtml(chapter.title)}</h1></div><strong>${chapterNumber}</strong></div>
      <p class="chapter-outline">${escapeHtml(chapter.brief)}</p>
      <form class="chapter-idea-form" id="chapter-idea-form">
        <div class="chapter-idea-head"><label for="chapter-idea">本章想法</label><span>可选</span></div>
        <textarea id="chapter-idea" placeholder="可以补充想看到的场面、人物表现、节奏或一句具体的对白……">${escapeHtml(chapterIdea)}</textarea>
        <div><p>不填写也可以，Agent 会依据故事设定和阶段计划继续创作。</p><button class="primary-button" type="submit" data-generate-chapter><span data-generate-label>${chapterIdea ? "生成本章" : "跳过并生成"}</span><span>→</span></button></div>
      </form>
    </section>`;
  } else if (chapterCreationState === "generating") {
    mainContent = `<section class="chapter-generating" aria-live="polite">
      <div class="chapter-overline">Chapter creation / ${chapterNumber}</div>
      <span class="generation-index">${chapterNumber}</span>
      <h1>正在写下这一章</h1>
      <p>Agent 正在把阶段纲领${chapterIdea ? "和你的本章想法" : ""}整理成可执行的章节计划，并据此生成正文。</p>
      <div class="generation-steps"><span class="is-active">整理章节计划</span><span>生成章节正文</span><span>检查连续性</span></div>
    </section>`;
  } else {
    mainContent = generatedChapterMarkup(
      chapter,
      stagePlan.chapters[chapterCreationIndex + 1],
    );
  }
  app.innerHTML = `<div class="chapter-page">
    <header class="explore-header"><a class="explore-back" href="#/projects/demo/explore">← 故事设定</a><div class="explore-project"><strong>${escapeHtml(explorationTitle)}</strong><span>章节创作</span></div><div class="save-state"><i></i> ${chapterFinalized ? "本章已定稿" : chapterCreationState === "reading" ? "草稿已保存" : "已保存"}</div></header>
    <main class="chapter-workbench"><div class="chapter-main">${mainContent}</div>${chapterContextMarkup(stagePlan)}</main>
  </div>`;
  bindChapterCreationInteractions();
}

function bindChapterCreationInteractions() {
  const idea = document.querySelector("#chapter-idea");
  idea?.addEventListener("input", () => {
    chapterIdea = idea.value;
    const button = document.querySelector("[data-generate-chapter]");
    button.querySelector("[data-generate-label]").textContent =
      chapterIdea.trim() ? "生成本章" : "跳过并生成";
  });
  document
    .querySelector("#chapter-idea-form")
    ?.addEventListener("submit", (event) => {
      event.preventDefault();
      chapterIdea = event.currentTarget.querySelector("textarea").value.trim();
      chapterCreationState = "generating";
      chapterRevision = 1;
      chapterAgentResult = "";
      chapterLastRevisionAction = "";
      chapterAnnotations = [];
      chapterAnnotationTarget = null;
      chapterAnnotationDraft = "";
      chapterAnnotationFocus = null;
      chapterFinalized = false;
      renderChapterCreation();
      window.setTimeout(() => {
        chapterCreationState = "reading";
        chapterReaderPage = 0;
        renderChapterCreation();
      }, 1200);
    });
  document.querySelectorAll("[data-chapter-page]").forEach((button) => {
    button.addEventListener("click", () => {
      chapterReaderPage += button.dataset.chapterPage === "next" ? 1 : -1;
      chapterAnnotationTarget = null;
      chapterAnnotationDraft = "";
      chapterAnnotationFocus = null;
      renderChapterCreation();
    });
  });
  document.querySelectorAll("[data-annotation-paragraph]").forEach((button) => {
    button.addEventListener("click", () => {
      chapterAnnotationTarget = {
        page: Number(button.dataset.annotationPage),
        paragraph: Number(button.dataset.annotationParagraph),
      };
      chapterAnnotationDraft = "";
      chapterAnnotationFocus = null;
      renderChapterCreation();
      document.querySelector("#chapter-feedback")?.focus();
    });
  });
  const feedback = document.querySelector("#chapter-feedback");
  feedback?.addEventListener("input", () => {
    if (chapterAnnotationTarget) chapterAnnotationDraft = feedback.value;
    else chapterFeedback = feedback.value;
    const improve = document.querySelector('[data-chapter-revision="improve"]');
    if (improve)
      improve.disabled = !chapterFeedback.trim() && !chapterAnnotations.length;
    const saveAnnotation = document.querySelector("[data-save-annotation]");
    if (saveAnnotation)
      saveAnnotation.disabled = !chapterAnnotationDraft.trim();
  });
  document
    .querySelector("[data-cancel-annotation]")
    ?.addEventListener("click", () => {
      chapterAnnotationTarget = null;
      chapterAnnotationDraft = "";
      renderChapterCreation();
    });
  document
    .querySelector("[data-save-annotation]")
    ?.addEventListener("click", () => {
      if (!chapterAnnotationTarget || !chapterAnnotationDraft.trim()) return;
      chapterAnnotations.push({
        ...chapterAnnotationTarget,
        text: chapterAnnotationDraft.trim(),
      });
      chapterAnnotationFocus = { ...chapterAnnotationTarget };
      chapterAnnotationTarget = null;
      chapterAnnotationDraft = "";
      renderChapterCreation();
    });
  document.querySelectorAll("[data-locate-annotation]").forEach((button) => {
    button.addEventListener("click", () => {
      chapterAnnotationFocus = {
        page: Number(button.dataset.annotationPage),
        paragraph: Number(button.dataset.annotationParagraph),
      };
      chapterReaderPage = chapterAnnotationFocus.page;
      chapterAnnotationTarget = null;
      chapterAnnotationDraft = "";
      renderChapterCreation();
      document
        .querySelector(
          `[data-paragraph-position="${chapterAnnotationFocus.page}:${chapterAnnotationFocus.paragraph}"]`,
        )
        ?.focus();
    });
  });
  document.querySelectorAll("[data-chapter-revision]").forEach((button) => {
    button.addEventListener("click", () => {
      const action = button.dataset.chapterRevision;
      if (
        action === "improve" &&
        !chapterFeedback.trim() &&
        !chapterAnnotations.length
      )
        return;
      const submittedFeedback = chapterFeedback.trim();
      const submittedAnnotationCount = chapterAnnotations.length;
      chapterAnnotationFocus = null;
      chapterAgentBusy = true;
      chapterAgentResult =
        action === "regenerate"
          ? "正在重新规划并生成这一章……"
          : "正在根据你的点评改进这一章……";
      renderChapterCreation();
      window.setTimeout(() => {
        chapterRevision += 1;
        chapterReaderPage = 0;
        chapterAgentBusy = false;
        chapterLastRevisionAction = action;
        chapterAgentResult =
          action === "regenerate"
            ? `已生成第 ${chapterRevision} 版草稿${submittedFeedback ? "，并参考了你补充的方向" : ""}。你可以重新阅读后继续反馈。`
            : `已根据${submittedAnnotationCount ? ` ${submittedAnnotationCount} 条段落批注${submittedFeedback ? "和整体点评" : ""}` : `“${submittedFeedback}”`}改进第 ${chapterRevision} 版草稿。修改从第一页开始呈现。`;
        if (action === "regenerate") chapterAnnotations = [];
        chapterFeedback = "";
        renderChapterCreation();
      }, 900);
    });
  });
  document
    .querySelector("[data-finalize-chapter]")
    ?.addEventListener("click", () => {
      chapterFinalized = true;
      chapterAnnotationTarget = null;
      chapterAnnotationDraft = "";
      chapterAnnotationFocus = null;
      chapterAgentResult = `第 ${String(chapterCreationIndex + 1).padStart(2, "0")} 章已采用第 ${chapterRevision} 版草稿定稿，并将作为后续章节的正式上下文。`;
      archiveDialogOpen = false;
      location.hash = "#/projects/demo/archive";
    });
}

function archiveSummaryFor(index) {
  if (index === 0) {
    return [
      [
        "本章发生了什么",
        "程野收到一封来自未来的匿名信，信中再次出现被所有人遗忘的姐姐程岚。他循着已经停用的邮戳进入地下档案库，发现一条本不存在的走廊。",
      ],
      [
        "人物变化",
        "程野从被动保存记忆，转为主动验证姐姐存在过的痕迹；他第一次决定用行动对抗周围人的否认。",
      ],
      [
        "新增事实与线索",
        "未来日期的邮戳、会浮现文字的信纸、第七码头邮局，以及照片中来自未来的另一个程野。",
      ],
      [
        "尚未解决的悬念",
        "是谁寄出了信？程岚为何仍能留下痕迹？照片里的另一个程野经历了什么？",
      ],
      [
        "章末状态",
        "程野打开标有未来日期的档案抽屉，并在黑暗中再次听见程岚的声音，已经无法回到原来的日常。",
      ],
    ];
  }
  return [
    [
      "本章发生了什么",
      "主角沿着上一章留下的线索继续调查，并遭遇新的异常证据。",
    ],
    ["人物变化", "主角对自身记忆的信任进一步动摇，但仍选择继续追查。"],
    ["新增事实与线索", "新的证据把故事推向阶段计划中的下一次关键选择。"],
    ["尚未解决的悬念", "异常现象背后的规则与行动者仍未完全显现。"],
    ["章末状态", "主角付出新的代价，进入下一章无法回避的冲突。"],
  ];
}

function archiveStagesForPreview(stagePlan) {
  return [
    {
      title: "第一阶段",
      chapters: stagePlan.chapters,
      completedCount: Math.min(
        chapterCreationIndex + 1,
        stagePlan.chapters.length,
      ),
      numberOffset: 0,
      preview: false,
    },
    {
      title: "第二阶段",
      chapters: [
        {
          title: "决裂的地图",
          brief: "主角发现城市的变化并非随机，而是有人在借此抹去特定的人。",
        },
        {
          title: "雨停之前",
          brief: "一场短暂的停雨让被隐藏的旧城轮廓重新显现。",
        },
        {
          title: "被替换的清晨",
          brief: "主角醒来后发现同伴已经站到了另一套记忆一边。",
        },
        {
          title: "留下名字的人",
          brief: "主角必须决定保住真相，还是保住仍记得自己的人。",
        },
      ],
      completedCount: 2,
      numberOffset: stagePlan.chapters.length,
      preview: true,
    },
  ];
}

function chapterArchiveDialogMarkup(stage, stageIndex, index) {
  const chapter = stage.chapters[index];
  const globalNumber = stage.numberOffset + index + 1;
  const items = archiveSummaryFor(stageIndex === 0 ? index : -1)
    .map(
      ([label, text], itemIndex) =>
        `<section><span>${String(itemIndex + 1).padStart(2, "0")} / ${label}</span><p>${text}</p></section>`,
    )
    .join("");
  return `<div class="archive-dialog-backdrop" data-close-archive-dialog>
    <section class="archive-dialog" role="dialog" aria-modal="true" aria-labelledby="archive-dialog-title">
      <header><div><span>${stage.title} / Chapter ${String(globalNumber).padStart(2, "0")}</span><h2 id="archive-dialog-title">${escapeHtml(chapter.title)}</h2><p>${escapeHtml(chapter.brief)}</p></div><button type="button" aria-label="关闭章节归档" data-close-archive-dialog>×</button></header>
      <div class="archive-dialog-body">${items}</div>
      <footer><span>这份归档将作为后续章节创作的长期上下文。</span><button type="button" data-close-archive-dialog>返回章节归档</button></footer>
    </section>
  </div>`;
}

function archiveStageGroupMarkup(stage, stageIndex) {
  const isCollapsed = archiveCollapsedStages.has(stageIndex);
  const completedCards = stage.chapters
    .slice(0, stage.completedCount)
    .map((chapter, index) => {
      const globalNumber = stage.numberOffset + index + 1;
      return `<button class="archive-chapter-card" type="button" data-open-archive-stage="${stageIndex}" data-open-archive-chapter="${index}">
        <div><span>${String(globalNumber).padStart(2, "0")}</span><em>已定稿</em></div>
        <h2>${escapeHtml(chapter.title)}</h2>
        <p>${escapeHtml(chapter.brief)}</p>
        <footer><span>查看章节归档</span><strong>→</strong></footer>
      </button>`;
    })
    .join("");
  const nextIndex = stage.completedCount;
  const globalNextNumber = stage.numberOffset + nextIndex + 1;
  const nextCard =
    nextIndex < stage.chapters.length
      ? `<button class="archive-next-card" type="button" ${stage.preview ? "data-preview-next-stage" : `data-start-next-chapter="${nextIndex}"`}>
          <div><span>${stage.preview ? "Layout preview" : "Next chapter"}</span><strong>${String(globalNextNumber).padStart(2, "0")}</strong></div>
          <h2>${escapeHtml(stage.chapters[nextIndex].title)}</h2>
          <p>${escapeHtml(stage.chapters[nextIndex].brief)}</p>
          <footer><span>开始创作第 ${String(globalNextNumber).padStart(2, "0")} 章</span><strong>→</strong></footer>
        </button>`
      : `<button class="archive-next-card" type="button"><div><span>Next stage</span><strong>＋</strong></div><h2>${stage.title}已经完成</h2><p>带着已经写下的故事，继续探索下一阶段。</p><footer><span>规划下一阶段</span><strong>→</strong></footer></button>`;
  return `<section class="archive-stage-group ${isCollapsed ? "is-collapsed" : ""}">
    <header class="archive-stage-row-head">
      <button class="archive-stage-toggle" type="button" data-toggle-archive-stage="${stageIndex}" aria-expanded="${!isCollapsed}" aria-controls="archive-stage-panel-${stageIndex}">
        <div><span>Stage / ${String(stageIndex + 1).padStart(2, "0")}</span><h2>${stage.title}</h2></div>
        <span class="archive-stage-state"><em>${String(stage.completedCount).padStart(2, "0")} 章已归档${stage.preview ? " · 排版预览" : ""}</em><strong aria-hidden="true">${isCollapsed ? "↓" : "↑"}</strong></span>
      </button>
    </header>
    <div class="archive-stage-collapse" id="archive-stage-panel-${stageIndex}">
      <div class="archive-stage-collapse-inner">
        <div class="archive-stage-spread ${stage.completedCount === 1 ? "is-sparse" : ""}" aria-label="${stage.title}章节卡片">${completedCards}${nextCard}</div>
      </div>
    </div>
  </section>`;
}

// 归档页缺省的设定圣经占位（未确认设定时使用，风格与归档 mock 一致）
const archiveStoryProfileFallback = [
  {
    label: "一句话构想",
    value:
      "一个在雨夜里收到未来来信的人，为了找回被所有人遗忘的姐姐，必须对抗一座不断替换过去的城市。",
  },
  {
    label: "主角",
    value:
      "程野，档案室管理员。执拗地保存着关于姐姐程岚的记忆，是城里唯一不肯承认她“从未存在”的人。",
  },
  {
    label: "核心冲突",
    value:
      "越接近真相，他就越难相信自己的记忆；每一次推进都会带来无法轻易撤销的代价。",
  },
  {
    label: "世界与氛围",
    value:
      "潮湿的旧城、凌晨将熄未熄的路灯，以及会自行改写的过去。世界规则先以反常细节显现，再逐步揭露边界。",
  },
  {
    label: "叙事风格",
    value:
      "以人物视角缓慢逼近真相，减少直接解释，让冲突通过选择、停顿与细节自然显现。",
  },
];

function archiveStoryProfileMarkup() {
  const profile =
    confirmedStoryProfile && confirmedStoryProfile.length
      ? confirmedStoryProfile
      : archiveStoryProfileFallback;
  const items = profile
    .map(
      (field, index) =>
        `<section class="archive-profile-item"><span>${String(index + 1).padStart(2, "0")} / ${escapeHtml(field.label)}</span><p>${escapeHtml(field.value)}</p></section>`,
    )
    .join("");
  const collapsed = archiveProfileCollapsed;
  return `<section class="archive-story-profile archive-stage-group ${collapsed ? "is-collapsed" : ""}" aria-labelledby="archive-profile-title">
    <header class="archive-stage-row-head">
      <button class="archive-stage-toggle" type="button" data-toggle-archive-profile aria-expanded="${!collapsed}" aria-controls="archive-profile-panel">
        <div><span>设定圣经</span><h2 id="archive-profile-title">已确认的故事设定</h2></div>
        <span class="archive-stage-state"><em>${String(profile.length).padStart(2, "0")} 项设定</em><strong aria-hidden="true">${collapsed ? "↓" : "↑"}</strong></span>
      </button>
    </header>
    <div class="archive-stage-collapse" id="archive-profile-panel">
      <div class="archive-stage-collapse-inner">
        <div class="archive-story-profile-grid">${items}</div>
      </div>
    </div>
  </section>`;
}

function renderChapterArchive() {
  const stagePlan = chapterStagePlan();
  const stages = archiveStagesForPreview(stagePlan);
  // 首次进入归档页时，把所有阶段默认预置为收起；之后由用户自由展开/收起。
  if (!archiveStagesInitialized) {
    stages.forEach((_, index) => archiveCollapsedStages.add(index));
    archiveStagesInitialized = true;
  }
  const stageGroups = stages
    .map((stage, index) => archiveStageGroupMarkup(stage, index))
    .join("");
  const completedCount = stages.reduce(
    (total, stage) => total + stage.completedCount,
    0,
  );
  document.title = `章节归档 · ${explorationTitle}`;
  app.innerHTML = `<div class="chapter-archive-page">
    <header class="explore-header"><a class="explore-back" href="#/projects">← 作品</a><div class="explore-project"><strong>${escapeHtml(explorationTitle)}</strong><span>章节归档</span></div><div class="save-state"><i></i> ${String(completedCount).padStart(2, "0")} 章已归档</div></header>
    <main class="chapter-archive-main">
      <header class="chapter-archive-heading"><div><span>Chapter archive</span><h1>已经写下的故事</h1><p>章节按阶段分行归档，每个阶段直接呈现已经写下的故事记忆。</p></div></header>
      ${archiveStoryProfileMarkup()}
      <div class="archive-stage-collection">${stageGroups}</div>
    </main>
    ${archiveDialogOpen ? chapterArchiveDialogMarkup(stages[archiveSelectedStage], archiveSelectedStage, archiveSelectedChapter) : ""}
  </div>`;
  document.body.classList.toggle("dialog-open", archiveDialogOpen);
  bindChapterArchiveInteractions();
}

function bindChapterArchiveInteractions() {
  document
    .querySelector("[data-toggle-archive-profile]")
    ?.addEventListener("click", () => {
      archiveProfileCollapsed = !archiveProfileCollapsed;
      renderChapterArchive();
    });
  document.querySelectorAll("[data-toggle-archive-stage]").forEach((toggle) => {
    toggle.addEventListener("click", () => {
      const stageIndex = Number(toggle.dataset.toggleArchiveStage);
      if (archiveCollapsedStages.has(stageIndex)) {
        archiveCollapsedStages.delete(stageIndex);
      } else {
        archiveCollapsedStages.add(stageIndex);
      }
      renderChapterArchive();
    });
  });
  document.querySelectorAll("[data-open-archive-chapter]").forEach((card) => {
    card.addEventListener("click", () => {
      archiveSelectedStage = Number(card.dataset.openArchiveStage);
      archiveSelectedChapter = Number(card.dataset.openArchiveChapter);
      archiveDialogOpen = true;
      renderChapterArchive();
    });
  });
  document.querySelectorAll("[data-close-archive-dialog]").forEach((target) => {
    target.addEventListener("click", (event) => {
      if (
        event.currentTarget === event.target ||
        event.currentTarget.tagName === "BUTTON"
      ) {
        archiveDialogOpen = false;
        renderChapterArchive();
      }
    });
  });
  document
    .querySelector("[data-start-next-chapter]")
    ?.addEventListener("click", (event) => {
      chapterCreationIndex = Number(
        event.currentTarget.dataset.startNextChapter,
      );
      chapterCreationState = "input";
      chapterIdea = "";
      chapterReaderPage = 0;
      chapterRevision = 1;
      chapterFeedback = "";
      chapterAgentBusy = false;
      chapterAgentResult = "";
      chapterLastRevisionAction = "";
      chapterAnnotations = [];
      chapterAnnotationTarget = null;
      chapterAnnotationDraft = "";
      chapterAnnotationFocus = null;
      chapterFinalized = false;
      location.hash = `#/projects/demo/chapters/${chapterCreationIndex + 1}`;
    });
  document
    .querySelector("[data-preview-next-stage]")
    ?.addEventListener("click", (event) => {
      event.currentTarget.querySelector("footer span").textContent =
        "第二阶段为多阶段排版预览";
    });
}

function bindAuthInteractions() {
  document.querySelectorAll("[data-mode]").forEach((tab) => {
    tab.addEventListener("click", () => {
      location.hash =
        tab.dataset.mode === "register" ? "#/register" : "#/login";
    });
  });
  document
    .querySelector(".toggle-password")
    ?.addEventListener("click", (event) => {
      const password = document.querySelector("#password");
      const visible = password.type === "text";
      password.type = visible ? "password" : "text";
      event.currentTarget.textContent = visible ? "显示" : "隐藏";
    });
  document.querySelector("#auth-form")?.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!event.currentTarget.reportValidity()) return;
    const form = event.currentTarget;
    const mode = currentMode();
    const submit = form.querySelector(".submit");
    const submitLabel = submit.querySelector("span");
    const originalLabel = submitLabel.textContent;
    submit.disabled = true;
    submitLabel.textContent = mode === "register" ? "正在创建账号…" : "正在登录…";

    // 失败复位：跳带 ?state= 的 hash 通常触发 render 重绘表单天然复位；但目标 hash 与当前
    // 完全一致时（连续同类错误）hashchange 不触发，须手动复位按钮（受控决策 2）。
    const restoreSubmit = () => {
      submit.disabled = false;
      submitLabel.textContent = originalLabel;
    };
    const showError = (err, errorMode = mode) => {
      // 严格按后端 code 映射状态位（AC6），不臆造分支；未知错误落 failed 中性兜底。
      // errorMode 决定呈现哪一页/哪套文案：注册阶段本身失败用 register；注册成功后
      // 串接 login 失败改用 login——账号已建成、不该再回注册页（否则用户换码重注册撞
      // 「邀请码已使用」死循环），应引导去登录页用刚建的账号登录（Story 7.2 Task 2 边界情形）。
      const state = authStateFromError(err);
      restoreSubmit();
      const base = errorMode === "register" ? "#/register" : "#/login";
      const target = `${base}?state=${state}`;
      // 同 hash 不会触发 render，此时按钮已手动复位、错误文案已在页面呈现，无需额外处理。
      location.hash = target;
    };

    const email = form.querySelector("#email").value;
    const password = form.querySelector("#password").value;

    (async () => {
      if (mode === "register") {
        const inviteCode = form.querySelector("#invite").value;
        // 注册不签发 token（受控决策 1）：register 成功后串接一次 login 拿会话 token。
        // 两阶段错误分开呈现：register 失败留注册页（邀请码等问题）；register 成功但
        // 串接 login 失败按 login 呈现（账号已建成，引导去登录页，勿回注册页死循环）。
        try {
          await authApi.register({ inviteCode, email, password });
        } catch (err) {
          showError(err, "register");
          return;
        }
        try {
          await authApi.login({ email, password });
        } catch (err) {
          showError(err, "login");
          return;
        }
      } else {
        // login 内部已 setTokens 落 localStorage（api.js），此处勿重复存 token。
        try {
          await authApi.login({ email, password });
        } catch (err) {
          showError(err, "login");
          return;
        }
      }
      location.hash = "#/projects";
    })();
  });
  document.querySelectorAll("[data-auth-state]").forEach((button) => {
    button.addEventListener("click", () => {
      const base = currentMode() === "register" ? "#/register" : "#/login";
      location.hash = button.dataset.authState
        ? `${base}?state=${button.dataset.authState}`
        : base;
    });
  });
}

function openCreate(step = "mode") {
  createStep = step;
  renderProjects();
}

// 新建作品成功后重置探索/章节全局态（原型「新建即进全新探索」机制，与作品创建正交）。
// 从原 data-create-submit handler 抽出，供真实创建成功后调用。入参 mode = guided/free。
function resetExplorationStateForNewProject(mode) {
  // 引导探索与自由探索都进入探索页，仅记录入口模式供探索页选择渲染哪种界面
  explorationEntryMode = mode === "free" ? "free" : "guided";
  window.sessionStorage.setItem(explorationEntryModeKey, explorationEntryMode);
  explorationHistory = [];
  freeConversation = [];
  freeClues = [];
  freeLoadState = "loading";
  freeLoadError = null;
  freeLoadSeq += 1;
  freeMessageSending = false;
  freeSettlePending = false;
  freeSettleErrorText = "";
  freeClueEditingIds.clear();
  freeClueFocusedIds.clear();
  deferredFreeClues = null;
  guidanceFields = {};
  guidanceCurrentField = null;
  guidanceCurrentQuestion = null;
  guidanceReadyToSettle = false;
  guidanceSuggestions = null;
  guidanceSuggestionsLoading = false;
  guidanceSkipping = false;
  guidanceStartingEntry = null;
  if (freeMessageAbortController) {
    freeMessageAbortController.abort();
    freeMessageAbortController = null;
  }
  explorationView = 0;
  guidedSettling = false;
  // Story 7.5：重置引导接线态，防新建作品跨会话残留（仿 7.4 logout 态重置）。
  guidedLoadState = "loading";
  guidedLoadError = null;
  guidedLoadSeq += 1; // 作废任何在途加载回调
  guidedAnswerSaving = false;
  settleErrorText = "";
  // 与 settle 对称 abort 在途 interpret 流（review R2）：自述作答 interpret 在途时点新建，
  // guidedLoadSeq++ 已作废回调不污染新会话，但流本身须取消，否则跑完整轮真实 LLM + 连接挂着。
  if (interpretAbortController) {
    interpretAbortController.abort();
    interpretAbortController = null;
  }
  if (freeMessageAbortController) {
    freeMessageAbortController.abort();
    freeMessageAbortController = null;
  }
  if (settleAbortController) {
    settleAbortController.abort();
    settleAbortController = null;
  }
  customStoryClues = [];
  finalStoryProfile = null;
  finalStoryProfileSignature = "";
  finalStoryProfileRevision = 1;
  pendingStoryProfile = false;
  lastProfileChangedFields = [];
  profileFeedbackStatus = "";
  explorationMode = "profile";
  confirmedStoryProfile = null;
  stagePlanningHistory = [];
  stagePlanningRound = 0;
  stagePlanningDraft = {
    goal: "",
    opening: "",
    conflict: "",
    events: "",
    chapters: "",
  };
  currentStagePlan = null;
  chapterCreationState = "input";
  chapterIdea = "";
  chapterReaderPage = 0;
  chapterRevision = 1;
  chapterFeedback = "";
  chapterAgentBusy = false;
  chapterAgentResult = "";
  chapterLastRevisionAction = "";
  chapterAnnotations = [];
  chapterAnnotationTarget = null;
  chapterAnnotationDraft = "";
  chapterAnnotationFocus = null;
  chapterFinalized = false;
  chapterCreationIndex = 0;
  archiveDialogOpen = false;
  archiveSelectedChapter = 0;
  archiveSelectedStage = 0;
  clearPendingStoryProfile();
  window.sessionStorage.removeItem(explorationModeKey);
  window.sessionStorage.removeItem(confirmedStoryProfileKey);
}

function bindProjectInteractions() {
  // 退出（Story 7.2 AC5）：拦截默认跳转，先调 authApi.logout 作废后端 refresh + 清本地 token
  // （logout 已保证 finally 清本地态、失败静默，api.js），再回登录态。避免纯 <a href> 绕过登出。
  document.querySelector("[data-logout]")?.addEventListener("click", (event) => {
    event.preventDefault();
    (async () => {
      await authApi.logout();
      // 重置作品库模块态，防下一账号登录看到上一账号残留（列表/邮箱）；自增代次作废
      // 任何在途 loadProjects 回调（防旧账号数据回写新会话）。
      projects = [];
      currentUserEmail = "";
      projectsLoadState = "loading";
      projectsLoadSeq++;
      // 同步重置 BYOK 模块态（Story 7.4）：防 A 绑定 Key 登出后 B 进设置页闪现 A 的
      // 绑定态；自增 byokLoadSeq 作废在途 loadByok 回调。
      byokBinding = null;
      usageView = null;
      byokKeyDraft = "";
      byokTab = "hosted";
      byokReplaceMode = false;
      byokSelectedProvider = "deepseek";
      byokSaving = false;
      byokLoadState = "loading";
      byokLoadSeq++;
      // review R2 P3：清引导探索态防跨用户残留（违反 7.4 review P3 先例 + 触碰 AC8 多租户）。
      // A 设定卡 pending 时 logout → B 同标签页登录进引导项目 → render 先判 pending 为真直接
      // 给 B 弹 A 的卡。须 abort 在途 SSE（teardown）+ 清 pending 内存态与 sessionStorage。
      teardownExplorationInflight();
      clearPendingStoryProfile();
      freeConversation = [];
      freeClues = [];
      freeLoadState = "loading";
      freeLoadError = null;
      freeSettleErrorText = "";
      freeClueEditingIds.clear();
      freeClueFocusedIds.clear();
      deferredFreeClues = null;
      guidanceFields = {};
      guidanceCurrentField = null;
      guidanceCurrentQuestion = null;
      guidanceReadyToSettle = false;
      guidanceSuggestions = null;
      guidanceSuggestionsLoading = false;
      guidanceSkipping = false;
      guidanceStartingEntry = null;
      finalStoryProfile = null;
      finalStoryProfileSignature = "";
      pendingStoryProfile = false;
      guidedLoadState = "loading";
      guidedLoadError = null;
      settleErrorText = "";
      explorationProjectId = "";
      location.hash = "#/login";
    })();
  });
  document
    .querySelectorAll("[data-new-project]")
    .forEach((button) => button.addEventListener("click", () => openCreate()));
  document.querySelectorAll("[data-close-modal]").forEach((target) =>
    target.addEventListener("click", (event) => {
      if (event.target === target || event.target.closest(".modal-close"))
        openCreate("closed");
    }),
  );
  document.querySelectorAll("[data-create-mode]").forEach((button) =>
    button.addEventListener("click", () => {
      selectedMode = button.dataset.createMode;
      openCreate("naming");
    }),
  );
  document
    .querySelector("[data-back-mode]")
    ?.addEventListener("click", () => openCreate("mode"));
  document
    .querySelector(".naming-input")
    ?.addEventListener("input", (event) => {
      document.querySelector("[data-create-submit]").textContent =
        event.target.value.trim() ? "继续" : "跳过";
    });
  document
    .querySelector("[data-create-submit]")
    ?.addEventListener("click", (event) => {
      const submit = event.currentTarget;
      if (submit.disabled) return; // 防重复提交（在途禁点）
      const mode = selectedMode;
      const titleInput =
        document.querySelector(".naming-input")?.value.trim() || "";
      const originalLabel = submit.textContent;
      submit.disabled = true;
      submit.textContent = "创建中…";
      (async () => {
        try {
          // 真实创建（AC3）：title 留空传 undefined，后端回落「未命名小说」，前端勿强制非空。
          const project = await projectApi.create({
            mode,
            title: titleInput || undefined,
          });
          // 响应必须含真实 id 才能进探索页；缺 id（后端 bug/代理裁字段）则当作失败，
          // 不跳 #/projects/undefined/explore 污染后续操作。
          if (!project || !project.id) {
            throw new ApiError(
              "invalid_response",
              "创建返回缺少作品标识。",
              undefined,
              undefined,
            );
          }
          // 保留原型「新建即进全新探索」语义：以真实 title 起头 + 重置探索/章节全局态，
          // 再按真实作品 id 进探索页（替换固定 demo）。
          explorationTitle = project.title || titleInput || "未命名小说";
          createStep = "closed";
          selectedMode = "";
          resetExplorationStateForNewProject(mode);
          location.hash = `#/projects/${project.id}/explore`;
        } catch (err) {
          // 失败恢复按钮 + 可读提示（不臆造后端未定义分支）。留在命名弹窗让用户重试。
          submit.disabled = false;
          submit.textContent = originalLabel;
          const hint = document.querySelector("[data-create-error]");
          const text = projectErrorText(err);
          if (hint) hint.textContent = text;
          else
            document
              .querySelector(".modal-actions")
              ?.insertAdjacentHTML(
                "beforebegin",
                `<p class="create-error" data-create-error role="alert">${escapeHtml(text)}</p>`,
              );
        }
      })();
    });
  document.querySelectorAll("[data-menu]").forEach((button) =>
    button.addEventListener("click", () => {
      const menu = button.nextElementSibling;
      const willOpen = menu.hidden;
      document.querySelectorAll(".project-menu").forEach((item) => {
        item.hidden = true;
      });
      menu.hidden = !willOpen;
      button.setAttribute("aria-expanded", String(willOpen));
    }),
  );
  document.querySelectorAll("[data-rename]").forEach((button) =>
    button.addEventListener("click", () => {
      const row = button.closest(".project-row");
      const title = row.querySelector("h2");
      // title.textContent 是已解码文本，插回 attribute 前 escapeHtml 防引号/尖括号破坏结构。
      title.outerHTML = `<div class="rename-form"><input class="rename-input" value="${escapeHtml(title.textContent)}" aria-label="新的小说名称" /><button data-save-rename>保存</button><button data-cancel-rename>取消</button></div>`;
      row.querySelector(".project-menu").hidden = true;
      row.querySelector(".rename-input").focus();
      bindInlineProjectActions(row);
    }),
  );
  document.querySelectorAll("[data-delete]").forEach((button) =>
    button.addEventListener("click", () => {
      const row = button.closest(".project-row");
      row
        .querySelector(".project-copy")
        .insertAdjacentHTML(
          "beforeend",
          `<div class="delete-confirm"><span>删除后无法恢复。</span><button data-confirm-delete>确认删除</button><button data-cancel-delete>取消</button></div>`,
        );
      row.querySelector(".project-menu").hidden = true;
      bindInlineProjectActions(row);
    }),
  );
  document.querySelectorAll("[data-continue]").forEach((button) =>
    button.addEventListener("click", () => {
      // continue = 回到已有作品断点，按 phase 路由，不重置任何状态
      const project = projects.find(
        (item) => item.id === button.dataset.continue,
      );
      const meta = project && PHASE_META[project.phase];
      if (meta) {
        // review R2 D1：按打开作品的真实 mode 设 entryMode，防残留 sessionStorage 值致模式错配
        // （上次进过 free 项目残留 "free" → 继续创作打开 guided 项目被当自由、不加载引导会话）。
        explorationEntryMode = project.mode === "free" ? "free" : "guided";
        window.sessionStorage.setItem(
          explorationEntryModeKey,
          explorationEntryMode,
        );
        location.hash = meta.route(project.id);
      }
    }),
  );
  document.querySelector("[data-reload]")?.addEventListener("click", () => {
    // 重新触发列表拉取（AC2），而非仅重置 hash。
    projectsLoadState = "loading";
    renderProjects();
  });
}

function bindInlineProjectActions(row) {
  const projectId = row.dataset.projectId;
  row.querySelector("[data-save-rename]")?.addEventListener("click", (event) => {
    const saveBtn = event.currentTarget;
    if (saveBtn.disabled) return;
    const input = row.querySelector(".rename-input");
    const value = input.value.trim();
    saveBtn.disabled = true;
    saveBtn.textContent = "保存中…";
    (async () => {
      try {
        // 真实改名（AC3）：title 留空传 undefined，后端回落「未命名小说」。成功后重拉列表反映
        // 最新（含刷新 updatedAt + 重新按更新时间排序）。
        await projectApi.rename(projectId, value || undefined);
        projectsLoadState = "loading";
        renderProjects();
      } catch (err) {
        saveBtn.disabled = false;
        saveBtn.textContent = "保存";
        // project_not_found（并发删除/越权）→ 刷新列表；其余给提示后重拉。
        window.alert(projectErrorText(err));
        projectsLoadState = "loading";
        renderProjects();
      }
    })();
  });
  row
    .querySelector("[data-cancel-rename]")
    ?.addEventListener("click", () => renderProjects());
  row
    .querySelector("[data-confirm-delete]")
    ?.addEventListener("click", (event) => {
      const confirmBtn = event.currentTarget;
      if (confirmBtn.disabled) return;
      confirmBtn.disabled = true;
      confirmBtn.textContent = "删除中…";
      (async () => {
        try {
          await projectApi.remove(projectId);
          // 真实删除成功（204）→ 重拉列表（与改名一致，过 loadProjects 的 hash+代次
          // 校验、并反映后端最新状态；空列表自动转 empty 态）。
          projectsLoadState = "loading";
          renderProjects();
        } catch (err) {
          // project_not_found 视为已删（幂等友好）：同样重拉刷新。
          if (err && err.code === "project_not_found") {
            projectsLoadState = "loading";
            renderProjects();
            return;
          }
          confirmBtn.disabled = false;
          confirmBtn.textContent = "确认删除";
          window.alert(projectErrorText(err));
        }
      })();
    });
  row
    .querySelector("[data-cancel-delete]")
    ?.addEventListener("click", () =>
      row.querySelector(".delete-confirm").remove(),
    );
}

// ============================================================
// 文风锚点入口（FR16 / 模块 2 · 红线验收前提）
// 用户从预置样本库选择或粘贴一段爱读的文字，系统抽取作品级 style_profile
// （人称、语气、句式节奏、意象密度、段落长度倾向），作为 §7.1 行为红线的验收锚。
// 原型此前无此页，属就绪报告 UX-ALIGN-01 新增。
// ============================================================
const styleSampleLibrary = [
  {
    id: "cold-rain",
    name: "冷峻夜雨",
    note: "克制的短句、潮湿的旧城意象",
    excerpt:
      "雨是在凌晨落下来的，比记忆里任何一场都更安静。他站在檐下，看水沿着旧招牌的裂缝往下走，没有点烟，也没有回头。",
    profile: {
      person: "第三人称限知",
      tone: "冷峻、克制",
      rhythm: "短句为主，偶有停顿",
      imagery: "高（雨、旧城、光影）",
      paragraph: "偏短，一段一景",
    },
  },
  {
    id: "warm-dusk",
    name: "黄昏暖光",
    note: "舒缓长句、细腻的情感铺陈",
    excerpt:
      "黄昏的光是慢慢漫上来的，先是染红了她搁在窗台上的手背，然后才一点一点爬满整间屋子，像怕惊动了谁似的，走得那样轻。",
    profile: {
      person: "第三人称限知",
      tone: "温暖、感伤",
      rhythm: "长句舒缓，节奏绵延",
      imagery: "中高（光线、居家细节）",
      paragraph: "偏长，情感层层递进",
    },
  },
  {
    id: "sharp-first",
    name: "凌厉第一人称",
    note: "紧凑口语、强推进感",
    excerpt:
      "我没时间解释。门在身后合上的那一秒，我已经算好了三条路——两条是死的，剩下一条，我赌它还没被他们发现。",
    profile: {
      person: "第一人称",
      tone: "凌厉、紧张",
      rhythm: "短促、强推进",
      imagery: "低（服务于动作）",
      paragraph: "短，逼近节奏",
    },
  },
];

function styleAnchorProfileMarkup(profile) {
  const rows = [
    ["人称", profile.person],
    ["语气", profile.tone],
    ["句式节奏", profile.rhythm],
    ["意象密度", profile.imagery],
    ["段落长度倾向", profile.paragraph],
  ];
  return `<div class="style-profile-grid">${rows
    .map(
      ([label, value]) =>
        `<div class="style-profile-row"><span>${label}</span><strong>${escapeHtml(value)}</strong></div>`,
    )
    .join("")}</div>`;
}

// ============================================================
// 全本通读视图（FR26 / 模块 5 · V1）
// 按顺序连续呈现已定稿章节，让用户从头读一遍自己的书。原型此前无此页。
// 章节数据为线框占位（真实数据由后端定稿章节提供）。
// ============================================================
const readthroughChapters = [
  {
    title: "打破日常",
    paragraphs: [
      "雨是在凌晨两点十七分落下来的，比程野记忆中的任何一场雨都更安静。",
      "他关掉桌上的台灯，准备离开档案室时，门缝里忽然多出了一只没有署名的信封。纸面已经湿透，边缘却没有留下任何被人捏过的痕迹。",
      "信封里只有一页纸。第一行写着他的名字，第二行写着一个早已被所有人否认的名字——程岚，他失踪了十二年的姐姐。",
      "程野把那张纸翻到背面。那里印着一枚已经停用多年的邮戳，日期却是三天以后。他以为自己看错了，伸手擦过墨迹，指腹沾上一点尚未干透的蓝色。",
      "纸页最下方原本空白的位置渐渐浮出一行小字，像有人正隔着雨夜写给他：不要相信明天醒来的自己。",
      "他把信重新折好，动作比自己预想的要慢。窗外的雨还在下，档案室的钟指向两点十九分，仿佛刚才那两分钟从未真正走过。",
      "他做的第一件事，是把档案室里所有的钟都记了一遍。墙上的、桌角的、还有腕表上那只——三只钟指向的分秒竟不完全一致，走得最快的那只，已经偏向了两天以后。",
      "程野想起姐姐失踪的那夜也下着这样的雨。她站在门口回头，说这座城市会一点点把人从别人的记忆里擦掉：先是名字，然后是脸，最后连‘她曾经存在过’这件事，都不再剩下。",
      "‘可只要还有一个人记得，’程岚当时笑了笑，‘被擦掉的那一块，就还留着一条缝。’那年他十四岁，把这句话当作姐姐惯常的胡话，随手丢在了脑后。",
      "十二年过去，他成了整座城市里唯一还守着那条缝的人。而这封信，正是从缝里递进来的——他几乎可以确定。",
      "他重新拧亮台灯，借着光又读了一遍那行浮字。墨迹已经开始变淡，像是写下它的人，也正被同一场遗忘缓缓收回。",
      "离开时程野没有锁门。他忽然觉得，在这座会自行改写的城市里，锁与不锁，大概从来就没有分别。雨声盖过下楼的脚步，档案室的钟，无声地跳到了两点二十分。",
    ],
  },
  {
    title: "不存在的证明",
    paragraphs: [
      "走廊尽头传来值班员的脚步声。程野下意识把信藏进外套，可对方经过门口时只是看了他一眼，像往常一样问：“你还在查那个不存在的人？”",
      "这句话他听过太多次。十二年前，程岚的房间在一夜之间变成了储物间，学校的名册里没有她的名字，连父母都坚称自己只有一个孩子。",
      "只有程野记得姐姐离开前说，这座城市每天都在悄悄替换一部分过去。而他，是唯一一个还留着旧版本记忆的人。",
      "他径直走向地下档案库。那枚邮戳属于旧城第七码头的临时邮局，而那间邮局早在九年前的火灾中被拆除。",
      "电梯下降时，楼层数字在负二层和负三层之间闪烁了一下。门打开后，原本封闭的走廊尽头亮着一盏陌生的绿灯。",
      "程野站在门口没有立刻进去。绿光越过他的鞋尖，在地面映出两个人的影子，可整条走廊里分明只有他一个人。",
      "他弯腰去碰那第二道影子。指尖穿过去，只触到冰凉的地面，影子却没有随之晃动，像是它属于另一个正站在同样位置、却与他错开了一点时间的人。",
      "走廊两侧的档案柜都空着，唯独尽头那只亮着绿灯的柜子上贴着一张借阅卡。卡上的借阅人一栏，写着他自己的名字，归还日期同样是三天以后。",
      "程野翻开随身的记事本，想记下这一切。可落笔时他发现，本子里前几页的字迹正在缓慢褪色——那些是他昨天才写下的、关于姐姐的线索。",
      "他忽然明白过来：这座城市擦除一个人，不是让别人忘记，而是让所有能证明她存在的东西一起消失。信、照片、他手写的字，都是与遗忘赛跑的证据。",
      "绿灯闪了两下，像在回应他的领悟。程野把记事本按在胸口，逼着自己一笔一划重新描过那些正在变淡的字，仿佛只要描得够用力，姐姐就还留在这世上。",
      "他决定顺着借阅卡的指引走下去。既然三天以后的自己借走过这里的东西，那么在那之前，他还有时间把姐姐从这场缓慢的抹除里，一寸一寸抢回来。",
    ],
  },
  {
    title: "代价显现",
    paragraphs: [
      "绿灯下面是一排他从未见过的档案柜。每只抽屉上都贴着日期，最靠近门口的那一格，写的正是三天以后。",
      "程野拉开抽屉，里面只有一张雨水浸过的照片。照片上，他和程岚并肩站在第七码头，身后的电子钟显示着明天凌晨两点十七分。",
      "更让他无法移开视线的是照片右下角。那里站着另一个程野，隔着十二年的雨幕望向镜头，手里握着一只没有署名的信封。",
      "头顶的灯忽然熄灭。黑暗里，有人贴近他的耳边，用程岚的声音轻声说：“你终于还是选择打开了它。”",
      "程野攥紧照片。远处传来整齐的钟声，一共十三下——这座城市从来只有十二座钟。",
      "第十三声钟响落下时，黑暗里那道声音又贴近了些：“记得，是要付代价的。你替她记了十二年，这十二年里，你自己丢了什么，从没算过吧。”",
      "他这才意识到，自己想不起父母的脸了。不是模糊，是彻底的空白——就像当年别人想不起程岚那样。原来守着那条缝的人，也会被缝一点点吞掉。",
      "照片在他掌心里发烫。画面开始变动：另一个程野转过身，把那只信封递向镜头，口型分明是‘别记了’，可程野知道，自己永远做不到。",
      "绿灯彻底熄灭。伸手不见五指的档案库里，只剩下十三声钟的余音，和他自己越来越轻、仿佛也要被抹去的呼吸。",
      "程野摸黑把照片贴身收好，又摸出那封信，两样东西一起攥在手里。它们是他与整座城市对赌的全部筹码——只要还攥着，他就还没输。",
      "他开始往回走，一步一数。数到第十七步时，走廊尽头透进一线灰白的光，是通往地面的楼梯口，也是三天倒计时真正开始的地方。",
      "登上最后一级台阶，雨已经停了。天边泛起病态的青灰色，像一张被反复擦写、终于露出底纹的纸。程野抬头，看见城中十二座钟楼在晨雾里静静矗立。",
      "可他分明听见，从某个看不见的方向，第十三座钟正在为他一个人，敲响倒数第三天的第一声。他握紧了手里的信和照片，朝那声音走了过去。",
    ],
  },
];

const READTHROUGH_PER_PAGE = 6;

function readthroughPages(chapter) {
  const pages = [];
  for (let i = 0; i < chapter.paragraphs.length; i += READTHROUGH_PER_PAGE) {
    pages.push(chapter.paragraphs.slice(i, i + READTHROUGH_PER_PAGE));
  }
  return pages.length ? pages : [[]];
}

// ============================================================
// 模型接入 · BYOK / 托管用量（FR4 / 模块 0）
// 托管为主：Muse 出 Key，用户零门槛，成本护栏 = 免费额度上限。
// BYOK 进阶：用户在设置页绑定自有 API Key，成本自付、解绑额度。
// 原型此前无设置页 / 用量入口，属就绪报告 UX-ALIGN-01 新增。
// ============================================================
// ============================================================
// 阶段交界方向输入（FR22 / 模块 3）
// 一个阶段章节写完、进入下一阶段前的极轻、可跳过入口：
// 「这一段想往哪走？（或直接继续）」，也是用户主动提出进入收尾的唯一控制点。
// 平时跳过无感，不打断「无缝进第一章」的默认流程。原型此前无此过渡态。
// ============================================================
function renderStageDirection() {
  document.title = `下一段方向 · ${explorationTitle} · Muse`;
  app.innerHTML = `<div class="stage-direction-page">
    <header class="explore-header"><a class="explore-back" href="#/projects/demo/chapters/1">← 返回创作</a><div class="explore-project"><strong>${escapeHtml(explorationTitle)}</strong><span>阶段交界</span></div><div class="save-state"><i></i> 上一阶段已写完</div></header>
    <main class="stage-direction-main">
      <section class="stage-direction-card">
        <div class="stage-direction-overline">Between stages / 阶段交界</div>
        <h1>这一段，想往哪走？</h1>
        <p class="stage-direction-lead">上一阶段写完了。如果心里已经有方向，写一句给我；没有也没关系，直接继续，我会顺着故事往下写。</p>
        <textarea class="input stage-direction-input" id="stage-direction" placeholder="比如：让主角开始怀疑同伴 / 节奏慢下来铺一段感情 / 我想开始收尾了……">${escapeHtml(stageDirectionText)}</textarea>
        <div class="stage-direction-actions">
          <button class="secondary-button" type="button" data-stage-continue>直接继续</button>
          <button class="primary-button" type="button" data-stage-submit>带着这个方向写下去 <span>→</span></button>
        </div>
        <button class="stage-direction-finale" type="button" data-stage-finale>我想开始收尾了 →</button>
      </section>
    </main>
  </div>`;
  bindStageDirectionInteractions();
}

function bindStageDirectionInteractions() {
  const input = document.querySelector("#stage-direction");
  input?.addEventListener("input", () => {
    stageDirectionText = input.value;
  });
  const goNext = () => {
    location.hash = "#/projects/demo/chapters/1";
  };
  document
    .querySelector("[data-stage-continue]")
    ?.addEventListener("click", goNext);
  document
    .querySelector("[data-stage-submit]")
    ?.addEventListener("click", goNext);
  document.querySelector("[data-stage-finale]")?.addEventListener("click", () => {
    stageDirectionText = "（用户已声明：进入收尾阶段）";
    goNext();
  });
}

// 模型接入页错误文案（仿 projectErrorText，按 err.code 出可读中文 + 中性兜底）。
function byokErrorText(err) {
  const code = err && err.code;
  if (code === "byok_invalid_key") return "API Key 不能为空，且长度需在限制内。";
  if (code === "byok_invalid_provider") return "不支持的模型提供方。";
  if (code === "validation_error") return "请检查 API Key 与模型提供方后重试。";
  return "操作未能完成，请检查网络后稍后重试。";
}

// provider 英文枚举 → 中文标签（后端 deepseek/claude/custom）。
function providerLabel(provider) {
  if (provider === "claude") return "Claude";
  if (provider === "custom") return "自定义";
  return "DeepSeek";
}

function renderByok() {
  document.title = "模型接入 · Muse";
  paintByok();
  bindByokInteractions();
  // 进入即拉真实绑定状态 + 用量（首帧 loading，回填后重绘）。
  if (byokLoadState === "loading") {
    loadByok();
  }
}

// 异步拉取 BYOK 绑定状态 + 托管用量（AC3/AC4/AC6）。
// 时序防护（承 7.3 受控决策 4）：hash + 代次双校验，防用户快速切走 / 往返并发覆盖。
// 401 由 apiFetch 兜底（自动刷新重放 / 失效跳登录），不在此重复处理。
async function loadByok() {
  const startedHash = hashPath();
  const seq = ++byokLoadSeq;
  // 并发拉绑定态 + 用量。status 是本页核心（决定绑定/解绑面板），usage 只读且非必需
  // （bound 时 hosted 面板本就显「不适用」）——故仅 status 失败才整页 error；usage 单独
  // 失败降级为 usageView=null（paintHostedPanel 显「用量暂不可用」占位），不锁死整页。
  const [statusResult, usageResult] = await Promise.allSettled([
    byokApi.status(),
    usageApi.view(),
  ]);
  if (seq !== byokLoadSeq || hashPath() !== startedHash) return;
  if (statusResult.status === "fulfilled") {
    byokBinding = statusResult.value || { bound: false };
    usageView =
      usageResult.status === "fulfilled" ? usageResult.value || null : null;
    // 绑定态回填时，把选中的 provider 同步为后端已绑定值（重填/展示一致）。
    byokSelectedProvider =
      byokBinding && byokBinding.bound && byokBinding.provider
        ? byokBinding.provider
        : "deepseek";
    byokReplaceMode = false;
    byokLoadState = "ready";
  } else {
    byokLoadState = "error";
  }
  renderByok();
}

// 同步绘制当前态。三层：byokLoadState(loading/error/ready) × byokTab(hosted/byok)
//   × byokBinding(已绑定/未绑定)。数据来自 loadByok 回填的 byokBinding / usageView。
function paintByok() {
  const bound = !!(byokBinding && byokBinding.bound);
  const headState =
    byokLoadState === "error"
      ? "加载失败"
      : bound
        ? "BYOK 已就绪"
        : byokTab === "byok"
          ? "绑定自有 Key"
          : "托管额度";

  let panel;
  if (byokLoadState === "loading") {
    panel = `<section class="byok-panel" aria-busy="true"><p class="byok-usage-note">正在读取你的模型接入状态…</p></section>`;
  } else if (byokLoadState === "error") {
    panel = `<section class="byok-panel">
        <p class="byok-usage-note">暂时无法读取模型接入状态。</p>
        <div class="style-anchor-actions"><button class="primary-button" type="button" data-byok-reload>重新加载 <span>→</span></button></div>
      </section>`;
  } else if (byokTab === "hosted") {
    panel = paintHostedPanel(bound);
  } else {
    panel = paintByokPanel(bound);
  }

  app.innerHTML = `<div class="byok-page">
    <header class="explore-header"><a class="explore-back" href="#/projects">← 作品库</a><div class="explore-project"><strong>模型接入</strong><span>设置</span></div><div class="save-state"><i></i> ${headState}</div></header>
    <main class="byok-main">
      <section class="byok-intro">
        <div class="byok-overline">Model access / 模型接入</div>
        <h1>用谁的算力，由你定</h1>
        <p>默认走 Muse 托管，进来就能写，有免费额度。想不受额度限制、或用自己的模型，就绑定一把自己的 API Key，成本自付、额度解绑。</p>
      </section>
      <div class="tabs" role="tablist" aria-label="模型接入方式">
        <button class="tab" role="tab" aria-selected="${byokTab === "hosted"}" data-byok-tab="hosted">Muse 托管（默认）</button>
        <button class="tab" role="tab" aria-selected="${byokTab === "byok"}" data-byok-tab="byok">绑定自有 Key</button>
      </div>
      ${panel}
    </main>
  </div>`;
}

// 托管 tab：展示真实 tokens 用量（AC4）。口径对齐（受控决策 1）：
//   后端按 tokens 计（非「章」）、resetAt 恒 null（累计总量护栏、非每日重置）——
//   故展示「已用 X / Y tokens」、文案改「累计免费额度」，不再显「N 章 / 每天重置」。
// BYOK 用户（quotaApplies=false）：额度不适用，展示「走自有 Key、不占免费额度」。
function paintHostedPanel(bound) {
  const usage = usageView;
  const isByokBilling = bound || (usage && usage.quotaApplies === false);
  if (isByokBilling) {
    return `<section class="byok-panel">
        <div class="byok-usage-head"><span>免费额度</span><strong>不适用</strong></div>
        <p class="byok-usage-note">你已绑定自有 API Key，生成走你自己的 Key、成本自付，Muse 不再计免费额度。</p>
        <div class="byok-tip">想回到托管免费额度？切到「绑定自有 Key」解绑当前 Key。</div>
      </section>`;
  }
  // 用量拉取失败/数据缺失（usageView=null 或字段缺失）：显占位而非画「0 / 0 tokens」假额度，
  // 避免用户误以为额度已耗尽（review P3：展示查询不误导）。
  if (!usage || typeof usage.used !== "number" || typeof usage.quota !== "number") {
    return `<section class="byok-panel">
        <div class="byok-usage-head"><span>免费额度（tokens）</span><strong>用量暂不可用</strong></div>
        <p class="byok-usage-note">暂时无法读取用量数据，请稍后重试。写作过程中不会弹付费墙。</p>
        <div class="byok-tip">重度创作、或想换用更强的模型？切到「绑定自有 Key」解除额度限制。</div>
      </section>`;
  }
  const used = usage.used;
  const quota = usage.quota;
  const remaining =
    typeof usage.remaining === "number"
      ? usage.remaining
      : Math.max(0, quota - used);
  const percent = quota > 0 ? Math.min(100, Math.round((used / quota) * 100)) : 0;
  return `<section class="byok-panel">
        <div class="byok-usage-head"><span>免费额度（tokens）</span><strong>${formatTokens(used)} / ${formatTokens(quota)}</strong></div>
        <div class="byok-usage-bar"><i style="width: ${percent}%"></i></div>
        <p class="byok-usage-note">剩余 ${formatTokens(remaining)} tokens（累计免费额度）。额度上限会在盲测跑出单章真实成本后定档（当前为占位值）。写作过程中不会弹付费墙。</p>
        <div class="byok-tip">重度创作、或想换用更强的模型？切到「绑定自有 Key」解除额度限制。</div>
      </section>`;
}

// 千分位格式化 tokens 数（展示可读）。
function formatTokens(n) {
  const value = typeof n === "number" && isFinite(n) ? n : 0;
  return value.toLocaleString("en-US");
}

// 绑定 tab：未绑定→输入 Key + provider 三选 + 保存；已绑定→掩码回显 + 更换 / 解绑（AC2/AC3/AC5）。
function paintByokPanel(bound) {
  // 已绑定且未进入「更换」态：展示掩码 + provider + 更换/解绑。
  if (bound && !byokReplaceMode) {
    return `<section class="byok-panel">
        <div class="field"><div class="field-head"><label>已绑定 API Key</label><span class="field-note">仅回显掩码，明文已加密存储</span></div><div class="byok-usage-head"><span>${escapeHtml(providerLabel(byokBinding.provider))}</span><strong>${escapeHtml(byokBinding.maskedKey || "已绑定")}</strong></div></div>
        <p class="byok-usage-note">该账户的生成走你自己的 Key，成本由你与模型方结算，Muse 不再计免费额度。</p>
        <div class="style-anchor-actions"><button class="secondary-button" type="button" data-byok-replace>更换 Key</button><button class="primary-button" type="button" data-byok-unbind>解绑</button></div>
      </section>`;
  }
  // 未绑定 / 更换态：输入框 + provider 三选（带 data-provider）+ 保存。
  const providers = [
    { value: "deepseek", label: "DeepSeek" },
    { value: "claude", label: "Claude" },
    { value: "custom", label: "自定义" },
  ];
  const providerButtons = providers
    .map(
      (p) =>
        `<button type="button" class="byok-provider-option${byokSelectedProvider === p.value ? " is-current" : ""}" data-provider="${p.value}">${p.label}</button>`,
    )
    .join("");
  return `<section class="byok-panel">
        <div class="field"><div class="field-head"><label for="byok-key">API Key</label><span class="field-note">提交后加密存储，仅回显掩码</span></div><input class="input" id="byok-key" type="password" placeholder="sk-..." value="${escapeHtml(byokKeyDraft)}" autocomplete="off" /></div>
        <div class="byok-provider"><span>模型提供方</span><div class="byok-provider-options">${providerButtons}</div></div>
        <p class="byok-usage-note">绑定后，该账户的生成走你自己的 Key，成本由你与模型方结算，Muse 不再计免费额度。密钥经 AES-GCM 加密存储、绝不回显明文。</p>
        <div class="style-anchor-actions">${bound ? `<button class="secondary-button" type="button" data-byok-replace-cancel>取消</button>` : ""}<button class="primary-button" type="button" data-byok-save ${byokKeyDraft.trim() ? "" : "disabled"}>保存并启用 <span>→</span></button></div>
      </section>`;
}

function bindByokInteractions() {
  document.querySelectorAll("[data-byok-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      byokTab = button.getAttribute("data-byok-tab");
      // 切 tab 复位更换态（review 复审 patch#3）：防已绑定用户点「更换 Key」后切走再
      // 切回仍停在半途重填表单，应回到已绑定摘要态。
      byokReplaceMode = false;
      byokKeyDraft = "";
      renderByok();
    });
  });
  // error 态重新加载：重置 loading 触发重拉（仿作品库 data-reload）。
  document.querySelector("[data-byok-reload]")?.addEventListener("click", () => {
    byokLoadState = "loading";
    renderByok();
  });
  const key = document.querySelector("#byok-key");
  key?.addEventListener("input", () => {
    byokKeyDraft = key.value;
    const save = document.querySelector("[data-byok-save]");
    // 保存在途（byokSaving）时不重新 enable，防在途打字把按钮放行触发并发双 PUT
    // （review 复审 patch#1）。
    if (save && !byokSaving) save.disabled = !key.value.trim();
  });
  document.querySelectorAll(".byok-provider-option").forEach((button) => {
    button.addEventListener("click", () => {
      document
        .querySelectorAll(".byok-provider-option")
        .forEach((other) => other.classList.remove("is-current"));
      button.classList.add("is-current");
      byokSelectedProvider = button.getAttribute("data-provider") || "deepseek";
    });
  });
  // 「更换 Key」：已绑定态切到重填态（显输入框 + provider）。
  document.querySelector("[data-byok-replace]")?.addEventListener("click", () => {
    byokReplaceMode = true;
    byokKeyDraft = "";
    renderByok();
  });
  // 「取消更换」：回到已绑定展示态。
  document
    .querySelector("[data-byok-replace-cancel]")
    ?.addEventListener("click", () => {
      byokReplaceMode = false;
      byokKeyDraft = "";
      renderByok();
    });
  bindByokSave();
  bindByokUnbind();
}

// 保存/替换：真实 PUT /api/byok（AC2）。成功→回填绑定态显掩码；失败→恢复按钮 + 可读提示。
function bindByokSave() {
  document.querySelector("[data-byok-save]")?.addEventListener("click", (event) => {
    const save = event.currentTarget;
    if (save.disabled) return;
    const input = document.querySelector("#byok-key");
    const apiKey = input ? input.value : "";
    // 空白前端软校验（后端 min_length=1 + strip 判空兜底，此处防无意义请求）。
    if (!apiKey.trim()) {
      save.disabled = true;
      return;
    }
    const provider = byokSelectedProvider || "deepseek";
    save.disabled = true;
    byokSaving = true; // 提交中：阻止 input 监听在途重新 enable 按钮（review 复审 patch#1）。
    const labelNode = save.childNodes[0];
    labelNode.textContent = "保存中… ";
    // 时序守卫（review P1）：记录发起时 hash，回调写 DOM 前校验仍在设置页，
    // 防用户点保存后立即切走、回调把别的页面 innerHTML 覆盖成 BYOK 页。
    const startedHash = hashPath();
    (async () => {
      try {
        const result = await byokApi.bind({ apiKey, provider });
        // 缺关键字段兜底假绑定会误导（review P4，同 7.3 P4「响应缺 id」）：
        // 后端契约保证 200 返完整 ByokStatusResponse，缺 bound 视为不可信响应，走失败分支。
        if (!result || !result.bound) {
          throw new ApiError(
            "invalid_response",
            "服务器返回了无法识别的绑定结果。",
            undefined,
            200,
          );
        }
        // 成功：更新绑定态、清草稿、退出更换态，切回 byok tab 展示掩码 + 重拉用量。
        byokBinding = result;
        byokKeyDraft = "";
        byokReplaceMode = false;
        byokSelectedProvider = result.provider || provider;
        // 用量口径随之变（转 BYOK 豁免态）：重拉一次 usage 保持展示一致。
        try {
          usageView = await usageApi.view();
        } catch {
          usageView = null; // 用量刷新失败不阻断绑定成功呈现（paintHostedPanel 显占位）。
        }
        // 切走则不写 DOM（回调竞态守卫）。
        if (hashPath() !== startedHash) return;
        renderByok();
      } catch (err) {
        // 401 已被 apiFetch 兜住（clearTokens + 跳登录），本页不重复弹窗（review P2）。
        if (err && err.status === 401) return;
        // 切走则不弹 alert / 不写已摘除按钮（回调竞态守卫，review P1）。
        if (hashPath() !== startedHash) return;
        // 失败恢复按钮 + 提示（error code 映射，不臆造分支）。
        save.disabled = false;
        labelNode.textContent = "保存并启用 ";
        window.alert(byokErrorText(err));
      } finally {
        // 无论成功/失败/切走早返，都解除在途标志（成功已重绘为绑定态、无输入框亦无害）。
        byokSaving = false;
      }
    })();
  });
}

// 解绑：真实 DELETE /api/byok（AC5）。成功→回未绑定空态 + 重拉用量（hosted 额度重新适用）。
function bindByokUnbind() {
  document.querySelector("[data-byok-unbind]")?.addEventListener("click", (event) => {
    const btn = event.currentTarget;
    if (btn.disabled) return;
    btn.disabled = true;
    btn.textContent = "解绑中…";
    const startedHash = hashPath(); // 时序守卫（review P1）
    (async () => {
      try {
        await byokApi.unbind();
        // 成功：清绑定态、重拉用量（从 BYOK 豁免态切回 hosted 真实额度）。
        byokBinding = { bound: false };
        byokKeyDraft = "";
        byokReplaceMode = false;
        byokSelectedProvider = "deepseek";
        try {
          usageView = await usageApi.view();
        } catch {
          usageView = null;
        }
        if (hashPath() !== startedHash) return; // 切走则不写 DOM
        renderByok();
      } catch (err) {
        if (err && err.status === 401) return; // 401 由 apiFetch 兜住，本页不重复弹窗（P2）
        if (hashPath() !== startedHash) return; // 切走则不弹 alert（P1）
        btn.disabled = false;
        btn.textContent = "解绑";
        window.alert(byokErrorText(err));
      }
    })();
  });
}

function renderReadthrough() {
  const totalChapters = readthroughChapters.length;
  // 越界保护：选章/翻页后索引始终落在合法范围内。
  readthroughChapterIndex = Math.min(
    Math.max(0, readthroughChapterIndex),
    totalChapters - 1,
  );
  const chapter = readthroughChapters[readthroughChapterIndex];
  const pages = readthroughPages(chapter);
  readthroughPageIndex = Math.min(
    Math.max(0, readthroughPageIndex),
    pages.length - 1,
  );
  const chapterNo = String(readthroughChapterIndex + 1).padStart(2, "0");
  const pageNo = String(readthroughPageIndex + 1).padStart(2, "0");
  const pageTotal = String(pages.length).padStart(2, "0");
  // 是否处于全书首页 / 末页，用于禁用翻页按钮。
  const atBookStart =
    readthroughChapterIndex === 0 && readthroughPageIndex === 0;
  const atBookEnd =
    readthroughChapterIndex === totalChapters - 1 &&
    readthroughPageIndex === pages.length - 1;
  const prose = pages[readthroughPageIndex]
    .map((paragraph) => `<p>${escapeHtml(paragraph)}</p>`)
    .join("");
  const chapterOptions = readthroughChapters
    .map(
      (item, index) =>
        `<option value="${index}" ${index === readthroughChapterIndex ? "selected" : ""}>第 ${String(index + 1).padStart(2, "0")} 章 · ${escapeHtml(item.title)}</option>`,
    )
    .join("");
  document.title = `通读 · ${chapter.title} · Muse`;
  app.innerHTML = `<div class="readthrough-page">
    <header class="explore-header readthrough-header"><a class="explore-back" href="#/projects/demo/archive">← 故事档案</a><div class="explore-project"><strong>${escapeHtml(explorationTitle)}</strong><span>通读</span></div></header>
    <main class="readthrough-main">
      <article class="readthrough-reader" aria-live="polite">
        <div class="readthrough-chapter-meta"><span>第 ${chapterNo} 章</span><i></i><span>共 ${String(totalChapters).padStart(2, "0")} 章</span></div>
        <div class="readthrough-title-select">
          <h1 class="readthrough-chapter-title">${escapeHtml(chapter.title)}<span class="readthrough-title-caret" aria-hidden="true">▾</span></h1>
          <select class="readthrough-title-picker" data-readthrough-chapter aria-label="切换章节">${chapterOptions}</select>
        </div>
        <div class="readthrough-reading-frame">
          <button class="readthrough-page-turn is-previous" type="button" data-readthrough-page="previous" aria-label="上一页" ${atBookStart ? "disabled" : ""}>←</button>
          <div class="readthrough-prose">${prose}</div>
          <button class="readthrough-page-turn is-next" type="button" data-readthrough-page="next" aria-label="下一页" ${atBookEnd ? "disabled" : ""}>→</button>
        </div>
        <footer class="readthrough-pagination"><span>本章 <strong>${pageNo}</strong> / ${pageTotal}</span></footer>
      </article>
    </main>
  </div>`;
  bindReadthroughInteractions();
}

function bindReadthroughInteractions() {
  document
    .querySelector("[data-readthrough-chapter]")
    ?.addEventListener("change", (event) => {
      readthroughChapterIndex = Number(event.currentTarget.value);
      readthroughPageIndex = 0;
      renderReadthrough();
    });
  document.querySelectorAll("[data-readthrough-page]").forEach((button) => {
    button.addEventListener("click", () => {
      const direction = button.getAttribute("data-readthrough-page");
      const pages = readthroughPages(
        readthroughChapters[readthroughChapterIndex],
      );
      if (direction === "next") {
        if (readthroughPageIndex < pages.length - 1) {
          readthroughPageIndex += 1;
        } else if (readthroughChapterIndex < readthroughChapters.length - 1) {
          // 翻过本章末页 → 进入下一章第一页（跨章连续通读）。
          readthroughChapterIndex += 1;
          readthroughPageIndex = 0;
        }
      } else {
        if (readthroughPageIndex > 0) {
          readthroughPageIndex -= 1;
        } else if (readthroughChapterIndex > 0) {
          // 从本章首页往前 → 回到上一章末页。
          readthroughChapterIndex -= 1;
          readthroughPageIndex =
            readthroughPages(readthroughChapters[readthroughChapterIndex])
              .length - 1;
        }
      }
      renderReadthrough();
    });
  });
}

function renderStyleAnchor() {
  const state = queryState();
  const anchored = state === "anchored";
  const activeSample =
    styleSampleLibrary.find((sample) => sample.id === styleAnchorSelected) ||
    null;
  const canExtract = styleAnchorTab === "paste"
    ? styleAnchorPasteText.trim().length >= 20
    : Boolean(activeSample);
  document.title = "锚定文风 · Muse";
  app.innerHTML = `<div class="style-anchor-page">
    <header class="explore-header"><a class="explore-back" href="#/projects/demo/explore">← 故事设定</a><div class="explore-project"><strong>${escapeHtml(explorationTitle)}</strong><span>文风锚点</span></div><div class="save-state"><i></i> ${anchored ? "文风已锚定" : "尚未锚定"}</div></header>
    <main class="style-anchor-main">
      <section class="style-anchor-intro">
        <div class="style-anchor-overline">Style anchor / 文风锚点</div>
        <h1>先告诉我，你想要的味道</h1>
        <p>选一段你爱读的文字，或粘贴一段你心里的范文。系统会抽取它的文风特征，作为这本书正文的锚——之后每一章都会贴着它写，去掉那股 AI 腔。</p>
      </section>
      ${anchored ? `<section class="style-anchor-result" aria-live="polite">
        <div class="style-anchor-result-head"><span>已锚定文风</span><strong>${activeSample ? escapeHtml(activeSample.name) : "自定义样本"}</strong></div>
        ${styleAnchorProfileMarkup(styleAnchorResult || (activeSample ? activeSample.profile : styleSampleLibrary[0].profile))}
        <div class="style-anchor-actions"><button class="secondary-button" data-style-reset>重新选择</button><a class="primary-button" href="#/projects/demo/chapters/1">带着这个文风开始写 <span>→</span></a></div>
      </section>` : `<section class="style-anchor-picker">
        <div class="tabs" role="tablist" aria-label="文风锚定方式">
          <button class="tab" role="tab" aria-selected="${styleAnchorTab === "library"}" data-style-tab="library">从样本库选</button>
          <button class="tab" role="tab" aria-selected="${styleAnchorTab === "paste"}" data-style-tab="paste">粘贴我的范文</button>
        </div>
        ${styleAnchorTab === "library" ? `<ul class="style-sample-list">${styleSampleLibrary
          .map(
            (sample) =>
              `<li><button type="button" class="style-sample-card ${styleAnchorSelected === sample.id ? "is-current" : ""}" data-style-sample="${sample.id}"><div class="style-sample-head"><strong>${escapeHtml(sample.name)}</strong><span>${escapeHtml(sample.note)}</span></div><p>${escapeHtml(sample.excerpt)}</p></button></li>`,
          )
          .join("")}</ul>` : `<div class="field style-paste-field"><div class="field-head"><label for="style-paste">粘贴一段范文</label><span class="field-note">至少 20 字</span></div><textarea class="input" id="style-paste" placeholder="贴一段你希望这本书读起来像的文字……">${escapeHtml(styleAnchorPasteText)}</textarea></div>`}
        <div class="style-anchor-actions"><button class="primary-button" type="button" data-style-extract ${canExtract ? "" : "disabled"}>抽取文风 <span>→</span></button></div>
      </section>`}
      <details class="state-preview"><summary>原型状态预览</summary><div class="preview-links"><a class="preview-link" href="#/projects/demo/style-anchor">未锚定</a><a class="preview-link" href="#/projects/demo/style-anchor?state=anchored">已锚定</a></div></details>
    </main>
  </div>`;
  bindStyleAnchorInteractions();
}

function bindStyleAnchorInteractions() {
  document.querySelectorAll("[data-style-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      styleAnchorTab = button.getAttribute("data-style-tab");
      renderStyleAnchor();
    });
  });
  document.querySelectorAll("[data-style-sample]").forEach((button) => {
    button.addEventListener("click", () => {
      styleAnchorSelected = button.getAttribute("data-style-sample");
      renderStyleAnchor();
    });
  });
  const paste = document.querySelector("#style-paste");
  paste?.addEventListener("input", () => {
    styleAnchorPasteText = paste.value;
    const extract = document.querySelector("[data-style-extract]");
    if (extract) extract.disabled = paste.value.trim().length < 20;
  });
  document
    .querySelector("[data-style-extract]")
    ?.addEventListener("click", () => {
      const activeSample = styleSampleLibrary.find(
        (sample) => sample.id === styleAnchorSelected,
      );
      styleAnchorResult = activeSample
        ? activeSample.profile
        : {
            person: "第一人称",
            tone: "紧凑、口语",
            rhythm: "短句偏多",
            imagery: "中",
            paragraph: "偏短",
          };
      location.hash = "#/projects/demo/style-anchor?state=anchored";
    });
  document.querySelector("[data-style-reset]")?.addEventListener("click", () => {
    styleAnchorSelected = null;
    styleAnchorResult = null;
    location.hash = "#/projects/demo/style-anchor";
  });
}

function render() {
  document.body.classList.remove("dialog-open");
  const exploreMatch = hashPath().match(/^#\/projects\/([^/]+)\/explore$/);
  const chapterMatch = hashPath().match(
    /^#\/projects\/([^/]+)\/chapters\/(\d+)$/,
  );
  const archiveMatch = hashPath().match(/^#\/projects\/([^/]+)\/archive$/);
  // review R2 P2：离开探索页时清理在途 SSE + 门禁（teardownExplorationInflight 原为死代码，此处挂载）。
  // 防 settle/interpret 在途时切走 → 流不 abort 连接悬挂 + 陈旧回调污染。teardown 不动 pending
  // 设定卡（会话内恢复态，导航离开应保留）。进 explore 分支由 loadGuidedExploration 自管清理。
  if (!exploreMatch) teardownExplorationInflight();
  if (hashPath() === "#/projects") {
    // 每次进入作品库都重新拉取最新列表（新建/改名/删除后返回能看到变化）。
    projectsLoadState = "loading";
    renderProjects();
  } else if (hashPath() === "#/projects/demo/style-anchor") renderStyleAnchor();
  else if (hashPath() === "#/projects/demo/readthrough") renderReadthrough();
  else if (hashPath() === "#/settings/model-access") {
    // 每次进入设置页都重拉最新绑定态 + 用量（绑定/解绑后返回、跨账号都能看到变化）。
    byokLoadState = "loading";
    renderByok();
  }
  else if (hashPath() === "#/projects/demo/stage-direction")
    renderStageDirection();
  else if (exploreMatch) {
    // Story 7.5：进引导探索页须建会话 + 回填已答（异步）。记录路由 projectId 供
    // 落库/settle 复用（替换 deferred-work.md:42「explore 目标页未消费路由 id」）。
    // 自由模式（7.6 未接）仍走 mock，不触发引导后端加载。
    const routeProjectId = exploreMatch[1];
    // review R2 P2/F7：进 explore 页先统一清理上一项目残留在途流 + 复位作答门禁（saving）。
    // 覆盖三条子分支（pending 恢复 / 引导加载 / 自由）——尤其 pending 恢复分支不走
    // loadGuidedExploration，若无此清理，A interpret 在途时导航到有 pending 卡的 B → saving
    // 卡死 + 旧流不 abort。teardown 幂等且不动 pending 卡（会话内恢复态保留）。
    teardownExplorationInflight();
    // review R2 D1：从路由项目派生 entryMode，不信残留 sessionStorage 值（防模式错配）。
    // projects 已加载且命中该项目时以其真实 mode 为准；找不到（直接 URL 访问 / 列表未加载）
    // 才回退残留值（继续创作路径已在 data-continue 按 project.mode 校准，此处双保险）。
    const routeProject = projects.find((p) => p.id === routeProjectId);
    if (routeProject) {
      explorationEntryMode = routeProject.mode === "free" ? "free" : "guided";
      window.sessionStorage.setItem(
        explorationEntryModeKey,
        explorationEntryMode,
      );
    }
    if (explorationEntryMode !== "free") {
      // 待确认设定卡刷新恢复优先（AC7）：pending 态直接渲染（renderExploration 末尾重挂弹窗），
      // 无需重拉后端（settle 结果已在 sessionStorage）。仅非 pending 时才建会话 + 回填。
      if (pendingStoryProfile && finalStoryProfile) {
        explorationProjectId = routeProjectId;
        guidedLoadState = "ready";
        renderExploration();
      } else {
        loadGuidedExploration(routeProjectId);
      }
    } else {
      loadFreeExploration(routeProjectId);
    }
  } else if (archiveMatch) {
    const archiveProject = projects.find(
      (project) => project.id === archiveMatch[1],
    );
    if (archiveProject) explorationTitle = archiveProject.title;
    renderChapterArchive();
  } else if (chapterMatch) {
    chapterCreationIndex = Math.max(0, Number(chapterMatch[2]) - 1);
    renderChapterCreation();
  } else renderAuth();
}

window.MUSE_SCREENSHOTS = [
  { file: "01-login.png", hash: "#/login", width: 1440, height: 1100 },
  { file: "02-register.png", hash: "#/register", width: 1440, height: 1100 },
  { file: "03-projects.png", hash: "#/projects", width: 1440, height: 1100 },
  {
    file: "04-projects-empty.png",
    hash: "#/projects?state=empty",
    width: 1440,
    height: 1100,
  },
  {
    file: "05-mobile-projects.png",
    hash: "#/projects",
    width: 390,
    height: 1200,
  },
  {
    file: "06-exploration.png",
    hash: "#/projects/demo/explore?state=conversation",
    width: 1440,
    height: 1100,
  },
  {
    file: "07-chapter-archive.png",
    hash: "#/projects/demo/archive",
    width: 1440,
    height: 1100,
  },
];

window.addEventListener("hashchange", render);
if (!location.hash) location.hash = "#/login";
render();

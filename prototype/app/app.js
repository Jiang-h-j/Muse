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
// freeMessageQueue：Agent 处理在途时用户继续发送的排队消息（通常 0-1 条）。输入框/发送
// 按钮不再因 freeMessageSending 锁死——点发送即视觉发出、清空输入框；若上一轮还没跑完
// 全部收尾步骤（消息同步/线索刷新/导航刷新），本条文本先入队，待收尾后自动继续发送。
let freeMessageQueue = [];
// freeMessageBusyLabel：非空时在对话区下方展示进度提示（如“Agent 正在思考…”），不阻塞输入。
let freeMessageBusyLabel = "";
let freeSettlePending = false;
let freeSettleErrorText = "";
let freeClueEditingIds = new Map();
let freeClueFocusedIds = new Set();
let deferredFreeClues = null;
// Story 2.8 消费（Correct Course 替换旧版「给方向」+「≥1条消息」门禁，2026-08-03 合并重构后
// 再次调整）：自由探索导航状态，完成度/当前追问字段/候选回复/就绪位恒以后端
// GuidanceStateResponse 为准，前端不本地推断。**不再有 currentQuestion**——聊天记录本身
// 就是唯一的问题事实源，候选回复（currentSuggestions）贴在最新一条 Agent 消息下方展示。
let guidanceFields = {};
let guidanceCurrentField = null;
// guidanceSuggestions：随每轮对话/开场/跳过一起从后端拿到，不再需要单独请求生成。
let guidanceSuggestions = [];
// guidanceSuggestionsExpanded：纯前端 UI 态，控制候选回复默认收起/点击展开，不发请求。
let guidanceSuggestionsExpanded = false;
let guidanceReadyToSettle = false;
let guidanceSkipping = false;
// guidanceSkipSeq：跳过操作的序号，每次 skipFreeGuidanceQuestion 递增。收尾里的
// refreshGuidance 若发现序号已变（期间发生过跳过），放弃 apply——避免跳过刚写入的新 state
// 被收尾里挂起的旧 GET guidance 结果覆盖回跳过前的状态。
let guidanceSkipSeq = 0;
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
// Story 4.7：当前所处阶段的「首章全局章号偏移」（0-based）。首阶段=0；进入第 k 阶段时 = 之前
// 各阶段章数之和。章渲染用「全局 chapterCreationIndex - stageChapterOffset」取当前阶段章列表
// 的相对索引（currentStagePlan.chapters 每阶段各自从 0 起）。GET stage-plan 取最新阶段
// （后端已改），chapters 即当前阶段章骨架；阶段末章判断用 相对序号+1 == chapters.length。
// 持久化按 projectId 存 sessionStorage，刷新/重进恢复（否则跨阶段刷新会误用 offset=0 越界）。
let stageChapterOffset = 0;
const stageOffsetKey = "muse-stage-offset";
function readStageOffset(projectId) {
  const stored = readStoredJson(stageOffsetKey);
  if (stored && stored.projectId === projectId && Number.isInteger(stored.offset))
    return stored.offset;
  return 0;
}
function persistStageOffset(projectId, offset) {
  window.sessionStorage.setItem(
    stageOffsetKey,
    JSON.stringify({ projectId, offset }),
  );
}
function clearStageOffset() {
  window.sessionStorage.removeItem(stageOffsetKey);
}
// Story 4.3：章节页真实 projectId（替换硬编码 demo）+ 阶段规划幕后加载态。
let chapterProjectId = "";
let stagePlanLoadState = "idle"; // idle | loading | ready | error | empty(未生成、待用户明示触发)
let stagePlanErrorText = "";
let stagePlanAbortController = null;
let stagePlanSeq = 0; // 拉取/生成代次，防在途赛跑（仿 guidedLoadSeq）
// Story 4.3（review 改时机）：阶段规划触发点从「进页面」挪到「确认设定成功那一次」（一次性事件、
// 天然不重复）。触发后把 {projectId, taskId} 存 sessionStorage；刷新/重进第一章时凭它接回**正在
// 跑的那个任务**的 SSE（后端 sse.py 快照补发支持晚订阅），而非再叫一次生成——从根上杜绝重复触发/
// 重复付费（不需加锁）。进页面查库空且无在途 taskId 时，只显示「未生成」态、由用户明示点「生成」才触发。
const stagePlanTaskKey = "muse-stage-plan-task";
function readStagePlanTask(projectId) {
  const stored = readStoredJson(stagePlanTaskKey);
  if (stored && stored.projectId === projectId && stored.taskId) return stored.taskId;
  return null;
}
function persistStagePlanTask(projectId, taskId) {
  window.sessionStorage.setItem(
    stagePlanTaskKey,
    JSON.stringify({ projectId, taskId }),
  );
}
function clearStagePlanTask() {
  window.sessionStorage.removeItem(stagePlanTaskKey);
}
// Story 4.4：章节正文真实生成态（替换 1200ms mock）。仿 stage-plan 的代次 + AbortController
// 三守卫（seq/projectId/abort）。生成流触发后把 {projectId, chapterNumber, taskId} 存
// sessionStorage；刷新/重进凭它接回**正在跑的那个任务**的 SSE（后端快照补发支持晚订阅），而非
// 再叫一次生成——杜绝重复触发/重复付费。chapterGeneratedText 存 SSE result/GET 恢复的终稿正文。
let chapterGenAbortController = null;
let chapterGenSeq = 0;
let chapterGeneratedText = "";
// 记录「本章正文态已恢复到哪一章」（projectId:chapterNumber）——route 分支据此判断跨章跳转是否
// 需要重新恢复正文态（同章内部重渲染直接渲染，跨章须 recoverChapterState 拉新章正文/接在途）。
let chapterRecoveredKey = "";
const chapterGenTaskKey = "muse-chapter-gen-task";
// Story 4.6 review：存储在途任务时带 kind（"gen" 首次生成 / "revise" 改进重生）+ action
// （revise 的 improve/regenerate，供刷新恢复时用对消费者、显示正确忙碌文案）。返回整个记录对象
// （非仅 taskId），调用方按 kind 分派——修订在途刷新须接回 revise SSE、不被 GET 到的旧正文短路。
function readChapterGenTask(projectId, chapterNumber) {
  const stored = readStoredJson(chapterGenTaskKey);
  if (
    stored &&
    stored.projectId === projectId &&
    stored.chapterNumber === chapterNumber &&
    stored.taskId
  )
    return stored;
  return null;
}
function persistChapterGenTask(
  projectId,
  chapterNumber,
  taskId,
  kind = "gen",
  action = null,
) {
  window.sessionStorage.setItem(
    chapterGenTaskKey,
    JSON.stringify({ projectId, chapterNumber, taskId, kind, action }),
  );
}
function clearChapterGenTask() {
  window.sessionStorage.removeItem(chapterGenTaskKey);
}
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
// Story 4.7：下一阶段规划触发态（阶段交界页「带方向写下去/直接继续/收尾」提交后异步生成）。
// idle=卡片输入态；loading=规划中 spinner；error=失败退回卡片+错误文案。复用 stagePlanSeq/
// stagePlanAbortController 做代次+abort 守卫（同一章节创作域）。task 存 sessionStorage 供刷新接回。
let nextStageLoadState = "idle"; // idle | loading | error
let nextStageErrorText = "";
const nextStageTaskKey = "muse-next-stage-task";
function readNextStageTask(projectId) {
  const stored = readStoredJson(nextStageTaskKey);
  if (stored && stored.projectId === projectId && stored.taskId) return stored.taskId;
  return null;
}
function persistNextStageTask(projectId, taskId) {
  window.sessionStorage.setItem(
    nextStageTaskKey,
    JSON.stringify({ projectId, taskId }),
  );
}
function clearNextStageTask() {
  window.sessionStorage.removeItem(nextStageTaskKey);
}
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
// Story 7.7：设定卡字段编辑落库的在途去合并（仿 7.6 freeClueEditingIds）：同一字段 blur 落库
// 在途时再次 blur 只更新排队值、不并发双 PATCH；key 为字段 camelCase key。
let profileFieldEditing = new Map();
// 反馈升版本 / 确认 / 丢弃的在途标志：防按钮在途被重复触发产生并发请求。
let profileReviseBusy = false;
let profileConfirmBusy = false;
let profileDiscardBusy = false;
// 文风锚点抽取在途标志（Task 6）。
let styleAnchorSaving = false;
let styleAnchorErrorText = "";
// #6：文风抽取代次守卫。discard/切作品时递增，使在途 anchorStyle/editProfile 回调识别到
// 「卡已丢弃」而不重挂已关闭的弹窗（hash/projectId 守卫挡不住同页内 discard 的情形）。
let styleAnchorSeq = 0;
// Story 7.7：设定卡内文风锚点入口从后端拉取的真实样本库（GET style-anchor/samples）。
// null=未拉取（含拉取失败，保持 null 以允许重试，#4）；[]=已拉取且后端确为空。
let styleAnchorSamples = null;
let styleAnchorSamplesLoading = false;
// 设定卡内文风锚点区展开态（默认收起，避免抢占 12 字段编辑焦点）。
let styleAnchorPanelOpen = false;

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

// Story 7.7：设定卡 + 文风锚点端点的 error code → 中文提示映射（仿 explorationErrorText）。
// 只按 err.code 判定（后端恒字符串）。no_pending_card 含「确认后对 confirmed 行再编辑/反馈」的
// 情形（后端 get_pending_by_project 只查 status='pending'，无独立 already_confirmed 码，AC8）。
function storyErrorText(err) {
  const code = err && err.code;
  switch (code) {
    case "no_pending_card":
      return "没有待确认的设定卡，请先整理故事设定。";
    case "unknown_style_sample":
      return "所选文风样本不存在。";
    case "generate_failed":
      return "生成失败，请稍后重试。";
    case "bible_not_confirmed":
      return "请先确认故事设定，再开始创作章节。";
    case "quota_exceeded":
      return "已用完当前免费额度。可到设置页绑定自己的 API Key 后继续。";
    case "project_not_found":
      return "找不到这部作品，请回到作品库重试。";
    // Story 4.7 review patch F11：定稿 / 下一阶段规划相关错误码（后端 ErrorEnvelope 透传 code）。
    case "no_stage_plan":
      return "还没有阶段规划，无法进入下一阶段。请先回到章节继续创作。";
    case "chapter_not_generated":
      return "本章还没有正文，请先生成再定稿。";
    case "chapter_out_of_range":
      return "章号超出范围，请回到章节页重试。";
    case "chapter_already_finalized":
      return "本章已定稿，无法再改进或重新生成。";
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
  freeMessageQueue = [];
  freeMessageBusyLabel = "";
  freeSettlePending = false;
  // Story 2.8 导航状态的提交门禁（无 AbortController，均是常规 apiFetch）：teardown 后
  // isCurrentFreeExploration 会因代次不匹配丢弃在途回调的状态写入，但 finally 里的门禁
  // 复位同样会被挡住——须在此显式复位，否则重进该项目后按钮永久卡在 disabled。
  guidanceStartingEntry = null;
  guidanceSkipping = false;
  // Story 7.7：复位设定卡/文风锚点操作的在途门禁（均是常规 apiFetch，无 AbortController）。
  // 与 saving 门禁同理——teardown 后代次/hash 校验会丢弃在途回调的状态写入，但门禁复位也会被挡，
  // 须显式复位，否则重进后按钮永久卡 disabled。pending 卡本身是会话内恢复态、此处不清（logout 才清）。
  profileFieldEditing.clear();
  profileReviseBusy = false;
  profileConfirmBusy = false;
  profileDiscardBusy = false;
  styleAnchorSaving = false;
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

// Story 7.7：进探索页时以后端 GET /story-profile 为待确认卡的权威来源（AC1/AC7/AC8）。
// sessionStorage 缓存卡先即时渲染（刷新无闪烁），再 GET 对账：
//   · 后端返卡 → openStoryProfileFromBackend 用权威卡覆盖（含最新 revision/changedFields/status）。
//   · 后端 204（卡已确认/丢弃，可能发生在别的标签页）→ 清陈旧 pending 缓存，回落正常探索加载。
//   · GET 失败（非 401，401 已由 apiFetch 跳登录）→ 保留缓存卡，不打断本地恢复。
// hash + explorationProjectId 双守卫（同 7.5/7.6 时序范式），防用户切走 / 换作品后旧回调污染。
function reconcilePendingStoryProfile(projectId) {
  const startedHash = location.hash;
  (async () => {
    let card;
    try {
      card = await storyApi.getProfile(projectId);
    } catch {
      return;
    }
    if (location.hash !== startedHash || explorationProjectId !== projectId) return;
    if (card) {
      openStoryProfileFromBackend(card);
    } else {
      pendingStoryProfile = false;
      finalStoryProfile = null;
      finalStoryProfileSignature = "";
      lastProfileChangedFields = [];
      profileFeedbackStatus = "";
      clearPendingStoryProfile();
      closeStoryProfileDialog();
      if (explorationEntryMode !== "free") loadGuidedExploration(projectId);
      else loadFreeExploration(projectId);
    }
  })();
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
// 把后端 GuidanceStateResponse（Story 2.8，2026-08-03 合并重构）写入前端导航态；
// currentField 变化即视为新一问，收起上一问遗留的候选回复展开态（新问题的候选默认也是
// 收起的，避免用户还没读新问题就先看到一堆候选回答）。
function applyGuidanceState(state) {
  const nextField = (state && state.currentField) || null;
  if (nextField !== guidanceCurrentField) guidanceSuggestionsExpanded = false;
  guidanceFields = (state && state.fields) || {};
  guidanceCurrentField = nextField;
  guidanceSuggestions = Array.isArray(state && state.currentSuggestions)
    ? state.currentSuggestions
    : [];
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

async function refreshGuidance(projectId, seq, startedHash, skipSeqSnapshot) {
  const state = await explorationApi.getGuidance(projectId);
  if (!isCurrentFreeExploration(projectId, seq, startedHash)) return false;
  // 收尾的 GET guidance 可能在跳过之后才返回——此时跳过已 apply 了最新 state，
  // 这里若再 apply 旧 state 会覆盖回跳过前。检测到期间发生过跳过就放弃。
  if (skipSeqSnapshot !== undefined && skipSeqSnapshot !== guidanceSkipSeq) return false;
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
    // 开场问题已落库为真实 agent 聊天消息（2026-08-03 合并重构）：必须重新拉取对话
    // 历史才能让它出现在聊天框里，仅更新导航状态（applyGuidanceState）不会带出新消息。
    await syncFreeMessages(projectId, seq, startedHash);
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

// 按需回答思路（AC4，2026-08-03 合并重构后）：候选回复随每轮对话/开场/跳过同一次 LLM
// 调用生成好，前端只是本地展开/收起，不发任何请求——点击「没想好？看看几个思路」瞬间显示。
function toggleGuidanceSuggestions() {
  guidanceSuggestionsExpanded = !guidanceSuggestionsExpanded;
  renderExploration();
}

// 跳过当前问题（AC6）：标记该字段 skipped，原地刷新导航状态（可能是下一问，也可能是收束
// 态，均已随后端响应带上新的候选回复）。不调用 submitFreeMessage、不新增对话消息。
async function skipFreeGuidanceQuestion() {
  if (
    guidanceSkipping ||
    !explorationProjectId ||
    !guidanceCurrentField
  )
    return;
  const projectId = explorationProjectId;
  const seq = freeLoadSeq;
  const startedHash = location.hash;
  // 递增跳过序号：让收尾里挂起的 refreshGuidance 检测到「跳过刚发生」后放弃 apply，
  // 避免它用跳过前的旧 state 覆盖跳过刚写入的新 state。跳过是独立 HTTP 端点，不依赖
  // freeMessageSending——收尾期间也允许点（用户在 Agent 刚说完话时最想跳过）。
  const skipSeq = ++guidanceSkipSeq;
  guidanceSkipping = true;
  renderExploration();
  try {
    const state = await explorationApi.skipGuidance(projectId);
    if (!isCurrentFreeExploration(projectId, seq, startedHash)) return;
    // 跳过后若还有下一问，后端会落库为真实 agent 聊天消息（2026-08-03 合并重构）；
    // 若已收束则不会有新消息。统一重新拉取一次对话历史，两种情况都覆盖，逻辑更简单。
    await syncFreeMessages(projectId, seq, startedHash);
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

// 提交自由对话一轮。输入框/发送按钮不因 freeMessageSending 锁死（真实聊天软件式体验）：
// 若上一轮仍在处理（含 SSE 消费完成后的消息同步/线索刷新/导航刷新收尾），本条文本先入队，
// 交由 finally 收尾时的 drainFreeMessageQueue 自动续发；队列里最多保留最新的排队消息，
// 不重复排队同一轮尚未处理的内容。
function submitFreeMessage(content) {
  const text = String(content || "").trim();
  if (!text || !explorationProjectId) return;
  if (freeMessageSending) {
    freeMessageQueue = [...freeMessageQueue, text];
    renderExploration();
    return;
  }
  return sendFreeMessageNow(text);
}

async function sendFreeMessageNow(text) {
  const projectId = explorationProjectId;
  const seq = freeLoadSeq;
  const startedHash = location.hash;
  // 捕获本轮开始时的跳过序号：收尾里 refreshGuidance 若发现序号变了（期间用户跳过过），
  // 就放弃 apply，避免用旧 state 覆盖跳过刚写入的新 state。
  const skipSeqSnapshot = guidanceSkipSeq;
  freeMessageSending = true;
  freeMessageBusyLabel = "Agent 正在思考…";
  freeSettleErrorText = "";
  freeConversation = [...freeConversation, { role: "user", text }];
  freeMessageAbortController = new AbortController();
  const signal = freeMessageAbortController.signal;
  let gotTerminal = false;
  let streamError = null;
  let agentText = "";
  let keepEditingDom = false;
  // 排队续发可能发生在用户正聚焦编辑线索输入框时；此时不重绘，避免打断输入
  // （用户消息气泡会随下一次 renderExploration 一起补上，不会丢）。
  if (!freeClueFocusedIds.size) renderExploration();
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
      freeMessageBusyLabel = "正在整理线索与下一个问题…";
      if (!freeClueFocusedIds.size) renderExploration();
      const messagesSynced = await syncFreeMessages(projectId, seq, startedHash);
      if (!messagesSynced) return;
      const cluesRefreshed = await refreshFreeClues(projectId, seq, startedHash);
      if (!cluesRefreshed) return;
      // AC3 第 3 步：后端 stream_free_chat 已在落库后同步调用 guidance_agent.refresh_guidance，
      // 此处重新 GET 一次即可拿到本轮判定后的当前具体问题/完成度/就绪位。失败不影响本轮已
      // 成功的对话与线索（同后端「主链路成功、副作用降级」的容忍粒度），静默保留旧导航态。
      // 传入 skipSeqSnapshot：若期间用户点了跳过，跳过已 apply 新 state，这里的旧 GET 结果
      // 放弃 apply，避免覆盖。
      await refreshGuidance(projectId, seq, startedHash, skipSeqSnapshot).catch(() => false);
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
    freeMessageBusyLabel = "";
    freeMessageAbortController = null;
    if (!keepEditingDom) renderExploration();
    if (streamError) showFreeInlineError(explorationErrorText(streamError));
    drainFreeMessageQueue();
  }
}

// 本轮收尾后若有排队消息，自动续发下一条（先进先出）；每次只取一条，续发完成后的
// finally 会再次调用本函数，从而顺序处理队列里剩余的排队消息。
function drainFreeMessageQueue() {
  if (freeMessageSending || !freeMessageQueue.length) return;
  const [next, ...rest] = freeMessageQueue;
  freeMessageQueue = rest;
  sendFreeMessageNow(next);
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

// Story 4.3：进第一章的阶段规划入口——先 GET 已落库规划，无则触发幕后生成 + SSE 消费。
// 幂等按 (projectId) 单守卫：同一作品重进复用已落库规划（重进不重生成，AC2）。
async function loadChapterStagePlan(projectId) {
  // 取消上一个在途流（切走/换项目防御），起新代次守卫。
  if (stagePlanAbortController) stagePlanAbortController.abort();
  stagePlanSeq += 1;
  const seq = stagePlanSeq;
  chapterProjectId = projectId;
  // P2：GET 恢复阶段也建 controller 并存入全局，让离页（render !chapterMatch）/登出能 abort、
  // 且 GET 带 signal 可中断——否则停在 GET 阶段切走时在途流不取消，回调仍继续触发多余生成 + 覆盖 DOM。
  if (stagePlanAbortController) stagePlanAbortController.abort();
  stagePlanAbortController = new AbortController();
  const signal = stagePlanAbortController.signal;
  const stale = () =>
    signal.aborted || seq !== stagePlanSeq || projectId !== chapterProjectId;

  // 先渲染加载态（chapterMatch 已把 index 设好；此时 currentStagePlan 可能是上一项目的残留）。
  currentStagePlan = null;
  stagePlanLoadState = "loading";
  stagePlanErrorText = "";
  // Story 4.4：重置章节生成态（防跨项目/跨章残留——如上一章 reading 态切到新项目第一章）。
  // 真实态由下方 recoverChapterState 按 GET 正文 / 在途任务重建。
  if (chapterGenAbortController) chapterGenAbortController.abort();
  chapterGenAbortController = null;
  chapterCreationState = "input";
  chapterGeneratedText = "";
  chapterIdea = "";
  renderChapterCreation();

  try {
    // 1. 先 GET 已落库的阶段规划（刷新/断线重进恢复，AC2）。
    const existing = await chapterApi.getStagePlan(projectId, { signal });
    if (stale()) return;
    if (existing && Array.isArray(existing.chapters) && existing.chapters.length) {
      currentStagePlan = existing;
      stagePlanLoadState = "ready";
      stagePlanAbortController = null;
      clearStagePlanTask(); // 已落库，在途 taskId 不再需要
      renderChapterCreation();
      // Story 4.4：阶段规划就绪后，恢复本章正文态（GET 已落库正文 → reading；否则接在途生成
      // 任务 / 显示 input）。不阻塞 stage-plan 渲染——先渲染骨架，再异步定 input/generating/reading。
      recoverChapterState(projectId, chapterCreationIndex + 1);
      return;
    }
    // existing 为 null = 204 未生成（GET 契约：无落库→204→apiFetch 返 null）。
  } catch (err) {
    if (stale()) return; // 被 abort（AbortError）/ 已切走：静默退出，不报错、不触发
    // P3：GET 抛 ApiError（404 租户/5xx/网络/invalid_response）≠「未生成」，不该重新触发生成
    // （已落库时真实错误重触发会重复付费）。判死为错误态、让用户重试，而非兜底触发。
    stagePlanAbortController = null;
    stagePlanLoadState = "error";
    stagePlanErrorText = storyErrorText(err);
    renderChapterCreation();
    return;
  }
  if (stale()) return;
  // 2. 未落库（204）——review 改时机：进页面**绝不主动叫新生成**。凭确认设定时存下的在途 taskId
  // 接回**正在跑的那个任务**的 SSE（后端快照补发支持晚订阅），从根上杜绝「进页面反复触发/重复付费」。
  const pendingTaskId = readStagePlanTask(projectId);
  if (pendingTaskId) {
    await consumeStagePlanTask(projectId, seq, pendingTaskId);
    return;
  }
  // 3. 既无落库、又无在途任务（确认时触发失败 / sessionStorage 丢失 / 关页重开）：显示未生成态，
  // 由用户明示点「生成阶段计划」才触发（renderChapterCreation empty 分支 + data-retry-stage-plan）。
  stagePlanAbortController = null;
  stagePlanLoadState = "empty";
  renderChapterCreation();
}

// 接回/消费一个已存在的阶段规划任务的 SSE（AC6，仿 startSettleFlow 的消费段）：GET
// /tasks/{id}/events 消费 progress/result/error。seq/projectId/abort 三守卫 + 无终态兜底 + 终态清
// 在途 taskId。**不发起 POST**——用于「刷新/重进凭本地 taskId 接回正在跑的那个任务」（后端快照
// 补发支持晚订阅）。复用当前 stagePlanAbortController（调用方已建），signal 随之被离页/登出 abort。
async function consumeStagePlanTask(projectId, seq, taskId) {
  const signal = stagePlanAbortController && stagePlanAbortController.signal;
  const stale = () =>
    (signal && signal.aborted) || seq !== stagePlanSeq || projectId !== chapterProjectId;
  let gotTerminal = false;
  try {
    await explorationApi.taskEvents(taskId, {
      signal,
      onEvent: (type, data) => {
        if (stale()) return;
        if (type === "result" && data && data.stagePlan) {
          gotTerminal = true;
          stagePlanAbortController = null;
          clearStagePlanTask();
          currentStagePlan = {
            stageNumber: data.stagePlan.stageNumber || 1,
            goal: data.stagePlan.goal || "",
            chapters: Array.isArray(data.stagePlan.chapters)
              ? data.stagePlan.chapters
              : [],
          };
          stagePlanLoadState = "ready";
          renderChapterCreation();
        } else if (type === "error") {
          gotTerminal = true;
          stagePlanAbortController = null;
          clearStagePlanTask();
          stagePlanLoadState = "error";
          stagePlanErrorText = storyErrorText({ code: data && data.code });
          renderChapterCreation();
        }
        // progress：加载态已在显示，V1 不额外更新（保持文案态）。
      },
    });
    // 无终态兜底（防永久 spinner，仿 startSettleFlow）：SSE 正常结束却没收到 result/error。
    if (!stale() && !gotTerminal && stagePlanLoadState === "loading") {
      stagePlanAbortController = null;
      clearStagePlanTask();
      stagePlanLoadState = "error";
      stagePlanErrorText = storyErrorText({ code: "generate_failed" });
      renderChapterCreation();
    }
  } catch (err) {
    if (stale()) return; // 用户主动 abort / 已切走，不报错
    stagePlanAbortController = null;
    clearStagePlanTask();
    stagePlanLoadState = "error";
    stagePlanErrorText = storyErrorText(err);
    renderChapterCreation();
  }
}

// 主动触发幕后阶段规划生成 + SSE 消费（AC1/AC6）：POST plan-stage 拿 taskId → 存 sessionStorage
// （刷新可接回）→ consumeStagePlanTask 消费 SSE。**仅用于用户明示触发**——确认设定成功时（一次性）、
// 或未生成/失败态用户点「生成/重新生成」。进页面渲染绝不调用本函数（改时机后进页面只查库/接在途）。
async function startStagePlanFlow(projectId, seq) {
  if (stagePlanAbortController) stagePlanAbortController.abort();
  stagePlanAbortController = new AbortController();
  const signal = stagePlanAbortController.signal;
  const stale = () =>
    signal.aborted || seq !== stagePlanSeq || projectId !== chapterProjectId;
  stagePlanLoadState = "loading";
  stagePlanErrorText = "";
  renderChapterCreation();
  let taskId;
  try {
    ({ taskId } = await chapterApi.planStage(projectId));
    if (stale()) return;
    persistStagePlanTask(projectId, taskId);
  } catch (err) {
    if (stale()) return;
    stagePlanAbortController = null;
    stagePlanLoadState = "error";
    stagePlanErrorText = storyErrorText(err);
    renderChapterCreation();
    return;
  }
  await consumeStagePlanTask(projectId, seq, taskId);
}

// Story 4.4：接回/消费一个已存在的章节生成任务的 SSE（仿 consumeStagePlanTask）：GET
// /tasks/{id}/events 消费 progress/result/error。seq/projectId/chapterNumber/abort 守卫 + 无终态
// 兜底 + 终态清在途 taskId。**不发起 POST**——用于「刷新/重进凭本地 taskId 接回正在跑的那个任务」。
// 复用当前 chapterGenAbortController（调用方已建），signal 随之被离页/登出 abort。
async function consumeChapterGenTask(projectId, chapterNumber, seq, taskId) {
  const signal = chapterGenAbortController && chapterGenAbortController.signal;
  const stale = () =>
    (signal && signal.aborted) ||
    seq !== chapterGenSeq ||
    projectId !== chapterProjectId ||
    chapterNumber !== chapterCreationIndex + 1;
  let gotTerminal = false;
  try {
    await explorationApi.taskEvents(taskId, {
      signal,
      onEvent: (type, data) => {
        if (stale()) return;
        if (type === "result" && data && typeof data.chapterText === "string") {
          gotTerminal = true;
          chapterGenAbortController = null;
          clearChapterGenTask();
          chapterGeneratedText = data.chapterText;
          chapterCreationState = "reading";
          chapterReaderPage = 0;
          renderChapterCreation();
        } else if (type === "error") {
          gotTerminal = true;
          chapterGenAbortController = null;
          clearChapterGenTask();
          // 生成失败：退回输入态可重试，给可读提示（复用 storyErrorText，含 429/502/泛化）。
          chapterCreationState = "input";
          renderChapterCreation();
          showChapterInlineError(storyErrorText({ code: data && data.code }));
        }
        // progress：generating 态文案已在显示，V1 不额外更新（仿 4.3 app.js:1646）。
      },
    });
    // 无终态兜底（防永久「生成中」，仿 consumeStagePlanTask）：SSE 正常结束却没收到 result/error。
    if (!stale() && !gotTerminal && chapterCreationState === "generating") {
      chapterGenAbortController = null;
      clearChapterGenTask();
      chapterCreationState = "input";
      renderChapterCreation();
      showChapterInlineError(storyErrorText({ code: "generate_failed" }));
    }
  } catch (err) {
    if (stale()) return; // 用户主动 abort / 已切走，不报错
    chapterGenAbortController = null;
    clearChapterGenTask();
    chapterCreationState = "input";
    renderChapterCreation();
    showChapterInlineError(storyErrorText(err));
  }
}

// Story 4.4：主动触发真实章节正文生成 + SSE 消费（仿 startStagePlanFlow）：POST generate 拿
// taskId → 存 sessionStorage（刷新可接回）→ consumeChapterGenTask 消费 SSE。**仅用于用户明示
// 点「生成本章/跳过并生成」**。进页面渲染绝不调用本函数（进页面只查库 / 接在途）。
async function startChapterGenFlow(projectId, chapterNumber, idea, seq) {
  if (chapterGenAbortController) chapterGenAbortController.abort();
  chapterGenAbortController = new AbortController();
  chapterRecoveredKey = `${projectId}:${chapterNumber}`;
  const signal = chapterGenAbortController.signal;
  const stale = () =>
    signal.aborted ||
    seq !== chapterGenSeq ||
    projectId !== chapterProjectId ||
    chapterNumber !== chapterCreationIndex + 1;
  chapterCreationState = "generating";
  renderChapterCreation();
  let taskId;
  try {
    ({ taskId } = await chapterApi.generateChapter(projectId, chapterNumber, {
      chapterIdea: idea,
    }));
    if (stale()) return;
    persistChapterGenTask(projectId, chapterNumber, taskId);
  } catch (err) {
    if (stale()) return;
    chapterGenAbortController = null;
    chapterCreationState = "input";
    renderChapterCreation();
    showChapterInlineError(storyErrorText(err));
    return;
  }
  await consumeChapterGenTask(projectId, chapterNumber, seq, taskId);
}

// Story 4.6：消费一个已存在的修订任务的 SSE（仿 consumeChapterGenTask，差异见下）。GET
// /tasks/{id}/events 消费 progress/result/error。seq/projectId/chapterNumber/abort 四守卫 +
// 无终态兜底 + 终态清在途 taskId。**不发起 POST**——用于「刷新/重进凭本地 taskId 接回在途修订」。
// 与生成流的关键差异：① result 取 data.revision 更新版本号（不本地 +1，AC4）；② 改进/重生都清
// 批注 chapterAnnotations=[]（决策 1，改进后旧坐标失真）+ 清整体点评；③ 失败退回 **reading 态**
// 保留旧正文可重看/重试（区别于 4.4 生成失败退 input 态，AC8）。
async function consumeChapterReviseTask(projectId, chapterNumber, seq, taskId, action) {
  const signal = chapterGenAbortController && chapterGenAbortController.signal;
  const stale = () =>
    (signal && signal.aborted) ||
    seq !== chapterGenSeq ||
    projectId !== chapterProjectId ||
    chapterNumber !== chapterCreationIndex + 1;
  let gotTerminal = false;
  try {
    await explorationApi.taskEvents(taskId, {
      signal,
      onEvent: (type, data) => {
        if (stale()) return;
        if (type === "result" && data && typeof data.chapterText === "string") {
          gotTerminal = true;
          chapterGenAbortController = null;
          clearChapterGenTask();
          chapterGeneratedText = data.chapterText;
          // 版本号取后端权威值（旧+1），不本地递增——防前后端因失败/重试脱节（AC4）。
          if (typeof data.revision === "number") chapterRevision = data.revision;
          chapterReaderPage = 0; // 回第一页（修改从头呈现）
          chapterAnnotations = []; // 改进+重生都清（决策 1）：旧批注坐标对不上新正文
          chapterFeedback = "";
          chapterAnnotationTarget = null;
          chapterAnnotationDraft = "";
          chapterAnnotationFocus = null;
          chapterAgentBusy = false;
          chapterLastRevisionAction = action;
          chapterAgentResult =
            action === "regenerate"
              ? `已生成第 ${chapterRevision} 版草稿。你可以重新阅读后继续反馈。`
              : `已按你的反馈改进为第 ${chapterRevision} 版草稿。修改从第一页开始呈现。`;
          chapterCreationState = "reading"; // 维持 reading（修订在 reading 态发起）
          renderChapterCreation();
        } else if (type === "error") {
          gotTerminal = true;
          chapterGenAbortController = null;
          clearChapterGenTask();
          // 修订失败：退回 reading 态保留旧正文（可重看/重试），给可读提示（AC8）。
          chapterAgentBusy = false;
          chapterCreationState = "reading";
          renderChapterCreation();
          showChapterInlineError(storyErrorText({ code: data && data.code }));
        }
        // progress：忙碌态文案已在显示，V1 不额外更新（仿 4.4）。
      },
    });
    // 无终态兜底（防永久忙碌）：SSE 正常结束却没收到 result/error。
    if (!stale() && !gotTerminal && chapterAgentBusy) {
      chapterGenAbortController = null;
      clearChapterGenTask();
      chapterAgentBusy = false;
      chapterCreationState = "reading";
      renderChapterCreation();
      showChapterInlineError(storyErrorText({ code: "generate_failed" }));
    }
  } catch (err) {
    if (stale()) return; // 用户主动 abort / 已切走，不报错
    chapterGenAbortController = null;
    clearChapterGenTask();
    chapterAgentBusy = false;
    chapterCreationState = "reading";
    renderChapterCreation();
    showChapterInlineError(storyErrorText(err));
  }
}

// Story 4.6：主动触发改进/重生 + SSE 消费（仿 startChapterGenFlow）：POST revise 拿 taskId →
// 存 sessionStorage（刷新可接回）→ consumeChapterReviseTask 消费 SSE。**仅用于用户明示点
// 「改进本章 →」/「重新生成」**。调用前已置 chapterAgentBusy + 递增 seq + abort 在途。
async function startChapterReviseFlow(
  projectId,
  chapterNumber,
  action,
  feedback,
  annotations,
  seq,
) {
  chapterGenAbortController = new AbortController();
  chapterRecoveredKey = `${projectId}:${chapterNumber}`;
  const signal = chapterGenAbortController.signal;
  const stale = () =>
    signal.aborted ||
    seq !== chapterGenSeq ||
    projectId !== chapterProjectId ||
    chapterNumber !== chapterCreationIndex + 1;
  let taskId;
  try {
    ({ taskId } = await chapterApi.reviseChapter(projectId, chapterNumber, {
      action,
      feedback,
      annotations,
    }));
    if (stale()) return;
    persistChapterGenTask(projectId, chapterNumber, taskId, "revise", action);
  } catch (err) {
    if (stale()) return;
    chapterGenAbortController = null;
    // 触发失败（如改进无反馈 400 被守卫拦）：退回 reading 态保留旧正文 + 错误提示。
    chapterAgentBusy = false;
    chapterCreationState = "reading";
    renderChapterCreation();
    showChapterInlineError(storyErrorText(err));
    return;
  }
  await consumeChapterReviseTask(projectId, chapterNumber, seq, taskId, action);
}

// Story 4.4：章节页内联错误提示（仿 showGuidedInlineError）。生成失败时在输入区顶部插一条错误
// 条，无遮挡、下次渲染清除；找不到容器则 alert 兜底。
function showChapterInlineError(text) {
  const host =
    document.querySelector(".chapter-entry") ||
    document.querySelector(".chapter-main");
  if (!host) {
    window.alert(text);
    return;
  }
  let bar = host.querySelector("[data-chapter-error]");
  if (!bar) {
    bar = document.createElement("p");
    bar.className = "guided-error";
    bar.setAttribute("data-chapter-error", "");
    bar.setAttribute("role", "alert");
    host.prepend(bar);
  }
  bar.textContent = text;
}

// Story 4.4：进第一章/刷新时恢复本章正文态（AC6，仿 loadChapterStagePlan 的「先 GET 落库、再接
// 在途」范式）。**绝不主动 POST 生成**——只查库 / 接在途，触发只发生在用户点「生成」那一次。
// 用 chapterGenSeq + AbortController 三守卫防跨章/切页赛跑。
async function recoverChapterState(projectId, chapterNumber) {
  if (chapterGenAbortController) chapterGenAbortController.abort();
  chapterGenSeq += 1;
  const seq = chapterGenSeq;
  chapterRecoveredKey = `${projectId}:${chapterNumber}`;
  // Story 4.4 review：进入新章恢复前统一重置全部章级编辑态。否则跨章/跨项目 hash 导航（不经
  // submit/换项目/logout 三处重置）会让上一章的批注/点评/定稿/版本号残留污染新章渲染——如第 1 章
  // 已定稿跳第 2 章，侧栏仍显示第 1 章批注、头部仍「本章已定稿」。恢复分支随后按真实态回填。
  chapterGeneratedText = "";
  chapterRevision = 1;
  chapterFinalized = false;
  chapterReaderPage = 0;
  chapterFeedback = "";
  chapterAgentResult = "";
  chapterLastRevisionAction = "";
  chapterAnnotations = [];
  chapterAnnotationTarget = null;
  chapterAnnotationDraft = "";
  chapterAnnotationFocus = null;
  chapterGenAbortController = new AbortController();
  const signal = chapterGenAbortController.signal;
  const stale = () =>
    signal.aborted ||
    seq !== chapterGenSeq ||
    projectId !== chapterProjectId ||
    chapterNumber !== chapterCreationIndex + 1;

  try {
    // 1. 先 GET 已落库的章节正文（刷新/断线重进恢复，AC6）。
    const existing = await chapterApi.getChapterText(projectId, chapterNumber, {
      signal,
    });
    if (stale()) return;
    // Story 4.6 review：读在途任务记录，区分 gen（首次生成）/ revise（改进重生）。
    const pending = readChapterGenTask(projectId, chapterNumber);
    const hasExisting = existing && typeof existing.chapterText === "string";

    // 1a. 在途是 revise（改进/重生）：即便 GET 到旧正文也**不短路**——修订正文要等流水线末尾才
    // upsert，此刻库里必是旧文，若短路则清掉在途 taskId、看不到「修订中」、诱发重复点重复付费
    // （code review Edge#2/#3）。故：先用旧正文铺底进 reading + 忙碌态，再接回 revise SSE。
    if (pending && pending.kind === "revise") {
      if (hasExisting) {
        chapterGeneratedText = existing.chapterText;
        chapterRevision = existing.revision || 1;
        chapterFinalized = existing.status === "finalized";
      }
      // 定稿态不该有在途修订（修订按钮已隐藏）——防御：定稿则清任务、进 reading 只读，不接回。
      if (chapterFinalized) {
        chapterGenAbortController = null;
        chapterCreationState = "reading";
        chapterReaderPage = 0;
        clearChapterGenTask();
        renderChapterCreation();
        return;
      }
      chapterCreationState = "reading";
      chapterReaderPage = 0;
      chapterAgentBusy = true;
      chapterAgentResult =
        pending.action === "regenerate"
          ? "正在重新规划并生成这一章……"
          : "正在根据你的点评改进这一章……";
      renderChapterCreation();
      await consumeChapterReviseTask(
        projectId,
        chapterNumber,
        seq,
        pending.taskId,
        pending.action,
      );
      return;
    }

    // 1b. 无在途 revise：有落库正文则直接进 reading 态（首次生成已完成 / 修订已跑完落库）。
    if (hasExisting) {
      chapterGeneratedText = existing.chapterText;
      chapterRevision = existing.revision || 1;
      chapterFinalized = existing.status === "finalized";
      chapterCreationState = "reading";
      chapterReaderPage = 0;
      chapterGenAbortController = null;
      clearChapterGenTask(); // 已落库，在途 taskId 不再需要
      renderChapterCreation();
      return;
    }
    // existing 为 null = 204 未生成。
  } catch (err) {
    if (stale()) return; // 被 abort / 已切走：静默退出
    // GET 抛 ApiError（404 租户/5xx/网络）≠「未生成」：保持 input 态，用户可点生成重试
    // （不臆断为已生成、不误触发）。真实错误经内联条提示。
    chapterGenAbortController = null;
    chapterCreationState = "input";
    renderChapterCreation();
    showChapterInlineError(storyErrorText(err));
    return;
  }
  if (stale()) return;
  // 2. 未落库（204）——凭本地在途 gen taskId 接回**正在跑的那个生成任务**的 SSE（生成中刷新恢复）。
  const pendingGen = readChapterGenTask(projectId, chapterNumber);
  if (pendingGen) {
    chapterCreationState = "generating";
    renderChapterCreation();
    await consumeChapterGenTask(
      projectId,
      chapterNumber,
      seq,
      pendingGen.taskId,
    );
    return;
  }
  // 3. 既无落库正文、又无在途任务：显示输入态，等用户填想法/点生成（不主动触发）。
  chapterGenAbortController = null;
  chapterCreationState = "input";
  renderChapterCreation();
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


// Story 7.5/7.7：把后端候选卡（StoryProfileCard 或 StoryProfileCardResponse，camelCase）转成
// 设定卡对话框渲染用的 [{key, label, value}] 结构。主干 7 恒显（缺料后端为空串）；题材特化 4
// 按值非空显（后端按 genre 激活、不匹配为 null）；⑫ 文风锚点非空才显。字段顺序对齐
// [[project_muse_setting_fields]] 的 ①-⑫ 编号。每项带 camelCase key，供编辑落库 / 变化高亮
// 按字段身份而非数组下标定位（渲染列表长度随特化字段激活而变，下标不稳）。
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

// 后端 changedFields 是 snake_case 列名（如 core_appeal）；前端字段身份用 camelCase key。
// 通用 snake→camel 转换（core_appeal→coreAppeal / style_profile→styleProfile），映射到前端 key。
function snakeToCamel(name) {
  return String(name || "").replace(/_([a-z])/g, (_, ch) => ch.toUpperCase());
}

function buildProfileFromBackend(profile) {
  const fields = [];
  for (const [key, label] of PROFILE_FIELD_LABELS) {
    const raw = profile ? profile[key] : undefined;
    const value = typeof raw === "string" ? raw.trim() : "";
    if (PROFILE_TRUNK_KEYS.has(key)) {
      // 主干恒显：空串回落占位文案，提示这项还没聊清楚。
      fields.push({ key, label, value: value || "（尚未聊到，可继续补充）", added: false });
    } else if (value) {
      // 题材特化 + 文风锚点：仅在后端给了非空值时显（按 genre 激活 / 已锚定文风）。
      fields.push({ key, label, value, added: false });
    }
  }
  return fields;
}

// 用后端真实候选卡弹出/刷新设定卡（会话内恢复用 AC7：写 finalStoryProfile + pending 态 + persist）。
// 会话内恢复用（AC7）：写 finalStoryProfile + pending 态 + persist 到 sessionStorage。
// Story 7.7：消费后端 revision/changedFields（缺省时回落 1/[]，保证 7.5/7.6 只传 12 内容字段的
// StoryProfileCard 调用方不因本改动挂掉——向后兼容，AC2 Task2 注意项）。changedFields 从后端
// snake_case 列名映射为前端 camelCase key，驱动 is-updated 高亮。
function openStoryProfileFromBackend(profile) {
  // #2：重建前捕获正在编辑（有焦点但未 blur）的字段——它的本地输入尚未 PATCH，后端权威卡
  // 里没有，直接用后端值重建会吞掉用户正打的字。重建后保留其在编辑文本，重挂后恢复焦点。
  const active = document.activeElement;
  const editingKey =
    active && active.dataset ? active.dataset.finalProfileField : null;
  const editingText = editingKey ? active.textContent.trim() : null;
  finalStoryProfile = buildProfileFromBackend(profile);
  if (editingKey) {
    const editingField = finalStoryProfile.find((f) => f.key === editingKey);
    if (editingField) editingField.value = editingText;
  }
  // signature 用后端 profile 序列化，标识「这份候选卡」；恢复时据此判定是否同一份。
  finalStoryProfileSignature = JSON.stringify(profile);
  finalStoryProfileRevision =
    profile && typeof profile.revision === "number" ? profile.revision : 1;
  pendingStoryProfile = true;
  lastProfileChangedFields = Array.isArray(profile && profile.changedFields)
    ? profile.changedFields.map(snakeToCamel)
    : [];
  profileFeedbackStatus = "";
  persistPendingStoryProfile();
  mountStoryProfileDialog();
  if (editingKey) restoreProfileFieldFocus(editingKey);
}

// #2：重挂后把焦点+光标恢复到重挂前正在编辑的字段末尾（重挂重建了全部 DOM，焦点会丢）。
function restoreProfileFieldFocus(key) {
  const el = document.querySelector(`[data-final-profile-field="${key}"]`);
  if (!el) return;
  el.focus();
  const range = document.createRange();
  range.selectNodeContents(el);
  range.collapse(false);
  const selection = window.getSelection();
  selection.removeAllRanges();
  selection.addRange(range);
}

// Story 7.7 文风锚点入口（UX-DR1 全新 UI）：设定卡内新增「从预置样本库选 / 粘贴范文」锚点区。
// 抽取后端返回的 styleProfile 是五维「标签：内容」多行文本（style_anchor_agent._parse_style_profile），
// 逐行渲染。当前已锚定值取自 finalStoryProfile 第⑫字段（styleProfile）——与设定卡编辑同源。
function currentStyleProfileValue() {
  const field = finalStoryProfile
    ? finalStoryProfile.find((f) => f.key === "styleProfile")
    : null;
  return field ? field.value : "";
}

function styleProfileLinesMarkup(text) {
  const lines = String(text || "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  if (lines.length === 0) return "";
  return `<dl class="style-anchor-profile">${lines
    .map((line) => {
      const sep = line.includes("：") ? "：" : line.includes(":") ? ":" : "";
      if (!sep) return `<dd>${escapeHtml(line)}</dd>`;
      const [label, ...rest] = line.split(sep);
      return `<div class="style-anchor-profile-row"><dt>${escapeHtml(label.trim())}</dt><dd>${escapeHtml(rest.join(sep).trim())}</dd></div>`;
    })
    .join("")}</dl>`;
}

function styleAnchorEntryMarkup() {
  const anchored = currentStyleProfileValue().trim();
  const summary = `<button type="button" class="style-anchor-toggle" data-style-anchor-toggle aria-expanded="${styleAnchorPanelOpen}">
    <span>文风锚点${anchored ? "（已锚定）" : "（可选）"}</span><i>${styleAnchorPanelOpen ? "－" : "＋"}</i>
  </button>`;
  if (!styleAnchorPanelOpen) {
    return `<section class="style-anchor-entry">${summary}</section>`;
  }
  const errorLine = styleAnchorErrorText
    ? `<p class="style-anchor-error" aria-live="polite">${escapeHtml(styleAnchorErrorText)}</p>`
    : "";
  let picker;
  if (styleAnchorTab === "library") {
    let list;
    if (styleAnchorSamplesLoading && styleAnchorSamples === null) {
      list = `<p class="style-anchor-loading">正在载入样本库…</p>`;
    } else if (!styleAnchorSamples || styleAnchorSamples.length === 0) {
      list = `<p class="style-anchor-loading">暂无可选样本。</p>`;
    } else {
      list = `<ul class="style-sample-list">${styleAnchorSamples
        .map(
          (sample) =>
            `<li><button type="button" class="style-sample-card ${styleAnchorSelected === sample.id ? "is-current" : ""}" data-style-sample="${escapeHtml(sample.id)}"><div class="style-sample-head"><strong>${escapeHtml(sample.name)}</strong><span>${escapeHtml(sample.note)}</span></div><p>${escapeHtml(sample.excerpt)}</p></button></li>`,
        )
        .join("")}</ul>`;
    }
    picker = list;
  } else {
    picker = `<div class="field style-paste-field"><div class="field-head"><label for="style-paste-inline">粘贴一段范文</label><span class="field-note">至少 20 字</span></div><textarea class="input" id="style-paste-inline" placeholder="贴一段你希望这本书读起来像的文字……">${escapeHtml(styleAnchorPasteText)}</textarea></div>`;
  }
  const canExtract =
    styleAnchorTab === "paste"
      ? styleAnchorPasteText.trim().length >= 20
      : Boolean(styleAnchorSelected);
  const resultMarkup = anchored
    ? `<div class="style-anchor-result"><div class="style-anchor-result-head"><span>当前文风锚点</span></div>${styleProfileLinesMarkup(anchored)}</div>`
    : "";
  return `<section class="style-anchor-entry is-open">
    ${summary}
    <div class="style-anchor-panel">
      <p class="style-anchor-copy">选一段你爱读的文字，或粘贴一段范文，抽取文风特征作为正文的锚（可留空用默认风格）。</p>
      <div class="tabs" role="tablist" aria-label="文风锚定方式">
        <button class="tab" role="tab" aria-selected="${styleAnchorTab === "library"}" data-style-tab="library">从样本库选</button>
        <button class="tab" role="tab" aria-selected="${styleAnchorTab === "paste"}" data-style-tab="paste">粘贴我的范文</button>
      </div>
      ${picker}
      ${errorLine}
      <div class="style-anchor-actions"><button class="secondary-button" type="button" data-style-extract ${canExtract && !styleAnchorSaving ? "" : "disabled"}>${styleAnchorSaving ? "抽取中…" : "抽取文风"}</button></div>
      ${resultMarkup}
    </div>
  </section>`;
}

// 拉取真实样本库（GET style-anchor/samples），仅在设定卡文风区展开且库 tab 时按需拉一次。
async function loadStyleSamplesIfNeeded() {
  if (styleAnchorSamples !== null || styleAnchorSamplesLoading) return;
  const projectId = explorationProjectId;
  const startedHash = location.hash;
  styleAnchorSamplesLoading = true;
  try {
    const samples = await storyApi.listStyleSamples(projectId);
    if (location.hash !== startedHash || explorationProjectId !== projectId) return;
    styleAnchorSamples = Array.isArray(samples) ? samples : [];
  } catch {
    if (location.hash !== startedHash || explorationProjectId !== projectId) return;
    // #4：拉取失败保持 null（而非 []），使下次展开/切回库 tab 时 `!== null` 判据放行重拉，
    // 不把瞬时网络错误固化成永久空态。设错误提示告知用户失败、可重试。
    styleAnchorErrorText = "样本库加载失败，请稍后重试。";
  } finally {
    styleAnchorSamplesLoading = false;
  }
  // #11：收尾重挂加当前 tab 校验——库 tab 触发拉取后用户可能已切到粘贴 tab 开始打字，此时
  // 样本返回不应重挂打断粘贴输入焦点。仅当仍停在库 tab 且面板展开时才重绘。
  if (
    location.hash === startedHash &&
    explorationProjectId === projectId &&
    styleAnchorPanelOpen &&
    styleAnchorTab === "library"
  ) {
    mountStoryProfileDialog();
  }
}

// 文风锚点抽取（AC6）：库选 POST {sampleId} / 粘贴 POST {sampleText}。成功把 styleProfile
// 写入 finalStoryProfile 第⑫字段 + 落库（editProfile，与直接编辑同源，保证刷新恢复一致），并重绘。
async function submitStyleAnchor() {
  if (styleAnchorSaving) return;
  const projectId = explorationProjectId;
  const startedHash = location.hash;
  const startedSeq = styleAnchorSeq;
  let payload;
  if (styleAnchorTab === "paste") {
    const text = styleAnchorPasteText.trim();
    if (text.length < 20) return; // 前端 dual validate（后端 min_length=20）
    payload = { sampleText: text };
  } else {
    if (!styleAnchorSelected) return;
    payload = { sampleId: styleAnchorSelected };
  }
  styleAnchorSaving = true;
  styleAnchorErrorText = "";
  mountStoryProfileDialog();
  // 三重守卫：hash（切页）/projectId（切作品）/seq（同页内 discard 丢弃卡）任一变即弃回调。
  const stale = () =>
    location.hash !== startedHash ||
    explorationProjectId !== projectId ||
    styleAnchorSeq !== startedSeq;
  // #5：记录第一段 anchorStyle 已抽取并锚定的 styleProfile。若随后 editProfile（同步落库）失败，
  // 后端其实已 upsert_style_profile 锚定，catch 里据此乐观回写第⑫字段，避免前后端不一致。
  let anchoredStyle = null;
  try {
    const result = await storyApi.anchorStyle(projectId, payload);
    if (stale()) return;
    anchoredStyle = (result && result.styleProfile) || "";
    // 把抽取结果落到候选卡第⑫字段（editProfile），后端权威行回来后覆盖重绘（含 styleProfile）。
    // #3：不在此提前复位 styleAnchorSaving——否则 editProfile 在途时 paste input 监听会把
    // 「抽取文风」按钮重新 enable，放行第二次并发提交。统一在 finally 复位。
    const card = await storyApi.editProfile(projectId, { styleProfile: anchoredStyle });
    if (stale()) return;
    if (card) openStoryProfileFromBackend(card);
    styleAnchorPanelOpen = true;
    mountStoryProfileDialog();
  } catch (err) {
    if (stale()) return;
    // #5：anchorStyle 成功但 editProfile 失败——后端已锚定，前端乐观把 styleProfile 写入第⑫
    // 字段 + persist，避免「前端显示失败、刷新后却已锚定」的不一致。anchoredStyle 非 null 即
    // 表示抽取已成功、仅同步落库这步失败（抽取本身失败则 anchoredStyle 仍为 null，不误写）。
    if (anchoredStyle) {
      const field = finalStoryProfile
        ? finalStoryProfile.find((f) => f.key === "styleProfile")
        : null;
      if (field) {
        field.value = anchoredStyle;
        persistPendingStoryProfile();
      }
    }
    styleAnchorErrorText = storyErrorText(err);
    mountStoryProfileDialog();
  } finally {
    if (!stale()) styleAnchorSaving = false;
  }
}

function bindStyleAnchorEntryInteractions() {
  document
    .querySelector("[data-style-anchor-toggle]")
    ?.addEventListener("click", () => {
      styleAnchorPanelOpen = !styleAnchorPanelOpen;
      styleAnchorErrorText = "";
      mountStoryProfileDialog();
      if (styleAnchorPanelOpen && styleAnchorTab === "library") {
        loadStyleSamplesIfNeeded();
      }
    });
  if (!styleAnchorPanelOpen) return;
  document.querySelectorAll("[data-style-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      styleAnchorTab = button.getAttribute("data-style-tab");
      styleAnchorErrorText = "";
      mountStoryProfileDialog();
      if (styleAnchorTab === "library") loadStyleSamplesIfNeeded();
    });
  });
  document.querySelectorAll("[data-style-sample]").forEach((button) => {
    button.addEventListener("click", () => {
      styleAnchorSelected = button.getAttribute("data-style-sample");
      mountStoryProfileDialog();
    });
  });
  const paste = document.querySelector("#style-paste-inline");
  paste?.addEventListener("input", () => {
    styleAnchorPasteText = paste.value;
    const extract = document.querySelector("[data-style-extract]");
    if (extract) extract.disabled = paste.value.trim().length < 20 || styleAnchorSaving;
  });
  document
    .querySelector("[data-style-extract]")
    ?.addEventListener("click", () => submitStyleAnchor());
  if (styleAnchorTab === "library") loadStyleSamplesIfNeeded();
}

function storyProfileDialogMarkup() {
  const items = finalStoryProfile
    .map(
      (
        field,
        index,
      ) => `<section class="profile-result-item ${lastProfileChangedFields.includes(field.key) ? "is-updated" : ""}">
        <div class="profile-result-label"><span>${String(index + 1).padStart(2, "0")} / ${escapeHtml(field.label)}</span></div>
        <div contenteditable="true" role="textbox" aria-label="编辑${escapeHtml(field.label)}" data-final-profile-field="${escapeHtml(field.key)}" data-final-profile-value="${escapeHtml(field.value)}">${escapeHtml(field.value)}</div>
      </section>`,
    )
    .join("");
  return `<div class="profile-dialog-backdrop">
    <section class="profile-dialog" role="dialog" aria-modal="true" aria-labelledby="profile-dialog-title">
      <header class="profile-dialog-head">
        <div><span>Story profile / v${finalStoryProfileRevision}</span><h2 id="profile-dialog-title">确认故事设定</h2><p>直接编辑设定，或者告诉 Agent 你希望怎样调整。确认后将进入第一章创作。</p></div>
      </header>
      <div class="profile-dialog-body">${items}${styleAnchorEntryMarkup()}</div>
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

// Story 7.7：回到探索 + 后端丢弃（AC5）。7.5 遗留债在此补齐——7.5 当时基于「settle emit-only
// 无落库副作用」的过时理解只做前端复位；实际 3.4 起 settle 既落库 pending 卡又推 SSE
// （story_settle_agent.settle_into_profile），所以只要弹过设定卡后端必有一行 status='pending'，
// 「确定返回」必须调后端 discard 删它。discard 幂等（无卡也 204），故无条件调用即安全——
// 不必区分「settle 未落库完成」的竞态。先 abort 在途 settle SSE（若还在整理中被点），再 discard。
async function discardStoryProfileAndReturn() {
  if (profileDiscardBusy) return;
  const projectId = explorationProjectId;
  const startedHash = location.hash;
  // 先 abort 在途 settle SSE（若还在整理中被点回到探索，先断流再丢弃）。
  if (settleAbortController) {
    settleAbortController.abort();
    settleAbortController = null;
  }
  // #6：递增文风代次，使在途 anchorStyle/editProfile 回调识别到卡已丢弃而不重挂已关闭的弹窗。
  styleAnchorSeq += 1;
  styleAnchorSaving = false;
  profileDiscardBusy = true;
  const confirmBtn = document.querySelector("[data-confirm-profile-return]");
  if (confirmBtn) {
    confirmBtn.disabled = true;
    confirmBtn.textContent = "返回中…";
  }
  try {
    await storyApi.discardProfile(projectId);
  } catch (err) {
    // 丢弃失败（非 401，401 已跳登录）：提示后保留设定卡，不误清前端 pending 态。
    if (location.hash !== startedHash || explorationProjectId !== projectId) return;
    profileDiscardBusy = false;
    if (confirmBtn) {
      confirmBtn.disabled = false;
      confirmBtn.textContent = "确定返回";
    }
    window.alert(storyErrorText(err));
    return;
  }
  if (location.hash !== startedHash || explorationProjectId !== projectId) {
    profileDiscardBusy = false;
    return;
  }
  // 后端已删 pending 行，前端复位所有设定卡态并回探索问答界面。
  finalStoryProfile = null;
  finalStoryProfileSignature = "";
  finalStoryProfileRevision = 1;
  pendingStoryProfile = false;
  lastProfileChangedFields = [];
  profileFeedbackStatus = "";
  profileFieldEditing.clear();
  // #9：复位全套文风锚点态（含展开/tab/样本），否则同会话再次 settle 弹卡时面板带旧残留展开。
  styleAnchorSelected = null;
  styleAnchorPasteText = "";
  styleAnchorErrorText = "";
  styleAnchorPanelOpen = false;
  styleAnchorTab = "library";
  styleAnchorSamples = null;
  styleAnchorSamplesLoading = false;
  // 复位“整理中”过渡态：否则回到探索页会卡在整理动画上（弹窗由末题触发时留下的态）。
  guidedSettling = false;
  settleErrorText = "";
  profileDiscardBusy = false;
  clearPendingStoryProfile();
  closeStoryProfileDialog();
  // 回到探索页需重新渲染 + 重载会话（#10）：内存 explorationHistory/freeConversation 可能已空
  // （如刷新后由 sessionStorage 恢复卡的情形），仅 renderExploration 会显示空白问答界面、丢失
  // 已答进度。仿 reconcile 的 204 分支按入口模式重载会话，把后端已答内容拉回。
  renderExploration();
  if (explorationEntryMode !== "free") loadGuidedExploration(projectId);
  else loadFreeExploration(projectId);
}

// Story 7.7：确认设定 → 后端翻 confirmed + 推 phase explore→chapter（同事务，Story 3.5 AC1）→
// 进第一章创作页（AC4）。替换 mock（window.setTimeout→confirmedStoryProfile sessionStorage→硬编码
// demo 跳转）。跳转用真实路由 projectId。
async function confirmStoryProfileAndEnterChapter() {
  if (profileConfirmBusy) return;
  const projectId = explorationProjectId;
  const startedHash = location.hash;
  profileConfirmBusy = true;
  const button = document.querySelector("[data-confirm-profile]");
  const note = document.querySelector("[data-profile-confirm-note]");
  if (button) {
    button.disabled = true;
    button.querySelector("span").textContent = "✓";
  }
  if (note) note.textContent = "故事设定已确认，正在进入第一章创作。";
  try {
    await storyApi.confirmProfile(projectId);
  } catch (err) {
    if (location.hash !== startedHash || explorationProjectId !== projectId) return;
    profileConfirmBusy = false;
    if (button) {
      button.disabled = false;
      button.querySelector("span").textContent = "→";
    }
    if (note) note.textContent = storyErrorText(err);
    return;
  }
  if (location.hash !== startedHash || explorationProjectId !== projectId) {
    profileConfirmBusy = false;
    return;
  }
  // #7：防 confirm 与 discard 并发——若 discard 的 await 先 resolve 已把 finalStoryProfile 置 null，
  // confirm 回来时 hash 未变会放行，此处 finalStoryProfile.map 会空指针。判空即中止后续跳转。
  if (!finalStoryProfile) {
    profileConfirmBusy = false;
    return;
  }
  // 本地缓存只读副本（归档页 / 章节上下文展示依赖）；phase 已由后端同事务推进，前端只消费。
  confirmedStoryProfile = finalStoryProfile.map((field) => ({ ...field }));
  window.sessionStorage.setItem(
    confirmedStoryProfileKey,
    JSON.stringify(confirmedStoryProfile),
  );
  explorationMode = "profile";
  window.sessionStorage.removeItem(explorationModeKey);
  pendingStoryProfile = false;
  profileConfirmBusy = false;
  clearPendingStoryProfile();
  // 确保第一章从头开始渲染
  chapterCreationState = "input";
  chapterIdea = "";
  // Story 4.3（review 改时机）：在「确认设定成功」这一次性事件里主动触发幕后生成阶段规划，
  // 而非把触发挂在「进第一章页面」（后者会被刷新/重进反复触发 → 重复叫 AI/重复付费）。触发拿到
  // taskId 存 sessionStorage，跳转后进页面凭它接回同一个在途任务的 SSE（不再新触发，FR17 幕后无阻塞）。
  currentStagePlan = null;
  stagePlanLoadState = "idle";
  stagePlanErrorText = "";
  chapterProjectId = "";
  clearStagePlanTask();
  try {
    const { taskId } = await chapterApi.planStage(projectId);
    if (taskId) persistStagePlanTask(projectId, taskId);
  } catch {
    // 触发失败不阻塞跳转（幕后无阻塞，FR17）：进页面查库空且无在途 taskId → 未生成态，
    // 用户可点「生成阶段计划」明示重试。confirm 已成功、phase 已进 chapter，不因此回退。
  }
  closeStoryProfileDialog();
  location.hash = `#/projects/${projectId}/chapters/1`;
}

function mountStoryProfileDialog() {
  closeStoryProfileDialog();
  app.insertAdjacentHTML("beforeend", storyProfileDialogMarkup());
  document.body.classList.add("dialog-open");
  bindStoryProfileDialogInteractions();
}

// Story 7.7：收集当前 DOM 里所有已改动字段（对比渲染时写死的 data-final-profile-value 快照），
// blur 时落库。返回 {camelCaseKey: newValue} 的改动集（空对象表示无改动）。变更基线用 DOM 属性
// 快照（仿 7.6 线索编辑 data-free-clue-value）而非 finalStoryProfile[].value——后者被 input
// 监听逐键改写、与 DOM 文本恒相等，拿它当基线会使改动检测恒为空、PATCH 永不发出。
function collectProfileFieldEdits() {
  const changes = {};
  document.querySelectorAll("[data-final-profile-field]").forEach((el) => {
    const key = el.dataset.finalProfileField;
    const field = finalStoryProfile.find((f) => f.key === key);
    if (!field) return;
    const next = el.textContent.trim();
    if (next !== el.dataset.finalProfileValue) {
      field.value = next;
      changes[key] = next;
    }
  });
  return changes;
}

// 落库单次字段编辑（AC2）：blur 触发。PATCH 只传改动字段、revision 不变。在途去合并（防并发双
// PATCH）：同一提交在途时排队最新值、结束后若又有新改动再发一轮。成功以后端权威行更新
// finalStoryProfile 并重绘（保留用户输入 + 刷新 is-updated 等 UI）。
async function persistProfileFieldEdits() {
  const changes = collectProfileFieldEdits();
  if (Object.keys(changes).length === 0) return;
  const editKey = "__profile__";
  const pending = profileFieldEditing.get(editKey);
  if (pending) {
    Object.assign(pending.changes, changes);
    pending.revision += 1;
    return;
  }
  const projectId = explorationProjectId;
  const startedHash = location.hash;
  const request = { changes: { ...changes }, revision: 0 };
  profileFieldEditing.set(editKey, request);
  try {
    while (true) {
      const revision = request.revision;
      const body = { ...request.changes };
      const card = await storyApi.editProfile(projectId, body);
      if (location.hash !== startedHash || explorationProjectId !== projectId) return;
      if (card) {
        // 后端权威行覆盖：直接编辑 revision 不变、changedFields 清空（后端 AC2）。
        openStoryProfileFromBackend(card);
      }
      if (request.revision === revision) return;
    }
  } catch (err) {
    if (location.hash !== startedHash || explorationProjectId !== projectId) return;
    if (err && err.code === "project_not_found") {
      // 作品已删/越权：回作品库。
      window.alert(storyErrorText(err));
      location.hash = "#/projects";
      return;
    }
    // #13：编辑落库失败用 alert 呈现（与本函数 project_not_found 分支、discard 失败呈现一致），
    // 不借用「你想调整什么？」反馈区状态行——那里语义是反馈升版本状态、与字段编辑无关。
    // no_pending_card 等：提示但保留本地输入不清除（用户可稍后重整理），故不重挂/不复位字段。
    window.alert(storyErrorText(err));
  } finally {
    profileFieldEditing.delete(editKey);
  }
}

// 反馈升版本（AC3）：POST revise（同步 REST），真实凝练 Agent 重生成、revision+1、changedFields 返。
async function submitProfileFeedback(feedback, textarea, button) {
  if (profileReviseBusy) return;
  const projectId = explorationProjectId;
  const startedHash = location.hash;
  profileReviseBusy = true;
  const originalLabel = button.textContent;
  button.disabled = true;
  button.textContent = "调整中…";
  try {
    const card = await storyApi.reviseProfile(projectId, { feedback });
    if (location.hash !== startedHash || explorationProjectId !== projectId) return;
    profileReviseBusy = false;
    // #8：revise 契约恒返 200 StoryProfileCardResponse；但防御性加 if(card) 守卫（仿
    // submitStyleAnchor/persistProfileFieldEdits），避免万一返回空体（apiFetch→null）时
    // openStoryProfileFromBackend(null) 把卡重建成占位吞掉用户内容、且 card.changedFields 抛错。
    if (card) {
      // openStoryProfileFromBackend 会读 card.revision（后端 +1）+ card.changedFields（映射 key 高亮）
      // + 重挂弹窗；反馈状态另行覆盖（openStoryProfileFromBackend 把 profileFeedbackStatus 清空）。
      openStoryProfileFromBackend(card);
      const changedCount = Array.isArray(card.changedFields)
        ? card.changedFields.length
        : 0;
      profileFeedbackStatus = `已根据反馈更新 ${changedCount} 项设定。`;
      persistPendingStoryProfile();
      mountStoryProfileDialog();
    } else {
      profileFeedbackStatus = storyErrorText({});
      button.disabled = false;
      button.textContent = originalLabel;
      const status = document.querySelector("[data-profile-feedback-status]");
      if (status) status.textContent = profileFeedbackStatus;
    }
  } catch (err) {
    if (location.hash !== startedHash || explorationProjectId !== projectId) return;
    profileReviseBusy = false;
    profileFeedbackStatus = storyErrorText(err);
    button.disabled = false;
    button.textContent = originalLabel;
    const status = document.querySelector("[data-profile-feedback-status]");
    if (status) status.textContent = profileFeedbackStatus;
  }
}

function bindStoryProfileDialogInteractions() {
  document.querySelectorAll("[data-final-profile-field]").forEach((field) => {
    // 落库时机 blur（同 7.6 线索编辑范式）：编辑中乐观写本地态即时反映，blur 才 PATCH 落库，
    // 避免逐键并发 PATCH。input 只更新本地态 + persist（刷新恢复）；blur 收集所有改动一次落库。
    field.addEventListener("input", () => {
      const key = field.dataset.finalProfileField;
      const target = finalStoryProfile.find((f) => f.key === key);
      if (target) target.value = field.textContent.trim();
      persistPendingStoryProfile();
    });
    field.addEventListener("blur", () => {
      persistProfileFieldEdits();
    });
  });
  document
    .querySelector("[data-profile-feedback]")
    ?.addEventListener("submit", (event) => {
      event.preventDefault();
      const textarea = event.currentTarget.querySelector("textarea");
      const feedback = textarea.value.trim();
      if (!feedback) return; // 前端 dual validate（后端 422 亦拦空反馈）
      const button = event.currentTarget.querySelector("button");
      submitProfileFeedback(feedback, textarea, button);
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
    ?.addEventListener("click", confirmStoryProfileAndEnterChapter);
  bindStyleAnchorEntryInteractions();
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

// Story 4.3：原 buildCurrentStagePlan 阶段计划 mock 已删除——阶段规划改为后端真实生成 +
// 落库（chapterApi.planStage/getStagePlan + SSE），currentStagePlan 只承载真实数据。

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
    // 零对话起点（AC2）：无对话且导航状态尚无 currentField 时展示四个固定入口；
    // 点击 startGuidance 生成开场问题后即使仍无对话消息，也按「已开始」渲染对话 + 常规输入框
    // （幂等重放/刷新恢复见 loadFreeExploration→applyGuidanceState）。
    const showEntryPoints = !hasConversation && !guidanceCurrentField;
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
    // 当前具体问题不再单独展示（2026-08-03 合并重构）：聊天记录本身就是唯一的问题
    // 事实源。按需思路 + 跳过挂在「最后一条 Agent 消息」下方——只有存在 current_field
    // （还有待补字段）且这是最后一条消息时才渲染，避免用户已经继续往下聊、这两个按钮
    // 还挂在半山腰的旧消息下面。
    const lastMessageIndex = freeConversation.length - 1;
    const suggestionsBlock = !guidanceSuggestionsExpanded
      ? ""
      : guidanceSuggestions.length
        ? `<div class="guidance-suggestions" role="group" aria-label="回答思路">${guidanceSuggestions
            .map(
              (text, index) =>
                `<button type="button" class="guidance-suggestion-option" data-guidance-suggestion="${index}">${escapeHtml(text)}</button>`,
            )
            .join("")}</div>`
        : `<p class="guidance-suggestions-empty">暂时没想到合适的思路，直接说说你的想法也可以。</p>`;
    // 跳过/候选/思路切换三个按钮不因 freeMessageSending 禁用：跳过是独立端点、候选点击
    // 走消息队列（收尾期间自动入队）、思路切换纯本地——都不该让用户在 Agent 刚说完话、
    // 收尾还在跑时「点不动」。只保留 guidanceSkipping 防跳过重复点击。
    const guidanceActionsBlock = guidanceCurrentField
      ? `<div class="guidance-question-actions">
          <button type="button" class="guidance-suggest-toggle" data-guidance-suggest>${guidanceSuggestionsExpanded ? "收起思路" : "没想好？看看几个思路"}</button>
          <button type="button" class="guidance-skip" data-guidance-skip ${guidanceSkipping ? "disabled" : ""}>先跳过这个问题</button>
        </div>
        ${suggestionsBlock}`
      : "";
    const freeMessages = freeConversation
      .map((entry, index) => {
        const isLastAgentMessage =
          entry.role === "agent" && index === lastMessageIndex;
        return `<article class="conversation-message ${entry.role === "agent" ? "agent-message" : "user-message"}">
          <div class="message-meta"><span>${entry.role === "agent" ? "Agent / 自由讨论" : "你"}</span></div>
          <p>${escapeHtml(entry.text)}</p>
          ${isLastAgentMessage ? guidanceActionsBlock : ""}
        </article>`;
      })
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
    const completionHintBlock =
      hasConversation && !guidanceCurrentField && canFinish
        ? `<p class="guidance-complete-hint">7 项设定主干都聊得差不多了，可以在右侧整理为故事设定了。</p>`
        : "";
    mainContent = `
      <section class="explore-dialogue" aria-labelledby="explore-title">
        <div class="explore-overline">Free exploration / 自由探索</div>
        <div class="explore-heading"><h1 id="explore-title">把故事聊出来</h1><span>自由探索</span></div>
        <section class="exploration-conversation" aria-label="自由讨论">
          <div class="conversation-scroll" data-conversation-scroll>${freeMessages || '<p class="guided-complete-hint">想到什么都可以先说出来。我们边聊边把人物、冲突和世界一点点理清楚。</p>'}</div>
        </section>
        ${entryPointsBlock}
        ${completionHintBlock}
        ${
          showEntryPoints
            ? ""
            : `<form class="explore-response compact-composer" id="explore-response" data-free-mode="true">
          <label for="explore-answer">继续讨论</label>
          <textarea id="explore-answer" placeholder="继续回答，或者和 Agent 讨论其他故事想法……" required></textarea>
          ${freeMessageBusyLabel ? `<p class="free-busy-hint" role="status" aria-live="polite"><span class="free-busy-spinner" aria-hidden="true"></span>${escapeHtml(freeMessageBusyLabel)}${freeMessageQueue.length ? `（还有 ${freeMessageQueue.length} 条待发送）` : ""}</p>` : ""}
          <div class="response-actions">
            <button class="primary-button explore-submit" type="submit">发送 <span>→</span></button>
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
    ?.addEventListener("click", () => toggleGuidanceSuggestions());
  document.querySelectorAll("[data-guidance-suggestion]").forEach((button) =>
    button.addEventListener("click", () => {
      const index = Number(button.dataset.guidanceSuggestion);
      const text = guidanceSuggestions[index];
      if (!text) return;
      // 点击即收起面板，避免建议列表悬在半空跨越到下一轮生成期间（视觉上像还没选定）。
      guidanceSuggestionsExpanded = false;
      submitFreeMessage(text);
    }),
  );
  document
    .querySelector("[data-guidance-skip]")
    ?.addEventListener("click", () => skipFreeGuidanceQuestion());
  document
    .querySelector("#explore-response")
    ?.addEventListener("submit", (event) => {
      event.preventDefault();
      const textarea = event.currentTarget.querySelector("#explore-answer");
      const answer = textarea.value;
      // 聊天式体验：提交即清空输入框视觉反馈，不等待网络/渲染；排队态下 submitFreeMessage
      // 只入队不触发整页重绘，故这里必须显式清空，否则文本会一直留在框里。
      textarea.value = "";
      submitFreeMessage(answer);
    });
  const conversation = document.querySelector("[data-conversation-scroll]");
  if (conversation) conversation.scrollTop = conversation.scrollHeight;
}

function chapterStagePlan() {
  // Story 4.3：只认真实阶段规划（幕后生成 + 落库恢复）。未就绪返 null——渲染层显示
  // 加载/占位态（buildCurrentStagePlan mock 已停用为真实数据源，AC2）。
  return currentStagePlan;
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
  // Story 4.3：非 reading 态侧栏渲染真实阶段计划（AC3）。未就绪（幕后生成中/失败）显示
  // 加载/占位态侧栏，不渲染 mock。
  if (!stagePlan) {
    const hint =
      stagePlanLoadState === "error"
        ? "阶段计划没能生成，可在左侧重试。"
        : stagePlanLoadState === "empty"
          ? "还没有阶段计划，可在左侧开始生成。"
          : "正在生成这个阶段的章节安排……";
    return `<aside class="chapter-context" aria-label="第一阶段章节安排">
      <div class="chapter-context-head"><span>第一阶段</span><strong>··</strong></div>
      <p>阶段计划提供每章的方向；详细章节计划只在准备创作当前章时生成。</p>
      <div class="chapter-context-list"><section class="is-empty"><div><p>${hint}</p></div></section></div>
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

// Story 4.5：真实正文长度不定（4.4 冒烟 ~3500 字），按段落数固定切页（Jianghj 2026-08-05 决议）。
// 每页固定 CHAPTER_PAGE_SIZE 段，贴合原型每页 ~5 段观感。
const CHAPTER_PAGE_SIZE = 5;

// Story 4.5：拆段 + 按段落数分页的纯函数（无副作用）。渲染与翻页监听共用它重算，避免渲染/监听
// 状态不同步（Dev Notes 推荐「重算最简单、不引入新状态」）。返回 `string[][]`（页→页内段）。
// 空正文返回 `[[]]`（1 个空页），供渲染层落占位段兜底。
function chapterPages() {
  const paragraphs = (chapterGeneratedText || "")
    .split(/\n+/)
    .map((p) => p.trim())
    .filter(Boolean);
  if (!paragraphs.length) return [[]];
  const pages = [];
  for (let i = 0; i < paragraphs.length; i += CHAPTER_PAGE_SIZE) {
    pages.push(paragraphs.slice(i, i + CHAPTER_PAGE_SIZE));
  }
  return pages;
}

function generatedChapterMarkup(chapter, nextChapter) {
  const chapterNumber = String(chapterCreationIndex + 1).padStart(2, "0");
  // Story 4.5：恢复分页阅读器（4.4 曾降为单页顺序渲染，保留骨架供本 story 复用）。
  const pages = chapterPages();
  // 越界钳制（AC1）：改进后正文变短、页数减少时把当前页钳到有效范围，防空白页。
  chapterReaderPage = Math.max(0, Math.min(chapterReaderPage, pages.length - 1));
  const pageParagraphs = pages[chapterReaderPage];
  const prose = pageParagraphs.length
    ? pageParagraphs
        .map((paragraph, indexInPage) => {
          // 批注坐标是「页:页内段」（chapterReaderPage:indexInPage），供 chapterAnnotations 定位与跨页跳转。
          const hasAnnotation = chapterAnnotations.some(
            (annotation) =>
              annotation.page === chapterReaderPage &&
              annotation.paragraph === indexInPage,
          );
          const isSelected =
            chapterAnnotationTarget?.page === chapterReaderPage &&
            chapterAnnotationTarget?.paragraph === indexInPage;
          const isLocated =
            chapterAnnotationFocus?.page === chapterReaderPage &&
            chapterAnnotationFocus?.paragraph === indexInPage;
          // 定稿后不渲染 ＋ 触发器（EXPERIENCE.md:94/112）。
          const trigger = chapterFinalized
            ? ""
            : `<button type="button" class="paragraph-annotation-trigger" data-annotation-page="${chapterReaderPage}" data-annotation-paragraph="${indexInPage}" aria-label="给第 ${indexInPage + 1} 段添加批注">＋</button>`;
          return `<div class="chapter-paragraph ${hasAnnotation ? "has-annotation" : ""} ${isSelected ? "is-selected" : ""} ${isLocated ? "is-located" : ""}" data-paragraph-position="${chapterReaderPage}:${indexInPage}" tabindex="-1">${trigger}<p>${escapeHtml(paragraph)}</p></div>`;
        })
        .join("")
    : '<div class="chapter-paragraph"><p>（本章正文为空，可点「改进本章」或重新生成。）</p></div>';
  const pageNumber = String(chapterReaderPage + 1).padStart(2, "0");
  const pageTotal = String(pages.length).padStart(2, "0");
  return `<article class="chapter-reader" aria-labelledby="chapter-reader-title">
    <div class="chapter-reader-meta"><span>第 ${(currentStagePlan && currentStagePlan.stageNumber) || 1} 阶段 / 第 ${chapterNumber} 章</span><span>${chapterFinalized ? "已定稿" : `草稿 V${chapterRevision}`}</span></div>
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
  const chapterNumber = String(chapterCreationIndex + 1).padStart(2, "0");
  // 真实 projectId（AC5）：章节页锚点用它替换硬编码 demo。回退到 explorationProjectId
  // （从探索无缝进入时已设），仍为空则退回作品库。
  const backProjectId = chapterProjectId || explorationProjectId;
  const backHref = backProjectId
    ? `#/projects/${backProjectId}/explore`
    : "#/projects";

  let mainContent;
  // Story 4.3：阶段规划幕后生成——就绪前主区显示加载/占位或错误态（AC1/AC6），不再用 mock。
  if (!stagePlan) {
    if (stagePlanLoadState === "error") {
      document.title = `第 ${chapterCreationIndex + 1} 章 · Muse`;
      mainContent = `<section class="chapter-generating" aria-live="polite">
        <div class="chapter-overline">Chapter creation / ${chapterNumber}</div>
        <span class="generation-index">${chapterNumber}</span>
        <h1>阶段计划没能生成</h1>
        <p>${escapeHtml(stagePlanErrorText || "生成失败，请稍后重试。")}</p>
        <div class="chapter-heading"><button class="primary-button" type="button" data-retry-stage-plan>重新生成 <span>→</span></button></div>
      </section>`;
    } else if (stagePlanLoadState === "empty") {
      // 未生成态（review 改时机）：确认时触发失败 / 关页重开丢了在途 taskId → 进页面查库空且无在途
      // 任务。不自动叫生成（杜绝进页面反复触发），由用户明示点「生成阶段计划」才触发。
      document.title = `第 ${chapterCreationIndex + 1} 章 · Muse`;
      mainContent = `<section class="chapter-generating" aria-live="polite">
        <div class="chapter-overline">Chapter creation / ${chapterNumber}</div>
        <span class="generation-index">${chapterNumber}</span>
        <h1>还没有阶段计划</h1>
        <p>确认设定后我们会在后台规划这个阶段的章节安排；如果还没生成，可以现在开始。</p>
        <div class="chapter-heading"><button class="primary-button" type="button" data-retry-stage-plan>生成阶段计划 <span>→</span></button></div>
      </section>`;
    } else {
      document.title = `第 ${chapterCreationIndex + 1} 章 · Muse`;
      mainContent = `<section class="chapter-generating" aria-live="polite">
        <div class="chapter-overline">Chapter creation / ${chapterNumber}</div>
        <span class="generation-index">${chapterNumber}</span>
        <h1>正在准备你的第一章</h1>
        <p>Agent 正在依据你的故事设定规划这个阶段的章节安排，稍等片刻就能开始创作。</p>
        <div class="generation-steps"><span class="is-active">规划阶段目标</span><span>安排章节骨架</span><span>进入第一章</span></div>
      </section>`;
    }
    app.innerHTML = `<div class="chapter-page">
      <header class="explore-header"><a class="explore-back" href="${backHref}">← 故事设定</a><div class="explore-project"><strong>${escapeHtml(explorationTitle)}</strong><span>章节创作</span></div><div class="save-state"><i></i> 阶段计划生成中</div></header>
      <main class="chapter-workbench"><div class="chapter-main">${mainContent}</div>${chapterContextMarkup(null)}</main>
    </div>`;
    bindChapterCreationInteractions();
    return;
  }

  // 章数由 LLM 按剧情定（AC2 不写死），路由章号只钳下界（app.js render 分支 Math.max(0,…)）；
  // 越界章号（如深链/下一章跳到超出真实章数）取不到骨架，退化为错误态而非 chapter.title 崩白页。
  // Story 4.7：chapterCreationIndex 是**全局** 0-based 章号；当前阶段章列表各自从 0 起，故用
  // 「全局 - stageChapterOffset」取相对索引（首阶段 offset=0 时与旧行为一致）。
  const stageChapterIndex = chapterCreationIndex - stageChapterOffset;
  const chapter = stagePlan.chapters[stageChapterIndex];
  if (!chapter) {
    document.title = `第 ${chapterCreationIndex + 1} 章 · Muse`;
    app.innerHTML = `<div class="chapter-page">
      <header class="explore-header"><a class="explore-back" href="${backHref}">← 故事设定</a><div class="explore-project"><strong>${escapeHtml(explorationTitle)}</strong><span>章节创作</span></div><div class="save-state"><i></i> 阶段计划</div></header>
      <main class="chapter-workbench"><div class="chapter-main"><section class="chapter-generating" aria-live="polite">
        <div class="chapter-overline">Chapter creation / ${chapterNumber}</div>
        <span class="generation-index">${chapterNumber}</span>
        <h1>这一章还没有规划</h1>
        <p>当前阶段计划只安排到第 ${stagePlan.chapters.length} 章，第 ${chapterCreationIndex + 1} 章暂不在其中。</p>
        <div class="chapter-heading"><a class="primary-button" href="${backProjectId ? `#/projects/${backProjectId}/chapters/1` : "#/projects"}">回到第一章 <span>→</span></a></div>
      </section></div>${chapterContextMarkup(stagePlan)}</main>
    </div>`;
    bindChapterCreationInteractions();
    return;
  }
  document.title = `${chapter.title} · 第 ${chapterCreationIndex + 1} 章 · Muse`;
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
      stagePlan.chapters[stageChapterIndex + 1],
    );
  }
  app.innerHTML = `<div class="chapter-page">
    <header class="explore-header"><a class="explore-back" href="${backHref}">← 故事设定</a><div class="explore-project"><strong>${escapeHtml(explorationTitle)}</strong><span>章节创作</span></div><div class="save-state"><i></i> ${chapterFinalized ? "本章已定稿" : chapterCreationState === "reading" ? "草稿已保存" : "已保存"}</div></header>
    <main class="chapter-workbench"><div class="chapter-main">${mainContent}</div>${chapterContextMarkup(stagePlan)}</main>
  </div>`;
  bindChapterCreationInteractions();
}

function bindChapterCreationInteractions() {
  // Story 4.3（review 改时机）：未生成/失败态的「生成/重新生成」——用户明示触发，直接走
  // startStagePlanFlow（POST 拿 taskId + 存储 + 消费 SSE）。进页面渲染绝不自动触发；只有此处
  // 用户点击、和「确认设定成功」那一次会触发。先取消在途 + 递增代次守卫。
  document
    .querySelector("[data-retry-stage-plan]")
    ?.addEventListener("click", () => {
      if (!chapterProjectId) return;
      if (stagePlanAbortController) stagePlanAbortController.abort();
      stagePlanSeq += 1;
      startStagePlanFlow(chapterProjectId, stagePlanSeq);
    });
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
      if (!chapterProjectId) return;
      chapterIdea = event.currentTarget.querySelector("textarea").value.trim();
      // Story 4.4：重置本章创作态（批注/点评/版本），启真实生成流（替换 1200ms mock）。
      chapterRevision = 1;
      chapterGeneratedText = "";
      chapterAgentResult = "";
      chapterLastRevisionAction = "";
      chapterAnnotations = [];
      chapterAnnotationTarget = null;
      chapterAnnotationDraft = "";
      chapterAnnotationFocus = null;
      chapterFinalized = false;
      // 递增代次 + 取消在途，防重复提交/切页赛跑（三守卫，仿 4.3）。
      if (chapterGenAbortController) chapterGenAbortController.abort();
      chapterGenSeq += 1;
      startChapterGenFlow(
        chapterProjectId,
        chapterCreationIndex + 1,
        chapterIdea,
        chapterGenSeq,
      );
    });
  // Story 4.5：翻页监听（4.4 接真实正文时删了分页 UI 与该死监听，本 story 恢复）。翻页只移
  // 指针、不改数据；页数上界用 chapterPages() 重算（与渲染共用纯函数，避免状态不同步）；
  // 翻页清当前批注目标但保留已保存批注列表与整体点评（EXPERIENCE.md:93）。
  document.querySelectorAll("[data-chapter-page]").forEach((button) => {
    button.addEventListener("click", () => {
      const pageCount = chapterPages().length;
      if (button.dataset.chapterPage === "previous") {
        chapterReaderPage = Math.max(0, chapterReaderPage - 1);
      } else {
        chapterReaderPage = Math.min(pageCount - 1, chapterReaderPage + 1);
      }
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
      document
        .querySelector(
          `[data-paragraph-position="${chapterAnnotationFocus.page}:${chapterAnnotationFocus.paragraph}"]`,
        )
        ?.focus();
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
      // 改进守卫（AC1）：无点评且无批注时改进不可用（与 canImprove 一致，app.js:3112）。
      if (
        action === "improve" &&
        !chapterFeedback.trim() &&
        !chapterAnnotations.length
      )
        return;
      if (chapterAgentBusy) return; // 忙碌中防重复提交（AC8，按钮已 disabled 兜底）
      if (!chapterProjectId) return;
      // Story 4.6：组装反馈随请求体一次性传（决策 3：不落库）。批注 {page,paragraph,text} →
      // {paragraph: 段落原文, comment: 批注文本}——原文反查 chapterPages()[page][paragraph]
      // 给 LLM 锚点（反查不到退化为空串，后端仍收 comment）。重生忽略批注、后端不消费。
      const pages = chapterPages();
      const annotations =
        action === "improve"
          ? chapterAnnotations.map((a) => ({
              paragraph: (pages[a.page] && pages[a.page][a.paragraph]) || "",
              comment: a.text || "",
            }))
          : [];
      const feedback = chapterFeedback.trim();
      chapterAnnotationFocus = null;
      chapterAgentBusy = true;
      chapterAgentResult =
        action === "regenerate"
          ? "正在重新规划并生成这一章……"
          : "正在根据你的点评改进这一章……";
      renderChapterCreation();
      // 递增代次 + 取消在途，防重复提交/切页赛跑（三守卫，仿 4.4 生成流）。
      if (chapterGenAbortController) chapterGenAbortController.abort();
      chapterGenSeq += 1;
      startChapterReviseFlow(
        chapterProjectId,
        chapterCreationIndex + 1,
        action,
        feedback,
        annotations,
        chapterGenSeq,
      );
    });
  });
  document
    .querySelector("[data-finalize-chapter]")
    ?.addEventListener("click", async () => {
      if (chapterAgentBusy) return; // 忙碌中防重复提交
      if (!chapterProjectId) return;
      const chapterNumber = chapterCreationIndex + 1;
      // 即时置忙碌防重复点（定稿走同步 REST，无 SSE）。
      chapterAgentBusy = true;
      chapterAgentResult = "正在定稿这一章……";
      renderChapterCreation();
      try {
        const result = await chapterApi.finalizeChapter(
          chapterProjectId,
          chapterNumber,
        );
        chapterFinalized = result && result.status === "finalized";
        chapterRevision = (result && result.revision) || chapterRevision;
        chapterAnnotationTarget = null;
        chapterAnnotationDraft = "";
        chapterAnnotationFocus = null;
        chapterAgentBusy = false;
        chapterAgentResult = `第 ${String(chapterNumber).padStart(2, "0")} 章已采用第 ${chapterRevision} 版草稿定稿，并将作为后续章节的正式上下文。`;
        archiveDialogOpen = false;
        // 阶段交界分流（AC6，决策 3）：本阶段末章定稿 → 进阶段交界方向输入页；否则走归档流。
        const stagePlan = chapterStagePlan();
        const stageChapterCount =
          (stagePlan && stagePlan.chapters && stagePlan.chapters.length) || 0;
        const isLastOfStage =
          stageChapterCount > 0 &&
          chapterNumber - stageChapterOffset === stageChapterCount;
        if (isLastOfStage) {
          stageDirectionText = "";
          location.hash = `#/projects/${chapterProjectId}/stage-direction`;
        } else {
          location.hash = `#/projects/${chapterProjectId}/archive`;
        }
      } catch (err) {
        // 定稿失败：保留 reading 态可重试 + 可读错误提示（AC9）。
        chapterFinalized = false;
        chapterAgentBusy = false;
        chapterAgentResult = "";
        renderChapterCreation();
        showChapterInlineError(storyErrorText(err));
      }
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
  // Story 4.3（review）：chapterStagePlan() 删 mock 后可能返 null（归档路由不加载 currentStagePlan，
  // 刷新直达/登出后进归档时为 null）。归档页本体属 4.5-4.7（第二阶段仍是占位 mock），本 story 只做
  // null 兜底防白屏，不扩范围接真实归档数据。
  // F6 review patch：GET stage-plan 自 4.7 起返回 latest（当前所处阶段）——若用户在第 k 阶段末章
  // 定稿进归档，stagePlan.chapters 是「第 k 阶段」骨架但仍按硬编码「第一阶段」展示。改为按
  // stagePlan.stageNumber 渲染真实阶段号；stageNumber 缺省（旧 mock / 未加载）回落「第一阶段」。
  const firstStageChapters = (stagePlan && stagePlan.chapters) || [];
  const currentStageNumber = (stagePlan && stagePlan.stageNumber) || 1;
  return [
    {
      title: `第 ${currentStageNumber} 阶段`,
      chapters: firstStageChapters,
      completedCount: Math.min(
        chapterCreationIndex + 1 - stageChapterOffset,
        firstStageChapters.length,
      ),
      numberOffset: stageChapterOffset,
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
      numberOffset: firstStageChapters.length,
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
      // Story 4.7：真实 projectId 替换 demo（归档页本体仍 mock，归 Epic 5 Story 5.3；此处只
      // 修死链，跳转 projectId 用真实值）。
      const nextProjectId = chapterProjectId || explorationProjectId || "demo";
      location.hash = `#/projects/${nextProjectId}/chapters/${chapterCreationIndex + 1}`;
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
  freeMessageQueue = [];
  freeMessageBusyLabel = "";
  freeSettlePending = false;
  freeClueFocusedIds.clear();
  deferredFreeClues = null;
  guidanceFields = {};
  guidanceCurrentField = null;
  guidanceReadyToSettle = false;
  guidanceSuggestions = [];
  guidanceSuggestionsExpanded = false;
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
  // Story 7.7：新建作品时一并复位设定卡编辑门禁 + 文风锚点全套状态（防跨作品残留）。
  profileFieldEditing.clear();
  profileReviseBusy = false;
  profileConfirmBusy = false;
  profileDiscardBusy = false;
  styleAnchorTab = "library";
  styleAnchorSelected = null;
  styleAnchorPasteText = "";
  styleAnchorSaving = false;
  styleAnchorErrorText = "";
  styleAnchorSamples = null;
  styleAnchorSamplesLoading = false;
  styleAnchorPanelOpen = false;
  styleAnchorSeq += 1;
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
  // Story 4.3：清阶段规划幕后加载态（登出/重置时 abort 在途流 + 复位守卫）。
  if (stagePlanAbortController) {
    stagePlanAbortController.abort();
    stagePlanAbortController = null;
  }
  chapterProjectId = "";
  stagePlanLoadState = "idle";
  stagePlanErrorText = "";
  stagePlanSeq += 1;
  clearStagePlanTask();
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
  // Story 4.7：重置阶段偏移 + 下一阶段规划态（登出/重置，防下一作品/账号残留）。
  stageChapterOffset = 0;
  clearStageOffset();
  nextStageLoadState = "idle";
  nextStageErrorText = "";
  clearNextStageTask();
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
      // Story 7.7：一并清确认设定 sessionStorage（防 B 读到 A 的 confirmedStoryProfile 缓存）。
      window.sessionStorage.removeItem(confirmedStoryProfileKey);
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
      guidanceReadyToSettle = false;
      guidanceSuggestions = [];
      guidanceSuggestionsExpanded = false;
      guidanceSkipping = false;
      guidanceStartingEntry = null;
      finalStoryProfile = null;
      finalStoryProfileSignature = "";
      pendingStoryProfile = false;
      // Story 7.7：清设定卡/文风锚点全套状态，防 A 的待确认卡/已抽文风泄漏给 B（多租户，AC8）。
      lastProfileChangedFields = [];
      profileFeedbackStatus = "";
      confirmedStoryProfile = null;
      profileFieldEditing.clear();
      profileReviseBusy = false;
      profileConfirmBusy = false;
      profileDiscardBusy = false;
      styleAnchorTab = "library";
      styleAnchorSelected = null;
      styleAnchorPasteText = "";
      styleAnchorSaving = false;
      styleAnchorErrorText = "";
      styleAnchorSamples = null;
      styleAnchorSamplesLoading = false;
      styleAnchorPanelOpen = false;
      styleAnchorSeq += 1;
      guidedLoadState = "loading";
      guidedLoadError = null;
      settleErrorText = "";
      explorationProjectId = "";
      // Story 4.3：清阶段规划态防跨用户残留（A 在第一章页登出→B 同标签页登录，勿见 A 的阶段
      // 计划）；abort 在途 SSE/生成流、自增 seq 作废在途回调（与各模块 logout 复位一致）。
      if (stagePlanAbortController) {
        stagePlanAbortController.abort();
        stagePlanAbortController = null;
      }
      currentStagePlan = null;
      chapterProjectId = "";
      stagePlanLoadState = "idle";
      stagePlanErrorText = "";
      stagePlanSeq += 1;
      clearStagePlanTask();
      // Story 4.7 review patch F5：同步清多阶段映射 + 下一阶段规划态——A 在第 k 阶段章号 N 登出 →
      // B 同 tab 登录另一 project，sessionStorage 里 stage-offset / next-stage-task 仍是 A 的，
      // 进 chapterMatch 用错 offset 渲染章骨架错位。与 resetExplorationStateForNewProject 同步清。
      stageChapterOffset = 0;
      clearStageOffset();
      nextStageLoadState = "idle";
      nextStageErrorText = "";
      clearNextStageTask();
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
  const projectId = chapterProjectId || explorationProjectId || "demo";
  // 「返回创作」回到刚定稿的上一阶段末章（reading 只读）；至少回第 1 章兜底。
  const backHref = `#/projects/${projectId}/chapters/${Math.max(1, chapterCreationIndex + 1)}`;
  // 规划中 / 失败态（AC5/AC9）：提交方向后异步生成下一阶段，就绪进下一阶段首章。
  if (nextStageLoadState === "loading") {
    app.innerHTML = `<div class="stage-direction-page">
      <header class="explore-header"><a class="explore-back" href="${backHref}">← 返回创作</a><div class="explore-project"><strong>${escapeHtml(explorationTitle)}</strong><span>阶段交界</span></div><div class="save-state"><i></i> 正在规划下一阶段</div></header>
      <main class="stage-direction-main">
        <section class="stage-direction-card" aria-live="polite">
          <div class="stage-direction-overline">Between stages / 阶段交界</div>
          <h1>正在规划下一阶段……</h1>
          <p class="stage-direction-lead">我在依据你的方向和前文，规划接下来这一阶段的章节安排，稍等片刻就能继续写。</p>
        </section>
      </main>
    </div>`;
    return;
  }
  const errorBlock =
    nextStageLoadState === "error"
      ? `<p class="stage-direction-error" role="alert">${escapeHtml(nextStageErrorText || "规划失败，请稍后重试。")}</p>`
      : "";
  // F9：demo 演示项目 stage-direction 只能看到占位（真实触发后端 plan_next_stage 需要真实 projectId）。
  // 三按钮 demo 下整体隐藏，文案说明「演示模式到此为止」；「返回创作」仍可用回 chapter 页。
  const isDemoProject = projectId === "demo";
  const actionBlock = isDemoProject
    ? `<p class="stage-direction-error" role="note">演示模式下不生成真实下一阶段规划，请返回创作或登录起始真实作品。</p>`
    : `<textarea class="input stage-direction-input" id="stage-direction" placeholder="比如：让主角开始怀疑同伴 / 节奏慢下来铺一段感情 / 我想开始收尾了……">${escapeHtml(stageDirectionText)}</textarea>
        <div class="stage-direction-actions">
          <button class="secondary-button" type="button" data-stage-continue>直接继续</button>
          <button class="primary-button" type="button" data-stage-submit>带着这个方向写下去 <span>→</span></button>
        </div>
        <button class="stage-direction-finale" type="button" data-stage-finale>我想开始收尾了 →</button>`;
  app.innerHTML = `<div class="stage-direction-page">
    <header class="explore-header"><a class="explore-back" href="${backHref}">← 返回创作</a><div class="explore-project"><strong>${escapeHtml(explorationTitle)}</strong><span>阶段交界</span></div><div class="save-state"><i></i> 上一阶段已写完</div></header>
    <main class="stage-direction-main">
      <section class="stage-direction-card">
        <div class="stage-direction-overline">Between stages / 阶段交界</div>
        <h1>这一段，想往哪走？</h1>
        <p class="stage-direction-lead">上一阶段写完了。如果心里已经有方向，写一句给我；没有也没关系，直接继续，我会顺着故事往下写。</p>
        ${errorBlock}
        ${actionBlock}
      </section>
    </main>
  </div>`;
  bindStageDirectionInteractions(projectId);
}

function bindStageDirectionInteractions(projectId) {
  const input = document.querySelector("#stage-direction");
  input?.addEventListener("input", () => {
    stageDirectionText = input.value;
  });
  document
    .querySelector("[data-stage-submit]")
    ?.addEventListener("click", () => {
      startNextStageFlow(projectId, stageDirectionText);
    });
  document
    .querySelector("[data-stage-continue]")
    ?.addEventListener("click", () => {
      // 「直接继续」= 空方向触发下一阶段规划（AC7，LLM 按设定+前文自然推进，非「什么都不做」）。
      startNextStageFlow(projectId, "");
    });
  document.querySelector("[data-stage-finale]")?.addEventListener("click", () => {
    // 「我想开始收尾了」= 收尾声明作方向，LLM 规划收束主线的收尾阶段（AC5）。
    startNextStageFlow(
      projectId,
      "（读者已声明：进入收尾阶段，请规划一个能收束主线、走向结局的阶段）",
    );
  });
}

// Story 4.7：触发并消费「下一阶段规划」——POST plan-next-stage 拿 taskId → 存 sessionStorage
// （刷新接回）→ 进 loading 态 → 消费 SSE result/error（仿 startChapterGenFlow + consumeStagePlanTask）。
// 就绪后进下一阶段首章：stageChapterOffset 推到上一阶段末章之后、chapterCreationIndex 置新阶段首章
// 全局号、跳 chapters/N。失败退回卡片保留方向文本可重试。
async function startNextStageFlow(projectId, direction) {
  if (nextStageLoadState === "loading") return; // 防重复提交
  if (!projectId || projectId === "demo") return; // 无真实 projectId 不触发
  stagePlanSeq += 1;
  const seq = stagePlanSeq;
  nextStageLoadState = "loading";
  nextStageErrorText = "";
  renderStageDirection();
  try {
    const { taskId } = await chapterApi.planNextStage(projectId, { direction });
    // F7：sessionStorage 写失败（隐私模式/quota）容忍——taskId 已在内存中走 SSE 消费；
    // sessionStorage 只是刷新接回的兜底，丢它不应让用户以为「后端失败请重试」（会触发重复付费请求）。
    try {
      persistNextStageTask(projectId, taskId);
    } catch (storageErr) {
      // eslint-disable-next-line no-console
      console.warn("[next-stage] sessionStorage 写失败，刷新接回失效", storageErr);
    }
    await consumeNextStageTask(projectId, seq, taskId);
  } catch (err) {
    if (seq !== stagePlanSeq) return; // 被后续提交取代
    clearNextStageTask();
    nextStageLoadState = "error";
    nextStageErrorText = storyErrorText(err);
    renderStageDirection();
  }
}

async function consumeNextStageTask(projectId, seq, taskId) {
  const stale = () => seq !== stagePlanSeq;
  let gotTerminal = false;
  try {
    await explorationApi.taskEvents(taskId, {
      onEvent: (type, data) => {
        if (stale()) return;
        if (type === "result" && data && data.stagePlan) {
          gotTerminal = true;
          clearNextStageTask();
          // 上一阶段末章全局号 = chapterCreationIndex（定稿末章时的全局 0-based）；下一阶段首章
          // 全局 index = 上一阶段末章 index + 1 = chapterCreationIndex + 1（末章 index 即
          // stageChapterOffset + 当前阶段章数 - 1）。offset 推到新阶段首章。
          const newOffset = chapterCreationIndex + 1;
          stageChapterOffset = newOffset;
          persistStageOffset(projectId, newOffset);
          currentStagePlan = {
            stageNumber: data.stagePlan.stageNumber || 1,
            goal: data.stagePlan.goal || "",
            chapters: Array.isArray(data.stagePlan.chapters)
              ? data.stagePlan.chapters
              : [],
          };
          stagePlanLoadState = "ready";
          // 进下一阶段首章输入态（重置章内态，仿 data-start-next-chapter）。
          chapterCreationIndex = newOffset;
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
          nextStageLoadState = "idle";
          stageDirectionText = "";
          location.hash = `#/projects/${projectId}/chapters/${chapterCreationIndex + 1}`;
        } else if (type === "error") {
          gotTerminal = true;
          clearNextStageTask();
          nextStageLoadState = "error";
          // F11：优先用后端透传的 message（ErrorEnvelope.message 是面向用户的中文），
          // code 走 storyErrorText 兜底。后端「尚无阶段规划，无法规划下一阶段。」等精心文案才不丢。
          nextStageErrorText =
            (data && data.message) || storyErrorText({ code: data && data.code });
          renderStageDirection();
        }
        // progress：loading 态已在显示，不额外更新。
      },
    });
    // 无终态兜底（防永久 spinner）。
    if (!stale() && !gotTerminal && nextStageLoadState === "loading") {
      clearNextStageTask();
      nextStageLoadState = "error";
      nextStageErrorText = storyErrorText({ code: "generate_failed" });
      renderStageDirection();
    }
  } catch (err) {
    if (stale()) return;
    clearNextStageTask();
    nextStageLoadState = "error";
    nextStageErrorText = storyErrorText(err);
    renderStageDirection();
  }
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

function render() {
  document.body.classList.remove("dialog-open");
  const exploreMatch = hashPath().match(/^#\/projects\/([^/]+)\/explore$/);
  const chapterMatch = hashPath().match(
    /^#\/projects\/([^/]+)\/chapters\/(\d+)$/,
  );
  const archiveMatch = hashPath().match(/^#\/projects\/([^/]+)\/archive$/);
  const stageDirectionMatch = hashPath().match(
    /^#\/projects\/([^/]+)\/stage-direction$/,
  );
  // review R2 P2：离开探索页时清理在途 SSE + 门禁（teardownExplorationInflight 原为死代码，此处挂载）。
  // 防 settle/interpret 在途时切走 → 流不 abort 连接悬挂 + 陈旧回调污染。teardown 不动 pending
  // 设定卡（会话内恢复态，导航离开应保留）。进 explore 分支由 loadGuidedExploration 自管清理。
  if (!exploreMatch) teardownExplorationInflight();
  // Story 4.3：离开章节页时 abort 在途阶段规划流（防切走后 SSE 悬挂 + 陈旧回调污染）。
  if (!chapterMatch && stagePlanAbortController) {
    stagePlanAbortController.abort();
    stagePlanAbortController = null;
  }
  // Story 4.4：离开章节页时 abort 在途章节生成流（同理防 SSE 悬挂 + 陈旧回调）。生成任务已入队、
  // 后端继续跑并落库；本地只是断开 SSE 消费，重进凭在途 taskId / 落库正文恢复（不重复付费）。
  if (!chapterMatch && chapterGenAbortController) {
    chapterGenAbortController.abort();
    chapterGenAbortController = null;
  }
  if (hashPath() === "#/projects") {
    // 每次进入作品库都重新拉取最新列表（新建/改名/删除后返回能看到变化）。
    projectsLoadState = "loading";
    renderProjects();
  } else if (hashPath() === "#/projects/demo/readthrough") renderReadthrough();
  else if (hashPath() === "#/settings/model-access") {
    // 每次进入设置页都重拉最新绑定态 + 用量（绑定/解绑后返回、跨账号都能看到变化）。
    byokLoadState = "loading";
    renderByok();
  }
  else if (stageDirectionMatch) {
    // Story 4.7：阶段交界方向输入页（参数化真实 projectId）。设 chapterProjectId 供
    // renderStageDirection / startNextStageFlow 消费；恢复 stageChapterOffset（跨阶段刷新）。
    chapterProjectId = stageDirectionMatch[1];
    stageChapterOffset = readStageOffset(chapterProjectId);
    // F8 review patch：进 stageDirectionMatch 路由**始终** bump stagePlanSeq——不再只在
    // pendingNextStage 分支 bump。否则 chapter 页在途 consumeStagePlanTask 占着旧 seq，
    // 本分支走 idle 渲染时陈旧回调仍可能写 currentStagePlan / stageChapterOffset 脏数据。
    stagePlanSeq += 1;
    const enterSeq = stagePlanSeq;
    // F2 review patch：进入时校验「chapterNumber（chapterCreationIndex+1）== 当前阶段末章全局号」，
    // 不在末章则不允许发新阶段规划——防直接 URL 跳 stage-direction / 中途手改 URL 绕过末章守卫。
    // 判据：已知 stageChapterOffset（首章全局 index，0-based）+ currentStagePlan.chapters.length
    // （当前阶段章数）。末章 1-based 全局号 = offset + chapters.length。当前章号（chapterCreationIndex+1）
    // 必须等于这个值；否则以「当前阶段已写出章数」为兜底重定向回本章（继续写作），而不是允许跳交界。
    (async () => {
      // 异步拉一次 stage-plan 确保 currentStagePlan 存在（直接 URL 进 stage-direction 时可能 null）。
      if (!currentStagePlan) {
        try {
          const existing = await chapterApi.getStagePlan(chapterProjectId);
          if (enterSeq !== stagePlanSeq) return;
          if (existing && Array.isArray(existing.chapters) && existing.chapters.length) {
            currentStagePlan = existing;
            stagePlanLoadState = "ready";
          }
        } catch (err) {
          // 拉取失败：当下面校验 currentStagePlan null 兜底重定向 chapter 1。
        }
      }
      if (enterSeq !== stagePlanSeq) return;
      const chaptersCount =
        (currentStagePlan && currentStagePlan.chapters && currentStagePlan.chapters.length) || 0;
      const lastChapterGlobalNumber = chaptersCount > 0 ? stageChapterOffset + chaptersCount : 0;
      const currentChapterNumber = chapterCreationIndex + 1;
      if (!chaptersCount || currentChapterNumber !== lastChapterGlobalNumber) {
        // 非末章 / 无当前阶段规划 / 直接 URL 进入：退回当前阶段首章或全局第 1 章兜底。
        // 当前阶段已写过章则回落到当前阶段末章（继续写作），否则回全局第 1 章。
        const fallbackNumber = chaptersCount > 0 ? lastChapterGlobalNumber : 1;
        location.hash = `#/projects/${chapterProjectId}/chapters/${Math.max(1, fallbackNumber)}`;
        return;
      }
      // 校验通过 = 当前章就是当前阶段末章。继续走 pendingNextStage 接回 或 idle 渲染。
      const pendingNextStage = readNextStageTask(chapterProjectId);
      if (pendingNextStage) {
        nextStageLoadState = "loading";
        nextStageErrorText = "";
        renderStageDirection();
        consumeNextStageTask(chapterProjectId, enterSeq, pendingNextStage);
      } else {
        nextStageLoadState = "idle";
        renderStageDirection();
      }
    })();
  } else if (exploreMatch) {
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
      // 待确认设定卡刷新恢复优先（AC7）：pending 态先即时渲染缓存卡（renderExploration 末尾
      // 重挂弹窗、刷新无闪烁），再 reconcilePendingStoryProfile 以后端 GET 对账（覆盖/清陈旧）。
      // 非 pending 时才建会话 + 回填已答。
      if (pendingStoryProfile && finalStoryProfile) {
        explorationProjectId = routeProjectId;
        guidedLoadState = "ready";
        renderExploration();
        reconcilePendingStoryProfile(routeProjectId);
      } else {
        loadGuidedExploration(routeProjectId);
      }
    } else if (pendingStoryProfile && finalStoryProfile) {
      // 自由模式同样支持待确认卡刷新恢复（AC7）：settle 弹卡后刷新不回退到自由对话主界面。
      explorationProjectId = routeProjectId;
      freeLoadState = "ready";
      renderExploration();
      reconcilePendingStoryProfile(routeProjectId);
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
    const routeProjectId = chapterMatch[1];
    chapterCreationIndex = Math.max(0, Number(chapterMatch[2]) - 1);
    // Story 4.7：恢复当前阶段首章偏移（跨阶段刷新/深链）。**F10 review patch**：不做 Math.min
    // 静默钳制——clamp 只改 module 变量不写回 sessionStorage，刷新前后行为不一致非常难调；改为
    // 直接读 sessionStorage。若 offset > chapterCreationIndex（用户手动 URL 回跳更早章 / 脏数据），
    // stageChapterIndex 为负数 → stagePlan.chapters[负数] 是 undefined → renderChapterCreation
    // 走「chapter 不存在」fallback 错误态，让用户看到「章节骨架缺失」而非内容错乱。当前阶段
    // 正常线性向前不触发；要支持「回看上一阶段旧章」属 Epic 5 通读视图范畴，不在本章页路由做。
    stageChapterOffset = readStageOffset(routeProjectId);
    // F2 review patch：进 chapterMatch 也 bump stagePlanSeq，让在途 consumeStagePlanTask /
    // consumeNextStageTask 走 stale 早退、不写脏 currentStagePlan / stageChapterOffset。
    // 与 stagePlanAbortController.abort() 一起在下方 loadChapterStagePlan 头部统一；这里先 bump seq。
    stagePlanSeq += 1;
    // Story 4.3：消费路由真实 projectId（AC5）。同一作品且阶段规划已就绪 → 直接渲染
    // （避免切页/内部重渲染时重复拉取）；否则走加载入口（review 改时机后：只 GET 落库恢复 / 凭本地
    // taskId 接回在途任务，绝不主动叫新生成——触发只发生在确认设定成功那一次或用户明示点生成）。
    if (
      currentStagePlan &&
      chapterProjectId === routeProjectId &&
      stagePlanLoadState === "ready"
    ) {
      // 阶段规划已就绪且同作品：同章内部重渲染直接渲染；跨章跳转（章号变了）须恢复新章正文态
      // （GET 落库正文 → reading / 接在途 / input），否则会用旧章正文渲染新章（Story 4.4）。
      // review 修复：同章 key 命中但正处 generating 且在途生成流已被离页 abort（controller=null）
      // 时，也须重新 recover——否则站内切走再回同章会永久卡「生成中」（无活跃 SSE 消费者、又因
      // key 命中不重连在途 taskId）。此时 recover 会凭 sessionStorage 的 taskId 接回或按落库/204 收敛。
      const sameChapterKey =
        chapterRecoveredKey === `${routeProjectId}:${chapterCreationIndex + 1}`;
      const stalledGenerating =
        chapterCreationState === "generating" && chapterGenAbortController === null;
      if (sameChapterKey && !stalledGenerating) {
        renderChapterCreation();
      } else {
        renderChapterCreation();
        recoverChapterState(routeProjectId, chapterCreationIndex + 1);
      }
    } else {
      loadChapterStagePlan(routeProjectId);
    }
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

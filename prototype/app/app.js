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
let showInspirationDirections = false;
// 引导探索答完最后一题后的“整理中”过渡态：遮住后台生成设定的等待，传递“它在认真理解我”的体感。
let guidedSettling = false;
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

const projects = [
  {
    id: "mist-harbor",
    title: "雾港回声",
    mode: "引导探索",
    phase: "章节创作",
    attention: "等待你",
    detail: "第 3 章草稿等待阅读",
    updated: "今天 16:40",
    action: "阅读草稿",
  },
  {
    id: "stardust-postman",
    title: "星尘邮差",
    mode: "自由探索",
    phase: "章节创作",
    attention: "等待你",
    detail: "第 2 章草稿等待阅读",
    updated: "昨天 21:08",
    action: "阅读草稿",
  },
  {
    id: "nameless",
    title: "未命名小说",
    mode: "引导探索",
    phase: "故事设定",
    attention: "可以继续",
    detail: "继续回答关于主角的问题",
    updated: "7 月 12 日",
    action: "继续设定",
  },
];

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
  };
  return messages[state] || null;
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
  return `
    <li class="project-row" data-project-id="${project.id}">
      <a class="project-archive-link" href="#/projects/${project.id}/archive" aria-label="查看《${project.title}》的章节归档"></a>
      <span class="project-number">${number}</span>
      <div class="project-copy">
        <div class="project-title-line"><h2>${project.title}</h2><span class="project-mode">${project.mode}</span></div>
        <div class="project-status"><span>${project.phase}</span><i></i><strong>${project.attention}</strong></div>
        <p>${project.detail}</p>
      </div>
      <time>${project.updated}</time>
      <button class="project-primary" data-continue="${project.id}">${project.action}<span>→</span></button>
      <div class="project-menu-wrap">
        <button class="project-menu-button" aria-label="${project.title}的更多操作" aria-expanded="false" data-menu="${project.id}">•••</button>
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

function renderProjects() {
  const state = queryState();
  const visibleProjects = state === "empty" ? [] : projects;
  document.title = "你的小说 · Muse";
  app.innerHTML = `
    <div class="library-page">
      <header class="library-header">
        <a class="wordmark" href="#/projects"><span class="wordmark-mark">M</span><span>Muse</span></a>
        <nav class="library-nav" aria-label="主导航"><a aria-current="page" href="#/projects">作品</a></nav>
        <div class="account"><span>creator@example.com</span><a href="#/login">退出</a></div>
      </header>
      <main class="library-main">
        <div class="library-heading">
          <div><div class="library-kicker">Library / ${String(visibleProjects.length).padStart(2, "0")} novels</div><h1>你的小说</h1><p>继续写下去。作品按照最后更新时间排列。</p></div>
          <span class="library-folio">02</span>
        </div>
        ${state === "error" ? `<section class="library-error"><strong>暂时无法读取你的作品。</strong><p>连接恢复后可以重新加载，不会影响已经保存的内容。</p><button class="secondary-button" data-reload>重新加载</button></section>` : visibleProjects.length ? `<ol class="project-list">${visibleProjects.map(projectRow).join("")}<li><button class="new-project" data-new-project><span class="new-number">＋</span><span><strong>开始一本新小说</strong><small>从一个想法，或者一份已经准备好的设定开始。</small></span><span class="new-arrow">→</span></button></li></ol>` : `<section class="empty-library"><div class="empty-lead"><div class="empty-index">First novel / 01</div><h2>你的第一本小说，<br />从这里开始。</h2></div><div class="empty-action"><p>不需要准备好完整故事。可以从一个模糊的想法开始，也可以直接写下已有设定。</p><button class="primary-button" data-new-project>开始一本新小说 <span>→</span></button></div></section>`}
        <details class="state-preview library-preview"><summary>原型状态预览</summary><div class="preview-links"><a class="preview-link" href="#/projects">作品列表</a><a class="preview-link" href="#/projects?state=empty">空状态</a><a class="preview-link" href="#/projects?state=error">加载失败</a></div></details>
      </main>
      ${createDialog()}
    </div>`;
  bindProjectInteractions();
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

// 引导探索提交一题答案：按当前翻页位置写入/覆盖答案并前进一题；
// 翻回旧题重选只更新该题，不清除后面的答案（问卷式前后翻页）。
// 只有停留在最后一题并作答时，才进“整理中”过渡态并弹故事设定卡。
function submitGuidedAnswer(answerText) {
  const answer = String(answerText || "").trim();
  if (!answer) return;
  const wasAnswered = explorationView < explorationHistory.length;
  explorationHistory[explorationView] = {
    question: currentExplorationQuestion().question,
    answer,
  };
  const isLastQuestion = explorationView >= explorationQuestions.length - 1;
  // 停在最后一题作答 = 全部答完：翻页指针推进到收尾页（题数），
  // 使“回到探索”落到带“上一题”的收尾屏而非死屏；随后进入整理中过渡态。
  if (isLastQuestion) {
    explorationView = explorationQuestions.length;
    guidedSettling = true;
    renderExploration();
    window.setTimeout(() => {
      guidedSettling = false;
      openStoryProfileDialog();
    }, 1200);
    return;
  }
  // 翻回旧题重选后前进：回到“已答进度”的下一题，避免把用户重新拽回问卷开头。
  explorationView = wasAnswered ? explorationView + 1 : explorationHistory.length;
  renderExploration();
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
  showInspirationDirections = false;
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
      stageInner = `
        <div class="guided-current is-complete">
          <span class="guided-progress">引导完成 · ${totalLabel} / ${totalLabel}</span>
          <p class="guided-question">这些问题已经把故事的骨架照亮了。</p>
          <p class="guided-complete-hint">如果想修改，可以回到上一题重新选择；准备好了就整理成一份故事设定。</p>
        </div>
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
  } else {
    // 自由探索：完全保持原有界面与右侧故事线索侧边栏（本次改动不触碰）。
    const canFinish = freeConversation.some((entry) => entry.role === "user");
    const formingHint = canFinish
      ? "故事线索已经足够，可以整理成一份故事设定。"
      : "继续和 Agent 讨论，线索足够时就能整理为故事设定。";
    storyForming = `
    <aside class="story-forming" aria-labelledby="story-forming-title">
      <div class="story-forming-head"><div><span>Living notes / draft</span><h2 id="story-forming-title">美好的故事即将展开</h2></div><strong>01</strong></div>
      <p class="story-forming-intro">Agent 会根据对话整理线索。这里的内容由你决定，也可以直接修改。</p>
      <div class="story-clues">
        ${storyClue("最初的念头", explorationHistory[0]?.answer || "")}
        ${storyClue("主角", explorationHistory[1]?.answer || "")}
        ${storyClue("核心冲突", explorationHistory[2]?.answer || "")}
        ${storyClue("世界与氛围", explorationHistory[4]?.answer || "")}
        ${customStoryClues.map(customStoryClue).join("")}
        <button class="add-story-clue" type="button" data-add-custom-clue><span>＋</span> 添加自定义设定</button>
      </div>
      <div class="forming-footer">
        <p>${formingHint}</p>
        <button class="finish-exploration" type="button" ${canFinish ? "" : "disabled"}>整理为故事设定 <span>→</span></button>
      </div>
    </aside>`;
    // 自由探索：进入即为自由讨论状态，沿用连续对话记录界面。
    const freeMessages = freeConversation
      .map(
        (
          entry,
        ) => `<article class="conversation-message ${entry.role === "agent" ? "agent-message" : "user-message"}">
          <div class="message-meta"><span>${entry.role === "agent" ? "Agent / 自由讨论" : "你"}</span></div>
          <p>${entry.text}</p>
        </article>`,
      )
      .join("");
    const freeOpening = `<article class="conversation-message agent-message">
      <div class="message-meta"><span>Agent / 自由讨论</span></div>
      <p>想到什么都可以先说出来。我们边聊边把人物、冲突和世界一点点理清楚。</p>
    </article>`;
    const inspirationOptions = [
      ["讨论人物", "我想让主角的性格更矛盾一些。"],
      ["讨论冲突", "这个核心冲突还能怎样变得更尖锐？"],
      ["讨论世界", "这个世界里还有哪些值得展开的规则？"],
    ];
    mainContent = `
      <section class="explore-dialogue" aria-labelledby="explore-title">
        <div class="explore-overline">Free exploration / 自由探索</div>
        <div class="explore-heading"><h1 id="explore-title">把故事聊出来</h1><span>自由探索</span></div>
        <section class="exploration-conversation" aria-label="自由讨论">
          <div class="conversation-scroll" data-conversation-scroll>
            ${freeOpening}
            ${freeMessages}
          </div>
        </section>
        <form class="explore-response compact-composer" id="explore-response" data-free-mode="true">
          <label for="explore-answer">继续讨论</label>
          <textarea id="explore-answer" placeholder="继续回答，或者和 Agent 讨论其他故事想法……" required></textarea>
          <div class="inspiration-list" ${showInspirationDirections ? "" : "hidden"}>
            ${inspirationOptions.map(([label, value]) => `<button type="button" data-direction="${value}">${label}</button>`).join("")}
          </div>
          <div class="response-actions">
            <label class="inspiration-toggle"><span>给我一些讨论方向</span><input type="checkbox" data-inspiration aria-label="显示灵感方向" ${showInspirationDirections ? "checked" : ""} /><i aria-hidden="true"></i></label>
            <button class="primary-button explore-submit" type="submit">发送 <span>→</span></button>
          </div>
        </form>
      </section>`;
  }

  document.title = `${explorationTitle} · ${isGuided ? "引导探索" : "自由探索"} · Muse`;
  app.innerHTML = `
    <div class="explore-page">
      <header class="explore-header">
        <a class="explore-back" href="#/projects">← 作品</a>
        <div class="explore-project"><strong>${explorationTitle}</strong><span>${isGuided ? "引导探索" : "自由探索"}</span></div>
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
      if (option) submitGuidedAnswer(option.value);
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
      submitGuidedAnswer(
        event.currentTarget.querySelector("[data-guided-custom-input]")?.value,
      );
    });
  });
  document
    .querySelector("[data-guided-finish]")
    ?.addEventListener("click", () => openStoryProfileDialog());

  // —— 自由探索：以下逻辑保持原样 ——
  document
    .querySelector(".finish-exploration:not(:disabled)")
    ?.addEventListener("click", () => openStoryProfileDialog());
  document
    .querySelector("[data-add-custom-clue]")
    ?.addEventListener("click", () => {
      customStoryClues.push({ label: "", value: "" });
      renderExploration();
      document
        .querySelector(
          `[data-custom-clue-label="${customStoryClues.length - 1}"]`,
        )
        ?.focus();
    });
  document.querySelectorAll("[data-remove-custom-clue]").forEach((button) => {
    button.addEventListener("click", () => {
      customStoryClues.splice(Number(button.dataset.removeCustomClue), 1);
      renderExploration();
    });
  });
  document.querySelectorAll("[data-custom-clue-label]").forEach((input) => {
    input.addEventListener("input", () => {
      customStoryClues[Number(input.dataset.customClueLabel)].label =
        input.value;
    });
  });
  document.querySelectorAll("[data-custom-clue-value]").forEach((input) => {
    input.addEventListener("input", () => {
      customStoryClues[Number(input.dataset.customClueValue)].value =
        input.value;
    });
  });
  document
    .querySelector("[data-inspiration]")
    ?.addEventListener("change", (event) => {
      const list = document.querySelector(".inspiration-list");
      showInspirationDirections = event.currentTarget.checked;
      list.hidden = !event.currentTarget.checked;
    });
  document.querySelectorAll("[data-direction]").forEach((button) =>
    button.addEventListener("click", () => {
      const answer = document.querySelector("#explore-answer");
      answer.value = button.dataset.direction;
      answer.focus();
    }),
  );
  document
    .querySelector("#explore-response")
    ?.addEventListener("submit", (event) => {
      // 该表单仅存在于自由探索模式（引导模式已改为选项式，不再渲染此表单）。
      event.preventDefault();
      const answer = event.currentTarget
        .querySelector("#explore-answer")
        .value.trim();
      if (!answer) return;
      freeConversation.push(
        { role: "user", text: answer },
        {
          role: "agent",
          text: "这个方向值得继续展开。我先把它保留在讨论里，不会替你直接改动设定。你更希望下一步把它落实到人物、冲突，还是世界规则中？",
        },
      );
      renderExploration();
    });
  document.querySelectorAll(".story-clue-value").forEach((field) => {
    field.addEventListener("focus", () => {
      if (field.classList.contains("is-empty")) {
        field.textContent = "";
        field.classList.remove("is-empty");
      }
    });
    field.addEventListener("blur", () => {
      if (!field.textContent.trim()) {
        field.textContent = field.dataset.placeholder;
        field.classList.add("is-empty");
      }
    });
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
    <header class="explore-header"><a class="explore-back" href="#/projects/demo/explore">← 故事设定</a><div class="explore-project"><strong>${explorationTitle}</strong><span>章节创作</span></div><div class="save-state"><i></i> ${chapterFinalized ? "本章已定稿" : chapterCreationState === "reading" ? "草稿已保存" : "已保存"}</div></header>
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
    <header class="explore-header"><a class="explore-back" href="#/projects">← 作品</a><div class="explore-project"><strong>${explorationTitle}</strong><span>章节归档</span></div><div class="save-state"><i></i> ${String(completedCount).padStart(2, "0")} 章已归档</div></header>
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
    const submit = event.currentTarget.querySelector(".submit");
    submit.disabled = true;
    submit.querySelector("span").textContent =
      currentMode() === "register" ? "正在创建账号…" : "正在登录…";
    window.setTimeout(() => {
      location.hash = "#/projects";
    }, 650);
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

function bindProjectInteractions() {
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
    ?.addEventListener("click", () => {
      const mode = selectedMode;
      explorationTitle =
        document.querySelector(".naming-input")?.value.trim() || "未命名小说";
      createStep = "closed";
      selectedMode = "";
      // 引导探索与自由探索都进入探索页，仅记录入口模式供探索页选择渲染哪种界面
      explorationEntryMode = mode === "free" ? "free" : "guided";
      window.sessionStorage.setItem(
        explorationEntryModeKey,
        explorationEntryMode,
      );
      explorationHistory = [];
      freeConversation = [];
      explorationView = 0;
      showInspirationDirections = false;
      guidedSettling = false;
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
      location.hash = "#/projects/demo/explore";
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
      title.outerHTML = `<div class="rename-form"><input class="rename-input" value="${title.textContent}" aria-label="新的小说名称" /><button data-save-rename>保存</button><button data-cancel-rename>取消</button></div>`;
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
      if (button.dataset.continue === "nameless")
        location.hash = "#/projects/demo/explore";
      else button.textContent = "目标页面待设计";
    }),
  );
  document.querySelector("[data-reload]")?.addEventListener("click", () => {
    location.hash = "#/projects";
  });
}

function bindInlineProjectActions(row) {
  row.querySelector("[data-save-rename]")?.addEventListener("click", () => {
    const value =
      row.querySelector(".rename-input").value.trim() || "未命名小说";
    row.querySelector(".rename-form").outerHTML = `<h2>${value}</h2>`;
  });
  row
    .querySelector("[data-cancel-rename]")
    ?.addEventListener("click", () => renderProjects());
  row
    .querySelector("[data-confirm-delete]")
    ?.addEventListener("click", () => row.remove());
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
    <header class="explore-header"><a class="explore-back" href="#/projects/demo/chapters/1">← 返回创作</a><div class="explore-project"><strong>${explorationTitle}</strong><span>阶段交界</span></div><div class="save-state"><i></i> 上一阶段已写完</div></header>
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

function renderByok() {
  const usedChapters = 3;
  const quotaChapters = 5;
  const usedPercent = Math.round((usedChapters / quotaChapters) * 100);
  document.title = "模型接入 · Muse";
  app.innerHTML = `<div class="byok-page">
    <header class="explore-header"><a class="explore-back" href="#/projects">← 作品库</a><div class="explore-project"><strong>模型接入</strong><span>设置</span></div><div class="save-state"><i></i> ${byokTab === "byok" ? "BYOK 已就绪" : "托管额度"}</div></header>
    <main class="byok-main">
      <section class="byok-intro">
        <div class="byok-overline">Model access / 模型接入</div>
        <h1>用谁的算力，由你定</h1>
        <p>默认走 Muse 托管，进来就能写，每天有免费额度。想不受额度限制、或用自己的模型，就绑定一把自己的 API Key，成本自付、额度解绑。</p>
      </section>
      <div class="tabs" role="tablist" aria-label="模型接入方式">
        <button class="tab" role="tab" aria-selected="${byokTab === "hosted"}" data-byok-tab="hosted">Muse 托管（默认）</button>
        <button class="tab" role="tab" aria-selected="${byokTab === "byok"}" data-byok-tab="byok">绑定自有 Key</button>
      </div>
      ${byokTab === "hosted" ? `<section class="byok-panel">
        <div class="byok-usage-head"><span>今日免费额度</span><strong>${usedChapters} / ${quotaChapters} 章</strong></div>
        <div class="byok-usage-bar"><i style="width: ${usedPercent}%"></i></div>
        <p class="byok-usage-note">免费额度每天重置。额度上限会在盲测跑出单章真实成本后定档（当前为线框占位值）。写作过程中不会弹付费墙。</p>
        <div class="byok-tip">重度创作、或想换用更强的模型？切到「绑定自有 Key」解除额度限制。</div>
      </section>` : `<section class="byok-panel">
        <div class="field"><div class="field-head"><label for="byok-key">API Key</label><span class="field-note">仅本地演示，不会上传</span></div><input class="input" id="byok-key" type="password" placeholder="sk-..." value="${escapeHtml(byokKeyDraft)}" autocomplete="off" /></div>
        <div class="byok-provider"><span>模型提供方</span><div class="byok-provider-options"><button type="button" class="byok-provider-option is-current">DeepSeek</button><button type="button" class="byok-provider-option">Claude</button><button type="button" class="byok-provider-option">自定义</button></div></div>
        <p class="byok-usage-note">绑定后，该账户的生成走你自己的 Key，成本由你与模型方结算，Muse 不再计免费额度。密钥在真实环境会加密存储。</p>
        <div class="style-anchor-actions"><button class="primary-button" type="button" data-byok-save ${byokKeyDraft.trim() ? "" : "disabled"}>保存并启用 <span>→</span></button></div>
      </section>`}
    </main>
  </div>`;
  bindByokInteractions();
}

function bindByokInteractions() {
  document.querySelectorAll("[data-byok-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      byokTab = button.getAttribute("data-byok-tab");
      renderByok();
    });
  });
  const key = document.querySelector("#byok-key");
  key?.addEventListener("input", () => {
    byokKeyDraft = key.value;
    const save = document.querySelector("[data-byok-save]");
    if (save) save.disabled = !key.value.trim();
  });
  document.querySelectorAll(".byok-provider-option").forEach((button) => {
    button.addEventListener("click", () => {
      document
        .querySelectorAll(".byok-provider-option")
        .forEach((other) => other.classList.remove("is-current"));
      button.classList.add("is-current");
    });
  });
  document.querySelector("[data-byok-save]")?.addEventListener("click", () => {
    const save = document.querySelector("[data-byok-save]");
    save.querySelector("span").textContent = "✓";
    save.childNodes[0].textContent = "已启用自有 Key ";
    save.disabled = true;
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
    <header class="explore-header readthrough-header"><a class="explore-back" href="#/projects/demo/archive">← 故事档案</a><div class="explore-project"><strong>${explorationTitle}</strong><span>通读</span></div></header>
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
    <header class="explore-header"><a class="explore-back" href="#/projects/demo/explore">← 故事设定</a><div class="explore-project"><strong>${explorationTitle}</strong><span>文风锚点</span></div><div class="save-state"><i></i> ${anchored ? "文风已锚定" : "尚未锚定"}</div></header>
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
  const chapterMatch = hashPath().match(/^#\/projects\/demo\/chapters\/(\d+)$/);
  const archiveMatch = hashPath().match(/^#\/projects\/([^/]+)\/archive$/);
  if (hashPath() === "#/projects") renderProjects();
  else if (hashPath() === "#/projects/demo/explore") renderExploration();
  else if (hashPath() === "#/projects/demo/style-anchor") renderStyleAnchor();
  else if (hashPath() === "#/projects/demo/readthrough") renderReadthrough();
  else if (hashPath() === "#/settings/model-access") renderByok();
  else if (hashPath() === "#/projects/demo/stage-direction")
    renderStageDirection();
  else if (archiveMatch) {
    const archiveProject = projects.find(
      (project) => project.id === archiveMatch[1],
    );
    if (archiveProject) explorationTitle = archiveProject.title;
    renderChapterArchive();
  } else if (chapterMatch) {
    chapterCreationIndex = Math.max(0, Number(chapterMatch[1]) - 1);
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

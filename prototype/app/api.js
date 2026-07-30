// Muse 前端连接底座（Story 7.1）
// =====================================================================
// Epic 7 全 epic 硬前置：统一请求工具 + token 存取 + 401 刷新重放 + error
// envelope 解包 + 跳登录封装 + auth API 薄封装。7.2–7.7 一律复用同一套，
// 不各自实现 token/401/error 处理。
//
// 加载方式（受控决策 1）：保持全局脚本，不上 ES module。本文件在 index.html
// 中于 app.js **之前**引入，以顶层符号（apiFetch/authApi/getAccessToken/...）
// 暴露给 app.js 复用；与 app.js 现有 ~60 个全局 function 同级。
//
// 命名边界唯一收敛点（AC4 / 受控决策 2）：后端出入参已是 camelCase
// （schemas/base.py alias_generator=to_camel），前端原型内部已纯 camelCase，
// 故 **不写 snake↔camel 转换器**（冗余且易造字段错配）。页面拿到的即 camelCase，
// 直接用。万一未来后端漏出某个 snake_case 字段，只在 apiFetch 这一处收口修正，
// 不散落到各页面——这就是「边界收敛在工具层」的落地。

// 后端 API 基址：原型静态站 :4173 与后端 :8000 跨域，走后端 dev CORS（受控决策 6
// 方案①）。可用 window.__MUSE_API_BASE 覆盖（如切同源反代时置 "" 走相对 /api）。
const API_BASE =
  (typeof window !== "undefined" && window.__MUSE_API_BASE) ||
  "http://127.0.0.1:8000";

// token 存储 key：沿用全站 muse- kebab 前缀（app.js:115），但介质用 localStorage
// 而非 sessionStorage（受控决策 7）：后端 refresh 有效期 30 天，鉴权态设计为跨浏览器
// 会话长期保持；sessionStorage 关标签页即登出，违背此意图。
const ACCESS_TOKEN_KEY = "muse-access-token";
const REFRESH_TOKEN_KEY = "muse-refresh-token";

// ---------------------------------------------------------------------
// Task 1：token 存取模块（localStorage，仿 readStoredJson app.js:175-181 容错范式）
// ---------------------------------------------------------------------

function getAccessToken() {
  try {
    return window.localStorage.getItem(ACCESS_TOKEN_KEY);
  } catch {
    // localStorage 不可用（隐私模式/被禁用）时降级为「无 token」，不抛异常打断请求。
    return null;
  }
}

function getRefreshToken() {
  try {
    return window.localStorage.getItem(REFRESH_TOKEN_KEY);
  } catch {
    return null;
  }
}

// 存双 token：登录/刷新成功后调用。缺字段时按各自存在性分别写，避免用 undefined 覆盖旧值。
function setTokens({ accessToken, refreshToken } = {}) {
  try {
    if (accessToken) window.localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
    if (refreshToken)
      window.localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
  } catch {
    // 写失败（配额/禁用）静默降级：本次会话仍可用内存态，不打断登录流程。
  }
}

function clearTokens() {
  try {
    window.localStorage.removeItem(ACCESS_TOKEN_KEY);
    window.localStorage.removeItem(REFRESH_TOKEN_KEY);
  } catch {
    // 清理失败无副作用可补救，忽略。
  }
}

// ---------------------------------------------------------------------
// Task 2：结构化错误 ApiError + 统一请求工具 apiFetch
// ---------------------------------------------------------------------

// 后端 error envelope {code, message, detail} 解包后的结构化错误（AC2）。
// 页面据 error.code（及 detail 里的布尔位 expired/invalid/locked）分支呈现，
// 不裸露原始 Response、不让调用方自己 res.json()。
class ApiError extends Error {
  constructor(code, message, detail, status) {
    super(message || code || "请求失败");
    this.name = "ApiError";
    this.code = code;
    this.detail = detail;
    this.status = status;
  }
}

// 解包失败响应体为 ApiError（AC2）。容错：响应体非 JSON 或缺字段时降级为兜底 code
// （unknown）+ 原始状态码，不抛裸 SyntaxError。
async function toApiError(res) {
  try {
    const body = await res.json();
    return new ApiError(
      body.code || "unknown",
      body.message || res.statusText,
      body.detail,
      res.status,
    );
  } catch {
    return new ApiError("unknown", res.statusText, undefined, res.status);
  }
}

// 单例在途 refresh promise（受控决策 3，High 级并发陷阱）：后端 refresh 一次性轮转，
// 多个并发 401 各自触发 refresh 会连环作废彼此的 refresh token 致连环登出。故同一时刻
// 只允许一个 refresh 在途，其余 401 请求 await 同一 promise，拿到新 token 后各自重放。
let inflightRefresh = null;

// 统一请求入口（AC1）。
// path: 形如 "/api/auth/me"；opts.auth=true 注入 Bearer，=false 用于 login/register/refresh。
// opts._retried: 内部标记，401 重放时置 true 避免死循环（调用方勿传）。
async function apiFetch(path, { method = "GET", body, auth = true, _retried = false } = {}) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";

  // 有 token 时注入；无 token 不附带该头（AC1）——登录/注册/刷新这类无需鉴权请求正常发出。
  const accessToken = getAccessToken();
  if (auth && accessToken) headers["Authorization"] = `Bearer ${accessToken}`;

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  // Task 3：业务请求（auth=true）401 → 刷新重放（仅重放一次）。登录/注册/刷新自身
  // （auth=false）的 401 是凭证错误/refresh 失效，不进刷新分支（受控决策 4）。
  if (res.status === 401 && auth && !_retried && getRefreshToken()) {
    await ensureRefresh(); // 失败会抛错并已 clearTokens + 跳登录，原请求链在此终止
    return apiFetch(path, { method, body, auth, _retried: true });
  }

  // 无法救回的业务 401（review 决策 1）：①重放后仍 401（新 access 也无权/账号已失效）；
  // ②本地无 refresh 可换。两者都表示会话已不可用——在此统一 clearTokens + 跳登录，把「跳登录」
  // 彻底收敛进本工具（AC3「全 epic 唯一跳登录入口」的完整落地），不散给各页各写一遍。
  // 注意仅业务请求（auth=true）走此收敛：auth=false 的 login/refresh 401 是凭证错误，照常抛出。
  if (res.status === 401 && auth) {
    clearTokens();
    redirectToLogin("expired");
    throw await toApiError(res);
  }

  if (!res.ok) {
    throw await toApiError(res);
  }

  // 成功直接返回资源体（camelCase，AC1）；204/无体返 null。
  if (res.status === 204) return null;
  const text = await res.text();
  if (!text) return null;
  // 成功响应体理应是 JSON；若遇 200 返 HTML 错误页/空格/代理拦截等非法 JSON（review patch#2），
  // 转成结构化 ApiError 而非抛裸 SyntaxError——守住「调用方只需 catch ApiError」的契约。
  try {
    return JSON.parse(text);
  } catch {
    throw new ApiError("invalid_response", "服务器返回了无法解析的响应。", undefined, res.status);
  }
}

// ---------------------------------------------------------------------
// Task 3：401 刷新重放 + refresh 失效跳登录
// ---------------------------------------------------------------------

// 跳登录封装（AC3）：全 epic 唯一「跳登录」入口，复用前端既有 ?state= 契约
// （queryState app.js:265-268 + stateMessage app.js:274-286 已认 expired/invalid/locked，
// renderAuth app.js:322 据此渲染文案）。
function redirectToLogin(state) {
  location.hash = state ? `#/login?state=${state}` : "#/login";
}

// 单例 refresh：同一时刻只有一个 refresh 在途，其余 401 请求 await 同一 promise（受控决策 3）。
function ensureRefresh() {
  if (!inflightRefresh) {
    inflightRefresh = doRefresh().finally(() => {
      inflightRefresh = null;
    });
  }
  return inflightRefresh;
}

// 用 refresh token 换新 access + 轮转后的新 refresh，存回本地。
// 失败区分处理（review 决策 2）：只有 refresh 真失效（后端 401 / token_invalid）才清 token 跳登录；
// 网络中断 / 后端 5xx / CORS 失败等**瞬时错误**不清 token、不踢人——原 refresh 仍有效，抛错让上层
// 稍后重试即可（避免 wifi 抖一下就被迫重新登录）。
async function doRefresh() {
  const refreshToken = getRefreshToken();
  if (!refreshToken) {
    clearTokens();
    redirectToLogin("expired");
    throw new ApiError("token_invalid", "会话已过期，请重新登录。", { expired: true }, 401);
  }
  let bundle;
  try {
    // auth=false：refresh 请求自身不注入 access、其 401 不再触发刷新（受控决策 4）。
    bundle = await apiFetch("/api/auth/refresh", {
      method: "POST",
      body: { refreshToken },
      auth: false,
    });
  } catch (err) {
    // 只有明确的鉴权失败（401，refresh 真失效）才登出；其余（5xx/网络/CORS/解析失败）视为瞬时错误，
    // 保留 token 抛错让上层重试（review 决策 2）。ApiError.status 由 toApiError 透传 HTTP 码。
    if (err instanceof ApiError && err.status === 401) {
      clearTokens();
      redirectToLogin("expired");
    }
    throw err;
  }
  // refresh 一次性轮转：新 access + 新 refresh 必须成对下发。若响应意外缺任一字段（后端 bug/代理裁剪），
  // 不能只写一半——旧 refresh 已被后端作废，半更新会让本地 token 处于必然失败态（review patch#3）。
  // 缺字段即视为会话不可续，清 token 跳登录。
  if (!bundle || !bundle.accessToken || !bundle.refreshToken) {
    clearTokens();
    redirectToLogin("expired");
    throw new ApiError("token_invalid", "会话已过期，请重新登录。", { expired: true }, 401);
  }
  setTokens({
    accessToken: bundle.accessToken,
    refreshToken: bundle.refreshToken,
  });
  return bundle;
}

// ---------------------------------------------------------------------
// Task 4：auth API 薄封装（供 7.2 复用，本 story 只封装不接 UI）
// ---------------------------------------------------------------------

const authApi = {
  // 注册：后端返回 {id, email}，**不签发 token**（受控决策 8）——注册成功后需另走 login，
  // 该串接归 7.2。本封装只做调用与返回，不自动 login。
  register({ inviteCode, email, password }) {
    return apiFetch("/api/auth/register", {
      method: "POST",
      body: { inviteCode, email, password },
      auth: false,
    });
  },

  // 登录：返回 {accessToken, refreshToken, tokenType, expiresIn}，成功后落 localStorage。
  async login({ email, password }) {
    const bundle = await apiFetch("/api/auth/login", {
      method: "POST",
      body: { email, password },
      auth: false,
    });
    setTokens({
      accessToken: bundle.accessToken,
      refreshToken: bundle.refreshToken,
    });
    return bundle;
  },

  // 刷新：即内部 401 用的 doRefresh，也可显式调用（走单例去重）。
  refresh() {
    return ensureRefresh();
  },

  // 登出：调后端作废 refresh；**无论后端结果都 clearTokens**（登出须清本地态）。
  // 后端/网络失败静默吞掉：本地态已在 finally 清空，对用户即「已登出」，不应因后端 500
  // 让用户卡在「登出失败」——后端 refresh 作废本就是幂等尽力而为。
  async logout() {
    const refreshToken = getRefreshToken();
    try {
      if (refreshToken) {
        await apiFetch("/api/auth/logout", {
          method: "POST",
          body: { refreshToken },
          auth: false,
        });
      }
    } catch {
      // 吞掉：本地态清理是登出的充分条件，后端结果不影响用户视角的登出成功。
    } finally {
      clearTokens();
    }
  },

  // 当前登录用户（受保护，需 Bearer）：返回 {id, email}。供 7.3 作品库 header 展示真实邮箱，
  // 替换原型硬编码 creator@example.com。经 apiFetch(auth=true) 自动注入 token + 401 兜底。
  me() {
    return apiFetch("/api/auth/me");
  },
};

// ---------------------------------------------------------------------
// 作品 API 薄封装（Story 7.3）：作品库列表/新建/重命名/删除。
// 全部经 apiFetch（默认 auth=true）——自动注入 Bearer、401 刷新重放、error envelope
// 解包、跳登录收敛均由地基处理，本封装只拼 path/method/body，不重复实现 token/401/error。
// 后端契约（backend/src/muse/routers/projects.py，Epic 1 已 done）：
//   GET    /api/projects            → 200 ProjectResponse[]（updated_at DESC，空返 []）
//   POST   /api/projects            → 201 ProjectResponse（body {mode, title?}）
//   PATCH  /api/projects/{id}       → 200 ProjectResponse（body {title?}，含刷新 updatedAt）
//   DELETE /api/projects/{id}       → 204 无体
// ProjectResponse 字段：{id, title, mode(guided/free), phase(explore/chapter/archive), updatedAt(ISO)}。
const projectApi = {
  list() {
    return apiFetch("/api/projects");
  },
  // title 可空：后端 max_length=255、无 min_length，留空回落「未命名小说」。前端勿强制非空。
  create({ mode, title }) {
    return apiFetch("/api/projects", {
      method: "POST",
      body: { mode, title },
    });
  },
  rename(projectId, title) {
    return apiFetch(`/api/projects/${projectId}`, {
      method: "PATCH",
      body: { title },
    });
  },
  remove(projectId) {
    return apiFetch(`/api/projects/${projectId}`, {
      method: "DELETE",
    });
  },
};

// ---------------------------------------------------------------------
// BYOK API 薄封装（Story 7.4）：模型接入页绑定/查询/解绑自有 API Key。
// 全部经 apiFetch（默认 auth=true）——token 注入、401 刷新重放、error envelope
// 解包、跳登录收敛均由地基处理，本封装只拼 path/method/body。
// 后端契约（backend/src/muse/routers/byok.py，Story 1.7 已 done）：
//   GET    /api/byok  → 200 ByokStatusResponse {bound, provider, maskedKey}
//   PUT    /api/byok  → 200 ByokStatusResponse（body {apiKey, provider}，幂等 upsert 覆盖）
//   DELETE /api/byok  → 204 无体（解绑，幂等）
// provider 枚举：deepseek/claude/custom；maskedKey = …+尾4位（≤4 全打码），绝不回显明文。
const byokApi = {
  status() {
    return apiFetch("/api/byok");
  },
  // 绑定/替换：PUT 幂等，已绑定时覆盖旧 Key。apiKey 后端 min_length=1（空串→422）、
  // service strip 判空（纯空白→byok_invalid_key 400）；前端在非空白前 disable 按钮即可。
  bind({ apiKey, provider }) {
    return apiFetch("/api/byok", {
      method: "PUT",
      body: { apiKey, provider },
    });
  },
  unbind() {
    return apiFetch("/api/byok", {
      method: "DELETE",
    });
  },
};

// ---------------------------------------------------------------------
// 用量 API 薄封装（Story 7.4）：托管免费额度用量展示。
// 后端契约（backend/src/muse/routers/usage.py，Story 1.8 已 done）：
//   GET /api/usage → 200 UsageViewResponse
//     托管用户：{billingPath:"hosted", quotaApplies:true, used, quota, remaining, resetAt}
//     BYOK 用户：{billingPath:"byok", quotaApplies:false, used/quota/remaining=null}
// 计量单位为 tokens（默认 quota 200000）；resetAt 恒 null（累计总量护栏，不做每日重置）。
// 只读接口，永不返 429（触顶护栏在生成链路、非本接口）——前端无需处理触顶分支。
const usageApi = {
  view() {
    return apiFetch("/api/usage");
  },
};

// ---------------------------------------------------------------------
// 全局暴露（受控决策 1：全局脚本，非 module）。app.js 及 7.2–7.7 直接引用这些符号。
// ---------------------------------------------------------------------
if (typeof window !== "undefined") {
  window.apiFetch = apiFetch;
  window.ApiError = ApiError;
  window.authApi = authApi;
  window.projectApi = projectApi;
  window.byokApi = byokApi;
  window.usageApi = usageApi;
  window.getAccessToken = getAccessToken;
  window.getRefreshToken = getRefreshToken;
  window.setTokens = setTokens;
  window.clearTokens = clearTokens;
  window.redirectToLogin = redirectToLogin;
}


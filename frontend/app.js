const API_BASE = window.TRANSITION_API_BASE || "http://127.0.0.1:5050/api";
const STORE_KEY = "transitionPortal.ui.v3";
const TOKEN_KEY = "accessToken";
const REFRESH_KEY = "refreshToken";
const SESSION_KEY = "sessionId";
const CASES_PAGE_SIZE = 10;
const CARS24_LOGO_URL = "https://static-cdn.cars24.com/prod/cms/2026/01/22/244d7828-5929-4f98-a068-7b2113c83339blue-brand-logo.svg";
const ADMIN_AVATAR_URL = "./assets/admin-avatar.svg?v=20260608";
const NAV_ITEMS = [
  { key: "team", icon: "◐", title: "My Team", subtitle: "Direct reports", hotkey: "1", step: "Team" },
  { key: "mycases", icon: "◇", title: "My Cases", subtitle: "Initiated by you", hotkey: "2", step: "My Cases" },
  { key: "allcases", icon: "▦", title: "All Cases", subtitle: "Org-wide", hotkey: "3", step: "All Cases" },
  { key: "sync", icon: "≋", title: "Employee Data", subtitle: "Sync · Darwinbox", hotkey: "4", step: "Sync" }
];
const ACTIVE_TABS = NAV_ITEMS.map((item) => item.key);

const app = document.getElementById("app");
const toastRoot = document.getElementById("toast-root");

let authConfig = null;
let bifrost = null;
let calcTimer = null;

let state = {
  authenticated: false,
  user: null,
  role: "",
  tab: "team",
  view: "dashboard",
  selectedEmployee: null,
  search: "",
  allCasesPage: 1,
  employees: [],
  cases: [],
  options: {
    separation_reasons: [],
    separation_sub_reasons: {},
    notice_types: [],
    garden_leave: [],
    communication_statuses: []
  },
  sync: {},
  metrics: {},
  publicMetrics: {},
  calculation: null,
  loading: true,
  calcLoading: false,
  backendError: "",
  authError: "",
  ssoIssue: "",
  ssoMetadata: null,
  ssoLoading: false,
  syncTesting: false,
  syncRecording: false,
  approvalUploading: false,
  form: defaultForm()
};

function defaultForm() {
  return {
    dor: "",
    lwd: "",
    reason: "",
    subReason: "",
    noticeType: "",
    gardenLeave: "",
    communication: "",
    remarks: "",
    approvalFileName: "",
    approvalFileUrl: "",
    approvalUploadId: ""
  };
}

function loadUiState() {
  const saved = JSON.parse(localStorage.getItem(STORE_KEY) || "{}");
  state.tab = ACTIVE_TABS.includes(saved.tab) ? saved.tab : "team";
  state.view = saved.view || "dashboard";
  state.selectedEmployee = saved.selectedEmployee || null;
  state.search = saved.search || "";
  state.allCasesPage = Number(saved.allCasesPage || 1);
  state.form = { ...defaultForm(), ...(saved.form || {}) };
}

function saveUiState() {
  localStorage.setItem(STORE_KEY, JSON.stringify({
    tab: state.tab,
    view: state.view,
    selectedEmployee: state.selectedEmployee,
    search: state.search,
    allCasesPage: state.allCasesPage,
    form: state.form
  }));
}

async function init() {
  loadUiState();
  await Promise.all([loadPublicSummary(), loadAuthConfig()]);
  await handleOAuthCallback();
  if (getAccessToken()) {
    state.authenticated = true;
    await loadBootstrap();
  } else {
    state.loading = false;
    render();
  }
}

async function loadPublicSummary() {
  try {
    const data = await publicApi("/public/summary");
    state.publicMetrics = data.metrics || {};
  } catch {
    state.publicMetrics = {};
  }
}

async function loadAuthConfig() {
  try {
    authConfig = normalizeAuthConfig(await publicApi("/auth/config"));
    bifrost = createBifrost(authConfig);
    await refreshSsoMetadata();
  } catch (error) {
    state.authError = error.message;
  }
}

async function refreshSsoMetadata() {
  if (!bifrost || !authConfig?.clientId) return null;
  try {
    const response = await bifrost.getLoginMethods();
    const methods = Array.isArray(response.data) ? response.data : [];
    const google = methods.find((method) => method.id === "GOOGLE_SSO");
    const meta = google?.meta_data || {};
    if (!meta.client_id || !meta.redirect_uri) {
      state.ssoMetadata = null;
      state.ssoIssue = `Bifrost client ${authConfig.clientId} has no GOOGLE_SSO metadata. Configure the Google SSO login method and register ${authConfig.redirectUri} as an allowed redirect URL.`;
      return null;
    }
    state.ssoMetadata = {
      method_id: google.id,
      client_id: meta.client_id,
      redirect_uri: meta.redirect_uri
    };
    state.ssoIssue = "";
    return state.ssoMetadata;
  } catch (error) {
    state.ssoMetadata = null;
    state.ssoIssue = `Unable to read Bifrost SSO methods for ${authConfig.clientId}: ${error.message}`;
    return null;
  }
}

function normalizeAuthConfig(config) {
  return {
    ...config,
    redirectUri: isLocalHost(window.location.hostname)
      ? `${window.location.origin}/login`
      : config.redirectUri || `${window.location.origin}/login`
  };
}

function isLocalHost(hostname) {
  return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "0.0.0.0";
}

async function publicApi(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || payload.detail || `Request failed: ${response.status}`);
  return payload;
}

async function api(path, options = {}, retry = true) {
  const token = getAccessToken();
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  const payload = await response.json().catch(() => ({}));
  if (response.status === 401 && retry && await refreshAccessToken()) {
    return api(path, options, false);
  }
  if (!response.ok) throw new Error(payload.error || payload.detail || `Request failed: ${response.status}`);
  return payload;
}

async function refreshAccessToken() {
  if (!bifrost) return false;
  const refreshToken = localStorage.getItem(REFRESH_KEY);
  const sessionId = localStorage.getItem(SESSION_KEY);
  if (!refreshToken || !sessionId) return false;
  try {
    const response = await bifrost.refreshToken({ refreshToken, sessionId });
    if (!response?.data?.access_token) return false;
    storeTokens(response.data);
    return true;
  } catch {
    clearSession();
    return false;
  }
}

async function loadBootstrap() {
  state.loading = true;
  render();
  try {
    const data = await api("/bootstrap");
    state.user = data.user;
    state.role = data.role || data.user?.role || "ADMIN";
    state.employees = (data.employees || []).map(mapEmployee);
    state.cases = (data.cases || []).map(mapCase);
    state.options = { ...state.options, ...(data.options || {}) };
    state.sync = data.sync || {};
    state.metrics = data.metrics || {};
    state.publicMetrics = state.metrics;
    applyFormDefaults();
    state.backendError = "";
  } catch (error) {
    state.backendError = error.message;
    if (error.message.toLowerCase().includes("auth")) {
      clearSession();
      state.authenticated = false;
    }
  } finally {
    state.loading = false;
    saveUiState();
    render();
  }
}

function applyFormDefaults(form = state.form) {
  if (!form.noticeType && state.options?.notice_types?.length) {
    form.noticeType = state.options.notice_types[0];
  }
  if (!form.gardenLeave && state.options?.garden_leave?.length) {
    form.gardenLeave = state.options.garden_leave[0];
  }
  return form;
}

function mapEmployee(row) {
  return {
    empCode: row.emp_code,
    name: row.full_name,
    designation: row.external_designation || row.internal_designation,
    grade: row.grade,
    band: row.band,
    entity: row.entity,
    doj: row.group_doj || row.doj,
    hrbp: row.hrbp_name,
    l1: row.l1_manager,
    l2: row.l2_manager,
    ctc: Number(row.total_ctc || 0),
    variable: Number(row.variable || 0),
    pf: Number(row.provident_fund || 0),
    gratuity: Number(row.gratuity || 0),
    medical: Number(row.medical_insurance || 0),
    raw: row
  };
}

function mapCase(row) {
  const noticePay = Number(row.notice_period_amount || 0);
  const severance = Number(row.severance_pay_amount || 0);
  const variable = Number(row.variable_pay_amount || 0);
  return {
    id: row.case_id,
    empCode: row.emp_code,
    empName: row.emp_name,
    lwd: row.last_working_date,
    dor: row.date_of_resignation,
    status: normalizeStatus(row.status),
    reason: row.separation_reason,
    subReason: row.separation_sub_reason,
    communication: row.communication_status,
    createdBy: row.created_by,
    entity: row.entity,
    noticePay,
    gratuity: severance,
    finalSettlement: noticePay + severance + variable,
    remarks: row.remarks || row.admin_remarks || "",
    raw: row
  };
}

function render() {
  if (!state.authenticated) {
    app.innerHTML = renderLogin();
    bindEvents();
    return;
  }
  app.innerHTML = state.view === "form" ? layout(renderForm()) : layout(renderPage());
  bindEvents();
}

function renderLogin() {
  const ssoButtonText = state.ssoLoading
    ? "Connecting to Cars24 SSO"
    : state.ssoMetadata ? "Continue with Cars24 SSO" : "Bifrost SSO Not Configured";
  return `
    <main class="login-screen ${state.ssoLoading ? "is-sso-loading" : ""}" aria-busy="${state.ssoLoading ? "true" : "false"}">
      <div class="login-ambient orb-a"></div>
      <div class="login-ambient orb-b"></div>
      <div class="login-ambient orb-c"></div>
      <div class="login-wave wave-one"></div>
      <div class="login-wave wave-two"></div>
      <div class="login-dots"></div>
      <div class="login-security-pill"><span></span>Enterprise Grade Security</div>
      <section class="login-copy">
        <div class="login-brand login-brand-hero">${brandMark()}<div><strong>Transition Portal</strong><span>by Cars24 HR</span></div></div>
        <h1>Every separation,<br>handled with <em>control</em><br>and clarity.</h1>
        <div class="login-accent-line"></div>
        <p>AI-powered separation management with <strong>automation</strong>, <strong>compliance</strong> and <strong>real-time visibility</strong> across the entire lifecycle.</p>
        <div class="login-flow" aria-label="Separation lifecycle">
          ${loginFlowStep("Employee", "Initiates Exit", "EE")}
          ${loginFlowStep("Manager", "Approves", "MG")}
          ${loginFlowStep("HRBP", "Reviews", "HR")}
          ${loginFlowStep("Finance", "Clears", "FN")}
          ${loginFlowStep("Settlement", "Completed", "OK")}
        </div>
        <div class="login-car-stage" aria-hidden="true">
          <span class="road-glow"></span>
          <span class="road-line line-a"></span>
          <span class="road-line line-b"></span>
          <span class="login-car car-primary"><i></i><b></b></span>
          <span class="login-car car-secondary"><i></i><b></b></span>
          <span class="login-car car-ghost"><i></i><b></b></span>
        </div>
        <div class="login-trust"><span></span>Secured. Compliant. Trusted by Cars24.</div>
      </section>
      <section class="login-card login-access-card">
        <div class="login-card-shine"></div>
        <div class="eyebrow secure-eyebrow"><span></span>Secure Access</div>
        <h2>Welcome back</h2>
        <p>Use Cars24 Bifrost SSO to access the portal.</p>
        <button class="btn primary full login-sso-btn" data-action="sso-login" ${state.ssoLoading || !state.ssoMetadata ? "disabled" : ""}>
          <span class="${state.ssoLoading ? "button-spinner" : "button-lock"}"></span>${ssoButtonText}<span class="button-arrow">-></span>
        </button>
        ${state.ssoIssue ? `<div class="alert error">${h(state.ssoIssue)}</div>` : ""}
        ${state.authError ? `<div class="alert error">${h(state.authError)}</div>` : ""}
        <div class="login-foot"><span></span>Secure Cars24 SSO access · HR operations workspace</div>
      </section>
      <div class="login-shield" aria-hidden="true"><span></span></div>
    </main>
  `;
}

function setSsoButtonLoading(isLoading) {
  const screen = app.querySelector(".login-screen");
  const button = app.querySelector("[data-action='sso-login']");
  if (!screen || !button) {
    render();
    return;
  }

  state.ssoLoading = isLoading;
  screen.classList.toggle("is-sso-loading", isLoading);
  screen.setAttribute("aria-busy", isLoading ? "true" : "false");
  button.disabled = isLoading || !state.ssoMetadata;
  button.innerHTML = `<span class="${isLoading ? "button-spinner" : "button-lock"}"></span>${isLoading ? "Connecting to Cars24 SSO" : "Continue with Cars24 SSO"}<span class="button-arrow">-></span>`;
}

function waitForNextPaint() {
  return new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
}

function layout(content) {
  return `
    <div class="shell">
      ${sidebar()}
      <main class="workspace">
        ${topbar()}
        ${content}
      </main>
    </div>
  `;
}

function sidebar() {
  return `
    <aside class="side">
      <div class="side-brand">${brandMark()}<div><strong>Transition Portal</strong><span>CARS24 · HR</span></div></div>
      <label class="quick" title="Press Cmd/Ctrl + K to quick jump">
        <span>⌕</span>
        <input data-quick-jump list="quick-jump-options" placeholder="Quick jump..." autocomplete="off">
        <kbd>⌘</kbd><kbd>K</kbd>
      </label>
      <datalist id="quick-jump-options">
        ${NAV_ITEMS.map((item) => `<option value="${h(item.title)}"></option>`).join("")}
      </datalist>
      <div class="nav-label">Journeys</div>
      <nav>
        ${NAV_ITEMS.map((item) => `
          <button class="nav-item ${state.tab === item.key && state.view !== "form" ? "active" : ""}" data-tab="${item.key}">
            <span class="nav-icon">${item.icon}</span>
            <span><strong>${item.title}</strong><small>${item.subtitle}</small></span>
            <kbd>${item.hotkey}</kbd>
          </button>
        `).join("")}
      </nav>
      <div class="side-user">
        <span class="avatar avatar-photo"><img src="${ADMIN_AVATAR_URL}" alt="Admin user"></span>
        <div><strong title="${h(state.user?.email || "")}">${h(truncate(state.user?.email || "", 24))}</strong><small>● ${h(state.role || "ADMIN")}</small></div>
      </div>
    </aside>
  `;
}

function topbar() {
  const email = state.user?.email || "";
  return `
    <div class="app-topbar">
      <div class="topbar-left">
        <span class="live-dot"></span>
        <span>Live workspace</span>
      </div>
      <div class="topbar-actions">
        <div class="user-chip">
          <span class="avatar avatar-photo small"><img src="${ADMIN_AVATAR_URL}" alt="Admin user"></span>
          <span><strong>${h(truncate(email, 28))}</strong><small>${h(state.role || "ADMIN")}</small></span>
        </div>
        <button class="btn logout-btn" data-action="logout" title="Sign out of Transition Portal">Logout</button>
      </div>
    </div>
  `;
}

function renderPage() {
  return `
    <div class="dashboard-sticky-shell">
      ${dashboardStepper()}
    </div>
    ${state.backendError ? `<div class="alert error">Backend issue: ${h(state.backendError)}</div>` : ""}
    ${state.loading ? `<div class="alert info">Refreshing API data from local Postgres...</div>` : ""}
    ${renderTab()}
  `;
}

function dashboardStepper() {
  const activeIndex = Math.max(0, NAV_ITEMS.findIndex((item) => item.key === state.tab));
  const progress = NAV_ITEMS.length <= 1 ? 0 : (activeIndex / (NAV_ITEMS.length - 1)) * 100;
  return `
    <div class="dashboard-stepper" style="--step-progress: ${progress / 100}">
      ${NAV_ITEMS.map((item, index) => `
        <button class="dash-step ${state.tab === item.key ? "active" : ""} ${index < activeIndex ? "done" : ""}" data-tab="${item.key}">
          <span>${h(item.hotkey)}</span><strong>${h(item.step)}</strong>
        </button>
      `).join("")}
    </div>
  `;
}

function formStepper(ready) {
  const hasInputs = Boolean(state.form.dor && state.form.lwd && state.form.reason && state.form.subReason);
  const hasCalculation = Boolean(state.calculation);
  const steps = [
    ["1", "Employee", "Selected", true],
    ["2", "Case Inputs", "Dates + reason", hasInputs],
    ["3", "Live Calc", "Settlement ready", hasCalculation],
    ["4", "Submit", "Create case", ready]
  ];
  return `
    <div class="form-stepper">
      ${steps.map(([number, title, subtitle, done], index) => `
        <div class="form-step ${done ? "done" : ""} ${!done && steps.slice(0, index).every((step) => step[3]) ? "active" : ""}">
          <span>${h(number)}</span>
          <strong>${h(title)}</strong>
          <small>${h(subtitle)}</small>
        </div>
      `).join("")}
    </div>
  `;
}

function renderTab() {
  if (state.tab === "team") return renderTeam();
  if (state.tab === "mycases") return renderMyCases();
  if (state.tab === "allcases") return renderAllCases();
  if (state.tab === "sync") return renderSync();
  return renderTeam();
}

function renderTeam() {
  return `
    <section class="card page-card team-card">
      <div class="card-head">
        <div><span class="section-kicker">Manager Console</span><h2>Your direct reports</h2><p>${state.employees.length} active · auto-detected from Darwinbox</p></div>
        <button class="btn ghost small" data-action="refresh">Refresh</button>
      </div>
      <div class="team-table">
        <div class="team-row head"><span>Employee</span><span>Designation</span><span>Grade</span><span>Entity</span><span>Action</span></div>
        ${state.employees.map((employee) => `
          <div class="team-row">
            <span class="person"><span class="avatar">${initials(employee.name)}</span><span><strong>${h(employee.name)}</strong><small>EMP · ${h(employee.empCode)}</small></span></span>
            <span>${h(employee.designation)}</span>
            <span><b class="pill">${h(employee.grade)}</b></span>
            <span>${h(employee.entity)}</span>
            <span><button class="btn primary small action-btn" data-open-employee="${h(employee.empCode)}">Initiate -></button></span>
          </div>
        `).join("") || emptyState("No direct reports found.")}
      </div>
    </section>
  `;
}

function renderMyCases() {
  const email = (state.user?.email || "").toLowerCase();
  const list = state.cases.filter((item) => (item.createdBy || "").toLowerCase() === email).slice(0, 5);
  return `
    <section class="card page-card cases-card">
      <div class="card-head"><div><span class="section-kicker">My Queue</span><h2>Separation cases you initiated</h2><p>${list.length} case(s)</p></div></div>
      <div class="case-list">${list.map((item, index) => caseRow(item, index === 0)).join("") || emptyState("No cases initiated by you yet.")}</div>
    </section>
  `;
}

function renderAllCases() {
  const list = filteredAllCases();
  const page = allCasesPageInfo(list);
  return `
    <section class="card page-card cases-card all-cases-card">
      <div class="cases-sticky-controls">
        <div class="card-head">
          <div><span class="section-kicker">Org-wide Tracker</span><h2>All cases</h2><p><span data-all-cases-count>${list.length}</span> case(s)</p></div>
        </div>
        <div class="search-row">
          <label>⌕<input value="${h(state.search)}" data-input="search" placeholder="Search by name, ID, or employee code..." autocomplete="off"></label>
          <button class="btn ghost" data-action="refresh">Refresh</button>
        </div>
      </div>
      <div class="case-list" data-all-cases-list>${renderAllCasesList(page.items)}</div>
      <div data-all-cases-pagination>${renderAllCasesPagination(page)}</div>
    </section>
  `;
}

function filteredAllCases() {
  const q = state.search.trim().toLowerCase();
  return state.cases.filter((item) => !q || `${item.id} ${item.empName} ${item.empCode} ${item.status} ${item.lwd}`.toLowerCase().includes(q));
}

function allCasesPageInfo(list) {
  const total = list.length;
  const totalPages = Math.max(1, Math.ceil(total / CASES_PAGE_SIZE));
  const pageNumber = Math.min(Math.max(Number(state.allCasesPage || 1), 1), totalPages);
  if (pageNumber !== state.allCasesPage) {
    state.allCasesPage = pageNumber;
    saveUiState();
  }
  const start = total === 0 ? 0 : (pageNumber - 1) * CASES_PAGE_SIZE + 1;
  const end = Math.min(pageNumber * CASES_PAGE_SIZE, total);
  return {
    total,
    totalPages,
    pageNumber,
    start,
    end,
    items: list.slice((pageNumber - 1) * CASES_PAGE_SIZE, pageNumber * CASES_PAGE_SIZE)
  };
}

function renderAllCasesList(items) {
  return items.map((item) => caseRow(item, false)).join("") || emptyState("No matching cases.");
}

function renderAllCasesPagination(page) {
  return `
    <div class="cases-pagination">
      <div><strong>${page.total ? `${page.start}-${page.end}` : "0"}</strong><span> of ${page.total} cases</span></div>
      <div class="pagination-actions">
        <button class="btn ghost small" data-action="cases-prev" ${page.pageNumber <= 1 ? "disabled" : ""}>← Previous</button>
        <span>Page ${page.pageNumber} / ${page.totalPages}</span>
        <button class="btn ghost small" data-action="cases-next" ${page.pageNumber >= page.totalPages ? "disabled" : ""}>Next →</button>
      </div>
    </div>
  `;
}

function updateAllCasesResults() {
  if (state.tab !== "allcases" || state.view === "form") return render();
  const list = filteredAllCases();
  const page = allCasesPageInfo(list);
  const count = app.querySelector("[data-all-cases-count]");
  const listNode = app.querySelector("[data-all-cases-list]");
  const pagination = app.querySelector("[data-all-cases-pagination]");
  if (!count || !listNode || !pagination) return render();
  count.textContent = String(list.length);
  listNode.innerHTML = renderAllCasesList(page.items);
  pagination.innerHTML = renderAllCasesPagination(page);
  bindAllCasesDynamicControls();
}

function caseRow(item, expanded) {
  return `
    <article class="case-row ${expanded ? "expanded" : ""} ${statusClass(item.status)}">
      <button class="case-main" data-case-detail="${h(item.id)}">
        <span class="case-id">${h(item.id)}</span>
        <strong>${h(item.empName)}</strong>
        <span>LWD · ${h(item.lwd)}</span>
        <em class="case-status-pill">${h(item.status)}</em>
        <i>›</i>
      </button>
      ${expanded ? `
        <div class="settlement-grid">
          ${settlementTile("Status", item.status)}
          ${settlementTile("Notice Pay", inr(item.noticePay))}
          ${settlementTile("Gratuity", inr(item.gratuity))}
          ${settlementTile("Final Settlement", inr(item.finalSettlement))}
        </div>
      ` : ""}
    </article>
  `;
}

function renderSync() {
  const metrics = state.metrics || {};
  const pipeline = metrics.pipeline || {};
  const lastSync = metrics.last_sync_minutes;
  const syncBusy = state.syncTesting || state.syncRecording;
  const syncCopy = lastSync === null || lastSync === undefined
    ? "No sync check has been recorded yet."
    : `Last checked ${lastSync} minutes ago.`;
  const syncTone = lastSync === null || lastSync === undefined ? "info" : lastSync <= 60 ? "success" : "info";
  return `
    <div class="sync-layout">
      <section class="card sync-card page-card">
        <div class="card-head"><div><span class="section-kicker">Data Pipeline</span><h2>Employee Data — Darwinbox API</h2><p>Cached in Postgres · sync checks are recorded from the backend</p></div></div>
        <div class="alert ${syncTone}">● <strong>${h(syncCopy)}</strong></div>
        <div class="info-box"><strong>What's included:</strong> Active employees + anyone who left after 31 March 2026.<br><strong>CTC data:</strong> Fetched from the payroll API in batches — Fixed, Variable, PF, Gratuity, Medical for accurate severance.</div>
        <div class="db-count"><span>Employees in database</span><strong>${formatNumber(metrics.employee_count || state.sync.employee_count || 0)}</strong><p>Managers read instantly — no API call on login.</p></div>
        <div class="split-actions">
          <button class="btn ghost" data-action="test-api" ${syncBusy ? "disabled" : ""}>${state.syncTesting ? "Testing Pipeline..." : "Test Sync Pipeline"}</button>
          <button class="btn primary" data-action="sync-check" ${syncBusy ? "disabled" : ""}>${state.syncRecording ? "Recording Check..." : "Record Sync Check ↻"}</button>
        </div>
      </section>
      <section class="card health-card page-card">
        <div class="card-head"><div><span class="section-kicker">Live Health</span><h2>Pipeline health</h2><p>Live API + DB metrics</p></div></div>
        ${health("Master API", pipeline.master_api || "-")}
        ${health("Payroll API", pipeline.payroll_api || "-")}
        ${health("Cache hit rate", pipeline.cache_hit_rate || "-")}
        ${health("Failed syncs (24h)", pipeline.failed_syncs || "0")}
        ${health("Next auto-sync", pipeline.next_auto_sync || "-")}
      </section>
    </div>
  `;
}

function renderForm() {
  const employee = state.employees.find((item) => item.empCode === state.selectedEmployee) || state.employees[0];
  if (!employee) return `<button class="btn ghost back-btn" data-action="back">← Back</button>${emptyState("No employee selected.")}`;
  const calculationReady = Boolean(state.form.dor && state.form.lwd && state.form.reason && state.calculation);
  const submitReady = isFormValid();
  const options = state.options || {};
  const uploadLabel = state.approvalUploading
    ? "Uploading approval file..."
    : state.form.approvalFileName || "200 MB per file · PDF, JPG, PNG";
  return `
    <button class="btn ghost back-btn" data-action="back">← Back</button>
    <section class="form-hero">
      <span class="avatar big">${initials(employee.name)}</span>
      <div><div class="eyebrow">Initiate Separation</div><h1>${h(employee.name)}</h1><p>${h(employee.empCode)} · ${h(employee.designation)} · ${h(employee.grade)} · ${h(employee.entity)}</p></div>
    </section>
    ${formStepper(submitReady)}
    <div class="form-layout">
      <section class="card form-card">
        <div class="eyebrow teal">Case Inputs</div>
        <div class="form-two">
          ${inputField("Date of Resignation", "dor", "date")}
          ${inputField("Last Working Date", "lwd", "date")}
        </div>
        ${selectField("Separation Reason", "reason", options.separation_reasons, "Select...")}
        ${selectField("Separation Sub Reason", "subReason", subReasonOptions(state.form.reason), state.form.reason ? "Select..." : "Pick a reason first")}
        <div class="form-two">
          ${selectField("Notice Type", "noticeType", options.notice_types, "Select...")}
          ${selectField("Garden Leave", "gardenLeave", options.garden_leave, "Select...")}
        </div>
        ${selectField("Communication Status", "communication", options.communication_statuses, "Select...")}
        ${textareaField("Remarks / Exception", "remarks")}
        <label class="upload-box ${state.approvalUploading ? "uploading" : ""}">
          <input type="file" data-input="approvalFile" accept=".pdf,.jpg,.jpeg,.png">
          <span class="btn chip">${state.approvalUploading ? "Uploading" : "Upload"}</span><span>${h(uploadLabel)}</span>
        </label>
        <button class="btn full ${submitReady ? "primary" : "disabled"}" data-action="submit-case">✓ Submit Separation Case</button>
      </section>
      <aside class="side-stack">
        <section class="card profile-card">
          <div class="eyebrow teal">Employee Profile</div>
          <div class="profile-grid">
            ${profile("Grade / Band", `${employee.grade} / ${employee.band}`)}
            ${profile("Entity", employee.entity)}
            ${profile("Date of Joining", formatDate(employee.doj))}
            ${profile("HRBP", employee.hrbp)}
            ${profile("L1 Manager", employee.l1)}
            ${profile("L2 Manager", employee.l2)}
          </div>
        </section>
        <section class="calc-panel ${calculationReady ? "ready" : ""}">
          <div class="eyebrow teal">Live Calculation</div>
          ${calculationReady ? `
            <div class="calc-mini">
              ${settlementTile("Notice Pay", inr(state.calculation.notice_period_amount))}
              ${settlementTile("Severance", inr(state.calculation.severance_pay_amount))}
              ${settlementTile("Variable", inr(state.calculation.variable_pay_amount))}
              ${settlementTile("Tenure", state.calculation.tenure || "-")}
            </div>
          ` : `<div class="empty-state"><span>${state.calcLoading ? "↻" : "⚡"}</span><strong>Fill Dates + Separation Reason</strong><small>to see live calculations</small></div>`}
        </section>
      </aside>
    </div>
  `;
}

function bindEvents() {
  app.querySelectorAll("[data-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      state.tab = button.dataset.tab;
      state.view = "dashboard";
      if (state.tab === "allcases") state.allCasesPage = Math.max(1, Number(state.allCasesPage || 1));
      saveUiState();
      render();
    });
  });
  app.querySelectorAll("[data-action]").forEach((button) => {
    button.addEventListener("click", () => handleAction(button.dataset.action));
  });
  app.querySelectorAll("[data-open-employee]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selectedEmployee = button.dataset.openEmployee;
      state.form = applyFormDefaults(defaultForm());
      state.calculation = null;
      state.view = "form";
      saveUiState();
      render();
    });
  });
  bindAllCasesDynamicControls();
  bindQuickJump();
  app.querySelectorAll("[data-input]").forEach((input) => {
    const update = () => handleInput(input);
    input.addEventListener("input", update);
    input.addEventListener("change", update);
  });
}

function bindQuickJump() {
  const quickInput = app.querySelector("[data-quick-jump]");
  if (!quickInput) return;
  quickInput.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    performQuickJump(quickInput.value);
  });
}

function bindAllCasesDynamicControls() {
  app.querySelectorAll("[data-case-detail]").forEach((button) => {
    button.onclick = () => openCaseModal(button.dataset.caseDetail);
  });
  app.querySelectorAll("[data-action='cases-prev']").forEach((button) => {
    button.onclick = () => changeAllCasesPage(-1);
  });
  app.querySelectorAll("[data-action='cases-next']").forEach((button) => {
    button.onclick = () => changeAllCasesPage(1);
  });
}

function changeAllCasesPage(delta) {
  const list = filteredAllCases();
  const totalPages = Math.max(1, Math.ceil(list.length / CASES_PAGE_SIZE));
  state.allCasesPage = Math.min(Math.max(Number(state.allCasesPage || 1) + delta, 1), totalPages);
  saveUiState();
  updateAllCasesResults();
}

async function handleInput(input) {
  const key = input.dataset.input;
  if (key === "search") {
    state.search = input.value;
    state.allCasesPage = 1;
    saveUiState();
    updateAllCasesResults();
    return;
  }
  if (key === "approvalFile") {
    await uploadApproval(input.files?.[0]);
    return;
  }
  if (key in state.form) {
    state.form[key] = input.value;
    if (key === "reason") {
      state.form.subReason = "";
      state.calculation = null;
    }
    saveUiState();
    if (["dor", "lwd", "reason", "subReason", "noticeType", "gardenLeave", "communication"].includes(key)) {
      queueCalculation();
      render();
    }
    return;
  }
  state[key] = input.value;
}

async function handleAction(action) {
  if (action === "sso-login") return startSso();
  if (action === "logout") return logout();
  if (action === "back") {
    state.view = "dashboard";
    state.tab = "team";
    saveUiState();
    return render();
  }
  if (action === "refresh") return loadBootstrap();
  if (action === "test-api") return testApi();
  if (action === "sync-check") return recordSyncCheck();
  if (action === "submit-case") return submitCase();
}

async function startSso() {
  if (!bifrost) return toast("Bifrost configuration is not loaded.");
  if (state.ssoLoading) return;
  setSsoButtonLoading(true);
  await waitForNextPaint();
  try {
    const meta = state.ssoMetadata || await refreshSsoMetadata();
    if (!meta) throw new Error(state.ssoIssue || "Bifrost SSO is not configured.");
    await bifrost.sso({
      method_id: meta.method_id,
      country_code: "IN",
      client_id: meta.client_id,
      redirect_uri: meta.redirect_uri
    });
  } catch (error) {
    setSsoButtonLoading(false);
    render();
    toast(error.message || "Failed to start Bifrost SSO.");
  }
}

async function logout() {
  const sessionId = localStorage.getItem(SESSION_KEY);
  const accessToken = getAccessToken();
  if (bifrost && sessionId && accessToken && !sessionId.startsWith("local-")) {
    try {
      await bifrost.logout({ sessionId, accessToken });
    } catch {
      // Local logout should still clear the browser session.
    }
  }
  clearSession();
  state.authenticated = false;
  state.user = null;
  state.role = "";
  state.view = "dashboard";
  render();
}

async function testApi() {
  if (state.syncTesting || state.syncRecording) return;
  state.syncTesting = true;
  render();
  try {
    const result = await api("/sync/test", { method: "POST", body: JSON.stringify({}) });
    state.metrics = result.metrics || state.metrics;
    state.publicMetrics = state.metrics;
    const databaseMs = result.checks?.database?.latency_ms ?? "-";
    const employeeRows = result.checks?.employee_cache?.rows ?? 0;
    const payrollRows = result.checks?.payroll_cache?.rows ?? 0;
    const darwinbox = result.checks?.darwinbox || {};
    const darwinboxText = darwinbox.configured
      ? darwinbox.ok ? `Darwinbox ${darwinbox.latency_ms}ms` : "Darwinbox returned an error"
      : "Darwinbox credentials missing";
    toast(`Pipeline check · DB ${databaseMs}ms · ${formatNumber(employeeRows)} employees · ${formatNumber(payrollRows)} payroll rows · ${darwinboxText}.`);
  } catch (error) {
    toast(error.message);
  } finally {
    state.syncTesting = false;
    render();
  }
}

async function recordSyncCheck() {
  if (state.syncTesting || state.syncRecording) return;
  state.syncRecording = true;
  render();
  try {
    const data = await api("/sync/check", { method: "POST", body: JSON.stringify({}) });
    state.sync = data.sync || state.sync;
    state.metrics = data.metrics || state.metrics;
    state.publicMetrics = state.metrics;
    const employeeRows = data.checks?.employee_cache?.rows ?? state.metrics.employee_count ?? 0;
    toast(`Sync check recorded. ${formatNumber(employeeRows)} employee rows verified from Postgres cache.`);
  } catch (error) {
    toast(error.message);
  } finally {
    state.syncRecording = false;
    render();
  }
}

async function uploadApproval(file) {
  if (!file) return;
  if (file.size > 200 * 1024 * 1024) {
    toast("File exceeds 200 MB limit.");
    return;
  }
  state.approvalUploading = true;
  render();
  try {
    const dataBase64 = await fileToBase64(file);
    const upload = await api("/uploads", {
      method: "POST",
      body: JSON.stringify({
        file_name: file.name,
        content_type: file.type || "application/octet-stream",
        data_base64: dataBase64
      })
    });
    state.form.approvalFileName = upload.original_name || file.name;
    state.form.approvalFileUrl = upload.url || "";
    state.form.approvalUploadId = upload.id || "";
    saveUiState();
    toast("Approval file uploaded.");
  } catch (error) {
    state.form.approvalFileName = "";
    state.form.approvalFileUrl = "";
    state.form.approvalUploadId = "";
    saveUiState();
    toast(error.message);
  } finally {
    state.approvalUploading = false;
    render();
  }
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("Unable to read selected file."));
    reader.readAsDataURL(file);
  });
}

async function submitCase() {
  if (state.approvalUploading) return toast("Approval upload is still in progress.");
  if (!isFormValid()) return toast("Fill all required fields first.");
  const employee = state.employees.find((item) => item.empCode === state.selectedEmployee) || state.employees[0];
  try {
    const created = await api("/cases", {
      method: "POST",
      body: JSON.stringify({
        emp_code: employee.empCode,
        date_of_resignation: state.form.dor,
        last_working_date: state.form.lwd,
        separation_reason: state.form.reason,
        separation_sub_reason: state.form.subReason,
        immediate_exit_or_serving_notice: state.form.noticeType,
        garden_leave: state.form.gardenLeave,
        communication_status: state.form.communication,
        remarks: state.form.remarks,
        approval_file_name: state.form.approvalFileName,
        approval_file_url: state.form.approvalFileUrl
      })
    });
    state.view = "dashboard";
    state.tab = "mycases";
    state.form = applyFormDefaults(defaultForm());
    state.calculation = null;
    await loadBootstrap();
    toast(`Case ${created.case_id} submitted.`);
  } catch (error) {
    toast(error.message);
  }
}

function queueCalculation() {
  clearTimeout(calcTimer);
  if (!state.selectedEmployee || !state.form.dor || !state.form.lwd || !state.form.reason) return;
  state.calcLoading = true;
  calcTimer = setTimeout(refreshCalculation, 240);
}

async function refreshCalculation() {
  const employee = state.employees.find((item) => item.empCode === state.selectedEmployee);
  if (!employee) return;
  try {
    state.calculation = await api("/calculate", {
      method: "POST",
      body: JSON.stringify({
        emp_code: employee.empCode,
        date_of_resignation: state.form.dor,
        last_working_date: state.form.lwd,
        separation_reason: state.form.reason,
        separation_sub_reason: state.form.subReason,
        immediate_exit_or_serving_notice: state.form.noticeType,
        garden_leave: state.form.gardenLeave,
        communication_status: state.form.communication
      })
    });
  } catch (error) {
    state.calculation = null;
    toast(error.message);
  } finally {
    state.calcLoading = false;
    render();
  }
}

async function openCaseModal(caseId) {
  const selected = state.cases.find((item) => item.id === caseId);
  if (!selected) return;
  const modal = document.createElement("div");
  modal.className = "modal-backdrop";
  modal.innerHTML = caseModal(selected, [], selected.raw);
  document.body.appendChild(modal);
  try {
    const detail = await api(`/cases/${encodeURIComponent(caseId)}`);
    modal.innerHTML = caseModal(mapCase(detail.case), detail.audit || [], detail.case);
  } catch (error) {
    toast(error.message);
  }
}

function caseModal(item, audit, raw = item.raw || {}) {
  return `
    <div class="modal">
      <div class="modal-head"><div><h2>${h(item.id)} · ${h(item.empName)}</h2><p>${statusChip(item.status)} LWD · ${h(item.lwd)}</p></div><button data-close-modal>×</button></div>
      <div class="modal-grid">
        <section>${sectionTitle("Details")}<div class="detail-grid">${detail("Emp Code", item.empCode)}${detail("Entity", item.entity)}${detail("Reason", item.reason)}${detail("Sub Reason", item.subReason)}${detail("Communication", item.communication)}${detail("Manager", raw.l1_manager || "-")}</div></section>
        <section>${sectionTitle("FNF Calculations")}<div class="settlement-grid">${settlementTile("Notice Pay", inr(item.noticePay))}${settlementTile("Gratuity", inr(item.gratuity))}${settlementTile("Final Settlement", inr(item.finalSettlement))}${settlementTile("Tenure", raw.tenure || "-")}</div></section>
        <section>${sectionTitle("Audit Log")}${audit.length ? audit.map((row) => `<div class="audit"><strong>${h(row.action)}</strong><span>${h(row.user_email || "-")}</span><small>${h(formatTs(row.created_at))}</small></div>`).join("") : `<p class="muted">No audit entries yet.</p>`}</section>
      </div>
    </div>
  `;
}

document.addEventListener("click", (event) => {
  if (event.target.closest("[data-close-modal]")) event.target.closest(".modal-backdrop").remove();
});

document.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
    event.preventDefault();
    const quickInput = app.querySelector("[data-quick-jump]");
    if (quickInput) {
      quickInput.focus();
      quickInput.select();
    }
  }
});

function performQuickJump(query) {
  const needle = normalizeQuickJump(query);
  if (!needle) {
    app.querySelector("[data-quick-jump]")?.focus();
    return;
  }
  const candidates = NAV_ITEMS.map((item) => ({
    item,
    terms: [item.key, item.title, item.subtitle, item.step, item.hotkey, ...(quickJumpAliases()[item.key] || [])]
      .map(normalizeQuickJump)
  }));
  const ranked = candidates
    .map((candidate) => {
      const exact = candidate.terms.some((term) => term === needle);
      const starts = candidate.terms.some((term) => term.startsWith(needle));
      const contains = candidate.terms.some((term) => term.includes(needle));
      return { ...candidate, score: exact ? 3 : starts ? 2 : contains ? 1 : 0 };
    })
    .filter((candidate) => candidate.score > 0)
    .sort((a, b) => b.score - a.score);
  if (!ranked.length) {
    toast(`No quick jump match for "${query}"`);
    app.querySelector("[data-quick-jump]")?.focus();
    return;
  }
  state.tab = ranked[0].item.key;
  state.view = "dashboard";
  saveUiState();
  render();
  toast(`Jumped to ${ranked[0].item.title}`);
}

function quickJumpAliases() {
  return {
    team: ["direct reports", "manager", "employees"],
    mycases: ["my case", "initiated", "started"],
    allcases: ["all case", "org", "tracker", "cases"],
    sync: ["employee data", "darwinbox", "data", "pipeline"]
  };
}

async function handleOAuthCallback() {
  const params = new URLSearchParams(window.location.search);
  const error = params.get("error");
  const code = params.get("code");
  if (error) {
    state.ssoLoading = false;
    state.authError = error === "access_denied" ? "Login was cancelled." : error;
    window.history.replaceState({}, "", "/login");
    return;
  }
  if (!code || !bifrost) return;
  state.loading = true;
  state.ssoLoading = true;
  render();
  try {
    const response = await bifrost.exchangeCodeForTokens({
      code,
      redirectUri: authConfig.redirectUri,
      sessionInfo: { platform: "WEB", loginMethod: "sso" }
    });
    if (!response?.data?.access_token) throw new Error("Authentication failed. Please try again.");
    storeTokens(response.data);
    state.ssoLoading = false;
    window.history.replaceState({}, "", "/");
  } catch (err) {
    state.ssoLoading = false;
    state.authError = err.message || "Authentication failed.";
    window.history.replaceState({}, "", "/login");
  }
}

function createBifrost(config) {
  const authApiBaseUrl = trimSlash(config.authApiUrl || "");
  const clientId = config.clientId || "";
  const deviceId = getDeviceId();
  const redirectUri = config.redirectUri || `${window.location.origin}/login`;
  const endpoint = (path) => `${authApiBaseUrl}${path}`;

  return {
    async getLoginMethods() {
      const response = await fetch(endpoint(`/oauth2/method/${clientId}`), {
        method: "GET",
        headers: { Accept: "application/json" }
      });
      return parseBifrostResponse(response);
    },
    async refreshToken(params) {
      const response = await fetch(endpoint("/oauth2/token"), {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-device-id": deviceId },
        credentials: "include",
        mode: "cors",
        body: JSON.stringify({
          grant_type: "refresh_token",
          refresh_token: params.refreshToken,
          client_id: clientId,
          session_id: params.sessionId,
          redirect_uri: redirectUri
        })
      });
      return parseBifrostResponse(response);
    },
    async exchangeCodeForTokens(params) {
      const codeVerifier = params.codeVerifier || sessionStorage.getItem("bifrostCodeVerifier");
      if (!codeVerifier) throw new Error("Missing PKCE code verifier. Please start sign-in again.");
      const response = await fetch(endpoint("/oauth2/token"), {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-device-id": deviceId },
        credentials: "include",
        mode: "cors",
        body: JSON.stringify({
          grant_type: "authorization_code",
          code: params.code,
          redirect_uri: params.redirectUri || redirectUri,
          client_id: clientId,
          code_verifier: codeVerifier,
          session_info: params.sessionInfo
        })
      });
      const tokenResponse = await parseBifrostResponse(response);
      sessionStorage.removeItem("bifrostCodeVerifier");
      return tokenResponse;
    },
    async logout(params) {
      const response = await fetch(endpoint("/api/v1/logout"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${params.accessToken}`,
          "x-device-id": deviceId
        },
        body: JSON.stringify({ session_id: params.sessionId })
      });
      return parseBifrostResponse(response);
    },
    async sso(params) {
      if (!authApiBaseUrl || !clientId) throw new Error("Bifrost auth URL or client id is missing.");
      const codeVerifier = createCodeVerifier();
      const codeChallenge = await createCodeChallenge(codeVerifier);
      sessionStorage.setItem("bifrostCodeVerifier", codeVerifier);
      const statePayload = {
        method_id: params.method_id,
        device_id: deviceId,
        country_code: params.country_code,
        client_id: clientId,
        redirect_uri: redirectUri,
        client_redirect_uri: redirectUri,
        isSSO: true
      };
      const authParams = new URLSearchParams({
        response_type: "code",
        client_id: clientId,
        redirect_uri: redirectUri,
        state: JSON.stringify(statePayload),
        code_challenge: codeChallenge,
        code_challenge_method: "S256",
        device_id: deviceId
      });
      const loginFlow = await fetch(endpoint(`/oauth2/auth?${authParams.toString()}`), {
        method: "GET",
        headers: { Accept: "application/json" },
        credentials: "include"
      });
      const payload = await parseBifrostResponse(loginFlow);
      if (!payload.data?.flow_token) throw new Error("Unable to start Bifrost login flow");
      statePayload.flow_token = payload.data.flow_token;
      const scopes = encodeURIComponent("https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/userinfo.profile openid");
      window.location.replace(
        `https://accounts.google.com/o/oauth2/v2/auth?redirect_uri=${encodeURIComponent(params.redirect_uri)}` +
        `&prompt=consent&response_type=code&client_id=${encodeURIComponent(params.client_id)}` +
        `&scope=${scopes}&state=${base64UrlEncode(JSON.stringify(statePayload))}`
      );
      return new Promise(() => undefined);
    }
  };
}

async function parseBifrostResponse(response) {
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) {
    throw new Error(data?.error_description || data?.error || data?.message || `HTTP ${response.status}`);
  }
  return data;
}

function storeTokens(data) {
  localStorage.setItem(TOKEN_KEY, data.access_token || data.accessToken || "");
  localStorage.setItem(REFRESH_KEY, data.refresh_token || data.refreshToken || "");
  localStorage.setItem(SESSION_KEY, data.session_id || data.sessionId || "");
}

function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
  localStorage.removeItem(SESSION_KEY);
}

function getAccessToken() {
  return localStorage.getItem(TOKEN_KEY);
}

function getDeviceId() {
  let id = localStorage.getItem("deviceId");
  if (!id) {
    id = `device-${crypto.randomUUID()}`;
    localStorage.setItem("deviceId", id);
  }
  return id;
}

function trimSlash(value) {
  return String(value || "").replace(/\/+$/, "");
}

function base64UrlEncodeBytes(bytes) {
  const bin = Array.from(bytes, (byte) => String.fromCharCode(byte)).join("");
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function base64UrlEncode(value) {
  return base64UrlEncodeBytes(new TextEncoder().encode(value));
}

async function createCodeChallenge(verifier) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
  return base64UrlEncodeBytes(new Uint8Array(digest));
}

function createCodeVerifier() {
  const bytes = new Uint8Array(64);
  crypto.getRandomValues(bytes);
  return base64UrlEncodeBytes(bytes);
}

function inputField(label, key, type = "text") {
  return `<label>${fieldLabel(`${label} *`)}<input class="input" type="${type}" value="${h(state.form[key])}" data-input="${key}"></label>`;
}

function textareaField(label, key) {
  return `<label>${fieldLabel(label)}<textarea class="input textarea" data-input="${key}" placeholder="Optional notes...">${h(state.form[key])}</textarea></label>`;
}

function selectField(label, key, options, placeholder = "") {
  return `<label>${fieldLabel(`${label} *`)}<select class="input" data-input="${key}">${optionTags(options, state.form[key], placeholder)}</select></label>`;
}

function optionTags(options = [], selected = "", placeholder = "") {
  const values = Array.isArray(options)
    ? options.filter((option) => option !== null && option !== undefined && option !== "")
    : [];
  const placeholderTag = placeholder
    ? `<option value="" ${!selected ? "selected" : ""}>${h(placeholder)}</option>`
    : "";
  return placeholderTag + values.map((option) => `<option value="${h(option)}" ${selected === option ? "selected" : ""}>${h(option)}</option>`).join("");
}

function fieldLabel(label) {
  return `<span class="field-label">${h(label)}</span>`;
}

function profile(label, value) {
  return `<div><small>${h(label)}</small><strong>${h(value || "-")}</strong></div>`;
}

function emptyState(message) {
  return `<div class="empty-state inline"><span>∅</span><strong>${h(message)}</strong></div>`;
}

function h(value) {
  return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");
}

function initials(name) {
  return String(name || "?").split(/\s+/).filter(Boolean).map((part) => part[0].toUpperCase()).slice(0, 2).join("");
}

function truncate(value, max) {
  return String(value || "").length > max ? `${String(value).slice(0, max)}...` : String(value || "");
}

function normalizeQuickJump(value) {
  return String(value || "").trim().toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

function brandMark() {
  return `<span class="brand-mark logo-mark"><img src="${CARS24_LOGO_URL}" alt="CARS24"></span>`;
}

function loginFlowStep(title, subtitle, icon) {
  return `
    <div class="login-flow-step">
      <span>${h(icon)}</span>
      <strong>${h(title)}</strong>
      <small>${h(subtitle)}</small>
    </div>
  `;
}

function settlementTile(label, value) {
  return `<div class="settlement"><small>${h(label)}</small><strong>${h(value)}</strong></div>`;
}

function health(label, value) {
  return `<div class="health-row"><span>${h(label)}</span><strong>${h(value)}</strong></div>`;
}

function sectionTitle(title) {
  return `<h3>${h(title)}</h3>`;
}

function detail(label, value) {
  return `<div><small>${h(label)}</small><strong>${h(value || "-")}</strong></div>`;
}

function normalizeStatus(status) {
  if (status === "Submitted") return "Processing";
  if (status === "Admin Closed") return "Completed";
  if (status === "Hold") return "Pending";
  return status || "Pending";
}

function statusChip(status) {
  return `<span class="status-chip">${h(normalizeStatus(status))}</span>`;
}

function statusClass(status) {
  const normalized = normalizeStatus(status).toLowerCase();
  if (normalized.includes("completed")) return "case-completed";
  if (normalized.includes("processing")) return "case-processing";
  if (normalized.includes("pending")) return "case-pending";
  return "case-neutral";
}

function inr(value) {
  return `₹ ${Math.round(Number(value || 0)).toLocaleString("en-IN")}`;
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString("en-IN");
}

function syncLatencyLabel(value) {
  return value === null || value === undefined ? "-" : `${value}m`;
}

function formatDate(value) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short", year: "numeric" }).format(new Date(`${value}T00:00:00`)).replace(/ /g, "-");
}

function formatTs(value) {
  if (!value) return "-";
  return new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function subReasonOptions(reason) {
  return state.options.separation_sub_reasons?.[reason] || [];
}

function isFormValid() {
  return Boolean(
    state.form.dor &&
    state.form.lwd &&
    state.form.reason &&
    state.form.subReason &&
    state.form.noticeType &&
    state.form.gardenLeave &&
    state.form.communication &&
    state.calculation &&
    !state.approvalUploading
  );
}

function toast(message) {
  const node = document.createElement("div");
  node.className = "toast";
  node.textContent = message;
  toastRoot.appendChild(node);
  setTimeout(() => node.remove(), 3800);
}

init();

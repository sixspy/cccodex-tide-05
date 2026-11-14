<script setup>
import { computed, ref } from "vue";

const token = ref(localStorage.getItem("tide.token") || "");
const profile = ref(JSON.parse(localStorage.getItem("tide.profile") || "null"));
const username = ref("admin");
const password = ref("123456");
const loginError = ref("");
const batches = ref([]);
const current = ref(null);
const policy = ref(null);
const skips = ref([]);
const title = ref("");
const rawText = ref("");
const formError = ref("");
const policyError = ref("");
const busy = ref(false);
const expandedSkips = ref(new Set());

const canWrite = computed(() => profile.value && profile.value.role === "writer");

const DISP_LABEL = {
  已落库: "留行落库",
  保留落库: "留行落库",
  单行: "待比较",
  保留: "留行",
  跳过重行: "跳过",
  双拒: "双拒",
  跨批重复: "跨批重复",
  解析失败: "解析失败",
  未比较: "未比较（顺序锁拦截）",
};

async function request(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (token.value) headers.Authorization = `Bearer ${token.value}`;
  const response = await fetch(path, { ...options, headers });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = data.detail || "请求没有完成";
    throw new Error(typeof message === "string" ? message : "请求没有完成");
  }
  return data;
}

async function refresh() {
  const [list, skipList, policyData] = await Promise.all([
    request("/api/batches"),
    request("/api/skips"),
    request("/api/policy"),
  ]);
  batches.value = list;
  skips.value = skipList;
  policy.value = policyData;
  if (!current.value && batches.value.length) {
    await openBatch(batches.value[0].id);
  } else if (current.value) {
    await openBatch(current.value.batch.id);
  }
}

async function openBatch(id) {
  current.value = await request(`/api/batches/${id}`);
}

async function submitLogin() {
  loginError.value = "";
  try {
    const data = await request("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: username.value, password: password.value }),
    });
    token.value = data.access_token;
    profile.value = { username: data.username, role: data.role, title: data.title };
    localStorage.setItem("tide.token", token.value);
    localStorage.setItem("tide.profile", JSON.stringify(profile.value));
    await refresh();
  } catch (error) {
    loginError.value = error.message;
  }
}

async function submitBatch() {
  formError.value = "";
  busy.value = true;
  try {
    const data = await request("/api/batches", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: title.value, raw_text: rawText.value }),
    });
    title.value = "";
    rawText.value = "";
    await refresh();
    current.value = data;
  } catch (error) {
    formError.value = error.message;
  } finally {
    busy.value = false;
  }
}

async function chooseDecision(decision) {
  if (!current.value || !current.value.can_edit_settings) return;
  formError.value = "";
  try {
    current.value = await request(
      `/api/batches/${current.value.batch.id}/decision`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision }),
      },
    );
    await refresh();
  } catch (error) {
    formError.value = error.message;
  }
}

async function runCompare() {
  if (!current.value) return;
  formError.value = "";
  busy.value = true;
  try {
    current.value = await request(
      `/api/batches/${current.value.batch.id}/compare`,
      { method: "POST" },
    );
    await refresh();
  } catch (error) {
    formError.value = error.message;
  } finally {
    busy.value = false;
  }
}

async function writePolicy(decision) {
  policyError.value = "";
  try {
    policy.value = await request("/api/policy", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision }),
    });
    await refresh();
  } catch (error) {
    policyError.value = error.message;
  }
}

function toggleSkip(id) {
  const next = new Set(expandedSkips.value);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  expandedSkips.value = next;
}

function lineText(value) {
  return value === null || value === undefined ? "缺行号" : value;
}

function logout() {
  token.value = "";
  profile.value = null;
  current.value = null;
  localStorage.removeItem("tide.token");
  localStorage.removeItem("tide.profile");
}

if (token.value) {
  refresh().catch(() => logout());
}
</script>

<template>
  <header class="top">
    <div>
      <p class="eyebrow">水文组 · 报文归集</p>
      <h1>潮位报文归集台</h1>
    </div>
    <div v-if="profile" class="who">
      <span>{{ profile.title }} {{ profile.username }}</span>
      <button class="ghost" @click="logout">离开</button>
    </div>
  </header>

  <main v-if="!profile" class="gate">
    <form @submit.prevent="submitLogin">
      <p>站码、时刻、潮位厘米、质量旗。一行一条，竖线分开。五段式首段可给行号，"-" 表示行号缺失。</p>
      <label>用户<input v-model="username" autocomplete="username" /></label>
      <label>口令<input v-model="password" type="password" autocomplete="current-password" /></label>
      <button>进入归集台</button>
      <p v-if="loginError" class="warn">{{ loginError }}</p>
    </form>
  </main>

  <main v-else class="desk">
    <section class="paste">
      <h2>贴入这一批</h2>
      <p class="rule">
        质量旗 A 实测，M 插补，B 可疑。批内同站同时刻为重行，落库前先去重。
      </p>
      <label>批次名<input v-model="title" :disabled="!canWrite" placeholder="例如 堡镇 11-13 午班" /></label>
      <textarea
        v-model="rawText"
        :disabled="!canWrite"
        placeholder="BZ03|202611130900|176|A&#10;-|BZ03|202611131000|165|M （首段 - 表示行号缺失）"
        spellcheck="false"
      />
      <button :disabled="!canWrite || busy" @click="submitBatch">贴入解析（不落库）</button>
      <p v-if="!canWrite" class="quiet">档案员只能翻已落入的报文。</p>
      <p v-if="formError" class="warn">{{ formError }}</p>

      <article v-if="policy" class="policy-card">
        <h3>当日策略簿</h3>
        <p v-if="policy.locked" class="quiet">
          今日取舍已定为「{{ policy.decision }}」，当日禁止改口。
        </p>
        <template v-else>
          <p class="quiet">今日尚未写策略簿，写入后当日锁定。</p>
          <div class="decision-row" v-if="canWrite">
            <button
              v-for="opt in policy.options"
              :key="opt"
              class="ghost-dark"
              @click="writePolicy(opt)"
            >写为「{{ opt }}」</button>
          </div>
        </template>
        <p v-if="policyError" class="warn">{{ policyError }}</p>
      </article>
    </section>

    <section class="slips">
      <h2>批内列表</h2>
      <button
        v-for="batch in batches"
        :key="batch.id"
        class="slip"
        :class="{ on: current && current.batch.id === batch.id }"
        @click="openBatch(batch.id)"
      >
        <strong>{{ batch.title }}</strong>
        <em>{{ batch.status }}</em>
        <span>取舍：{{ batch.decision || "未设" }}<b v-if="batch.decision_mismatch" class="mismatch">（批内取舍不符）</b></span>
        <span>保留行号：{{ batch.retained_line_nos.length ? batch.retained_line_nos.join("、") : "无" }}</span>
        <span>跳过行号：{{ batch.skipped_line_nos.length ? batch.skipped_line_nos.map(lineText).join("、") : "无" }}</span>
        <span>落入 {{ batch.accepted_count }} · 跳过 {{ batch.skipped_count }} · 未接纳 {{ batch.rejected_count }}</span>
      </button>

      <article v-if="current" class="tape">
        <header>
          <h3>{{ current.batch.title }}</h3>
          <span :class="{ mismatch: current.batch.decision_mismatch }">{{ current.batch.status }}</span>
        </header>

        <!-- 批内设置：仅待比较阶段可改，比较开始即冻结 -->
        <div class="settings">
          <h4>批内设置</h4>
          <p v-if="current.batch.decision_mismatch" class="warn">批内取舍不符：策略簿为「{{ current.batch.policy_decision }}」，本批选了「{{ current.batch.decision }}」</p>
          <div class="decision-row">
            <button
              v-for="opt in (policy?.options || ['留行', '双拒'])"
              :key="opt"
              class="ghost-dark"
              :class="{ picked: current.batch.decision === opt }"
              :disabled="!canWrite || !current.can_edit_settings"
              @click="chooseDecision(opt)"
            >{{ opt }}</button>
          </div>
          <p v-if="!current.can_edit_settings" class="quiet">比较已开始，批内设置冻结，不许再改。</p>
          <button
            v-if="canWrite && current.can_edit_settings"
            :disabled="busy"
            @click="runCompare"
          >开始比较并落库</button>
        </div>

        <div v-if="current.batch.status === '顺序锁拦截'" class="lock-note">
          <p class="warn">本批被顺序锁拦截：另一批已先持有同一对重行，本批整批未入库。</p>
          <ul v-if="current.locks.length">
            <li v-for="lock in current.locks" :key="lock.lock_key">
              {{ lock.station_code }} · {{ lock.observed_at }} — 先到批次 #{{ lock.holder_batch_id }}
            </li>
          </ul>
        </div>

        <!-- 行号详情：分清留行与双拒，被跳过的可点开看原文 -->
        <h4>行号详情</h4>
        <table>
          <thead>
            <tr><th>行号</th><th>站</th><th>时刻</th><th>厘米</th><th>旗</th><th>去向</th></tr>
          </thead>
          <tbody>
            <tr
              v-for="row in current.rows"
              :key="row.id"
              :class="{
                kept: ['保留', '保留落库'].includes(row.disposition),
                doubled: row.disposition === '双拒',
                skipped: ['跳过重行', '跨批重复'].includes(row.disposition),
                bad: row.disposition === '解析失败',
                locked: row.disposition === '未比较',
              }"
            >
              <td>{{ lineText(row.line_no) }}</td>
              <td>{{ row.station_code || "—" }}</td>
              <td>{{ row.observed_at || "—" }}</td>
              <td>{{ row.tide_cm ?? "—" }}</td>
              <td>{{ row.flag_label || "—" }}</td>
              <td>{{ row.parse_reason || DISP_LABEL[row.disposition] || row.disposition }}</td>
            </tr>
          </tbody>
        </table>

        <h4>跳过队列（点开看原文）</h4>
        <ul class="skip-list">
          <li v-for="row in current.skipped" :key="row.id">
            <button class="ghost-dark skip-head" @click="toggleSkip(row.id)">
              行 {{ lineText(row.line_no) }} · {{ row.reason }}
              <em v-if="row.kept_line_no">（留行 #{{ row.kept_line_no }}）</em>
              <b :class="{ doubled: row.decision === '双拒' }">{{ row.decision }}</b>
            </button>
            <code v-if="expandedSkips.has(row.id)">{{ row.raw_line }}</code>
          </li>
          <li v-if="!current.skipped.length" class="quiet">没有被跳过的行</li>
        </ul>

        <h4>解析未接纳</h4>
        <ul>
          <li v-for="row in current.rejected" :key="row.line_no ?? row.raw_line">
            <code>{{ row.raw_line }}</code>
            <span>{{ row.reason }}</span>
          </li>
          <li v-if="!current.rejected.length" class="quiet">没有解析失败的行</li>
        </ul>
      </article>

      <article class="tape">
        <h4>全站跳过队列</h4>
        <table>
          <thead>
            <tr><th>批次</th><th>行号</th><th>站/时刻</th><th>原因</th><th>取舍</th></tr>
          </thead>
          <tbody>
            <tr v-for="row in skips" :key="row.id" :class="{ doubled: row.decision === '双拒' }">
              <td>{{ row.batch_title }}</td>
              <td>{{ lineText(row.line_no) }}</td>
              <td>{{ row.station_code }} · {{ row.observed_at }}</td>
              <td>{{ row.reason }}</td>
              <td>{{ row.decision }}</td>
            </tr>
            <tr v-if="!skips.length"><td colspan="5">跳过队列是空的</td></tr>
          </tbody>
        </table>
      </article>
    </section>
  </main>
</template>

<style scoped>
.top, .desk, .gate { width: min(1280px, calc(100% - 32px)); margin: 0 auto; }
.top { display: flex; justify-content: space-between; align-items: end; padding: 28px 0 12px; }
.eyebrow { letter-spacing: 0.18em; text-transform: uppercase; color: #d7a15f; font-size: 12px; margin: 0 0 6px; }
h1 { margin: 0; font-weight: 560; font-size: 34px; }
h2, h3, h4 { margin: 0; }
.who { display: flex; gap: 12px; align-items: center; }
.ghost { background: transparent; color: #f3efe2; border: 1px solid rgba(243, 239, 226, 0.35); padding: 6px 12px; }
.ghost-dark { background: #1c2430; color: #f3efe2; border: 1px solid rgba(28, 36, 48, 0.4); padding: 6px 12px; }
.ghost-dark.picked { outline: 2px solid #d7a15f; }
.gate { padding: 24px 0 48px; }
.gate form, .paste, .tape {
  background: #f3efe2;
  color: #1c2430;
  padding: 22px;
}
.gate form { width: min(420px, 100%); display: grid; gap: 12px; }
label { display: grid; gap: 6px; font-size: 14px; }
input, textarea {
  width: 100%;
  border: 0;
  background: #fffdf8;
  color: #1c2430;
  padding: 10px 12px;
  box-shadow: inset 0 0 0 1px #d9d0bc;
}
textarea { min-height: 200px; font-family: "IBM Plex Mono", Consolas, monospace; line-height: 1.6; }
button { background: #9d2c2c; color: #fffaf2; padding: 10px 14px; }
.desk { display: grid; grid-template-columns: 380px 1fr; gap: 22px; padding-bottom: 48px; }
.paste, .slips { display: grid; gap: 12px; align-content: start; }
.rule, .quiet { margin: 0; color: #5c5648; font-size: 14px; }
.policy-card { border: 1px dashed #b9ac90; padding: 14px; display: grid; gap: 8px; background: #fbf7ec; }
.decision-row { display: flex; gap: 10px; flex-wrap: wrap; }
.slip {
  text-align: left;
  background: transparent;
  color: #f3efe2;
  border: 1px solid rgba(243, 239, 226, 0.2);
  padding: 12px 14px;
  display: grid;
  gap: 4px;
}
.slip.on { border-color: #d7a15f; }
.slip em { font-style: normal; color: #d7a15f; }
.slip span, .tape li span { color: #5c5648; font-size: 13px; }
.mismatch { color: #9d2c2c; font-weight: 700; }
.tape header { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 8px; }
.tape h4 { margin: 14px 0 8px; }
.settings { border: 1px solid #d9d0bc; padding: 12px; display: grid; gap: 10px; background: #fbf7ec; }
.lock-note { border: 1px solid #9d2c2c; padding: 10px 12px; margin-top: 10px; background: #f7e7e7; }
table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }
th, td { text-align: left; padding: 6px 4px; border-bottom: 1px solid #e4dcc8; font-size: 13px; }
tr.kept td { background: #e6f0e2; }
tr.doubled td { background: #f3d9d9; }
tr.skipped td { background: #f6ecd6; }
tr.bad td { background: #ece4f0; }
tr.locked td { background: #e3e6ea; color: #555c66; }
ul { list-style: none; padding: 0; margin: 0; display: grid; gap: 8px; }
li { display: grid; gap: 2px; }
code { font-family: Consolas, monospace; background: #fffdf8; padding: 6px 8px; box-shadow: inset 0 0 0 1px #d9d0bc; }
.warn { color: #9d2c2c; margin: 0; }
.skip-list .skip-head { text-align: left; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.skip-list em { font-style: normal; color: #5c5648; }
.skip-list b.doubled { color: #9d2c2c; }
@media (max-width: 960px) {
  .desk { grid-template-columns: 1fr; }
}
</style>

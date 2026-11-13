<script setup>
import { computed, ref } from "vue";

const token = ref(localStorage.getItem("tide.token") || "");
const profile = ref(JSON.parse(localStorage.getItem("tide.profile") || "null"));
const username = ref("admin");
const password = ref("123456");
const loginError = ref("");
const batches = ref([]);
const current = ref(null);
const title = ref("");
const rawText = ref("");
const formError = ref("");
const busy = ref(false);

const canWrite = computed(() => profile.value && profile.value.role === "writer");

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
  batches.value = await request("/api/batches");
  if (!current.value && batches.value.length) {
    await openBatch(batches.value[0].id);
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
      <p>站码、时刻、潮位厘米、质量旗。一行一条，竖线分开。</p>
      <label>用户<input v-model="username" autocomplete="username" /></label>
      <label>口令<input v-model="password" type="password" autocomplete="current-password" /></label>
      <button>进入归集台</button>
      <p v-if="loginError" class="warn">{{ loginError }}</p>
    </form>
  </main>

  <main v-else class="desk">
    <section class="paste">
      <h2>贴入这一批</h2>
      <p class="rule">质量旗 A 实测，M 插补，B 可疑。同一站同一时刻只能落一次。</p>
      <label>批次名<input v-model="title" :disabled="!canWrite" placeholder="例如 堡镇 11-13 午班" /></label>
      <textarea
        v-model="rawText"
        :disabled="!canWrite"
        placeholder="BZ03|202611130900|176|A"
        spellcheck="false"
      />
      <button :disabled="!canWrite || busy" @click="submitBatch">归集这一批</button>
      <p v-if="!canWrite" class="quiet">档案员只能翻已落入的报文。</p>
      <p v-if="formError" class="warn">{{ formError }}</p>
    </section>

    <section class="slips">
      <h2>已收批次</h2>
      <button
        v-for="batch in batches"
        :key="batch.id"
        class="slip"
        :class="{ on: current && current.batch.id === batch.id }"
        @click="openBatch(batch.id)"
      >
        <strong>{{ batch.title }}</strong>
        <em>{{ batch.status }}</em>
        <span>落入 {{ batch.accepted_count }} 行 · 未接纳 {{ batch.rejected_count }} 行</span>
      </button>

      <article v-if="current" class="tape">
        <header>
          <h3>{{ current.batch.title }}</h3>
          <span>{{ current.batch.status }}</span>
        </header>
        <h4>已落库</h4>
        <table>
          <thead>
            <tr><th>行</th><th>站</th><th>时刻</th><th>厘米</th><th>旗</th></tr>
          </thead>
          <tbody>
            <tr v-for="row in current.landed" :key="row.line_no">
              <td>{{ row.line_no }}</td>
              <td>{{ row.station_code }}</td>
              <td>{{ row.observed_at }}</td>
              <td>{{ row.tide_cm }}</td>
              <td>{{ row.flag_label }}</td>
            </tr>
            <tr v-if="!current.landed.length"><td colspan="5">这一批没有落入的行</td></tr>
          </tbody>
        </table>
        <h4>未接纳</h4>
        <ul>
          <li v-for="row in current.rejected" :key="row.line_no">
            <code>{{ row.raw_line }}</code>
            <span>{{ row.reason }}</span>
          </li>
          <li v-if="!current.rejected.length">没有被挡下的行</li>
        </ul>
      </article>
    </section>
  </main>
</template>

<style scoped>
.top, .desk, .gate { width: min(1180px, calc(100% - 32px)); margin: 0 auto; }
.top { display: flex; justify-content: space-between; align-items: end; padding: 28px 0 12px; }
.eyebrow { letter-spacing: 0.18em; text-transform: uppercase; color: #d7a15f; font-size: 12px; margin: 0 0 6px; }
h1 { margin: 0; font-weight: 560; font-size: 34px; }
h2, h3, h4 { margin: 0; }
.who { display: flex; gap: 12px; align-items: center; }
.ghost { background: transparent; color: #f3efe2; border: 1px solid rgba(243, 239, 226, 0.35); padding: 6px 12px; }
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
textarea { min-height: 220px; font-family: "IBM Plex Mono", Consolas, monospace; line-height: 1.6; }
button { background: #9d2c2c; color: #fffaf2; padding: 10px 14px; }
.desk { display: grid; grid-template-columns: 360px 1fr; gap: 22px; padding-bottom: 48px; }
.paste, .slips { display: grid; gap: 12px; align-content: start; }
.rule, .quiet { margin: 0; color: #5c5648; font-size: 14px; }
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
.slip span, .tape li span { color: #5c5648; }
.tape header { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 8px; }
.tape h4 { margin: 14px 0 8px; }
table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }
th, td { text-align: left; padding: 6px 4px; border-bottom: 1px solid #e4dcc8; font-size: 14px; }
ul { list-style: none; padding: 0; margin: 0; display: grid; gap: 8px; }
li { display: grid; gap: 2px; }
code { font-family: Consolas, monospace; }
.warn { color: #9d2c2c; margin: 0; }
@media (max-width: 900px) {
  .desk { grid-template-columns: 1fr; }
}
</style>

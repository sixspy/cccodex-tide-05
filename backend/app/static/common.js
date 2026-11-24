async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(url + " " + r.status);
  return r.json();
}
async function postJSON(url, body) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? "{}" : JSON.stringify(body),
  });
  const t = await r.text();
  let data;
  try { data = JSON.parse(t); } catch { data = { 原文: t }; }
  if (!r.ok) throw new Error((data && (data.错误 || data.detail)) || t || String(r.status));
  return data;
}
function 行(html) {
  const tr = document.createElement("tr");
  tr.innerHTML = html;
  return tr;
}
function 徽章(文, 类) {
  return `<span class="徽章 ${类 || ""}">${文}</span>`;
}
function 空态(文) {
  return `<p class="说明条">${文}</p>`;
}
function 格式概览(o) {
  return [
    ["观测点", o["观测点"] || 0],
    ["在缓冲", o["在缓冲"] || 0],
    ["窗切片", o["窗切片"] || 0],
    ["迟到", o["迟到"] || 0],
  ];
}
function 渲染水位(el, overview) {
  if (!el) return;
  el.innerHTML = "";
  for (const [标, 值] of 格式概览(overview || {})) {
    const d = document.createElement("div");
    d.className = "水卡";
    d.innerHTML = `<div class="数">${值}</div><div class="标">${标}</div>`;
    el.appendChild(d);
  }
}
function 窗规一行(rules) {
  if (!rules) return "窗规未加载";
  return `${rules["当前窗号"] || "?"} · ${rules["窗起"] || ""} → ${rules["窗止"] || ""} · 窗长秒 ${rules["窗长秒"] || "?"}`;
}
function 装载摘要(report) {
  if (!report) return "";
  return `入流 ${report["入流"] || 0} / 入缓冲 ${report["入缓冲"] || 0} / 迟到 ${report["迟到"] || 0} / 驳回 ${report["驳回"] || 0}`;
}
function 关窗摘要(report) {
  if (!report) return "";
  return `窗 ${report["窗号"] || "?"} · 成片 ${report["成片数"] || 0} · 缓冲消耗 ${report["缓冲消耗"] || 0}`;
}
function 贯验摘要(report) {
  if (!report) return "";
  return `${report["是否对齐"] ? "对齐" : "撕裂"} · 在缓冲 ${report["在缓冲"]} · 切片事件 ${report["切片事件"]} · 迟到 ${report["迟到"]}`;
}
function 安全文本(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
}
window.潮切 = {
  getJSON, postJSON, 行, 徽章, 空态, 格式概览, 渲染水位,
  窗规一行, 装载摘要, 关窗摘要, 贯验摘要, 安全文本,
};

/** 潮切页面模块：sources
 * 网点源：上报源登记与换绑切口
 * 真实页面在 backend/app/static；本模块提供渲染辅助与状态文案。
 */
export const PAGE = 'sources';
export const TITLE = '网点源：上报源登记与换绑切口';

export const STAGE_COPY = {
  load: "装载：校验运单键、网点键、事件时后写入观测点",
  buffer: "入窗：事件时落在当前窗则进缓冲，否则进迟到匣",
  close: "关窗：缓冲按运单物化为窗切片账，消耗缓冲命运",
  verify: "贯验：已物化缓冲事件数必须等于切片事件数之和",
};

export function fateChip(fate) {
  const map = {
    "已装载": "ok",
    "已入缓冲": "ok",
    "在缓冲": "ok",
    "已物化": "ok",
    "已成片": "ok",
    "已迟到": "warn",
    "撕裂": "danger",
    "对齐": "ok",
  };
  return { text: fate, tone: map[fate] || "" };
}

export function windowLabel(rules) {
  if (!rules) return "窗规未加载";
  return `${rules["当前窗号"] || "?"}  ${rules["窗起"] || ""} → ${rules["窗止"] || ""}`;
}

export function summarizeLoad(report) {
  if (!report) return "无装载回执";
  return `入流 ${report["入流"] || 0} · 入缓冲 ${report["入缓冲"] || 0} · 迟到 ${report["迟到"] || 0} · 驳回 ${report["驳回"] || 0}`;
}

export function summarizeClose(report) {
  if (!report) return "无关窗回执";
  return `窗 ${report["窗号"] || "?"} · 成片 ${report["成片数"] || 0} · 缓冲消耗 ${report["缓冲消耗"] || 0}`;
}

export function summarizeVerify(report) {
  if (!report) return "无贯验回执";
  const ok = report["是否对齐"] ? "对齐" : "撕裂";
  return `${ok} · 在缓冲 ${report["在缓冲"]} · 切片事件 ${report["切片事件"]} · 迟到 ${report["迟到"]}`;
}

export function emptyState(kind) {
  const tips = {
    observe: "尚无观测点。请在潮切台灌「窗内成片样例」或「迟到样例」。",
    buffer: "缓冲为空。要么尚未装载，要么已经关窗物化。",
    slice: "尚无切片。装载窗内事件后点「关当前窗」。",
    late: "迟到匣为空。灌「迟到样例」可看到事件时出窗旁路。",
    verify: "尚无贯验记录。关窗后点「跑窗贯验」。",
  };
  return tips[kind] || "暂无数据";
}

export function assertBoneCopy() {
  return "去皮：事件时关窗管道。勿做成运单 CRUD，勿抄闸对开腿或对拍左右轨。";
}

export function buildMetricCards(overview) {
  const o = overview || {};
  return [
    { key: "观测点", value: o["观测点"] || 0, hint: "装载入流累计" },
    { key: "在缓冲", value: o["在缓冲"] || 0, hint: "未关窗物化" },
    { key: "窗切片", value: o["窗切片"] || 0, hint: "关窗产物笔数" },
    { key: "迟到", value: o["迟到"] || 0, hint: "事件时出窗" },
  ];
}

export function sortByEventTime(rows) {
  return [...(rows || [])].sort((a, b) => String(a["事件时"] || "").localeCompare(String(b["事件时"] || "")));
}

export function groupBufferByWaybill(rows) {
  const g = {};
  for (const r of rows || []) {
    const k = r["运单键"] || "_";
    (g[k] ||= []).push(r);
  }
  return g;
}

export function verifyExplainer(row) {
  if (!row) return "";
  if (row["是否对齐"]) return "缓冲已物化事件数与切片账事件数一致，窗账闭合。";
  return row["说明"] || "缓冲与切片撕裂，需回查关窗批次。";
}

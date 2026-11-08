"use strict";
const $ = selector => document.querySelector(selector);
const statuses = {
  content_review:"待审内容", ready_import_audio:"待导入配音", paid_tts_review:"待确认配音生成",
  audio_review:"待试听配音", segmentation_needed:"待分段", segmentation_review:"待审分段",
  prompt_needed:"待制作提示词", prompt_review:"待审提示词", paid_video_review:"待确认视频生成",
  running:"生成中", needs_reconciliation:"提交结果待核查", execution_failed:"生成失败",
  output_review:"待审产物", clip_review:"待审片段", ready_assembly:"待合成", final_review:"待审成片",
  completed:"已完成", blocked:"需要处理"
};
let selected = new URLSearchParams(location.search).get("task");
let requestVersion = 0;
function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined && text !== null) element.textContent = text;
  if (className) element.className = className;
  return element;
}
function notice(message) { $("#notice").textContent = message; $("#notice").classList.add("visible"); }
async function get(url) {
  const response = await fetch(url, {cache:"no-store"});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "读取失败，请刷新重试。");
  return data;
}
function section(title, note) {
  const container = node("section", null, "section");
  const heading = node("div", null, "section-heading");
  heading.append(node("h2", title));
  if (note) heading.append(node("small", note));
  container.append(heading); return container;
}
function player(path, media, kind="audio") {
  if (!media[path]) return node("p", "媒体文件不可用，请通过 Skill 核查本地文件。", "subtle");
  const element = node(kind);
  element.controls = true; element.preload = "metadata"; element.src = media[path];
  if (kind === "video") element.playsInline = true;
  return element;
}
function badge(text, warn=false) {return node("span", text, "badge" + (warn ? " warning" : ""));}
function details(title, value) {
  const element = node("details");
  element.append(node("summary", title), node("pre", value)); return element;
}
function renderTask(task, media, reviewsCurrent) {
  const main = $("#main"); main.replaceChildren();
  main.append(node("p", task.id + " / 本地制作项目", "eyebrow"));
  const title = node("div", null, "title-row");
  title.append(node("h1", task.title), badge(statuses[task.status] || task.status,
    ["needs_reconciliation","execution_failed","blocked"].includes(task.status)));
  main.append(title);
  if (["needs_reconciliation","execution_failed","blocked"].includes(task.status)) {
    const warning = node("div", null, "callout");
    warning.append(node("strong", task.status === "needs_reconciliation" ? "先核查平台记录，再继续" : "当前任务需要处理"));
    warning.append(node("p", task.blocker || (task.status === "needs_reconciliation"
      ? "没有取得可查询的平台任务 ID。请通过 Skill 核查并恢复；本页不会重新提交。"
      : "查看下方操作记录，并通过 Skill 处理失败原因。")));
    main.append(warning);
  }
  const refs = section("画面参考", "人物 / 场景 / 产品");
  const assets = node("div", null, "assets");
  for (const [key,label] of [["presenter","人物参考"],["scene","场景参考"],["product","产品参考"]]) {
    const figure = node("figure", null, "asset");
    const path = task.assets[key]?.path;
    if (media[path]) {const image = node("img"); image.src=media[path]; image.alt=label; figure.append(image);}
    else figure.append(node("p", "参考图不可用", "segment-placeholder"));
    figure.append(node("figcaption", label)); assets.append(figure);
  }
  refs.append(assets); main.append(refs);
  const script = section("完整口播"); script.append(node("p", task.plan.script, "script")); main.append(script);
  const sound = section("主音频", task.audio ? `${task.audio.duration_seconds.toFixed(2)} 秒 · ${task.audio.source === "user" ? "导入配音" : "Drama3 配音"}` : "尚未准备");
  if (task.audio) sound.append(player(task.audio.path, media));
  else if (task.assets.audio) {sound.append(player(task.assets.audio.path, media)); sound.append(node("p", "已绑定录音，尚未由 Skill 导入为主音频。", "subtle"));}
  else if (task.assets.voice) {sound.append(player(task.assets.voice.path, media)); sound.append(node("p", "这是参考声音，尚未生成主音频。", "subtle"));}
  main.append(sound);
  if (task.segments.length) {
    const segments = section("分段审片", "每段先试听，再检查画面与口型");
    for (const segment of task.segments) {
      const card = node("article", null, "segment");
      const heading = node("div", null, "segment-top");
      heading.append(node("h3", `第 ${segment.index+1} 段 · ${segment.mode === "fl-base" ? "基础画面" : "尾帧续接"}`), node("span", `${segment.duration_seconds.toFixed(2)} 秒`, "subtle"));
      card.append(heading, node("p", segment.text, "segment-text"), player(segment.audio, media));
      if (segment.clip) card.append(player(segment.clip, media, "video"));
      else card.append(node("div", "尚无生成视频", "segment-placeholder"));
      if (segment.prompt) card.append(details("查看本段提示词", segment.prompt));
      segments.append(card);
    }
    main.append(segments);
  }
  if (task.final) {
    const final = section("最终成片", task.status === "completed" ? "已审核通过" : "待播放审核");
    final.append(player(task.final.path, media, "video")); main.append(final);
  }
  const logs = section("生成记录", "仅展示本地日志，不查询平台");
  const entries = Object.entries(task.operations);
  if (!entries.length) logs.append(node("p", "尚未提交生成。", "subtle"));
  for (const [key,op] of entries) {
    const entry = node("article", null, "log");
    entry.append(node("strong", key), node("p", ({attempting:"提交结果待核查",submitted:"已提交，待查询",failed:"失败",succeeded:"产物已下载"})[op.status] || op.status));
    entry.append(node("p", op.platform_task_id ? "平台任务 ID："+op.platform_task_id : "尚无平台任务 ID"));
    if (Number.isInteger(op.error_code)) entry.append(node("p", "平台错误码："+op.error_code));
    logs.append(entry);
  }
  main.append(logs);
  const progress = $("#progress"); progress.replaceChildren(node("div", "审核记录", "section-label"));
  const steps = node("ol", null, "steps");
  for (const [stage,label] of [["content","内容与素材"],["audio","完整配音"],["segments","语义分段"],
    ...task.segments.map(s=>[`clip:${s.index}`,`第 ${s.index+1} 段画面`]),["final","最终成片"]]) {
    const record = task.reviews[stage];
    const current = reviewsCurrent[stage] === true;
    const item = node("li", label, current ? "passed" : "");
    item.append(node("small", current ? "当前版本已批准" : (record ? "旧批准已失效" : "尚无批准记录"))); steps.append(item);
  }
  progress.append(steps, node("p", "审核与生成由 Skill 推进。本页按当前对象核对批准记录，不会修改任务。", "env-note"));
}
async function chooseTask(id) {
  const version = ++requestVersion;
  selected = id;
  history.replaceState(null, "", "/?task="+encodeURIComponent(id));
  document.querySelectorAll(".task").forEach(button => button.setAttribute("aria-current", String(button.dataset.id === id)));
  $("#main").replaceChildren(node("p", "正在读取任务…", "empty"));
  try {
    const result = await get("/api/tasks/"+encodeURIComponent(id));
    if (version === requestVersion) renderTask(result.task, result.media, result.reviews_current);
  } catch (error) {if (version === requestVersion) $("#main").replaceChildren(node("p", error.message, "empty"));}
}
async function refresh() {
  $("#refresh").disabled = true; $("#notice").classList.remove("visible");
  try {
    const [tasks, doctor] = await Promise.all([get("/api/tasks"), get("/api/doctor")]);
    const list = $("#tasks"); list.replaceChildren();
    for (const task of tasks) {
      const button = node("button", null, "task"); button.type = "button"; button.dataset.id=task.id;
      button.append(node("strong", task.title), node("small", statuses[task.status] || task.status));
      button.addEventListener("click", ()=>chooseTask(task.id)); list.append(button);
    }
    const env = $("#environment"); env.replaceChildren();
    for (const [label,value] of [["本机 FFmpeg",doctor.ffmpeg ? "可用" : "未找到"],["进程中的 Key",doctor.api_key_present ? "已配置" : "未配置"],
      ["基础流",doctor.workflows["fl-base"].configured ? "已填工作流 ID" : "未配置"],["续接流",doctor.workflows["fl-i2v"].configured ? "已填工作流 ID" : "未配置"]]) {
      const line=node("div",null,"env-line"); line.append(node("span",label),node("span",value)); env.append(line);
    }
    env.append(node("p", "离线检查，不代表账号权限、余额或真实生成已验证。", "env-note"));
    if (tasks.length) await chooseTask(tasks.some(t=>t.id === selected) ? selected : tasks[0].id);
    else {++requestVersion; selected=null; history.replaceState(null,"","/"); $("#progress").replaceChildren(); $("#main").replaceChildren(node("h1","开始一条口播视频"),node("p","还没有本地任务。请让 Skill 使用你的人物图、场景图、产品图和文案创建任务，再刷新这里。","empty"));}
  } catch (error) {notice(error.message);}
  finally {$("#refresh").disabled=false;}
}
$("#refresh").addEventListener("click",refresh);
refresh();

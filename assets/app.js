/* ═══════════════════════════════════════════════════════════
   tonia-checkin-reminder · 页面特效层（三页共用）
   ────────────────────────────────────────────────────────────
     1. 顶部加载进度条（首屏 + 页面跳转）
     2. 页面切换转场幕布（淡出 → 新页淡入，视觉上连成一体）
     3. 内容分段入场（.fx-in 上浮）
     4. 滚动揭示（[data-reveal]）
     5. 数字滚动 / Toast
     6. 吸顶导航（.nav.stuck）
     7. 左侧页内锚点（#px-toc）
     8. 主题切换（跟随系统 / 浅色 / 深色）
     9. 回到顶部（滚动进度环）
    10. 背景粒子（Canvas，环境氛围层）
   ═══════════════════════════════════════════════════════════ */
(function () {
  "use strict";

  var reduce = false;
  try { reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches; } catch (e) {}

  var NAV_FLAG = "tcr:naving";
  var cameFromNav = false;
  try {
    cameFromNav = sessionStorage.getItem(NAV_FLAG) === "1";
    sessionStorage.removeItem(NAV_FLAG);
  } catch (e) {}

  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };

  /* ══ 1. 顶部进度条 ══════════════════════════════════════ */

  var bar = document.createElement("div");
  bar.className = "px-bar";
  bar.innerHTML = "<i></i>";
  document.body.appendChild(bar);
  var barFill = bar.firstChild;
  var barTicks = [];

  function barStart() {
    bar.classList.remove("done");
    bar.classList.add("on");
    barFill.style.width = "0%";
    requestAnimationFrame(function () { barFill.style.width = "38%"; });
    barTicks.push(setTimeout(function () { barFill.style.width = "62%";  }, 220));
    barTicks.push(setTimeout(function () { barFill.style.width = "79%";  }, 720));
    barTicks.push(setTimeout(function () { barFill.style.width = "89%";  }, 1500));
  }

  function barDone() {
    barTicks.forEach(clearTimeout);
    barTicks = [];
    bar.classList.add("done");
    barFill.style.width = "100%";
    setTimeout(function () { bar.classList.remove("on", "done"); }, 320);
  }

  /* ══ 2. 转场幕布 ════════════════════════════════════════ */
  /* 幕布是内联在 <body> 首行的 #px-veil（见各页 HTML），这里只负责开合。
     新页的"显示 → 自动淡出"整条链路走纯 CSS（html.naving + @keyframes veilOut），
     所以即使本文件加载慢了，幕布也一定盖得住首帧、也一定会自己消失。 */

  var veil = document.getElementById("px-veil");

  /** 跳转前：淡入幕布把当前页压住 */
  var navigating = false;

  function veilLeave(href, label) {
    if (navigating) return;
    navigating = true;

    try { sessionStorage.setItem(NAV_FLAG, "1"); } catch (e) {}

    var v = reduce ? null : veil;   // 减弱动效时直接硬跳，不摆幕布
    if (v) {
      var lab = v.querySelector("#px-veil-label");
      if (lab && label) lab.textContent = label;
      // 先 display:flex（此时 opacity 仍是 0），强制 reflow 让 0 成为真实起点
      v.classList.add("show");
      v.getBoundingClientRect();
      v.classList.add("on");            // 真正的淡入动画（.16s），不再瞬间硬切
      var tr = v.querySelector(".px-track i");
      if (tr) {
        tr.style.transition = "none";
        tr.style.width = "10%";
        tr.getBoundingClientRect();
        tr.style.transition = "";
        tr.style.width = "84%";
      }
    }

    // 别让用户等：幕布 .16s 就铺满了，200ms 后就走
    var wait = reduce ? 0 : 200;
    setTimeout(function () { window.location.href = href; }, wait);
    // 兜底：万一被拦截没跳走，重试一次，并把页面还给用户
    setTimeout(function () {
      if (document.visibilityState !== "visible") return;
      window.location.href = href;
      setTimeout(function () {
        if (navigating && veil) { veil.classList.remove("show", "on"); navigating = false; }
      }, 1400);
    }, wait + 900);
  }

  /** 新页落地：幕布已由 CSS 自动淡出，这里只等它退场后解锁页面 */
  function veilEnterAuto() {
    var v = veil;
    if (!v) { document.documentElement.classList.remove("naving"); return; }

    var done = false;
    var finish = function () {
      if (done) return;
      done = true;
      v.classList.remove("show", "on");                              // 先藏幕布
      document.documentElement.classList.remove("naving");            // 再解锁滚动
    };

    var tr = v.querySelector(".px-track i");
    if (tr) tr.style.width = "100%";
    v.addEventListener("animationend", finish, { once: true });
    setTimeout(finish, 1000);   // 兜底：animationend 万一没来，也最多只多挂 .2s
  }

  /* ══ 3/4. 入场与揭示 ════════════════════════════════════ */

  function reveal() {
    var els = $$(".fx-in:not(.is-in), [data-reveal]:not(.is-in)");
    if (!els.length) return;
    if (reduce || !("IntersectionObserver" in window)) {
      els.forEach(function (el) { el.classList.add("is-in"); });
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (!en.isIntersecting) return;
        var el = en.target;
        var sib = el.parentNode ? Array.prototype.indexOf.call(el.parentNode.children, el) : 0;
        el.style.transitionDelay = Math.min(sib, 8) * 55 + "ms";
        el.classList.add("is-in");
        io.unobserve(el);
      });
    }, { rootMargin: "0px 0px -6% 0px", threshold: 0.04 });
    els.forEach(function (el) { io.observe(el); });
    // 兜底：2.6 秒后强制全部显示，避免任何情况下内容被藏住
    setTimeout(function () { $$(".fx-in:not(.is-in), [data-reveal]:not(.is-in)").forEach(function (el) { el.classList.add("is-in"); }); }, 2600);
  }

  function stagger() {
    $$(".stagger").forEach(function (box) {
      $$(":scope > *", box).forEach(function (el, i) {
        el.style.animationDelay = Math.min(i, 14) * 45 + "ms";
      });
    });
  }

  document.documentElement.classList.add("fx-ready");

  /* ══ 5. 工具 ════════════════════════════════════════════ */

  function countUp(el, value, unit, dur) {
    if (!el) return;
    var target = Number(value) || 0;
    var suffix = unit ? "<small>" + unit + "</small>" : "";
    var finish = function () { el.innerHTML = target + suffix; el.classList.remove("counting"); };
    if (reduce) { finish(); return; }
    var t0 = 0, ms = dur || 760;
    el.classList.add("counting");
    requestAnimationFrame(function step(ts) {
      if (!t0) t0 = ts;
      var p = Math.min(1, (ts - t0) / ms);
      var eased = 1 - Math.pow(1 - p, 3);
      el.innerHTML = Math.round(target * eased) + suffix;
      if (p < 1) requestAnimationFrame(step);
      else finish();
    });
    // 兜底：无论 rAF 被怎么节流，到点也一定落到终值
    setTimeout(finish, ms + 260);
  }

  var toastBox = null;
  function toast(msg, kind, ms) {
    if (!toastBox) {
      toastBox = document.createElement("div");
      toastBox.className = "px-toasts";
      document.body.appendChild(toastBox);
    }
    var t = document.createElement("div");
    t.className = "px-toast " + (kind || "");
    t.innerHTML = '<span class="px-toast-ico"></span><span class="px-toast-txt"></span>';
    t.querySelector(".px-toast-txt").textContent = msg;
    toastBox.appendChild(t);
    requestAnimationFrame(function () { t.classList.add("on"); });
    setTimeout(function () {
      t.classList.remove("on");
      setTimeout(function () { t.remove(); }, 380);
    }, ms || 3200);
  }

  function timeAgo(iso) {
    var d = new Date(String(iso).replace(" ", "T"));
    if (isNaN(d.getTime())) return "";
    var s = Math.floor((Date.now() - d.getTime()) / 1000);
    if (s < 60) return "刚刚";
    if (s < 3600) return Math.floor(s / 60) + " 分钟前";
    if (s < 86400) return Math.floor(s / 3600) + " 小时前";
    if (s < 2592000) return Math.floor(s / 86400) + " 天前";
    return "";
  }

  /* ══ 内部跳转拦截 ══════════════════════════════════════ */

  var NAV_TEXT = { "index.html": "正在打开看板", "settings.html": "正在打开设置", "changelog.html": "正在打开更新日志" };

  function isInternal(a) {
    if (!a || a.target === "_blank" || a.hasAttribute("download")) return false;
    var href = a.getAttribute("href");
    if (!href) return false;
    if (/^(https?:|mailto:|tel:|javascript:|data:|#)/i.test(href)) return false;
    if (href.indexOf(".html") === -1) return false;
    return true;
  }

  document.addEventListener("click", function (e) {
    var a = e.target.closest ? e.target.closest("a") : null;
    if (!isInternal(a)) return;
    var href = a.getAttribute("href");
    var here = location.pathname.split("/").pop() || "index.html";
    if (href === here) { e.preventDefault(); return; }
    e.preventDefault();
    try { sessionStorage.setItem(NAV_FLAG, "1"); } catch (err) {}
    var label = NAV_TEXT[href.split("/").pop().split("?")[0].split("#")[0]];
    veilLeave(href, label || "正在跳转");
  });

  /* bfcache 返回时重置状态（内联脚本与 CSS 动画都不会重跑，必须手动清干净） */
  window.addEventListener("pageshow", function (e) {
    if (!e.persisted) return;
    navigating = false;
    document.documentElement.classList.remove("naving");
    if (veil) veil.classList.remove("show", "on");
    bar.classList.remove("on", "done");
    document.documentElement.classList.add("fx-ready");
    window.__fxT = setTimeout(function () { document.documentElement.classList.remove("fx-ready"); }, 1800);
    paintTheme(readMode(), false);   // bfcache 里主题属性可能已过期，对齐一次
    reveal();
  });

  /* ══ 主题切换 ════════════════════════════════════════ */
  /* 三态：auto（跟随系统）/ light / dark。
     data-theme 已由各页 <head> 的内联脚本在首帧前写好，
     这里只负责「用户点按钮之后」的事：切模式、存偏好、放过渡动画。 */

  /** 由 initFx 注入：主题变了要重新给粒子上色 */
  var fxRetint = null;

  var THEME_KEY = "tcr:theme";
  var MODES = ["auto", "light", "dark"];
  var MODE_LABEL = { auto: "跟随系统", light: "浅色", dark: "深色" };
  var mql = null;
  try { mql = window.matchMedia("(prefers-color-scheme: dark)"); } catch (e) {}

  function readMode() {
    try {
      var v = localStorage.getItem(THEME_KEY);
      if (v === "light" || v === "dark" || v === "auto") return v;
    } catch (e) {}
    return "auto";
  }

  function resolveTheme(mode) {
    if (mode === "light" || mode === "dark") return mode;
    return (mql && mql.matches) ? "dark" : "light";
  }

  var themeAnimT = 0;

  /** animate=true 时临时挂 .theme-anim，让颜色平滑过渡（平时不挂，免得拖慢 hover） */
  function paintTheme(mode, animate) {
    var root = document.documentElement;
    var t = resolveTheme(mode);
    if (animate) {
      root.classList.add("theme-anim");
      clearTimeout(themeAnimT);
      themeAnimT = setTimeout(function () { root.classList.remove("theme-anim"); }, 320);
    }
    root.setAttribute("data-theme", t);
    root.setAttribute("data-theme-mode", mode);
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", t === "dark" ? "#0b0f16" : "#f5f7fa");
    if (fxRetint) fxRetint();   // 粒子跟着换配色
  }

  function initTheme() {
    var btn = document.getElementById("theme-btn");
    var mode = readMode();

    function syncBtn() {
      if (!btn) return;
      var tip = "主题：" + MODE_LABEL[mode];
      btn.title = tip;
      btn.setAttribute("aria-label", "切换主题，当前" + MODE_LABEL[mode]);
    }

    if (btn) {
      btn.addEventListener("click", function () {
        mode = MODES[(MODES.indexOf(readMode()) + 1) % MODES.length];
        try { localStorage.setItem(THEME_KEY, mode); } catch (e) {}
        paintTheme(mode, true);
        syncBtn();
        toast("主题：" + MODE_LABEL[mode], "ok", 1800);
      });
    }

    // 系统主题变化 —— 只有 auto 模式才跟着变，手动指定的不被动摇
    if (mql) {
      var onSys = function () { if (readMode() === "auto") paintTheme("auto", true); };
      if (mql.addEventListener) mql.addEventListener("change", onSys);
      else if (mql.addListener) mql.addListener(onSys);
    }

    paintTheme(mode, false);   // 与 head 内联脚本对齐，不重复播动画
    syncBtn();
  }

  /* ══ 吸顶导航 ══════════════════════════════════════════ */
  /* 阈值用「导航的静态文档位置」，不用 getBoundingClientRect().top ——
     吸住时 rect.top 恰好等于 0，拿它判断会在边界上反复抖动。
     测量前先摘掉 .stuck 强制回到静态布局，否则页面若在滚动位置恢复
     （bfcache）时会把 scrollY 当成静态位置，阈值从此永久偏大。 */
  function initNav() {
    var nav = $(".nav");
    if (!nav) return;
    nav.classList.remove("stuck");
    var at = Math.round(nav.getBoundingClientRect().top + window.scrollY);
    var stuck = false;
    var run = function () {
      var v = window.scrollY > at - 1;
      if (v === stuck) return;
      stuck = v;
      nav.classList.toggle("stuck", v);
    };
    window.addEventListener("scroll", run, { passive: true });
    run();
  }

  /* ══ 左侧页内锚点 ══════════════════════════════════════ */
  /* 由 HTML 里带 [data-toc="标题"] 的元素自动生成 ——
     要增删章节只改 HTML，不必回来动这个文件。
     少于 2 个目标就直接摘掉，避免出现「一个孤零零的标题」那种尴尬。 */
  function initToc() {
    var box = document.getElementById("px-toc");
    if (!box) return;

    var targets = $$("[data-toc]");
    if (targets.length < 2) { if (box.parentNode) box.parentNode.removeChild(box); return; }

    var head = document.createElement("div");
    head.className = "px-toc-t";
    head.textContent = box.getAttribute("data-title") || "本页内容";
    box.appendChild(head);

    var items = [];
    targets.forEach(function (el, i) {
      if (!el.id) el.id = "sec-" + (i + 1);
      var a = document.createElement("a");
      a.href = "#" + el.id;
      a.textContent = el.getAttribute("data-toc") || el.textContent.trim().slice(0, 18);
      box.appendChild(a);
      items.push({ a: a, el: el, top: 0 });
    });

    var cur = null;
    function setActive(a) {
      if (cur === a) return;
      if (cur) cur.classList.remove("on");
      cur = a;
      if (a) a.classList.add("on");
    }

    items.forEach(function (it) {
      it.a.addEventListener("click", function (e) {
        e.preventDefault();
        it.el.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
        if (history.replaceState) history.replaceState(null, "", "#" + it.el.id);
        setActive(it.a);      // 立刻点亮，不等滚动结束
      });
    });

    /* 用 offsetTop 累加而不是 getBoundingClientRect()：
       目标里可能有 .fx-in 这种带 transform 的元素（入场时 translateY 未归零），
       rect 会把那十几像素的位移算进去，offsetTop 不受 transform 影响。 */
    function docTop(el) {
      var y = 0;
      while (el) { y += el.offsetTop; el = el.offsetParent; }
      return y;
    }
    var lastH = -1;
    function measure() {
      items.forEach(function (it) { it.top = docTop(it.el); });
      lastH = document.documentElement.scrollHeight;
    }
    function sync() {
      /* 页面高度变了就说明布局变了（数据 fetch 回来、卡片增删…），锚点位置必须
         跟着重测 —— 设置页的提醒列表要等用户点「连接并加载」才渲染，只在启动时
         量一次的话，之后的高亮会一直偏。读一次 scrollHeight 比每次重测便宜得多。 */
      var h = document.documentElement.scrollHeight;
      if (h !== lastH) measure();

      var y = window.scrollY + 104;                 // 让出吸顶导航的高度
      var pick = items[0];
      for (var i = 0; i < items.length; i++) {
        if (items[i].top <= y) pick = items[i]; else break;
      }
      // 末章往往永远越不过那条线（页面到底了它还没到顶部），滚到底强制点亮
      var max = h - window.innerHeight;
      if (max > 0 && window.scrollY >= max - 4) pick = items[items.length - 1];
      setActive(pick.a);
    }

    measure();
    var pend = false;
    window.addEventListener("scroll", function () {
      if (pend) return;
      pend = true;
      requestAnimationFrame(function () { pend = false; sync(); });
    }, { passive: true });
    window.addEventListener("resize", function () { measure(); sync(); });

    // 内容多半是 fetch 之后才渲染的，页面高度会变 —— 多测两次把位置校准回来
    setTimeout(function () { measure(); sync(); }, 700);
    setTimeout(function () { measure(); sync(); }, 1800);
    sync();
  }

  /* ══ 回到顶部（滚动进度环） ══════════════════════════════ */

  /* 环长 = 2πr，r=19 → 119.38。dashoffset 从满到 0 就是 0% → 100%。 */
  var RING = 119.38;

  function initTop() {
    var b = document.createElement("button");
    b.type = "button";
    b.className = "px-top";
    b.setAttribute("aria-label", "回到顶部");
    b.title = "回到顶部";
    b.innerHTML =
      '<svg viewBox="0 0 44 44" aria-hidden="true">' +
        '<circle class="pt-bg" cx="22" cy="22" r="19"/>' +
        '<circle class="pt-fg" cx="22" cy="22" r="19" transform="rotate(-90 22 22)"' +
        ' stroke-dasharray="' + RING + '" stroke-dashoffset="' + RING + '"/>' +
        '<path class="pt-arw" d="M22 29.5V16.5M16.4 22.1 22 16.5l5.6 5.6"/>' +
      '</svg>';
    b.addEventListener("click", function () {
      window.scrollTo({ top: 0, behavior: reduce ? "auto" : "smooth" });
    });
    document.body.appendChild(b);

    var fill = b.querySelector(".pt-fg");

    function onScroll() {
      var y = window.scrollY;
      var max = document.documentElement.scrollHeight - window.innerHeight;
      // 阈值每次都现算：内容晚到会让页面变长，启动时定死的阈值会随之失真
      var showAt = Math.min(460, Math.max(160, max * 0.1));
      b.classList.toggle("on", y > showAt);
      var p = max > 0 ? Math.min(1, y / max) : 0;
      fill.setAttribute("stroke-dashoffset", String(RING * (1 - p)));
    }

    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    onScroll();
  }

  /* ══ 10. 背景粒子 ══════════════════════════════════════ */
  /* 极其克制的环境氛围层 —— 是"桌面空气里的微弱数字尘埃"，不是视觉主体。
     硬约束（改之前先读一遍，很容易不小心把克制改没了）：
       · 数量按视口面积算并封顶 34 个
       · 半径 0.5~1.5px（直径 1~3px），基础透明度 0.08~0.25
       · 速度 ≤ 0.16px/帧，随机方向，越界回绕并在边缘透明度归零
       · 连线只在 112px 内出现，alpha 上限 0.075
       · 配色 6 灰 / 3 蓝 / 1 橙 —— 灰打底，橙只是点缀
       · 文档不可见时停掉 rAF；prefers-reduced-motion 直接不建
       · 帧率封顶 ~33fps：粒子本就慢，60fps 是纯浪费，还会牵着吸顶导航的
         backdrop-filter 每帧重算一遍 */

  var THEME_GRAY = { light: "150,162,180", dark: "150,166,192" };

  function initFx() {
    if (reduce) return;
    var probe = document.createElement("canvas");
    if (!probe.getContext) return;

    var cv = document.createElement("canvas");
    cv.className = "px-fx";
    cv.setAttribute("aria-hidden", "true");
    document.body.appendChild(cv);

    var ctx = cv.getContext("2d");
    if (!ctx) { cv.remove(); return; }

    var DPR = Math.min(2, window.devicePixelRatio || 1);
    var W = 0, H = 0;
    var parts = [];
    var palette = [];
    var LINK = 112;
    var raf = 0, last = 0, resizeT = 0;
    var css = window.getComputedStyle(document.documentElement);

    /* 取色：直接读主题令牌，保证粒子色永远跟着主题令牌走，
       不会出现"主题换了两边色号对不上"。 */
    function readPalette() {
      css = window.getComputedStyle(document.documentElement);
      var acc = (css.getPropertyValue("--accent-rgb") || "").trim() || "232,93,4";
      var blu = (css.getPropertyValue("--blue-rgb") || "").trim() || "79,140,255";
      var gray = THEME_GRAY[document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light"];
      palette = [];
      for (var i = 0; i < 6; i++) palette.push(gray);
      for (var j = 0; j < 3; j++) palette.push(blu);
      palette.push(acc);
    }

    function spawn(i) {
      var ang = Math.random() * Math.PI * 2;
      var sp = 0.05 + Math.random() * 0.11;
      return {
        x: Math.random() * W,
        y: Math.random() * H,
        vx: Math.cos(ang) * sp,
        vy: Math.sin(ang) * sp,
        r: 0.5 + Math.random() * 1.0,
        a: 0.08 + Math.random() * 0.17,
        ph: Math.random() * Math.PI * 2,
        c: palette[i % palette.length]
      };
    }

    function resize() {
      W = window.innerWidth;
      H = window.innerHeight;
      cv.width = Math.round(W * DPR);
      cv.height = Math.round(H * DPR);
      cv.style.width = W + "px";
      cv.style.height = H + "px";
      ctx.setTransform(DPR, 0, 0, DPR, 0, 0);

      var n = Math.min(34, Math.max(14, Math.round(W * H / 46000)));
      if (parts.length > n) parts.length = n;
      while (parts.length < n) parts.push(spawn(parts.length));
    }

    function frame(ts) {
      raf = requestAnimationFrame(frame);
      if (last && ts - last < 30) return;   // 封顶 ~33fps
      last = ts;

      ctx.clearRect(0, 0, W, H);

      var i, j, k, p, q, dx, dy, d2, d, alpha;

      /* 连线：只连近邻，且必须很淡 */
      ctx.lineWidth = 1;
      for (i = 0; i < parts.length; i++) {
        p = parts[i];
        for (j = i + 1; j < parts.length; j++) {
          q = parts[j];
          dx = p.x - q.x; dy = p.y - q.y;
          d2 = dx * dx + dy * dy;
          if (d2 > LINK * LINK) continue;
          d = Math.sqrt(d2) || 1;
          alpha = (1 - d / LINK) * 0.075;
          if (alpha < 0.03) continue;
          ctx.strokeStyle = "rgba(" + p.c + "," + alpha.toFixed(3) + ")";
          ctx.beginPath();
          ctx.moveTo(p.x, p.y);
          ctx.lineTo(q.x, q.y);
          ctx.stroke();
        }
      }

      /* 粒子：先走位，再按"离最近边缘的距离"决定显隐 */
      for (k = 0; k < parts.length; k++) {
        p = parts[k];
        p.x += p.vx;
        p.y += p.vy;
        p.ph += 0.006;
        if (p.x < -6) p.x = W + 6; else if (p.x > W + 6) p.x = -6;
        if (p.y < -6) p.y = H + 6; else if (p.y > H + 6) p.y = -6;

        var edge = Math.min(p.x, W - p.x, p.y, H - p.y);
        if (edge <= 0) continue;
        var fade = edge < 70 ? edge / 70 : 1;
        alpha = p.a * fade * (0.72 + 0.28 * Math.sin(p.ph));
        if (alpha <= 0.005) continue;

        ctx.fillStyle = "rgba(" + p.c + "," + alpha.toFixed(3) + ")";
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, 6.283185307179586);
        ctx.fill();
      }
    }

    function start() {
      if (raf || document.hidden) return;
      last = 0;
      raf = requestAnimationFrame(frame);
    }
    function stop() {
      if (!raf) return;
      cancelAnimationFrame(raf);
      raf = 0;
    }

    readPalette();
    resize();
    start();
    requestAnimationFrame(function () { cv.classList.add("on"); });

    document.addEventListener("visibilitychange", function () {
      if (document.hidden) stop(); else start();
    });
    window.addEventListener("resize", function () {
      clearTimeout(resizeT);
      resizeT = setTimeout(resize, 200);
    });

    /* 主题切换时只换颜色，不重建 —— 重建会在切换瞬间"抖"一下 */
    fxRetint = function () {
      readPalette();
      for (var i = 0; i < parts.length; i++) parts[i].c = palette[i % palette.length];
    };
  }

  /* ══ 启动 ══════════════════════════════════════════════ */

  var booted = false;
  function boot() {
    if (booted) return;
    booted = true;
    if (window.__fxT) { clearTimeout(window.__fxT); }

    if (cameFromNav && !reduce) {
      // 幕布在场、自带进度条 —— 顶部细条就不重复出场了
      veilEnterAuto();
    } else {
      barStart();
      barDone();
    }
    reveal();
    stagger();
    initNav();
    initToc();
    initTop();
    initFx();
    initTheme();
    // 动态内容（fetch 后渲染）再扫一次
    setTimeout(function () { stagger(); reveal(); }, 420);
  }

  // 尽早跑：defer 脚本执行时 DOM 已解析完（readyState = interactive），
  // 不必等 window.load —— 那要等完所有图片/字体，白白让幕布多挂几百毫秒
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();

  window.PFX = {
    reveal: reveal,
    stagger: stagger,
    countUp: countUp,
    toast: toast,
    timeAgo: timeAgo,
    reduce: reduce
  };
})();

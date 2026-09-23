/* ═══════════════════════════════════════════════════════════
   tonia-checkin-reminder · 页面特效层（三页共用）
   ────────────────────────────────────────────────────────────
     1. 顶部加载进度条（首屏 + 页面跳转）
     2. 页面切换转场幕布（淡出 → 新页淡入，视觉上连成一体）
     3. 内容分段入场（.fx-in 上浮）
     4. 滚动揭示（[data-reveal]）
     5. 数字滚动 / Toast / 回到顶部
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
    var at = 38;
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

  var veil = null;

  function buildVeil() {
    if (veil) return veil;
    veil = document.createElement("div");
    veil.className = "px-veil";
    veil.innerHTML =
      '<div class="px-veil-box">' +
        '<div class="px-logo"><img src="assets/icons/avatar-128.png" alt=""><span class="px-ring"></span></div>' +
        '<div class="px-veil-txt"><span id="px-veil-label">正在进入</span><span class="px-dots"><i></i><i></i><i></i></span></div>' +
        '<div class="px-track"><i></i></div>' +
      "</div>";
    document.body.appendChild(veil);
    return veil;
  }

  /** 跳转前：压暗当前页 */
  var navigating = false;

  function veilLeave(href, label) {
    if (navigating) return;
    navigating = true;
    var v = buildVeil();
    var lab = v.querySelector("#px-veil-label");
    if (lab && label) lab.textContent = label;
    v.querySelector(".px-track i").style.width = "0%";
    // 关闭过渡，直接置为不透明，避免闪一帧
    v.style.transition = "none";
    v.classList.add("on");
    v.getBoundingClientRect();
    v.style.transition = "";
    requestAnimationFrame(function () {
      v.querySelector(".px-track i").style.width = "100%";
    });
    var t = reduce ? 0 : 300;
    setTimeout(function () { window.location.href = href; }, t);
    // 兜底：万一被拦截没跳走，重试一次
    setTimeout(function () { if (document.visibilityState === "visible") window.location.href = href; }, t + 900);
  }

  /** 新页落地：幕布已在不透明态，淡出 */
  function veilEnter() {
    var v = buildVeil();
    v.style.transition = "none";
    v.classList.add("on");
    v.querySelector(".px-track i").style.width = "100%";
    v.getBoundingClientRect();
    v.style.transition = "";
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        v.classList.remove("on");
        setTimeout(function () {
          v.style.display = "none";
        }, 420);
      });
    });
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

  /* bfcache 返回时重置状态 */
  window.addEventListener("pageshow", function (e) {
    if (e.persisted) {
      if (veil) { veil.classList.remove("on"); veil.style.display = "none"; }
      bar.classList.remove("on", "done");
      document.documentElement.classList.add("fx-ready");
      reveal();
    }
  });

  /* ══ 回到顶部 ══════════════════════════════════════════ */

  function initTop() {
    var b = document.createElement("button");
    b.className = "px-top";
    b.type = "button";
    b.setAttribute("aria-label", "回到顶部");
    b.innerHTML = "↑";
    b.addEventListener("click", function () { window.scrollTo({ top: 0, behavior: reduce ? "auto" : "smooth" }); });
    document.body.appendChild(b);
    var onScroll = function () { b.classList.toggle("on", window.scrollY > 460); };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  /* ══ 启动 ══════════════════════════════════════════════ */

  if (document.readyState === "loading") barStart();
  else barStart();

  var booted = false;
  function boot() {
    if (booted) return;
    booted = true;
    if (window.__fxT) { clearTimeout(window.__fxT); }
    if (cameFromNav && !reduce) {
      veilEnter();
      setTimeout(function () { barDone(); }, 240);
    } else {
      barDone();
    }
    reveal();
    stagger();
    initTop();
    // 动态内容（fetch 后渲染）再扫一次
    setTimeout(function () { stagger(); reveal(); }, 420);
  }

  window.addEventListener("load", boot);
  if (document.readyState === "complete") boot();

  window.PFX = {
    reveal: reveal,
    stagger: stagger,
    countUp: countUp,
    toast: toast,
    timeAgo: timeAgo,
    reduce: reduce
  };
})();

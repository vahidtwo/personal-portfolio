(function () {
  const ASSET_COLORS = {
    gold: "#f59e0b",
    coin_emami: "#d97706",
    coin_bahar: "#fbbf24",
    coin_half: "#b45309",
    coin_quarter: "#fcd34d",
    coin_gram: "#92400e",
    silver: "#cbd5e1",
    btc: "#f97316",
    ada: "#3b82f6",
    eth: "#8b5cf6",
    sol: "#14b8a6",
    doge: "#eab308",
    matic: "#a855f7",
    usd: "#22c55e",
    cash: "#38bdf8",
    car: "#94a3b8",
    total: "#3ee0b8",
  };

  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  const FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹";

  function toPersianDigits(text) {
    return String(text).replace(/\d/g, (d) => FA_DIGITS[d]);
  }

  // Canvas text must use the page font: the browser's default canvas font draws the
  // Persian thousands separator «٬» like an apostrophe («۱'۱۲۰»).
  const APP_FONT = 'Vazirmatn, Tahoma, "Segoe UI", sans-serif';
  function useAppFont() {
    if (window.Chart && Chart.defaults && Chart.defaults.font) Chart.defaults.font.family = APP_FONT;
  }

  // Shared display formatter (number-format.js, mirrors Python format_number).
  const fmtNum = (v, d) => window.NumberFa.format(v, d);

  function axisLabelDecimals(step, divisor) {
    const unit = step / divisor;
    if (unit >= 1) return 0;
    if (unit >= 0.1) return 1;
    if (unit >= 0.01) return 2;
    if (unit >= 0.001) return 3;
    return 4;
  }

  /** Display unit for a toman series: «میلیون تومان» for big numbers (no Latin M/K/B suffix). */
  function axisUnit(maxAbs) {
    if (maxAbs >= 1e6) return { divisor: 1e6, label: "میلیون تومان" };
    if (maxAbs >= 1e3) return { divisor: 1e3, label: "هزار تومان" };
    return { divisor: 1, label: "تومان" };
  }

  function dataMinMaxFromDatasets(datasets) {
    let min = Infinity;
    let max = -Infinity;
    for (const ds of datasets) {
      for (const v of ds.data || []) {
        const n = Number(v && typeof v === "object" ? v.y : v);
        if (Number.isFinite(n)) {
          if (n < min) min = n;
          if (n > max) max = n;
        }
      }
    }
    if (!Number.isFinite(min) || !Number.isFinite(max)) {
      return { min: 0, max: 1 };
    }
    return { min, max };
  }

  /** Nice-number axis bounds so Y zooms to the data (not 0..max). */
  function buildYAxisScale(dataMin, dataMax, targetTicks, unit) {
    const ticks = targetTicks || 5;
    const dataSpan = Math.max(dataMax - dataMin, 0);
    let lo = dataMin;
    let hi = dataMax;
    if (lo === hi) {
      const margin = lo === 0 ? 1 : Math.abs(lo) * 0.04;
      lo -= margin;
      hi += margin;
    } else {
      const pad = dataSpan * 0.06;
      lo -= pad;
      hi += pad;
    }
    const step = niceAxisStep((hi - lo) / Math.max(ticks - 1, 1), true);
    const axisMin = Math.floor(lo / step) * step;
    const axisMax = Math.ceil(hi / step) * step;
    const decimals = axisLabelDecimals(step, unit.divisor);
    const formatTick = (v) => fmtNum(v / unit.divisor, decimals);
    return { min: axisMin, max: axisMax, stepSize: step, formatTick };
  }

  function niceAxisStep(range, roundUp) {
    if (!Number.isFinite(range) || range <= 0) return 1;
    const exp = Math.floor(Math.log10(range));
    const f = range / Math.pow(10, exp);
    let nf;
    if (roundUp) {
      if (f < 1.5) nf = 1;
      else if (f < 3) nf = 2;
      else if (f < 7) nf = 5;
      else nf = 10;
    } else if (f <= 1) nf = 1;
    else if (f <= 2) nf = 2;
    else if (f <= 5) nf = 5;
    else nf = 10;
    return nf * Math.pow(10, exp);
  }

  function formatToman(v) {
    if (v == null || Number.isNaN(v)) return "—";
    return fmtNum(v, 0) + " تومان";
  }

  /** Percent change vs previous point in the same series. */
  function formatChangeFromPrevious(current, previous) {
    if (
      previous == null ||
      Number.isNaN(previous) ||
      Number.isNaN(current)
    ) {
      return null;
    }
    if (previous === 0) {
      if (current === 0) {
        return toPersianDigits("0") + "٪";
      }
      return null;
    }
    const pct = ((current - previous) / Math.abs(previous)) * 100;
    const body = fmtNum(Math.abs(pct), 2);
    let sign = "";
    if (pct > 0) sign = "+";
    else if (pct < 0) sign = "−";
    return sign + body + "٪";
  }

  function changeLabelForPoint(ctx) {
    const idx = ctx.dataIndex;
    if (idx <= 0) {
      return "تغییر نسبت به قبل: —";
    }
    const series = ctx.dataset.data;
    const current = ctx.parsed.y;
    const prevPoint = series[idx - 1];
    const previous = Number(prevPoint && typeof prevPoint === "object" ? prevPoint.y : prevPoint);
    const change = formatChangeFromPrevious(current, previous);
    if (change == null) {
      return "تغییر نسبت به قبل: —";
    }
    return "تغییر نسبت به قبل: " + change;
  }

  let pieChartInited = false;

  function initPieChart() {
    if (pieChartInited) return;
    const el = document.getElementById("pie-data");
    const canvas = document.getElementById("allocation-chart");
    if (!el || !canvas || typeof Chart === "undefined") return;

    let payload = { slices: [] };
    try {
      payload = JSON.parse(el.textContent || "{}");
    } catch (_) {
      payload = { slices: [] };
    }

    const slices = payload.slices || [];
    if (!slices.length) return;

    const surface = cssVar("--surface") || "#181d27";
    const text = cssVar("--text") || "#eef1f6";
    const border = cssVar("--border") || "#2a3140";

    const labels = slices.map((s) => s.label);
    const data = slices.map((s) => Number(s.value));
    const colors = slices.map((s) => s.color || ASSET_COLORS[s.key] || "#9aa3b2");

    pieChartInited = true;
    new Chart(canvas, {
      type: "doughnut",
      data: {
        labels,
        datasets: [
          {
            data,
            backgroundColor: colors,
            borderColor: cssVar("--bg-elevated") || surface,
            borderWidth: 2,
            hoverOffset: 6,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "72%",
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: surface,
            titleColor: text,
            bodyColor: text,
            borderColor: border,
            borderWidth: 1,
            padding: 12,
            usePointStyle: true,
            callbacks: {
              label: function (ctx) {
                const slice = slices[ctx.dataIndex];
                if (!slice) return "";
                return (
                  slice.value_label +
                  " · " +
                  slice.share_label +
                  "٪"
                );
              },
            },
          },
        },
      },
    });
  }

  function registerZoomPlugin() {
    if (typeof Chart === "undefined") return false;
    const zoomPlugin = window.ChartZoom;
    if (!zoomPlugin) return false;
    if (!Chart.registry.plugins.get("zoom")) {
      Chart.register(zoomPlugin);
    }
    return Chart.registry.plugins.get("zoom") != null;
  }

  function singleSeriesDataset(row, color, fill) {
    const many = (row.data?.length || 0) > 49;
    const data = row.data.map((v) => Number(v));
    return {
      label: row.label,
      data,
      borderColor: color,
      backgroundColor: fill,
      fill: true,
      tension: 0.3,
      borderWidth: 2.5,
      hoverBorderWidth: 4,
      pointRadius: data.map((_, i) => (i === data.length - 1 ? 5 : many ? 3 : 4)),
      pointHitRadius: 28,
      pointHoverRadius: 8,
      pointBackgroundColor: color,
      pointBorderColor: cssVar("--surface") || "#fff",
      pointBorderWidth: 2,
    };
  }

  function buildDatasets(series, seriesKey) {
    const accent = cssVar("--accent") || ASSET_COLORS.total;
    const fill = cssVar("--chart-fill") || "rgba(62, 224, 184, 0.12)";
    const key = seriesKey || "total";
    const row = series.find((s) => s.key === key);
    if (!row) return [];

    if (key === "total") {
      return [singleSeriesDataset(row, accent, fill)];
    }

    const color = ASSET_COLORS[key] || accent;
    const assetFill = color.length === 7 ? color + "22" : fill;
    return [singleSeriesDataset(row, color, assetFill)];
  }

  // Jalali day / time labels in Tehran time for the time axis (Persian digits).
  const DAY_FMT = new Intl.DateTimeFormat("fa-IR-u-ca-persian", { timeZone: "Asia/Tehran", day: "numeric", month: "long" });
  const TIME_FMT = new Intl.DateTimeFormat("fa-IR-u-ca-persian", { timeZone: "Asia/Tehran", hour: "2-digit", minute: "2-digit", hour12: false });
  const DAY_MS = 86400000;

  /** A few evenly spaced time ticks (width-based) with de-duplicated labels, so they never overlap. */
  function timeTicks(first, last, width, nowMs) {
    const slots = Math.max(2, Math.floor((width || 320) / 96));
    const short = last - first <= 2 * DAY_MS;
    const today = DAY_FMT.format(nowMs);
    const out = [];
    let prev = null;
    for (let i = 0; i < slots; i++) {
      const v = first + ((last - first) * i) / Math.max(slots - 1, 1);
      let label = short ? TIME_FMT.format(v) : DAY_FMT.format(v);
      if (!short && label === today) label = "امروز";
      if (label === prev) continue;
      prev = label;
      out.push({ value: v, label });
    }
    return out;
  }

  function chartOptions(view, opts) {
    const { labels, datasets, unit, first, last, nowMs } = view;
    const { rangeSelect, zoomOn, height } = opts;
    const muted = cssVar("--text-muted") || "#9aa3b2";
    const grid = cssVar("--chart-grid") || "rgba(255,255,255,0.06)";
    const extent = dataMinMaxFromDatasets(datasets || []);
    const targetTicks = Math.max(3, Math.min(6, Math.floor((height || 220) / 55)));
    const yScale = buildYAxisScale(extent.min, extent.max, targetTicks, unit);
    const surface = cssVar("--surface") || "#181d27";
    const text = cssVar("--text") || "#eef1f6";
    const border = cssVar("--border") || "#2a3140";

    const plugins = {
      legend: { display: false },
      tooltip: {
        enabled: !rangeSelect,
        position: "nearest",
        rtl: true,
        backgroundColor: surface,
        titleColor: text,
        bodyColor: text,
        borderColor: border,
        borderWidth: 1,
        padding: 12,
        boxPadding: 6,
        displayColors: true,
        usePointStyle: true,
        titleFont: { size: 13, weight: "600" },
        bodyFont: { size: 12 },
        callbacks: {
          title: function (items) {
            if (!items.length) return "";
            return labels[items[0].dataIndex] ?? "";
          },
          label: function (ctx) {
            const v = ctx.parsed.y;
            if (v == null || Number.isNaN(v)) return null;
            return (ctx.dataset.label || "") + ": " + formatToman(v);
          },
          afterLabel: function (ctx) {
            const v = ctx.parsed.y;
            if (v == null || Number.isNaN(v)) return null;
            return changeLabelForPoint(ctx);
          },
        },
      },
      // Zoom/pan only in full screen; on the page the wheel and touch scroll the page.
      zoom: zoomOn
        ? {
            limits: { x: { min: "original", max: "original", minRange: 3600000 } },
            pan: { enabled: !rangeSelect, mode: "x" },
            zoom: {
              wheel: { enabled: !rangeSelect, speed: 0.1 },
              pinch: { enabled: !rangeSelect },
              drag: {
                enabled: rangeSelect,
                backgroundColor: "rgba(62, 224, 184, 0.15)",
                borderColor: "rgba(62, 224, 184, 0.6)",
                borderWidth: 1,
                threshold: 4,
              },
              mode: "x",
            },
          }
        : {
            pan: { enabled: false },
            zoom: { wheel: { enabled: false }, pinch: { enabled: false }, drag: { enabled: false } },
          },
    };

    return {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      events: ["mousemove", "mouseout", "click", "touchstart", "touchmove", "touchend"],
      layout: { padding: { top: 8, right: 14, bottom: 0, left: 4 } },
      interaction: { mode: "index", intersect: false, axis: "x", includeInvisible: true },
      elements: { point: { hitRadius: 28, hoverRadius: 7 }, line: { borderWidth: 2 } },
      plugins,
      scales: {
        x: {
          type: "linear",
          reverse: false,
          min: first,
          max: last,
          // Real time axis: older history is one point a day, the last week is hourly.
          afterBuildTicks: function (scale) {
            const lo = Number.isFinite(scale.min) ? scale.min : first;
            const hi = Number.isFinite(scale.max) ? scale.max : last;
            const ticks = timeTicks(lo, hi, scale.width || scale.chart.width, nowMs);
            scale._phase2Labels = new Map(ticks.map((t) => [t.value, t.label]));
            scale.ticks = ticks.map((t) => ({ value: t.value }));
          },
          ticks: {
            autoSkip: false,
            align: "inner", // first/last labels stay inside the plot instead of clipping
            maxRotation: 0,
            minRotation: 0,
            color: muted,
            font: { size: 11.5 },
            padding: 6,
            callback: function (value) {
              return (this._phase2Labels && this._phase2Labels.get(value)) || "";
            },
          },
          grid: { display: false },
          border: { display: false },
        },
        y: {
          min: yScale.min,
          max: yScale.max,
          beginAtZero: false,
          ticks: {
            color: muted,
            font: { size: 11.5, weight: "500" },
            stepSize: yScale.stepSize,
            autoSkip: true,
            autoSkipPadding: 12,
            callback: yScale.formatTick,
            padding: 8,
          },
          grid: { color: grid, drawBorder: false },
          border: { display: false },
        },
      },
    };
  }

  const RANGE_CHANGE_LABEL = { "7": "این هفته", "30": "این ماه", "90": "۳ ماه", "365": "این سال", all: "کل دوره" };

  function init() {
    const el = document.getElementById("chart-data");
    const canvas = document.getElementById("timeline-chart");
    const chartWrap = canvas?.closest(".chart-wrap");
    const panel = document.getElementById("chart-panel");
    const assetSelect = document.getElementById("chart-asset-select");
    const zoomBtns = document.querySelectorAll("[data-zoom]");
    const rangeBtn = document.getElementById("chart-range-btn");
    const fullscreenBtn = document.getElementById("chart-fullscreen");
    const rangeBtns = document.querySelectorAll("#chart-range [data-range]");
    const unitEl = document.getElementById("chart-unit");
    const foot = document.getElementById("chart-foot");

    if (!el || !canvas || typeof Chart === "undefined") {
      return false;
    }

    const zoomAvailable = registerZoomPlugin();
    if (!zoomAvailable) {
      console.warn("chartjs-plugin-zoom not loaded; zoom/range disabled");
    }

    let payload = { labels: [], series: [] };
    try {
      payload = JSON.parse(el.textContent || "{}");
    } catch (_) {
      payload = { labels: [], series: [] };
    }

    const labels = payload.labels || [];
    const times = payload.times || [];
    const nowMs = payload.now || (times.length ? times[times.length - 1] : Date.now());
    const series = payload.series || [];
    // Arabi: one point per Tehran day for week/month/3-month, one per week for year/all (server-bucketed).
    const weekly = payload.weekly && (payload.weekly.times || []).length >= 2 ? payload.weekly : null;
    function src() {
      if (weekly && (range === "365" || range === "all")) return weekly;
      return { labels, times, series };
    }
    const assetOptions = payload.assetOptions || [];
    // A single point is not a trend: show the empty state until there are 2+ points.
    if ((labels.length < 2 && !weekly) || !series.length) {
      chartWrap?.classList.add("hidden");
      panel?.classList.add("is-empty");
      const empty = document.getElementById("chart-empty");
      if (empty) empty.hidden = false;
      return true;
    }

    if (assetSelect && assetSelect.options.length === 0 && assetOptions.length) {
      assetOptions.forEach((opt) => {
        const o = document.createElement("option");
        o.value = opt.key;
        o.textContent = opt.label || opt.name_fa || opt.key;
        assetSelect.appendChild(o);
      });
      assetSelect.disabled = false;
    }

    let chart = null;
    let seriesKey = assetSelect?.value || "total";
    let rangeSelect = false;
    let fullscreen = false;
    let range = (document.querySelector('#chart-range [aria-pressed="true"]') || {}).dataset?.range || "30";
    const fsIconOpen = fullscreenBtn ? fullscreenBtn.innerHTML : "";
    const fsIconClose =
      '<svg class="ui-icon" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>';

    /** First index inside the selected range (Tehran "now" comes from the server). */
    function rangeStart() {
      const times = src().times;
      if (range === "all" || !times.length) return 0;
      const cutoff = nowMs - Number(range) * 86400000;
      let start = times.findIndex((t) => t >= cutoff);
      if (start < 0) start = times.length - 1;
      return Math.max(0, Math.min(start, times.length - 2)); // keep at least two points
    }

    function currentView() {
      const start = rangeStart();
      const { labels, times, series } = src();
      const full = buildDatasets(series, seriesKey);
      const xs = times.slice(start);
      const datasets = full.map((ds) => {
        const data = ds.data.slice(start).map((y, i) => ({ x: xs[i], y }));
        const many = data.length > 49;
        return Object.assign({}, ds, {
          data,
          pointRadius: data.map((_, i) => (i === data.length - 1 ? 5 : many ? 0 : 3)),
        });
      });
      const extent = dataMinMaxFromDatasets(datasets);
      const unit = axisUnit(Math.max(Math.abs(extent.min), Math.abs(extent.max)));
      return { labels: labels.slice(start), datasets, unit, first: xs[0], last: xs[xs.length - 1], nowMs };
    }

    function updateFoot(view) {
      if (!foot) return;
      const data = ((view.datasets[0] && view.datasets[0].data) || []).map((p) => p.y);
      if (data.length < 2) {
        foot.hidden = true;
        return;
      }
      const max = Math.max(...data);
      const min = Math.min(...data);
      const first = data[0];
      const last = data[data.length - 1];
      const d = view.unit.divisor;
      document.getElementById("chart-max").textContent = fmtNum(max / d, d === 1 ? 0 : 1);
      document.getElementById("chart-min").textContent = fmtNum(min / d, d === 1 ? 0 : 1);
      const changeEl = document.getElementById("chart-change");
      const label = document.getElementById("chart-change-label");
      if (label) label.textContent = RANGE_CHANGE_LABEL[range] || "";
      changeEl.classList.remove("is-up", "is-down");
      if (first === 0) {
        changeEl.textContent = "—";
      } else {
        const pct = ((last - first) / Math.abs(first)) * 100;
        const rounded = Math.round(pct * 10) / 10;
        if (rounded > 0) {
          changeEl.textContent = "▲ " + fmtNum(rounded, 1) + "٪";
          changeEl.classList.add("is-up");
        } else if (rounded < 0) {
          changeEl.textContent = "▼ " + fmtNum(-rounded, 1) + "٪";
          changeEl.classList.add("is-down");
        } else {
          changeEl.textContent = "۰٪";
        }
      }
      foot.hidden = false;
    }

    function renderChart() {
      const view = currentView();
      if (!view.datasets.length) return;
      if (unitEl) unitEl.textContent = view.unit.label;
      updateFoot(view);
      if (chart) chart.destroy();
      chart = new Chart(canvas, {
        type: "line",
        data: { datasets: view.datasets },
        options: chartOptions(view, {
          rangeSelect,
          zoomOn: zoomAvailable && fullscreen,
          height: chartWrap ? chartWrap.clientHeight : 220,
        }),
      });
    }

    function onSeriesChange() {
      if (!assetSelect || assetSelect.disabled) return;
      seriesKey = assetSelect.value || "total";
      renderChart();
    }

    function setRange(next) {
      range = next;
      rangeBtns.forEach((btn) => {
        const on = btn.dataset.range === next;
        btn.classList.toggle("on", on);
        btn.setAttribute("aria-pressed", on ? "true" : "false");
      });
      renderChart();
    }

    function setRangeMode(on) {
      rangeSelect = on;
      rangeBtn?.classList.toggle("is-active", on);
      rangeBtn?.setAttribute("aria-pressed", on ? "true" : "false");
      chartWrap?.classList.toggle("is-range-mode", on);
      renderChart();
    }

    function zoomChart(action) {
      if (!fullscreen || !chart || typeof chart.resetZoom !== "function") return;
      if (action === "reset") {
        chart.resetZoom();
        return;
      }
      if (typeof chart.zoomScale !== "function") return;
      const factor = action === "in" ? 1.25 : 0.8;
      chart.zoomScale("x", { factor, center: "center" });
    }

    function setFullscreen(on) {
      if (fullscreen === on) return;
      fullscreen = on;
      if (!on) {
        rangeSelect = false;
        rangeBtn?.classList.remove("is-active");
        rangeBtn?.setAttribute("aria-pressed", "false");
        chartWrap?.classList.remove("is-range-mode");
      }
      panel.classList.toggle("is-fullscreen", on);
      document.documentElement.classList.toggle("chart-fs-open", on);
      if (fullscreenBtn) {
        fullscreenBtn.innerHTML = on ? fsIconClose : fsIconOpen;
        fullscreenBtn.setAttribute("aria-label", on ? "خروج از تمام‌صفحه" : "تمام‌صفحه");
        fullscreenBtn.title = on ? "خروج از تمام‌صفحه" : "تمام‌صفحه";
      }
      window.requestAnimationFrame(renderChart);
    }

    rangeBtns.forEach((btn) => {
      btn.addEventListener("click", function () {
        setRange(btn.dataset.range);
      });
    });

    rangeBtn?.addEventListener("click", function () {
      if (fullscreen) setRangeMode(!rangeSelect);
    });

    zoomBtns.forEach((btn) => {
      btn.addEventListener("click", function () {
        if (rangeSelect) setRangeMode(false);
        zoomChart(btn.dataset.zoom);
      });
    });

    if (fullscreenBtn && panel) {
      fullscreenBtn.addEventListener("click", function () {
        if (!fullscreen) {
          // Real full screen where the browser allows it; a fixed overlay otherwise (iPhone).
          if (panel.requestFullscreen && document.fullscreenEnabled) {
            panel.requestFullscreen().catch(() => setFullscreen(true));
          } else {
            setFullscreen(true);
          }
        } else if (document.fullscreenElement) {
          document.exitFullscreen?.();
        } else {
          setFullscreen(false);
        }
      });
      document.addEventListener("fullscreenchange", function () {
        setFullscreen(document.fullscreenElement === panel);
      });
      document.addEventListener("keydown", function (e) {
        if (e.key === "Escape" && fullscreen && !document.fullscreenElement) setFullscreen(false);
      });
    }

    assetSelect?.addEventListener("change", onSeriesChange);
    assetSelect?.addEventListener("input", onSeriesChange);

    renderChart();
    // Re-draw once Vazirmatn has loaded (font-display: swap), so axis/tooltip digits match.
    if (document.fonts && document.fonts.load) {
      Promise.all([document.fonts.load('12px Vazirmatn', "۱٬۲۳۴٫۵"), document.fonts.ready])
        .then(() => renderChart())
        .catch(() => {});
    }
    return true;
  }

  // Home v2: skeleton if the chart isn't drawn within 1s; a retry message if Chart.js never loads.
  let chartSkelTimer = null;
  function chartHolder() {
    const canvas = document.getElementById("timeline-chart");
    return canvas ? canvas.parentElement : null;
  }
  function clearChartPlaceholders() {
    if (chartSkelTimer) { window.clearTimeout(chartSkelTimer); chartSkelTimer = null; }
    document.querySelectorAll("#chart-panel .v2-chart-skel, #chart-panel .v2-chart-msg").forEach((n) => n.remove());
    const holder = chartHolder();
    if (holder) holder.classList.remove("v2-hide");
  }
  function showChartSkeleton() {
    const holder = chartHolder();
    if (!holder || document.querySelector("#chart-panel .v2-chart-skel")) return;
    holder.classList.add("v2-hide");
    const sk = document.createElement("div");
    sk.className = "v2-skel v2-chart-skel";
    sk.setAttribute("aria-hidden", "true");
    holder.after(sk);
  }
  function showChartFailed() {
    const holder = chartHolder();
    if (!holder) return;
    clearChartPlaceholders();
    holder.classList.add("v2-hide");
    const foot = document.getElementById("chart-foot");
    if (foot) foot.hidden = true;
    const msg = document.createElement("div");
    msg.className = "v2-chart-msg";
    msg.setAttribute("role", "status");
    msg.innerHTML = '<span>نمودار باز نشد. اینترنت را بررسی کنید و دوباره امتحان کنید.</span><button class="btn btn-ghost" type="button">تلاش دوباره</button>';
    msg.querySelector("button").addEventListener("click", () => {
      msg.remove();
      showChartSkeleton();
      const s = document.createElement("script");
      s.src = "/static/vendor/chart.umd.min.js?retry=" + Date.now();
      s.onload = () => boot(25);
      s.onerror = () => showChartFailed();
      document.head.appendChild(s);
    });
    holder.after(msg);
  }

  function boot(retries) {
    useAppFont();
    if (chartSkelTimer === null && chartHolder() && document.getElementById("chart-data")) {
      chartSkelTimer = window.setTimeout(showChartSkeleton, 1000);
    }
    const timelineOk = init();
    initPieChart();
    if (timelineOk) { clearChartPlaceholders(); return; }
    if (retries > 0) {
      window.setTimeout(() => boot(retries - 1), 80);
    } else if (typeof Chart === "undefined") {
      showChartFailed();
    } else {
      clearChartPlaceholders();
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => boot(25));
  } else {
    boot(25);
  }
})();

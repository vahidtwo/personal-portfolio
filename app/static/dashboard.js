(function () {
  const ASSET_COLORS = {
    gold: "#f59e0b",
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

  function formatAxisCompact(v, divisor, suffix, decimals) {
    const n = v / divisor;
    let raw;
    if (decimals > 0) {
      raw = n.toFixed(decimals);
      raw = raw.replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "");
    } else {
      raw = String(Math.round(n));
    }
    return toPersianDigits(raw) + suffix;
  }

  function dataMinMaxFromDatasets(datasets) {
    let min = Infinity;
    let max = -Infinity;
    for (const ds of datasets) {
      for (const v of ds.data || []) {
        const n = Number(v);
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
  function buildYAxisScale(dataMin, dataMax, targetTicks) {
    const ticks = targetTicks || 6;
    let lo = dataMin;
    let hi = dataMax;
    if (lo === hi) {
      const margin = lo === 0 ? 1 : Math.abs(lo) * 0.06;
      lo -= margin;
      hi += margin;
    } else {
      const span = hi - lo;
      const pad = span * 0.06;
      lo -= pad;
      hi += pad;
    }

    const roughRange = hi - lo;
    const range = niceAxisStep(roughRange, false);
    const step = niceAxisStep(range / Math.max(ticks - 1, 1), true);
    const axisMin = Math.floor(lo / step) * step;
    const axisMax = Math.ceil(hi / step) * step;
    const formatTick = makeAxisTickFormatter(step, axisMax);
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

  function makeAxisTickFormatter(step, axisMax) {
    const ref = Math.max(Math.abs(axisMax), Math.abs(step));
    if (ref >= 1e9) {
      const decimals =
        step < 5e6 ? 3 : step < 2e7 ? 2 : step < 1e8 ? 1 : 0;
      return (v) => formatAxisCompact(v, 1e9, "B", decimals);
    }
    if (ref >= 1e6) {
      const decimals = step < 5e3 ? 2 : step < 5e4 ? 1 : 0;
      return (v) => formatAxisCompact(v, 1e6, "M", decimals);
    }
    if (ref >= 1e3) {
      const decimals = step < 50 ? 1 : 0;
      return (v) => formatAxisCompact(v, 1e3, "K", decimals);
    }
    const decimals = step < 1 ? 2 : step < 10 ? 1 : 0;
    return (v) => formatAxisCompact(v, 1, "", decimals);
  }

  function formatToman(v) {
    if (v == null || Number.isNaN(v)) return "—";
    const grouped = Math.round(v)
      .toLocaleString("en-US")
      .replace(/,/g, "٬");
    return toPersianDigits(grouped) + " تومان";
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
    const abs = Math.abs(pct);
    const body =
      abs >= 100 ? abs.toFixed(0) : abs.toFixed(1).replace(/\.0$/, "");
    let sign = "";
    if (pct > 0) sign = "+";
    else if (pct < 0) sign = "−";
    return sign + toPersianDigits(body) + "٪";
  }

  function changeLabelForPoint(ctx) {
    const idx = ctx.dataIndex;
    if (idx <= 0) {
      return "تغییر نسبت به قبل: —";
    }
    const series = ctx.dataset.data;
    const current = ctx.parsed.y;
    const previous = Number(series[idx - 1]);
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

    const muted = cssVar("--text-muted") || "#9aa3b2";
    const surface = cssVar("--surface") || "#181d27";
    const text = cssVar("--text") || "#eef1f6";
    const border = cssVar("--border") || "#2a3140";

    const labels = slices.map((s) => s.label);
    const data = slices.map((s) => Number(s.value));
    const colors = slices.map((s) => ASSET_COLORS[s.key] || "#9aa3b2");

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
        cutout: "58%",
        plugins: {
          legend: {
            position: "bottom",
            rtl: true,
            labels: {
              boxWidth: 12,
              boxHeight: 12,
              padding: 14,
              usePointStyle: true,
              color: muted,
              font: { size: 12, weight: "500" },
            },
          },
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

  function buildDatasets(mode, series, assetKey) {
    const accent = cssVar("--accent") || ASSET_COLORS.total;
    const fill = cssVar("--chart-fill") || "rgba(62, 224, 184, 0.12)";

    if (mode === "total") {
      const row = series.find((s) => s.key === "total");
      if (!row) return [];
      return [singleSeriesDataset(row, accent, fill)];
    }

    if (mode === "asset" && assetKey) {
      const row = series.find((s) => s.key === assetKey);
      if (!row) return [];
      const color = ASSET_COLORS[assetKey] || accent;
      const assetFill = color.length === 7 ? color + "22" : fill;
      return [singleSeriesDataset(row, color, assetFill)];
    }

    return [];
  }

  function chartOptions(mode, labels, rangeSelect, zoomEnabled, datasets) {
    const muted = cssVar("--text-muted") || "#9aa3b2";
    const grid = cssVar("--chart-grid") || "rgba(255,255,255,0.06)";
    const extent = dataMinMaxFromDatasets(datasets || []);
    const yScale = buildYAxisScale(extent.min, extent.max, 6);
    const surface = cssVar("--surface") || "#181d27";
    const text = cssVar("--text") || "#eef1f6";
    const border = cssVar("--border") || "#2a3140";

    const plugins = {
      legend: {
        display: false,
        position: "bottom",
        rtl: true,
        labels: {
          boxWidth: 12,
          boxHeight: 12,
          padding: 16,
          usePointStyle: true,
          color: muted,
          font: { size: 12, weight: "500" },
        },
      },
      tooltip: {
        enabled: !rangeSelect,
        position: "nearest",
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
            const idx = items[0].dataIndex;
            return labels[idx] ?? "";
          },
          label: function (ctx) {
            const name = ctx.dataset.label || "";
            const v = ctx.parsed.y;
            if (v == null || Number.isNaN(v)) return null;
            return name + ": " + formatToman(v);
          },
          afterLabel: function (ctx) {
            const v = ctx.parsed.y;
            if (v == null || Number.isNaN(v)) return null;
            return changeLabelForPoint(ctx);
          },
        },
      },
    };

    if (zoomEnabled) {
      plugins.zoom = {
        limits: {
          x: { minRange: 1 },
        },
        pan: {
          enabled: true,
          mode: "x",
          modifierKey: "shift",
        },
        zoom: {
          wheel: {
            enabled: !rangeSelect,
            speed: 0.1,
          },
          pinch: {
            enabled: !rangeSelect,
          },
          drag: {
            enabled: rangeSelect,
            backgroundColor: "rgba(62, 224, 184, 0.15)",
            borderColor: "rgba(62, 224, 184, 0.6)",
            borderWidth: 1,
            threshold: 4,
          },
          mode: "x",
        },
      };
    }

    return {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      events: ["mousemove", "mouseout", "click", "touchstart", "touchmove", "touchend"],
      layout: { padding: { top: 8, right: 12, bottom: 4, left: 4 } },
      interaction: {
        mode: "index",
        intersect: false,
        axis: "x",
        includeInvisible: true,
      },
      elements: {
        point: {
          hitRadius: 28,
          hoverRadius: 7,
        },
        line: {
          borderWidth: 2,
        },
      },
      plugins,
      scales: {
        x: {
          reverse: false,
          title: {
            display: true,
            text: "تاریخ و زمان (شمسی)",
            color: muted,
            font: { size: 12, weight: "500" },
            padding: { top: 8 },
          },
          ticks: {
            maxRotation: 40,
            minRotation: 0,
            autoSkip: true,
            maxTicksLimit: 8,
            color: muted,
            font: { size: 11 },
          },
          grid: { color: grid, drawBorder: false },
          border: { display: false },
        },
        y: {
          min: yScale.min,
          max: yScale.max,
          beginAtZero: false,
          title: {
            display: true,
            text: "ارزش (تومان)",
            color: muted,
            font: { size: 12, weight: "500" },
          },
          ticks: {
            color: muted,
            font: { size: 12, weight: "500" },
            stepSize: yScale.stepSize,
            maxTicksLimit: 7,
            callback: yScale.formatTick,
            padding: 8,
          },
          grid: { color: grid, drawBorder: false },
          border: { display: false },
        },
      },
    };
  }

  function init() {
    const el = document.getElementById("chart-data");
    const canvas = document.getElementById("timeline-chart");
    const chartWrap = canvas?.closest(".chart-wrap");
    const panel = document.getElementById("chart-panel");
    const totalTab = document.getElementById("chart-tab-total");
    const assetSelect = document.getElementById("chart-asset-select");
    const assetField = document.getElementById("chart-asset-field");
    const zoomBtns = document.querySelectorAll("[data-zoom]");
    const rangeBtn = document.getElementById("chart-range-btn");
    const fullscreenBtn = document.getElementById("chart-fullscreen");

    if (!el || !canvas || typeof Chart === "undefined") {
      return false;
    }

    const zoomEnabled = registerZoomPlugin();
    if (!zoomEnabled) {
      console.warn("chartjs-plugin-zoom not loaded; zoom/range disabled");
    }

    let payload = { labels: [], series: [] };
    try {
      payload = JSON.parse(el.textContent || "{}");
    } catch (_) {
      payload = { labels: [], series: [] };
    }

    const labels = payload.labels || [];
    const series = payload.series || [];
    const assetOptions = payload.assetOptions || [];
    if (!labels.length || !series.length) {
      chartWrap?.classList.add("hidden");
      return true;
    }

    if (assetSelect && assetSelect.options.length === 0 && assetOptions.length) {
      assetOptions.forEach((opt) => {
        const o = document.createElement("option");
        o.value = opt.key;
        o.textContent = opt.label || opt.key;
        assetSelect.appendChild(o);
      });
      assetSelect.disabled = false;
    }

    let chart = null;
    let mode = "total";
    let assetKey = assetSelect?.value || assetOptions[0]?.key || "";
    let rangeSelect = false;

    function showAssetChart() {
      if (!assetSelect || assetSelect.disabled) return;
      assetKey = assetSelect.value;
      if (!assetKey) return;
      mode = "asset";
      syncChartModeUi();
      renderChart();
    }

    function syncChartModeUi() {
      const onTotal = mode === "total";
      totalTab?.classList.toggle("is-active", onTotal);
      totalTab?.setAttribute("aria-selected", onTotal ? "true" : "false");
      assetField?.classList.toggle("is-active", !onTotal);
    }

    function renderChart() {
      const datasets = buildDatasets(mode, series, assetKey);
      if (!datasets.length) return;

      if (chart) chart.destroy();
      chart = new Chart(canvas, {
        type: "line",
        data: { labels, datasets },
        options: chartOptions(mode, labels, rangeSelect, zoomEnabled, datasets),
      });
    }

    function setRangeMode(on) {
      rangeSelect = on;
      rangeBtn?.classList.toggle("is-active", on);
      rangeBtn?.setAttribute("aria-pressed", on ? "true" : "false");
      chartWrap?.classList.toggle("is-range-mode", on);
      renderChart();
    }

    function zoomChart(action) {
      if (!chart || typeof chart.resetZoom !== "function") return;
      if (action === "reset") {
        chart.resetZoom();
        return;
      }
      if (typeof chart.zoomScale !== "function") return;
      const factor = action === "in" ? 1.25 : 0.8;
      chart.zoomScale("x", { factor, center: "center" });
    }

    rangeBtn?.addEventListener("click", function () {
      setRangeMode(!rangeSelect);
    });

    zoomBtns.forEach((btn) => {
      btn.addEventListener("click", function () {
        if (rangeSelect) setRangeMode(false);
        zoomChart(btn.dataset.zoom);
      });
    });

    if (fullscreenBtn && panel) {
      fullscreenBtn.addEventListener("click", function () {
        if (!document.fullscreenElement) {
          panel.requestFullscreen?.().catch(() => {});
        } else {
          document.exitFullscreen?.();
        }
      });
      document.addEventListener("fullscreenchange", function () {
        const on = document.fullscreenElement === panel;
        panel.classList.toggle("is-fullscreen", on);
        fullscreenBtn.textContent = on ? "✕" : "⛶";
        fullscreenBtn.setAttribute("aria-label", on ? "خروج از تمام‌صفحه" : "تمام‌صفحه");
        chart?.resize();
      });
    }

    totalTab?.addEventListener("click", function () {
      if (mode === "total") return;
      mode = "total";
      syncChartModeUi();
      renderChart();
    });

    assetSelect?.addEventListener("change", showAssetChart);
    assetSelect?.addEventListener("input", showAssetChart);
    assetField?.addEventListener("click", function (e) {
      if (e.target === assetSelect) return;
      assetSelect?.focus();
      showAssetChart();
    });

    syncChartModeUi();
    renderChart();
    return true;
  }

  function boot(retries) {
    const timelineOk = init();
    initPieChart();
    if (timelineOk) return;
    if (retries > 0) {
      window.setTimeout(() => boot(retries - 1), 80);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => boot(25));
  } else {
    boot(25);
  }
})();

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

  function formatAxis(v) {
    let raw;
    if (v >= 1e9) raw = (v / 1e9).toFixed(1) + "B";
    else if (v >= 1e6) raw = (v / 1e6).toFixed(0) + "M";
    else if (v >= 1e3) raw = (v / 1e3).toFixed(0) + "K";
    else raw = String(v);
    return toPersianDigits(raw);
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

  function buildDatasets(mode, series) {
    const accent = cssVar("--accent") || ASSET_COLORS.total;
    const fill = cssVar("--chart-fill") || "rgba(62, 224, 184, 0.12)";
    const many = (series[0]?.data?.length || 0) > 49;

    if (mode === "total") {
      const row = series.find((s) => s.key === "total");
      if (!row) return [];
      const data = row.data.map((v) => Number(v));
      return [
        {
          label: row.label,
          data,
          borderColor: accent,
          backgroundColor: fill,
          fill: true,
          tension: 0.3,
          borderWidth: 2.5,
          hoverBorderWidth: 4,
          pointRadius: data.map((_, i) =>
            i === data.length - 1 ? 5 : many ? 3 : 4
          ),
          pointHitRadius: 28,
          pointHoverRadius: 8,
          pointBackgroundColor: accent,
          pointBorderColor: cssVar("--surface") || "#fff",
          pointBorderWidth: 2,
        },
      ];
    }

    return series
      .filter((s) => s.key !== "total")
      .filter((s) => s.data.some((v) => Number(v) > 0))
      .map((s) => {
        const color = ASSET_COLORS[s.key] || "#9aa3b2";
        const data = s.data.map((v) => Number(v));
        return {
          label: s.label,
          data,
          borderColor: color,
          backgroundColor: color + "33",
          fill: false,
          tension: 0.3,
          borderWidth: 2,
          hoverBorderWidth: 4,
          pointRadius: many ? 3 : 4,
          pointHitRadius: 28,
          pointHoverRadius: 7,
          pointBackgroundColor: color,
          pointBorderColor: cssVar("--surface") || "#fff",
          pointBorderWidth: 1,
        };
      });
  }

  function chartOptions(mode, labels, rangeSelect, zoomEnabled) {
    const muted = cssVar("--text-muted") || "#9aa3b2";
    const grid = cssVar("--chart-grid") || "rgba(255,255,255,0.06)";
    const surface = cssVar("--surface") || "#181d27";
    const text = cssVar("--text") || "#eef1f6";
    const border = cssVar("--border") || "#2a3140";

    const plugins = {
      legend: {
        display: mode === "assets",
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
          title: {
            display: true,
            text: "ارزش (تومان)",
            color: muted,
            font: { size: 12, weight: "500" },
          },
          ticks: {
            color: muted,
            font: { size: 11 },
            callback: formatAxis,
            padding: 6,
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
    const tabs = document.querySelectorAll(".chart-tab");
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
    if (!labels.length || !series.length) {
      chartWrap?.classList.add("hidden");
      return true;
    }

    let chart = null;
    let mode = "total";
    let rangeSelect = false;

    function renderChart() {
      const datasets = buildDatasets(mode, series);
      if (!datasets.length) return;

      if (chart) chart.destroy();
      chart = new Chart(canvas, {
        type: "line",
        data: { labels, datasets },
        options: chartOptions(mode, labels, rangeSelect, zoomEnabled),
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

    tabs.forEach((tab) => {
      tab.addEventListener("click", function () {
        const next = tab.dataset.chartTab;
        if (!next || next === mode) return;
        mode = next;
        tabs.forEach((t) => {
          const on = t === tab;
          t.classList.toggle("is-active", on);
          t.setAttribute("aria-selected", on ? "true" : "false");
        });
        renderChart();
      });
    });

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

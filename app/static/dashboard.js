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
    total: "#5b9dff",
  };

  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function formatAxis(v) {
    if (v >= 1e9) return (v / 1e9).toFixed(1) + "B";
    if (v >= 1e6) return (v / 1e6).toFixed(0) + "M";
    if (v >= 1e3) return (v / 1e3).toFixed(0) + "K";
    return v;
  }

  function formatToman(v) {
    if (v == null || Number.isNaN(v)) return "—";
    return Math.round(v).toLocaleString("en-US") + " تومان";
  }

  function buildDatasets(mode, series, labels) {
    const accent = cssVar("--accent") || ASSET_COLORS.total;
    const fill = cssVar("--chart-fill") || "rgba(91, 157, 255, 0.12)";
    const many = labels.length > 49;

    if (mode === "total") {
      const row = series.find((s) => s.key === "total");
      if (!row) return [];
      return [
        {
          label: row.label,
          data: row.data,
          borderColor: accent,
          backgroundColor: fill,
          fill: true,
          tension: 0.3,
          borderWidth: 2.5,
          hoverBorderWidth: 4,
          pointRadius: row.data.map((_, i) => (i === 0 ? 5 : many ? 0 : 3)),
          pointHoverRadius: 7,
          pointBackgroundColor: accent,
          pointBorderColor: cssVar("--surface") || "#fff",
          pointBorderWidth: 2,
        },
      ];
    }

    return series
      .filter((s) => s.key !== "total")
      .filter((s) => s.data.some((v) => v > 0))
      .map((s) => {
        const color = ASSET_COLORS[s.key] || "#9aa3b2";
        return {
          label: s.label,
          data: s.data,
          borderColor: color,
          backgroundColor: color + "33",
          fill: false,
          tension: 0.3,
          borderWidth: 2,
          hoverBorderWidth: 4,
          pointRadius: many ? 0 : 2,
          pointHoverRadius: 6,
          pointBackgroundColor: color,
          pointBorderColor: cssVar("--surface") || "#fff",
          pointBorderWidth: 1,
        };
      });
  }

  function chartOptions(mode, labels) {
    const muted = cssVar("--text-muted") || "#9aa3b2";
    const grid = cssVar("--chart-grid") || "rgba(255,255,255,0.06)";
    const surface = cssVar("--surface") || "#181d27";
    const text = cssVar("--text") || "#eef1f6";
    const border = cssVar("--border") || "#2a3140";
    const hasZoom = typeof Chart !== "undefined" && Chart.registry.plugins.get("zoom");

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
        onHover: (e) => {
          e.native.target.style.cursor = "pointer";
        },
        onLeave: (e) => {
          e.native.target.style.cursor = "default";
        },
      },
      tooltip: {
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
            return items[0].label || labels[items[0].dataIndex] || "";
          },
          label: function (ctx) {
            const name = ctx.dataset.label || "";
            const v = ctx.parsed.y;
            return " " + name + ": " + formatToman(v);
          },
        },
      },
    };

    if (hasZoom) {
      plugins.zoom = {
        zoom: {
          wheel: { enabled: true, speed: 0.08 },
          pinch: { enabled: true },
          drag: {
            enabled: true,
            backgroundColor: "rgba(91, 157, 255, 0.12)",
            borderColor: "rgba(91, 157, 255, 0.45)",
            borderWidth: 1,
          },
          mode: "x",
        },
        pan: {
          enabled: true,
          mode: "x",
          modifierKey: "shift",
        },
        limits: {
          x: { minRange: 2 },
        },
      };
    }

    return {
      responsive: true,
      maintainAspectRatio: false,
      layout: { padding: { top: 8, right: 12, bottom: 4, left: 4 } },
      interaction: {
        mode: "nearest",
        intersect: true,
        axis: "xy",
      },
      hover: {
        mode: "nearest",
        intersect: true,
        axis: "xy",
      },
      plugins,
      scales: {
        x: {
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

  document.addEventListener("DOMContentLoaded", function () {
    const el = document.getElementById("chart-data");
    const canvas = document.getElementById("timeline-chart");
    const panel = document.getElementById("chart-panel");
    const tabs = document.querySelectorAll(".chart-tab");
    const zoomBtns = document.querySelectorAll("[data-zoom]");
    const fullscreenBtn = document.getElementById("chart-fullscreen");
    if (!el || !canvas || typeof Chart === "undefined") return;

    let payload = { labels: [], series: [] };
    try {
      payload = JSON.parse(el.textContent || "{}");
    } catch (_) {
      payload = { labels: [], series: [] };
    }

    const labels = payload.labels || [];
    const series = payload.series || [];
    if (!labels.length || !series.length) {
      canvas.closest(".chart-stage")?.classList.add("hidden");
      return;
    }

    let chart = null;
    let mode = "total";

    function renderChart() {
      const datasets = buildDatasets(mode, series, labels);
      if (!datasets.length) return;

      if (chart) chart.destroy();
      chart = new Chart(canvas, {
        type: "line",
        data: { labels, datasets },
        options: chartOptions(mode, labels),
      });
    }

    function zoomChart(action) {
      if (!chart || !chart.resetZoom) return;
      if (action === "reset") {
        chart.resetZoom();
        return;
      }
      const factor = action === "in" ? 1.2 : 0.82;
      chart.zoomScale("x", { factor, center: "center" });
    }

    zoomBtns.forEach((btn) => {
      btn.addEventListener("click", function () {
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
  });
})();

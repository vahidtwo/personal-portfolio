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
          tension: 0.25,
          borderWidth: 2,
          pointRadius: row.data.map((_, i) => (i === 0 ? 6 : many ? 0 : 3)),
          pointBackgroundColor: row.data.map((_, i) => (i === 0 ? accent : accent)),
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
          backgroundColor: color + "22",
          fill: false,
          tension: 0.25,
          borderWidth: 2,
          pointRadius: many ? 0 : 2,
          pointHoverRadius: 5,
        };
      });
  }

  document.addEventListener("DOMContentLoaded", function () {
    const el = document.getElementById("chart-data");
    const canvas = document.getElementById("timeline-chart");
    const tabs = document.querySelectorAll(".chart-tab");
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
      canvas.classList.add("hidden");
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
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: "index", intersect: false },
          plugins: {
            legend: {
              display: mode === "assets",
              position: "bottom",
              rtl: true,
              labels: { boxWidth: 10, padding: 14 },
            },
            tooltip: {
              rtl: true,
              callbacks: {
                label: function (ctx) {
                  const v = ctx.parsed.y;
                  if (v == null) return "";
                  return " " + ctx.dataset.label + ": " + Math.round(v).toLocaleString("en-US") + " تومان";
                },
              },
            },
          },
          scales: {
            x: {
              title: {
                display: true,
                text: "تاریخ و زمان (شمسی)",
                color: cssVar("--text-muted"),
                font: { size: 12 },
              },
              ticks: {
                maxRotation: 45,
                minRotation: 0,
                autoSkip: true,
                maxTicksLimit: 7,
                color: cssVar("--text-muted"),
              },
              grid: { color: cssVar("--chart-grid") },
            },
            y: {
              ticks: {
                color: cssVar("--text-muted"),
                callback: formatAxis,
              },
              grid: { color: cssVar("--chart-grid") },
            },
          },
        },
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

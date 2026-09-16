(function () {
  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  document.addEventListener("DOMContentLoaded", function () {
    const el = document.getElementById("timeline-data");
    const canvas = document.getElementById("timeline-chart");
    const empty = document.getElementById("chart-empty");
    if (!el || !canvas || typeof Chart === "undefined") return;

    let points = [];
    try {
      points = JSON.parse(el.textContent || "[]");
    } catch (_) {
      points = [];
    }
    if (!points.length) {
      canvas.classList.add("hidden");
      return;
    }
    if (empty) empty.classList.add("hidden");

    const labels = points.map((p) => p.t);
    const values = points.map((p) => p.v);

    new Chart(canvas, {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "ارزش پرتفوی (تومان)",
            data: values,
            borderColor: cssVar("--chart-line") || "#5b9dff",
            backgroundColor: cssVar("--chart-fill") || "rgba(91, 157, 255, 0.12)",
            fill: true,
            tension: 0.25,
            pointRadius: points.length > 48 ? 0 : 3,
            pointHoverRadius: 5,
            borderWidth: 2,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: {
            rtl: true,
            callbacks: {
              label: function (ctx) {
                const v = ctx.parsed.y;
                if (v == null) return "";
                return " " + Math.round(v).toLocaleString("en-US") + " تومان";
              },
            },
          },
        },
        scales: {
          x: {
            ticks: {
              maxRotation: 0,
              autoSkip: true,
              maxTicksLimit: 8,
              color: cssVar("--text-muted"),
            },
            grid: { color: cssVar("--chart-grid") },
          },
          y: {
            ticks: {
              color: cssVar("--text-muted"),
              callback: function (v) {
                if (v >= 1e9) return (v / 1e9).toFixed(1) + "B";
                if (v >= 1e6) return (v / 1e6).toFixed(0) + "M";
                if (v >= 1e3) return (v / 1e3).toFixed(0) + "K";
                return v;
              },
            },
            grid: { color: cssVar("--chart-grid") },
          },
        },
      },
    });
  });
})();

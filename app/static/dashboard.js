(function () {
  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  document.addEventListener("DOMContentLoaded", function () {
    const el = document.getElementById("timeline-data");
    const canvas = document.getElementById("timeline-chart");
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

    const labels = points.map((p) => p.t);
    const values = points.map((p) => p.v);
    const accent = cssVar("--accent") || "#5b9dff";
    const line = cssVar("--chart-line") || accent;
    const pointRadius = points.map((p, i) => {
      if (p.live) return 6;
      return points.length > 49 ? 0 : 3;
    });
    const pointBg = points.map((p) => (p.live ? accent : line));

    new Chart(canvas, {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "ارزش پرتفوی (تومان)",
            data: values,
            borderColor: line,
            backgroundColor: cssVar("--chart-fill") || "rgba(91, 157, 255, 0.12)",
            fill: true,
            tension: 0.25,
            pointRadius,
            pointBackgroundColor: pointBg,
            pointBorderColor: pointBg,
            pointHoverRadius: 6,
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

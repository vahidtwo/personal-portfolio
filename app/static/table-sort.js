(function () {
  const COL_ATTR = {
    name: "sortName",
    qty: "sortQty",
    unit: "sortUnit",
    unit_price: "sortUnitPrice",
    value: "sortValue",
    share: "sortShare",
  };

  function parseNum(raw) {
    if (raw == null || raw === "") return null;
    const n = Number(String(raw).replace(/,/g, ""));
    return Number.isFinite(n) ? n : null;
  }

  function compareRows(a, b, col, dir) {
    const attr = COL_ATTR[col];
    if (!attr) return 0;
    const va = a.dataset[attr] ?? "";
    const vb = b.dataset[attr] ?? "";

    if (col === "name" || col === "unit") {
      const cmp = va.localeCompare(vb, "fa", { sensitivity: "base" });
      return cmp * dir;
    }

    const na = parseNum(va);
    const nb = parseNum(vb);
    if (na == null && nb == null) return 0;
    if (na == null) return 1;
    if (nb == null) return -1;
    if (na === nb) return 0;
    return (na < nb ? -1 : 1) * dir;
  }

  function setHeaderState(buttons, active, dir) {
    buttons.forEach((btn) => {
      const on = btn.dataset.col === active;
      btn.setAttribute("aria-sort", on ? (dir > 0 ? "ascending" : "descending") : "none");
      btn.classList.toggle("is-sorted", on);
      btn.classList.toggle("is-desc", on && dir < 0);
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    const table = document.getElementById("portfolio-table");
    if (!table) return;
    const tbody = table.querySelector("tbody");
    const buttons = table.querySelectorAll("thead .th-sort");
    if (!tbody || !buttons.length) return;

    let sortCol = "value";
    let sortDir = -1;

    function sort() {
      const rows = Array.from(tbody.querySelectorAll("tr"));
      rows.sort((a, b) => compareRows(a, b, sortCol, sortDir));
      rows.forEach((row) => tbody.appendChild(row));
      setHeaderState(buttons, sortCol, sortDir);
    }

    buttons.forEach((btn) => {
      btn.addEventListener("click", function () {
        const col = btn.dataset.col;
        if (!col) return;
        if (sortCol === col) sortDir *= -1;
        else {
          sortCol = col;
          sortDir = col === "name" || col === "unit" ? 1 : -1;
        }
        sort();
      });
    });

    sort();
  });
})();

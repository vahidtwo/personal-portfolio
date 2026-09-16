(function () {
  const LEGACY_COL_ATTR = {
    name: "sortName",
    qty: "sortQty",
    unit: "sortUnit",
    unit_price: "sortUnitPrice",
    value: "sortValue",
    share: "sortShare",
  };

  function sortDatasetKey(col) {
    if (LEGACY_COL_ATTR[col]) {
      return LEGACY_COL_ATTR[col];
    }
    const parts = col.split("_");
    return (
      "sort" +
      parts
        .map(function (part) {
          return part.charAt(0).toUpperCase() + part.slice(1);
        })
        .join("")
    );
  }

  function parseNum(raw) {
    if (raw == null || raw === "") return null;
    const n = Number(String(raw).replace(/,/g, ""));
    return Number.isFinite(n) ? n : null;
  }

  function isStringCol(col) {
    return col === "name" || col === "unit" || col === "user" || col === "symbol" || col === "sanjeh";
  }

  function compareRows(a, b, col, dir) {
    const attr = sortDatasetKey(col);
    const va = a.dataset[attr] ?? "";
    const vb = b.dataset[attr] ?? "";

    if (
      isStringCol(col) ||
      col === "created" ||
      col === "fetched" ||
      col === "last_login"
    ) {
      const cmp = String(va).localeCompare(String(vb), "fa", { sensitivity: "base" });
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
    buttons.forEach(function (btn) {
      const on = btn.dataset.col === active;
      btn.setAttribute("aria-sort", on ? (dir > 0 ? "ascending" : "descending") : "none");
      btn.classList.toggle("is-sorted", on);
      btn.classList.toggle("is-desc", on && dir < 0);
    });
  }

  function initSortableTable(table) {
    const tbody = table.querySelector("tbody");
    const buttons = table.querySelectorAll("thead .th-sort");
    if (!tbody || !buttons.length) return;

    const defaultCol = table.dataset.sortDefault || "value";
    const defaultDesc = table.dataset.sortDesc === "1";
    let sortCol = defaultCol;
    let sortDir = defaultDesc ? -1 : 1;
    if (isStringCol(sortCol) && !defaultDesc) {
      sortDir = 1;
    }

    function sort() {
      const rows = Array.from(tbody.querySelectorAll("tr"));
      rows.sort(function (a, b) {
        return compareRows(a, b, sortCol, sortDir);
      });
      rows.forEach(function (row) {
        tbody.appendChild(row);
      });
      setHeaderState(buttons, sortCol, sortDir);
    }

    buttons.forEach(function (btn) {
      btn.addEventListener("click", function () {
        const col = btn.dataset.col;
        if (!col) return;
        if (sortCol === col) sortDir *= -1;
        else {
          sortCol = col;
          sortDir =
            isStringCol(col) ||
            col === "created" ||
            col === "fetched" ||
            col === "last_login"
              ? 1
              : -1;
        }
        sort();
      });
    });

    sort();
  }

  document.addEventListener("DOMContentLoaded", function () {
    const portfolio = document.getElementById("portfolio-table");
    if (portfolio) {
      initSortableTable(portfolio);
    }
    document.querySelectorAll("table[data-sortable]").forEach(initSortableTable);
  });
})();

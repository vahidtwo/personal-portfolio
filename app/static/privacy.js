(function () {
  var keys = { portfolio: "privacy-portfolio", salary: "privacy-salary" };
  var showAttr = { portfolio: "showPortfolio", salary: "showSalary" };

  function isHidden(kind) {
    try {
      return localStorage.getItem(keys[kind]) !== "0";
    } catch (e) {
      return true;
    }
  }

  function paint(kind) {
    var hidden = isHidden(kind);
    if (hidden) delete document.documentElement.dataset[showAttr[kind]];
    else document.documentElement.dataset[showAttr[kind]] = "1";
    document.querySelectorAll('[data-privacy-toggle="' + kind + '"]').forEach(function (button) {
      button.setAttribute("aria-pressed", hidden ? "true" : "false");
    });
  }

  document.querySelectorAll("[data-privacy-toggle]").forEach(function (button) {
    var kind = button.getAttribute("data-privacy-toggle");
    paint(kind);
    button.addEventListener("click", function () {
      try {
        localStorage.setItem(keys[kind], isHidden(kind) ? "0" : "1");
      } catch (e) {}
      paint(kind);
    });
  });
})();

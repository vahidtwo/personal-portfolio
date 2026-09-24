(function () {
  var PERSIAN = "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩";

  function toLatin(text) {
    return String(text).replace(/[۰-۹٠-٩]/g, function (ch) {
      var index = PERSIAN.indexOf(ch);
      return index === -1 ? ch : String(index % 10);
    });
  }

  function plainNumber(text) {
    var latin = toLatin(text).replace(/[,٬\s]/g, "");
    if (!/^\d*\.?\d*$/.test(latin) || latin === "" || latin === ".") return "";
    return latin;
  }

  function groupInteger(digits) {
    return digits.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  }

  function formatAmount(text) {
    var plain = plainNumber(text);
    if (!plain) return "";
    var parts = plain.split(".");
    var whole = parts[0].replace(/^0+(?=\d)/, "");
    var grouped = groupInteger(whole === "" ? "0" : whole);
    return parts.length > 1 ? grouped + "." + parts[1] : grouped;
  }

  function scaleByZeros(plain, zeros) {
    var parts = plain.split(".");
    var whole = parts[0].replace(/^0+(?=\d)/, "") || "0";
    var frac = parts[1] || "";
    var digits = (whole + frac).replace(/^0+(?=\d)/, "") || "0";
    var shift = zeros - frac.length;
    if (shift >= 0) return digits + "0".repeat(shift);
    var cut = digits.length + shift;
    if (cut <= 0) return "0." + "0".repeat(-cut) + digits;
    return digits.slice(0, cut) + "." + digits.slice(cut);
  }

  function bindThousands(input) {
    function paint() {
      var start = input.selectionStart || 0;
      var digitsBefore = toLatin(input.value.slice(0, start)).replace(/\D/g, "").length;
      var next = formatAmount(input.value);
      if (input.value === next) return;
      input.value = next;
      var seen = 0;
      var pos = next.length;
      for (var i = 0; i < next.length; i++) {
        if (/\d/.test(next[i])) seen += 1;
        if (seen >= digitsBefore) {
          pos = i + 1;
          break;
        }
      }
      input.setSelectionRange(pos, pos);
    }
    input.addEventListener("input", paint);
    input.addEventListener("blur", paint);
    paint();
    var form = input.form;
    if (form && !form.dataset.amountStrip) {
      form.dataset.amountStrip = "1";
      form.addEventListener("submit", function () {
        form.querySelectorAll("[data-thousands]").forEach(function (field) {
          field.value = plainNumber(field.value);
        });
      });
    }
  }

  function bindSuggest(input) {
    var box = document.createElement("div");
    box.className = "amount-suggest";
    box.hidden = true;
    var factors = [3, 6, 9];
    var buttons = factors.map(function (zeros) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "amount-suggest-btn";
      button.addEventListener("click", function () {
        var plain = plainNumber(input.value);
        if (!plain) return;
        input.value = formatAmount(scaleByZeros(plain, zeros));
        input.dispatchEvent(new Event("input", { bubbles: true }));
        input.focus();
      });
      box.appendChild(button);
      return button;
    });
    input.insertAdjacentElement("afterend", box);

    function refresh() {
      var plain = plainNumber(input.value);
      var amount = plain === "" ? 0 : Number(plain);
      if (!plain || !isFinite(amount) || amount === 0) {
        box.hidden = true;
        return;
      }
      factors.forEach(function (zeros, index) {
        buttons[index].textContent = formatAmount(scaleByZeros(plain, zeros));
      });
      box.hidden = false;
    }
    input.addEventListener("input", refresh);
    refresh();
  }

  document.querySelectorAll("[data-thousands]").forEach(bindThousands);
  document.querySelectorAll("[data-amount-suggest]").forEach(bindSuggest);
})();

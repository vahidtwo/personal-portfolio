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

  // Display form inside inputs: Persian digits and ٬ (submit strips back to Latin).
  function displayAmount(text) {
    var plain = formatAmount(text);
    if (!plain) return "";
    return plain.replace(/,/g, "٬").replace(/\d/g, function (d) { return "۰۱۲۳۴۵۶۷۸۹"[Number(d)]; });
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
      var next = displayAmount(input.value);
      if (input.value === next) return;
      input.value = next;
      var seen = 0;
      var pos = next.length;
      for (var i = 0; i < next.length; i++) {
        if (/\d/.test(toLatin(next[i]))) seen += 1;
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

  var FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹";
  function toPersianDigits(text) {
    return String(text).replace(/\d/g, function (d) { return FA_DIGITS[Number(d)]; });
  }

  // 150000 -> "۱۵۰ هزار تومان", 1500000 -> "۱٫۵ میلیون تومان" (at most 2 decimals, trailing zeros dropped).
  function amountInWords(amount) {
    if (!isFinite(amount) || amount <= 0) return "";
    var units = [[1e12, "هزار میلیارد"], [1e9, "میلیارد"], [1e6, "میلیون"], [1e3, "هزار"]];
    for (var i = 0; i < units.length; i++) {
      if (amount >= units[i][0]) {
        var n = Math.round((amount / units[i][0]) * 100) / 100;
        var text = String(n).replace(".", "٫");
        return toPersianDigits(text) + " " + units[i][1] + " تومان";
      }
    }
    var small = Math.round(amount * 100) / 100;
    return toPersianDigits(String(small).replace(".", "٫")) + " تومان";
  }

  // QA (Oct 17): a chip may never be more than 100x what was typed, so one tap
  // can't silently log 1000x. Each chip is labeled in Persian words.
  var MAX_CHIP_FACTOR = 100;
  var CHIP_ZEROS = [1, 2];

  function chipOptions(plain) {
    var amount = plain === "" ? 0 : Number(plain);
    if (!plain || !isFinite(amount) || amount <= 0) return [];
    var out = [];
    CHIP_ZEROS.forEach(function (zeros) {
      var scaledPlain = scaleByZeros(plain, zeros);
      var scaled = Number(scaledPlain);
      if (!isFinite(scaled) || scaled > amount * MAX_CHIP_FACTOR) return;
      out.push({ plain: scaledPlain, label: amountInWords(scaled) });
    });
    return out;
  }

  function bindSuggest(input) {
    var words = document.createElement("p");
    words.className = "amount-words";
    words.setAttribute("aria-live", "polite");
    words.hidden = true;
    var box = document.createElement("div");
    box.className = "amount-suggest";
    box.hidden = true;
    input.insertAdjacentElement("afterend", box);
    input.insertAdjacentElement("afterend", words);

    function refresh() {
      var plain = plainNumber(input.value);
      var amount = plain === "" ? 0 : Number(plain);
      var label = amountInWords(amount);
      words.textContent = label ? "= " + label : "";
      words.hidden = !label;
      box.innerHTML = "";
      var options = chipOptions(plain);
      options.forEach(function (option) {
        var button = document.createElement("button");
        button.type = "button";
        button.className = "amount-suggest-btn";
        button.textContent = option.label;
        button.setAttribute("aria-label", "تغییر مبلغ به " + option.label);
        button.addEventListener("click", function () {
          input.value = displayAmount(option.plain);
          input.dispatchEvent(new Event("input", { bubbles: true }));
          input.focus();
        });
        box.appendChild(button);
      });
      box.hidden = options.length === 0;
    }
    input.addEventListener("input", refresh);
    refresh();
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { amountInWords: amountInWords, chipOptions: chipOptions, plainNumber: plainNumber,
                       formatAmount: formatAmount, displayAmount: displayAmount, MAX_CHIP_FACTOR: MAX_CHIP_FACTOR };
  }
  if (typeof document === "undefined") return;

  document.querySelectorAll("[data-thousands]").forEach(bindThousands);
  document.querySelectorAll("[data-amount-suggest]").forEach(bindSuggest);
})();

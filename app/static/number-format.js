/* Single display formatter for numbers (mirrors app.formatting.format_number in Python).
   Persian digits, ٬ thousands, ٫ decimals, round half-up to maxDecimals, no trailing zeros, "−" for negatives.
   Used by amount chips/words (amount-input.js) and the dashboard chart (dashboard.js). */
(function (root) {
  var FA = "۰۱۲۳۴۵۶۷۸۹";
  var IN_DIGITS = "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩";

  function toDecimalString(value) {
    if (value === null || value === undefined) return null;
    if (typeof value === "number") {
      if (!isFinite(value)) return null;
      var s = String(value);
      if (/e/i.test(s)) {
        s = Math.abs(value) < 1 ? value.toFixed(20)
          : value.toLocaleString("en-US", { useGrouping: false, maximumFractionDigits: 0 });
      }
      return s;
    }
    var t = String(value).trim().replace(/[۰-۹٠-٩]/g, function (ch) {
      return String(IN_DIGITS.indexOf(ch) % 10);
    }).replace(/[,٬\s]/g, "").replace("٫", ".").replace("−", "-");
    if (!/^-?\d*\.?\d*$/.test(t) || t === "" || t === "-" || t === "." || t === "-.") return null;
    return t;
  }

  function formatNumberFa(value, maxDecimals) {
    if (maxDecimals === undefined) maxDecimals = 2;
    var s = toDecimalString(value);
    if (s === null) return "";
    var neg = s.charAt(0) === "-";
    if (neg) s = s.slice(1);
    var parts = s.split(".");
    var ip = parts[0] || "0";
    var fp = parts[1] || "";
    if (fp.length > maxDecimals) {
      var roundUp = fp.charCodeAt(maxDecimals) - 48 >= 5;
      var digits = (ip + fp.slice(0, maxDecimals)).split("").map(Number);
      if (roundUp) {
        var i = digits.length - 1;
        while (i >= 0) {
          if (digits[i] === 9) { digits[i] = 0; i--; } else { digits[i] += 1; break; }
        }
        if (i < 0) digits.unshift(1);
      }
      var all = digits.join("");
      ip = all.slice(0, all.length - maxDecimals) || "0";
      fp = maxDecimals ? all.slice(all.length - maxDecimals) : "";
    }
    fp = fp.replace(/0+$/, "");
    ip = ip.replace(/^0+(?=\d)/, "");
    var out = ip.replace(/\B(?=(\d{3})+(?!\d))/g, "٬") + (fp ? "٫" + fp : "");
    if (neg && /[1-9]/.test(ip + fp)) out = "−" + out;
    return out.replace(/\d/g, function (d) { return FA[Number(d)]; });
  }

  var api = { format: formatNumberFa, MONEY_DECIMALS: 2, QTY_DECIMALS: 8 };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (root) root.NumberFa = api;
})(typeof window !== "undefined" ? window : null);

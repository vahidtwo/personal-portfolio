/* Leave warning for forms marked data-leave-warn (the daily spend form).
   "Dirty" = a field differs from the value the server rendered (defaultValue / defaultSelected /
   defaultChecked), so a value the browser restored on Back/Forward still counts as unsaved.
   Submitting the form never warns. */
(function () {
  "use strict";

  function fieldDirty(el) {
    if (!el.name || el.disabled) return false;
    var type = (el.type || "").toLowerCase();
    if (type === "hidden" || type === "submit" || type === "button" || type === "reset") return false;
    if (type === "checkbox" || type === "radio") return el.checked !== el.defaultChecked;
    if (el.tagName === "SELECT") {
      for (var i = 0; i < el.options.length; i++) {
        var opt = el.options[i];
        if (opt.selected !== opt.defaultSelected) {
          // A select with no option marked "selected" in the HTML shows its first option by default.
          var anyDefault = false;
          for (var j = 0; j < el.options.length; j++) if (el.options[j].defaultSelected) anyDefault = true;
          if (!anyDefault && el.selectedIndex === 0) return false;
          return true;
        }
      }
      return false;
    }
    return el.value !== el.defaultValue;
  }

  function formDirty(form) {
    var els = form.elements;
    for (var i = 0; i < els.length; i++) if (fieldDirty(els[i])) return true;
    return false;
  }

  var forms = Array.prototype.slice.call(document.querySelectorAll("form[data-leave-warn]"));
  if (!forms.length) return;
  var submitting = false;

  forms.forEach(function (form) {
    form.addEventListener("submit", function (event) {
      // pwa.js cancels submits while offline (capture phase, so it already ran); then we still warn.
      submitting = !event.defaultPrevented;
    });
  });

  window.addEventListener("pageshow", function () { submitting = false; });

  window.addEventListener("beforeunload", function (event) {
    if (submitting) return;
    for (var i = 0; i < forms.length; i++) {
      if (formDirty(forms[i])) {
        event.preventDefault();
        event.returnValue = ""; // older Chrome / WebView need returnValue set
        return "";
      }
    }
  });

  window.__leaveGuard = { formDirty: formDirty };
})();

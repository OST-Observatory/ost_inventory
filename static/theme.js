(function () {
  var theme = null;
  try {
    theme = localStorage.getItem("ost-theme");
  } catch (e) {
    /* ignore */
  }
  if (theme !== "dark" && theme !== "light") {
    try {
      theme = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    } catch (e) {
      theme = "light";
    }
  }
  document.documentElement.setAttribute("data-theme", theme);
})();

(function () {
  try {
    var theme = localStorage.getItem("ost-theme");
    if (theme === "dark" || theme === "light") {
      document.documentElement.setAttribute("data-theme", theme);
    }
  } catch (e) {
    /* ignore */
  }
})();

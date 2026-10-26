// Applies the saved or OS theme before first paint. A separate file, so the CSP needs no inline scripts.
(function () {
  try {
    var t = localStorage.getItem('ll-theme');
    var dark = t ? t === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches;
    if (dark) document.documentElement.classList.add('dark');
  } catch (e) {}
})();

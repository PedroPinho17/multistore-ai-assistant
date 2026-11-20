;(function () {
  try {
    var pref = localStorage.getItem('theme')
    var theme = 'light'
    if (pref === 'light' || pref === 'dark') {
      theme = pref
    } else if (
      window.matchMedia &&
      window.matchMedia('(prefers-color-scheme: dark)').matches
    ) {
      theme = 'dark'
    }
    document.documentElement.dataset.theme = theme
  } catch (_) {
    /* ignore */
  }
})()

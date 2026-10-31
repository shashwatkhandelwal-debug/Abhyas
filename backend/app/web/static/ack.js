/* Instant "Opening…" bar on link/form navigation. */
(function () {
  var d = document.currentScript.dataset, bar;
  function hide() { if (bar) bar.hidden = true; }
  function show() {
    if (!bar) { bar = document.createElement('div'); bar.className = 'nav-ack'; bar.setAttribute('role', 'status'); document.body.appendChild(bar); }
    bar.textContent = d.opening; bar.hidden = false;
  }
  document.addEventListener('click', function (e) {
    var a = e.target instanceof Element && e.target.closest('a[href]');
    if (!a || e.defaultPrevented || e.button || e.metaKey || e.ctrlKey || e.shiftKey || a.target === '_blank' || a.hasAttribute('download') || a.hasAttribute('data-no-ack')) return;
    if (a.origin === location.origin && a.getAttribute('href').charAt(0) !== '#') show();
  });
  document.addEventListener('submit', function (e) { if (!e.defaultPrevented) show(); });
  window.addEventListener('pageshow', hide);
})();

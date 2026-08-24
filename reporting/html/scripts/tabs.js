// JS for HTML Report tabs

document.querySelectorAll('.tab-btn').forEach(function (btn) {
  btn.addEventListener('click', function () {
    var id = btn.getAttribute('data-tab');
    document.querySelectorAll('.tab-btn').forEach(function (b) { b.classList.remove('active'); });
    document.querySelectorAll('.tab-pane').forEach(function (p) { p.classList.remove('active'); });
    btn.classList.add('active');
    var pane = document.getElementById('tab-' + id);
    if (pane) pane.classList.add('active');
  });
});
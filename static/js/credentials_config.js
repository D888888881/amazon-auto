(function () {
  'use strict';

  document.querySelectorAll('.cred-password-toggle').forEach(function (btn) {
    var targetId = btn.getAttribute('data-target');
    var input = targetId ? document.getElementById(targetId) : null;
    if (!input) return;

    btn.addEventListener('click', function () {
      var show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      btn.textContent = show ? '隐藏' : '显示';
    });
  });

  var saveForm = document.getElementById('cred-save-form');
  var saveBtn = document.getElementById('cred-save-btn');
  if (saveForm && saveBtn) {
    saveForm.addEventListener('submit', function () {
      saveBtn.disabled = true;
      saveBtn.classList.add('cred-btn--loading');
      saveBtn.innerHTML = '<span class="cred-spinner" aria-hidden="true"></span> 保存中…';
    });
  }

  ['cred-refresh-btn-desktop', 'cred-refresh-btn-mobile'].forEach(function (id) {
    var btn = document.getElementById(id);
    if (!btn) return;
    var form = btn.closest('form');
    if (!form) return;
    form.addEventListener('submit', function () {
      btn.disabled = true;
      btn.classList.add('cred-btn--loading');
      var label = btn.querySelector('svg') ? ' 刷新中…' : '刷新中…';
      btn.innerHTML = '<span class="cred-spinner" aria-hidden="true"></span>' + label;
    });
  });

  var toasts = document.querySelector('.cred-toast');
  if (toasts) {
    window.setTimeout(function () {
      toasts.style.opacity = '0';
      toasts.style.transform = 'translateY(-6px)';
      window.setTimeout(function () {
        toasts.remove();
      }, 320);
    }, 5200);
  }
})();

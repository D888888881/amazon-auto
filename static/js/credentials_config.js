(function () {
  'use strict';

  function bindPasswordToggle(btn) {
    var targetId = btn.getAttribute('data-target');
    var input = targetId ? document.getElementById(targetId) : btn.previousElementSibling;
    if (!input || input.tagName !== 'INPUT') {
      input = btn.closest('.cred-password-wrap') && btn.closest('.cred-password-wrap').querySelector('input');
    }
    if (!input) return;

    btn.addEventListener('click', function () {
      var show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      btn.textContent = show ? '隐藏' : '显示';
    });
  }

  document.querySelectorAll('.cred-password-toggle').forEach(bindPasswordToggle);

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

  var bulkList = document.getElementById('bulk-accounts-list');
  var addBtn = document.getElementById('bulk-add-account');

  function reindexBulkRows() {
    if (!bulkList) return;
    bulkList.querySelectorAll('[data-bulk-row]').forEach(function (row, idx) {
      var label = row.querySelector('.bulk-account-row__index');
      if (label) label.textContent = '账号 ' + (idx + 1);
    });
  }

  function createBulkRow() {
    var row = document.createElement('div');
    row.className = 'bulk-account-row';
    row.setAttribute('data-bulk-row', '');
    row.innerHTML =
      '<div class="bulk-account-row__head">' +
      '<span class="bulk-account-row__index">账号</span>' +
      '<button type="button" class="bulk-account-row__remove" data-bulk-remove aria-label="删除此账号">删除</button>' +
      '</div>' +
      '<input type="hidden" name="bulk_account_key" value="">' +
      '<div class="cred-field"><label>子账号 ID <span class="cred-required">*</span></label>' +
      '<input type="text" name="bulk_child_id" class="cred-input" placeholder="1805119" required></div>' +
      '<div class="cred-field-row">' +
      '<div class="cred-field"><label>用户名 <span class="cred-required">*</span></label>' +
      '<input type="text" name="bulk_username" class="cred-input" placeholder="ITBM000066" autocomplete="off" required></div>' +
      '<div class="cred-field"><label>密码 <span class="cred-required">*</span></label>' +
      '<div class="cred-password-wrap">' +
      '<input type="password" name="bulk_password" class="cred-input" placeholder="必填" autocomplete="new-password" required>' +
      '<button type="button" class="cred-password-toggle" data-target="" aria-label="显示或隐藏密码">显示</button>' +
      '</div></div></div>' +
      '<div class="cred-field"><label>ao_lo_to_n Cookie</label>' +
      '<textarea name="bulk_ao_lo_to_n" class="cred-textarea cred-textarea--mono" rows="2"></textarea></div>';
    return row;
  }

  if (bulkList) {
    bulkList.addEventListener('click', function (ev) {
      var removeBtn = ev.target.closest('[data-bulk-remove]');
      if (!removeBtn) return;
      var row = removeBtn.closest('[data-bulk-row]');
      if (!row) return;
      var rows = bulkList.querySelectorAll('[data-bulk-row]');
      if (rows.length <= 1) return;
      row.remove();
      reindexBulkRows();
    });

    if (addBtn) {
      addBtn.addEventListener('click', function () {
        var row = createBulkRow();
        bulkList.appendChild(row);
        var toggle = row.querySelector('.cred-password-toggle');
        if (toggle) bindPasswordToggle(toggle);
        reindexBulkRows();
      });
    }

    reindexBulkRows();
  }
})();

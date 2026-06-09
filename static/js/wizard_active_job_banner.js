(function (global) {
  'use strict';

  function getCookie(name) {
    var m = document.cookie.match(new RegExp('(^|; )' + name + '=([^;]*)'));
    return m ? decodeURIComponent(m[2]) : '';
  }

  function updateActiveBannerFromJob(banner, job) {
    if (!banner || !job) return;
    if (job.is_terminal) {
      banner.hidden = true;
      banner.removeAttribute('data-job-id');
      return;
    }
    banner.hidden = false;
    banner.setAttribute('data-job-id', job.job_id || '');
    var st = document.getElementById('roi-active-status');
    var hint = document.getElementById('roi-active-hint');
    var last = document.getElementById('roi-active-last');
    if (st) st.textContent = job.status_label || job.status || '';
    if (hint) hint.textContent = job.status_hint || '';
    if (last) last.textContent = job.last_progress || '';
  }

  function refreshActiveBanner(banner, activeUrl) {
    if (!activeUrl) return Promise.resolve(null);
    return fetch(activeUrl, { credentials: 'same-origin' })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (data) {
        if (!data.ok || !data.has_active) {
          if (banner) {
            banner.hidden = true;
            banner.removeAttribute('data-job-id');
          }
          return null;
        }
        updateActiveBannerFromJob(banner, data.active_job);
        return data.active_job;
      })
      .catch(function (err) {
        console.warn('refreshActiveBanner failed', err);
        return null;
      });
  }

  function resolveJobId(banner, activeUrl) {
    var jid = banner ? banner.getAttribute('data-job-id') : '';
    if (jid) return Promise.resolve(jid);
    return refreshActiveBanner(banner, activeUrl).then(function (job) {
      return job && job.job_id ? job.job_id : '';
    });
  }

  function dismissActiveJob(banner, dismissUrl, csrfInput, activeUrl) {
    if (!dismissUrl) return Promise.resolve(false);
    return resolveJobId(banner, activeUrl).then(function (jid) {
      if (!jid) {
        alert('当前没有可解除的任务占用');
        return false;
      }
      if (!confirm('确定解除占用？若后台仍在计算，可能会与新建任务并行。')) {
        return false;
      }
      var csrf = csrfInput ? csrfInput.value : getCookie('csrftoken');
      var fd = new FormData();
      fd.append('job_id', jid);
      return fetch(dismissUrl, {
        method: 'POST',
        body: fd,
        credentials: 'same-origin',
        headers: { 'X-CSRFToken': csrf }
      })
        .then(function (r) {
          return r.json().then(function (data) {
            if (!r.ok || !data.ok) {
              throw new Error((data && data.error) || ('HTTP ' + r.status));
            }
            return data;
          });
        })
        .then(function (data) {
          if (banner) {
            banner.hidden = true;
            banner.removeAttribute('data-job-id');
          }
          alert(data.message || '已解除占用');
          return true;
        })
        .catch(function (e) {
          alert('解除失败：' + (e.message || e));
          return false;
        });
    });
  }

  function initBanner(options) {
    options = options || {};
    var banner = document.getElementById('roi-active-job-banner');
    if (!banner) return null;

    var activeUrl = banner.getAttribute('data-active-url') || options.activeUrl;
    var dismissUrl = banner.getAttribute('data-dismiss-url') || options.dismissUrl;
    var csrfInput = options.csrfInput || document.querySelector('[name=csrfmiddlewaretoken]');
    var pollTimer = null;
    var bound = banner.getAttribute('data-banner-bound');

    function refresh() {
      return refreshActiveBanner(banner, activeUrl);
    }

    if (!bound) {
      banner.setAttribute('data-banner-bound', '1');
      banner.addEventListener('click', function (ev) {
        var target = ev.target;
        if (!target || !target.id) return;
        if (target.id === 'btn-view-active-job') {
          ev.preventDefault();
          resolveJobId(banner, activeUrl).then(function (jid) {
            if (!jid) {
              alert('未找到进行中的任务，请刷新页面');
              refresh();
              return;
            }
            banner.setAttribute('data-job-id', jid);
            if (typeof options.onViewProgress === 'function') {
              options.onViewProgress(jid);
            } else {
              var base = options.computeUrl || '/compute-roi/';
              window.location.href = base + (base.indexOf('?') >= 0 ? '&' : '?') + 'job_id=' + encodeURIComponent(jid);
            }
          });
        } else if (target.id === 'btn-dismiss-active-job') {
          ev.preventDefault();
          dismissActiveJob(banner, dismissUrl, csrfInput, activeUrl).then(function (ok) {
            if (ok && typeof options.onDismissed === 'function') {
              options.onDismissed();
            }
          });
        }
      });
    }

    if (activeUrl) {
      pollTimer = setInterval(refresh, options.pollIntervalMs || 5000);
      refresh();
    }

    return {
      banner: banner,
      refresh: refresh,
      updateFromJob: function (job) { updateActiveBannerFromJob(banner, job); },
      stop: function () {
        if (pollTimer) {
          clearInterval(pollTimer);
          pollTimer = null;
        }
      }
    };
  }

  function initNavIndicator(options) {
    options = options || {};
    var el = document.getElementById('nav-wizard-job');
    if (!el) return null;

    var activeUrl = el.getAttribute('data-active-url') || options.activeUrl;
    var computeUrl = el.getAttribute('data-compute-url') || options.computeUrl || '/compute-roi/';
    var pollTimer = null;

    function render(job) {
      if (!job || job.is_terminal) {
        el.hidden = true;
        el.removeAttribute('href');
        return;
      }
      el.hidden = false;
      el.href = computeUrl + (computeUrl.indexOf('?') >= 0 ? '&' : '?') + 'job_id=' + encodeURIComponent(job.job_id);
      var label = el.querySelector('.nav-wizard-job__label');
      if (label) {
        label.textContent = '计算任务 · ' + (job.status_label || job.status || '进行中');
      }
      el.title = (job.status_hint || job.last_progress || '').slice(0, 240);
    }

    function refresh() {
      if (!activeUrl) return;
      fetch(activeUrl, { credentials: 'same-origin' })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (data) {
          if (!data || !data.ok || !data.has_active) {
            render(null);
            return;
          }
          render(data.active_job);
        })
        .catch(function () {});
    }

    refresh();
    pollTimer = setInterval(refresh, options.pollIntervalMs || 5000);

    return {
      refresh: refresh,
      stop: function () {
        if (pollTimer) {
          clearInterval(pollTimer);
          pollTimer = null;
        }
      }
    };
  }

  global.WizardActiveJob = {
    initBanner: initBanner,
    initNavIndicator: initNavIndicator,
    updateActiveBannerFromJob: updateActiveBannerFromJob
  };
})(window);

/*
============================================================
    Template Name: Admio - AI Bootstrap 5 Admin Dashboard Template
    Author: Themiverse
    Support: techsupport@themiverse.com
    Description: Admio - AI Bootstrap 5 Admin Dashboard Template
    Version: 1.0
    
============================================================
  TABLE OF CONTENTS
  01. DOM Ready Init
  02. Sidebar — Toggle / Collapse / Mobile / Dropdowns
  03. Theme — Dark / Light Mode Toggle
  04. Active Navigation
  05. Topbar — Search / Notifications / User Dropdown
  06. AI Insight Banner
  07. Stat Animations (Count-up + Progress Fill)
  08. Data Table Search (Inline)
  09. Settings Tabs
  10. AI Chat Interface
  11. File Upload (Drag & Drop + Preview)
  12. Modal System
  13. Toast Notifications
  14. Form Validation
  15. Calendar (Vanilla JS)
  16. Charts Theme Update
  17. DataTables Init
  18. Tooltips
  19. Keyboard Shortcuts
  20. Utilities
  21. REUSABLE PAGINATION
  22. Auth
  23. Maps
  24. Form Wizard
  25. Maintenance Countdown
  26. Gallery Upload Modal
============================================================ */

'use strict';

/* ============================================================
   01. DOM READY INIT
   ============================================================ */
document.addEventListener('DOMContentLoaded', function () {
  initSidebar();
  initTheme();
  initActiveNav();
  initTopbar();
  initAIBanner();
  initStatAnimations();
  initTableSearch();
  initSettingsTabs();
  initAIChat();
  initFileUpload();
  initModals();
  initGlobalActions();
  initFormValidation();
  initTooltips();
  initKeyboardShortcuts();
  initPageFadeIn();
  initAutoPagination();
  initbacktoTop();
});

/* ============================================================
   02. SIDEBAR
   ============================================================ */
function initSidebar() {
  const sidebar = document.getElementById('admioSidebar');
  const main = document.getElementById('admioMain');
  const toggle = document.getElementById('sidebarToggle');
  const close = document.getElementById('sidebarClose');
  const overlay = document.getElementById('sidebarOverlay');
  const collapse = document.getElementById('sidebarCollapseToggle');

  if (!sidebar) return;

  const isMobile = () => window.innerWidth < 992;

  // Restore collapsed state on desktop
  const wasCollapsed = localStorage.getItem('admioSidebarCollapsed') === 'true';
  if (!isMobile() && wasCollapsed) {
    sidebar.classList.add('collapsed');
    if (main) main.classList.add('sidebar-collapsed');
    if (collapse) updateCollapseIcon(collapse, true);
  }

  // Main toggle: hamburger
  if (toggle) {
    toggle.addEventListener('click', function () {
      if (isMobile()) {
        openMobileSidebar();
      } else {
        const isCollapsed = sidebar.classList.toggle('collapsed');
        if (main) main.classList.toggle('sidebar-collapsed', isCollapsed);
        localStorage.setItem('admioSidebarCollapsed', isCollapsed);
        if (collapse) updateCollapseIcon(collapse, isCollapsed);
      }
    });
  }

  // Desktop collapse toggle button
  if (collapse) {
    collapse.addEventListener('click', function () {
      const isCollapsed = sidebar.classList.toggle('collapsed');
      if (main) main.classList.toggle('sidebar-collapsed', isCollapsed);
      localStorage.setItem('admioSidebarCollapsed', isCollapsed);
      updateCollapseIcon(collapse, isCollapsed);
    });
  }

  function updateCollapseIcon(btn, collapsed) {
    const icon = btn.querySelector('i');
    if (!icon) return;
    icon.className = collapsed ? 'icon-chevron-right' : 'icon-chevron-left';
  }

  // Mobile close
  if (close) close.addEventListener('click', closeMobileSidebar);
  if (overlay) overlay.addEventListener('click', closeMobileSidebar);

  function openMobileSidebar() {
    sidebar.classList.add('mobile-open');
    if (overlay) overlay.classList.add('active');
    document.body.style.overflow = 'hidden';
  }
  function closeMobileSidebar() {
    sidebar.classList.remove('mobile-open');
    if (overlay) overlay.classList.remove('active');
    document.body.style.overflow = '';
  }

  window.addEventListener('resize', function () {
    if (!isMobile()) closeMobileSidebar();
  });

  // Nav dropdowns
  document.querySelectorAll('.nav-item.has-dropdown').forEach(function (item) {
    const toggle = item.querySelector('.nav-dropdown-toggle');
    if (!toggle) return;
    toggle.addEventListener('click', function (e) {
      e.preventDefault();
      const isOpen = item.classList.toggle('open');
      // Close siblings
      item.closest('.nav-list') && item.closest('.nav-list').querySelectorAll('.has-dropdown').forEach(function (sib) {
        if (sib !== item) sib.classList.remove('open');
      });
    });
  });

  // Auto-open dropdown containing active link
  document.querySelectorAll('.nav-dropdown-menu .nav-link.active').forEach(function (link) {
    const dropdown = link.closest('.has-dropdown');
    if (dropdown) dropdown.classList.add('open');
  });
}

/* ============================================================
   03. THEME
   ============================================================ */

// Header switch
document.addEventListener("DOMContentLoaded", function () {
  var dm = document.getElementById("darkModeToggle");
  if (dm) {
    dm.checked = document.documentElement.getAttribute("data-theme") === "dark";
    dm.addEventListener("change", function () {
      document.documentElement.setAttribute("data-theme", this.checked ? "dark" : "light");
      localStorage.setItem("admioTheme", this.checked ? "dark" : "light");
    });
  }
});

// setting tab switch
function initTheme() {
  const toggleBtn = document.getElementById('themeToggle');
  const themeIcon = document.getElementById('themeIcon');
  const html = document.documentElement;

  const saved = localStorage.getItem('admioTheme') || 'light';
  applyTheme(saved);

  if (toggleBtn) {
    toggleBtn.addEventListener('click', function () {
      const current = html.getAttribute('data-theme');
      applyTheme(current === 'dark' ? 'light' : 'dark');
    });
  }

  function applyTheme(theme) {
    html.setAttribute('data-theme', theme);
    localStorage.setItem('admioTheme', theme);
    if (themeIcon) {
      themeIcon.className = theme === 'dark' ? 'icon-sun' : 'icon-moon';
    }
    // Update charts if available
    if (typeof window.admioUpdateChartsTheme === 'function') {
      setTimeout(window.admioUpdateChartsTheme, 50);
    }
  }
}

  // ---- Back to Top ----
  function initbacktoTop() {
  const btt = document.getElementById('backToTop');
  if (btt) {
    window.addEventListener('scroll', () => {
      btt.classList.toggle('visible', window.scrollY > 400);
    }, {passive:true});
    btt.addEventListener('click', () => {
      window.scrollTo({top:0, behavior:'smooth'});
    });
  }
}
/* ============================================================
   04. ACTIVE NAVIGATION
   ============================================================ */
function initActiveNav() {
  const page = location.pathname.split('/').pop() || 'index.html';
  document.querySelectorAll('.nav-link').forEach(function (link) {
    const href = (link.getAttribute('href') || '').split('/').pop();
    if (href && href === page) {
      link.classList.add('active');
      // Expand parent dropdown
      const parent = link.closest('.has-dropdown');
      if (parent) parent.classList.add('open');
    }
  });
}

/* ============================================================
   05. TOPBAR
   ============================================================ */
function initTopbar() {
  const notifBtn          = document.getElementById('notifBtn');
  const notifPanel        = document.getElementById('notifPanel');
  const topbarUser        = document.querySelector('.topbar-user');
  const userDropdownMenu  = document.querySelector('.user-dropdown-menu');
  const sidebarUserTrigger = document.getElementById('sidebarUserTrigger');
  const sidebarProfilePopup = document.getElementById('sidebarProfilePopup');
  const sidebarProfileClose = document.getElementById('sidebarProfileClose');

  // Close every topbar dropdown/panel at once
  function closeAllTopbarDropdowns() {
    notifPanel        && notifPanel.classList.remove('open');
    userDropdownMenu  && userDropdownMenu.classList.remove('open');
    sidebarProfilePopup && sidebarProfilePopup.classList.remove('open');
    document.querySelectorAll('.lang-switcher').forEach(function (el) {
      el.classList.remove('open');
    });
  }

  // Notification Panel
  if (notifBtn && notifPanel) {
    notifBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      var wasOpen = notifPanel.classList.contains('open');
      closeAllTopbarDropdowns();
      if (!wasOpen) notifPanel.classList.add('open');
    });
  }

  // User Dropdown
  if (topbarUser && userDropdownMenu) {
    topbarUser.addEventListener('click', function (e) {
      e.stopPropagation();
      var wasOpen = userDropdownMenu.classList.contains('open');
      closeAllTopbarDropdowns();
      if (!wasOpen) userDropdownMenu.classList.add('open');
    });
  }

  // Sidebar profile popup
  if (sidebarUserTrigger && sidebarProfilePopup) {
    sidebarUserTrigger.addEventListener('click', function (e) {
      e.stopPropagation();
      var wasOpen = sidebarProfilePopup.classList.contains('open');
      closeAllTopbarDropdowns();
      if (!wasOpen) sidebarProfilePopup.classList.add('open');
    });
    sidebarProfilePopup.addEventListener('click', function (e) {
      e.stopPropagation();
    });
  }
  if (sidebarProfileClose) {
    sidebarProfileClose.addEventListener('click', function (e) {
      e.stopPropagation();
      sidebarProfilePopup && sidebarProfilePopup.classList.remove('open');
    });
  }

  // Language Switcher
  document.querySelectorAll('.lang-switcher').forEach(function (switcher) {
    const langBtn      = switcher.querySelector('.lang-btn');
    const langDropdown = switcher.querySelector('.lang-dropdown');
    const langSearch   = switcher.querySelector('.lang-search');
    const langList     = switcher.querySelector('.lang-list');
    const labelEl      = switcher.querySelector('.lang-label');

    if (!langBtn) return;

    langBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      var wasOpen = switcher.classList.contains('open');
      closeAllTopbarDropdowns();
      if (!wasOpen) {
        switcher.classList.add('open');
        setTimeout(function () { langSearch && langSearch.focus(); }, 150);
      }
    });

    langDropdown && langDropdown.addEventListener('click', function (e) {
      e.stopPropagation();
    });

    langList && langList.querySelectorAll('.lang-item').forEach(function (item) {
      item.addEventListener('click', function () {
        const abbr    = this.dataset.abbr || this.dataset.lang;
        const flagEl  = this.querySelector('.lang-flag');
        const flagCode = flagEl ? (flagEl.dataset.code || '') : '';

        if (labelEl) labelEl.textContent = abbr;

        const flagBtnEl = switcher.querySelector('.lang-flag-btn');
        if (flagBtnEl && flagCode) {
          flagBtnEl.src = 'assets/img/flags/' + flagCode + '.svg';
          flagBtnEl.alt = flagCode.toUpperCase();
          flagBtnEl.dataset.code = flagCode;
        }

        langList.querySelectorAll('.lang-item').forEach(function (el) {
          el.classList.remove('active');
        });
        this.classList.add('active');
        switcher.classList.remove('open');

        if (langSearch) {
          langSearch.value = '';
          filterLangItems('');
        }
      });
    });

    function filterLangItems(q) {
      const query = q.toLowerCase().trim();
      let visible = 0;
      langList && langList.querySelectorAll('.lang-item').forEach(function (item) {
        const name  = (item.dataset.name || '').toLowerCase();
        const code  = (item.dataset.lang || '').toLowerCase();
        const match = !query || name.includes(query) || code.includes(query);
        item.style.display = match ? '' : 'none';
        if (match) visible++;
      });
      const noRes = langDropdown && langDropdown.querySelector('.lang-no-results');
      if (noRes) noRes.style.display = visible === 0 ? 'flex' : 'none';
    }

    langSearch && langSearch.addEventListener('input', function () {
      filterLangItems(this.value);
    });
  });

  // Close everything on outside click (single listener)
  document.addEventListener('click', closeAllTopbarDropdowns);

  // Search input — Escape blurs
  const searchInput = document.querySelector('.search-input');
  if (searchInput) {
    searchInput.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') searchInput.blur();
    });
  }
}
/* ============================================================
   06. AI INSIGHT BANNER
   ============================================================ */
function initAIBanner() {
  const closeBtn = document.querySelector('.ai-banner-close');
  const banner = document.querySelector('.ai-insight-banner');
  if (closeBtn && banner) {
    closeBtn.addEventListener('click', function () {
      banner.style.opacity = '0';
      banner.style.transform = 'translateY(-10px)';
      setTimeout(function () { banner.remove(); }, 300);
    });
  }
}

/* ============================================================
   07. STAT ANIMATIONS
   ============================================================ */
function initStatAnimations() {
  // Count-up animation
  const statValues = document.querySelectorAll('.stat-value[data-target]');
  statValues.forEach(function (el) {
    const target = parseFloat(el.getAttribute('data-target'));
    const prefix = el.getAttribute('data-prefix') || '';
    const suffix = el.getAttribute('data-suffix') || '';
    const isFloat = target % 1 !== 0;
    const duration = 1200;
    const start = performance.now();
    el.textContent = prefix + '0' + suffix;

    function step(now) {
      const elapsed = now - start;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      const current = target * eased;
      const display = isFloat
        ? current.toFixed(1)
        : Math.floor(current).toLocaleString();
      el.textContent = prefix + display + suffix;
      if (progress < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  });

  // Progress fill
  document.querySelectorAll('.progress-fill[style]').forEach(function (el) {
    const targetWidth = el.style.width;
    el.style.width = '0';
    setTimeout(function () { el.style.width = targetWidth; }, 100);
  });
}

/* ============================================================
   08. INLINE TABLE SEARCH
   ============================================================ */
function initTableSearch() {
  document.querySelectorAll('[data-table-search]').forEach(function (input) {
    const tableId = input.getAttribute('data-table-search');
    const table = document.getElementById(tableId);
    if (!table) return;
    input.addEventListener('input', function () {
      const q = input.value.toLowerCase().trim();
      table.querySelectorAll('tbody tr').forEach(function (row) {
        row.style.display = row.textContent.toLowerCase().includes(q) ? '' : 'none';
      });
    });
  });
}

/* ============================================================
   09. SETTINGS TABS
   ============================================================ */
function initSettingsTabs() {
  const tabs = document.querySelectorAll('.settings-tab');
  tabs.forEach(function (tab) {
    tab.addEventListener('click', function () {
      tabs.forEach(function (t) { t.classList.remove('active'); });
      document.querySelectorAll('.settings-panel').forEach(function (p) { p.classList.remove('active'); });
      tab.classList.add('active');
      const panelId = 'tab-' + tab.getAttribute('data-tab');
      const panel = document.getElementById(panelId);
      if (panel) panel.classList.add('active');
    });
  });
}

/* ============================================================
   10. AI CHAT
   ============================================================ */
function initAIChat() {
  const sendBtn = document.getElementById('chatSendBtn');
  const chatInput = document.getElementById('chatInput');
  const messages = document.getElementById('chatMessages');

  if (!sendBtn || !chatInput || !messages) return;

  const aiResponses = [
    'Based on your data, I can see some interesting patterns. Revenue is trending upward by 18.3% this quarter, with AI-generated leads converting at 2.4x the rate of traditional channels.',
    'Analysing your current AI model performance: the GPT-4 integration is achieving 94.2% accuracy across all prediction tasks. I recommend fine-tuning on your Q4 dataset to push this to 97%+.',
    'I\'ve identified 3 customers at high churn risk in the next 30 days. Recommend sending personalised retention offers within 48 hours — historical data shows 68% effectiveness.',
    'Your API usage is up 340% this month. The top use cases are: content generation (42%), data analysis (28%), and customer service automation (18%). Current cost: $2,847/month.',
    'Looking at your prompt library, the top 5 most effective prompts have a 91% user satisfaction rating. I can help you optimise the underperforming ones if you\'d like.',
    'The latest AI model training completed with 97.1% validation accuracy. Loss curves look healthy — no overfitting detected. Ready to deploy to production.',
    'I\'ve generated the weekly performance report: 24,840 total AI requests, 99.8% uptime, average response time 1.2s. Full report attached.',
  ];

  function sendMessage() {
    const text = chatInput.value.trim();
    if (!text) return;

    // User message
    appendMessage('user', text);
    chatInput.value = '';
    chatInput.style.height = 'auto';

    // AI typing indicator
    const typingEl = document.createElement('div');
    typingEl.className = 'chat-message';
    typingEl.innerHTML = `
      <div class="chat-avatar ai-avatar"><i class="icon-brain"></i></div>
      <div>
        <div class="typing-indicator">
          <div class="typing-dot"></div>
          <div class="typing-dot"></div>
          <div class="typing-dot"></div>
        </div>
      </div>`;
    messages.appendChild(typingEl);
    messages.scrollTop = messages.scrollHeight;

    // AI response
    setTimeout(function () {
      typingEl.remove();
      const response = aiResponses[Math.floor(Math.random() * aiResponses.length)];
      appendMessage('ai', response);
    }, 1200 + Math.random() * 600);
  }

  function appendMessage(type, text) {
    const isAI = type === 'ai';
    const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const avatar = isAI
      ? '<div class="chat-avatar ai-avatar"><i class="icon-brain"></i></div>'
      : ' <span class="avatar-gen avatar avatar-md" data-name="Alex K" data-bg="#7C3AED" data-size="38">AK</span>';
    const bubble = `<div class="chat-bubble">${escapeHtml(text).replace(/\n/g, '<br>')}</div>
                    <span class="chat-time">${time} · ${isAI ? 'Admio AI' : 'You'}</span>`;
    const el = document.createElement('div');
    el.className = `chat-message${isAI ? ' ai-message ' : ' user-message'} fade-in`;
    el.innerHTML = isAI ? `${avatar}<div>${bubble}</div>` : `${avatar}<div>${bubble}</div>`;
    messages.appendChild(el);
    messages.scrollTop = messages.scrollHeight;
  }

  sendBtn.addEventListener('click', sendMessage);
  chatInput.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });

  // Auto-resize textarea
  chatInput.addEventListener('input', function () {
    this.style.height = 'auto';
    this.style.height = Math.min(this.scrollHeight, 120) + 'px';
  });

  // Prompt chips
  document.querySelectorAll('.prompt-chip').forEach(function (chip) {
    chip.addEventListener('click', function () {
      chatInput.value = chip.textContent.trim();
      chatInput.focus();
    });
  });
}
/* ── ai chat model ─────────────────────────────────────────── */
document.getElementById("modelSelect") && document.getElementById("modelSelect").addEventListener("change", function () {
  document.getElementById("currentModel").textContent = this.value;
});
/* ============================================================
   11. FILE UPLOAD
   ============================================================ */
function initFileUpload() {
  document.querySelectorAll('.file-upload-zone').forEach(function (zone) {
    const input = zone.querySelector('input[type="file"]');
    const listId = zone.getAttribute('data-file-list');
    const fileList = listId ? document.getElementById(listId) : null;

    // Drag events
    zone.addEventListener('dragover', function (e) { e.preventDefault(); zone.classList.add('dragover'); });
    zone.addEventListener('dragleave', function () { zone.classList.remove('dragover'); });
    zone.addEventListener('drop', function (e) {
      e.preventDefault();
      zone.classList.remove('dragover');
      handleFiles(e.dataTransfer.files);
    });

    if (input) {
      input.addEventListener('change', function () { handleFiles(this.files); });
    }

    function handleFiles(files) {
      if (!files || !files.length) return;
      Array.from(files).forEach(function (file) {
        if (fileList) renderFileItem(file, fileList);
      });
      showToast('success', files.length + ' file(s) added successfully', 'circle-check');
    }

    function renderFileItem(file, container) {
      const size = formatFileSize(file.size);
      const icon = getFileIcon(file.name);
      const item = document.createElement('div');
      item.className = 'file-list-item';
      item.innerHTML = `
        <div class="file-list-icon text-primary-c" style="background:var(--tmv-primary-xlight)">
          <i class="icon-${icon}"></i>
        </div>
        <span class="file-list-name">${escapeHtml(file.name)}</span>
        <span class="file-list-size">${size}</span>
        <button class="file-list-remove" title="Remove"><i class="icon-x"></i></button>`;
      item.querySelector('.file-list-remove').addEventListener('click', function () {
        item.style.opacity = '0';
        setTimeout(function () { item.remove(); }, 200);
      });
      container.appendChild(item);
    }
  });
}

function formatFileSize(bytes) {
  if (bytes === 0) return '0 B';
  const k = 1024, sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function getFileIcon(name) {
  const ext = name.split('.').pop().toLowerCase();
  const map = {
    pdf: 'file-text', doc: 'file-text', docx: 'file-text', xls: 'file-spreadsheet', xlsx: 'file-spreadsheet',
    ppt: 'file-text', pptx: 'file-text', png: 'image', jpg: 'image', jpeg: 'image', gif: 'image',
    svg: 'image', mp4: 'file-video', mp3: 'file-audio-2', zip: 'archive', rar: 'archive',
    js: 'file-code-2', css: 'file-code-2', html: 'file-code-2', py: 'file-code-2', json: 'file-code-2', csv: 'file-spreadsheet'
  };
  return map[ext] || 'file';
}

/* ============================================================
   12. MODAL SYSTEM
   ============================================================ */
function initModals() {
  // Open modals
  document.querySelectorAll('[data-modal]').forEach(function (trigger) {
    trigger.addEventListener('click', function (e) {
      e.preventDefault();
      const modalId = trigger.getAttribute('data-modal');
      openModal(modalId);
    });
  });

  // Close buttons inside modals
  document.querySelectorAll('.admio-modal-close, [data-modal-close]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      const backdrop = btn.closest('.admio-modal-backdrop');
      if (backdrop) closeModalBackdrop(backdrop);
    });
  });

  // Close on backdrop click
  document.querySelectorAll('.admio-modal-backdrop').forEach(function (backdrop) {
    backdrop.addEventListener('click', function (e) {
      if (e.target === backdrop) closeModalBackdrop(backdrop);
    });
  });

  // Esc key
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      document.querySelectorAll('.admio-modal-backdrop.open').forEach(closeModalBackdrop);
    }
  });
}

function openModal(id) {
  const backdrop = document.getElementById(id);
  if (backdrop) {
    backdrop.classList.add('open');
    document.body.style.overflow = 'hidden';
  }
}

function closeModalBackdrop(backdrop) {
  backdrop.classList.remove('open');
  document.body.style.overflow = '';
}

/* ── Expose globally ─────────────────────────────────────────── */
window.openModal = openModal;
window.closeModal = function (id) {
  const backdrop = document.getElementById(id);
  if (backdrop) closeModalBackdrop(backdrop);
};

/* ============================================================
   13. TOAST NOTIFICATIONS
   ============================================================ */
function showToast(type, message, icon, duration) {
  duration = duration || 4000;
  icon = icon || (type === 'success' ? 'circle-check' : type === 'error' ? 'circle-x' : type === 'warning' ? 'triangle-alert' : 'info');

  let container = document.getElementById('toastContainer');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toastContainer';
    container.className = 'toast-container';
    document.body.appendChild(container);
  }

  const colors = { success: 'var(--tmv-success)', error: 'var(--tmv-danger)', warning: 'var(--tmv-warning)', info: 'var(--tmv-info)' };
  const color = colors[type] || colors.info;

  const toast = document.createElement('div');
  toast.className = 'toast-item';
  toast.innerHTML = `
    <i class="icon-${icon}" style="color:${color};font-size:16px;flex-shrink:0"></i>
    <span style="flex:1;font-size:13px">${escapeHtml(message)}</span>
    <button onclick="this.parentElement.remove()" style="background:none;border:none;cursor:pointer;color:var(--tmv-text-muted);font-size:14px;padding:0;flex-shrink:0">
      <i class="icon-x"></i>
    </button>`;
  container.appendChild(toast);

  setTimeout(function () {
    if (toast.parentElement) {
      toast.classList.add('removing');
      setTimeout(function () { toast.remove(); }, 300);
    }
  }, duration);
}

/* ── Expose globally ─────────────────────────────────────────── */
window.showToast = showToast;

/* ============================================================
   14. FORM VALIDATION
   ============================================================ */
function initFormValidation() {
  document.querySelectorAll('form[data-validate]').forEach(function (form) {
    form.addEventListener('submit', function (e) {
      let valid = true;
      form.querySelectorAll('[required]').forEach(function (field) {
        const val = field.value.trim();
        if (!val) {
          field.classList.add('is-invalid');
          field.classList.remove('is-valid');
          valid = false;
        } else {
          field.classList.remove('is-invalid');
          field.classList.add('is-valid');
        }
      });
      if (!valid) {
        e.preventDefault();
        showToast('error', 'Please fill in all required fields', 'circle-x');
      }
    });

    // Live validation
    form.querySelectorAll('[required]').forEach(function (field) {
      field.addEventListener('blur', function () {
        if (!field.value.trim()) {
          field.classList.add('is-invalid');
          field.classList.remove('is-valid');
        } else {
          field.classList.remove('is-invalid');
          field.classList.add('is-valid');
        }
      });
    });
  });
}
/* ── advance form ─────────────────────────────────────────── */
document.addEventListener("DOMContentLoaded", function () {
  var form = document.getElementById("advForm");
  if (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      showToast("success", "Form submitted successfully!", "circle-check");
    });
  }
  // Password strength
  var pwd = document.getElementById("advPwd");
  if (pwd) {
    pwd.addEventListener("input", function () {
      var v = this.value;
      var bars = document.querySelectorAll("#strengthBar div");
      var strength = 0;
      if (v.length >= 8) strength++;
      if (/[0-9]/.test(v)) strength++;
      if (/[A-Z]/.test(v)) strength++;
      if (/[^A-Za-z0-9]/.test(v)) strength++;
      var colors = ["var(--tmv-danger)", "var(--tmv-warning)", "var(--tmv-success)", "var(--tmv-success)"];
      bars.forEach(function (b, i) {
        b.style.background = i < strength ? colors[strength - 1] : "var(--tmv-border-light)";
      });
    });
  }
});

/* ============================================================
   16. CHARTS THEME UPDATE
   ============================================================ */
window.admioGetChartDefaults = function () {
  const dark = document.documentElement.getAttribute('data-theme') === 'dark';
  return {
    gridColor: dark ? 'rgba(255,255,255,0.10)' : 'rgba(0,0,0,0.06)',
    textColor: dark ? '#94A3B8' : '#6B7280',
    borderColor: dark ? 'rgba(255,255,255,0.10)' : 'rgba(0,0,0,0.08)',
  };
};

/* ============================================================
   17. DATATABLES INIT
   ============================================================ */
window.initDataTable = function (tableId, options) {
  if (typeof $.fn === 'undefined' || typeof $.fn.DataTable === 'undefined') return;
  const defaults = {
    pageLength: 10,
    responsive: true,
    dom: "<'row align-items-center mb-3 justify-content-between'<'col-sm-6'l><'col-sm-6'f>>t<'row align-items-center mt-3 justify-content-between'<'col-sm-6'i><'col-sm-6'p>>",
    language: {
      search: '',
      searchPlaceholder: 'Search...',
      lengthMenu: '_MENU_ per page',
      info: 'Showing _START_ to _END_ of _TOTAL_ records',
      paginate: { first: '‹‹', last: '››', next: '›', previous: '‹' },
    }
  };
  $('#' + tableId).DataTable(Object.assign({}, defaults, options || {}));
};

document.addEventListener("DOMContentLoaded", function () {
  if (typeof $ !== "undefined" && $.fn.DataTable) {
    window.initDataTable("mainDataTable");
  }
});
/* ── Grid tables ─────────────────────────────────────────── */
document.addEventListener("DOMContentLoaded", function () {
  if (typeof gridjs === "undefined") return;

  new gridjs.Grid({
    columns: [
      { name: "#", width: "50px" },
      { name: "Model", sort: true },
      { name: "Provider", sort: true },
      { name: "Accuracy", sort: true, formatter: function (v) { return gridjs.html("<div style='display:flex;align-items:center;gap:8px'><div style='width:60px;height:5px;border-radius:3px;background:var(--tmv-border-light);overflow:hidden'><div style='height:100%;width:" + v + "%;background:var(--tmv-primary)'></div></div><span style='font-weight:700;font-size:12px'>" + v + "%</span></div>"); } },
      { name: "Cost/1K", sort: true },
      { name: "Context" },
      { name: "Status", formatter: function (v) { var c = v === "Active" ? "var(--tmv-success)" : "var(--tmv-warning)"; return gridjs.html("<span style='display:inline-flex;align-items:center;gap:5px;padding:3px 9px;border-radius:100px;background:rgba(16,185,129,0.1);color:" + c + ";font-size:11px;font-weight:700'><span style='width:6px;height:6px;border-radius:50%;background:" + c + "'></span>" + v + "</span>"); } },
    ],
    data: [
      ["1", "GPT-4 Turbo", "OpenAI", 97.2, "$0.045", "128K", "Active"],
      ["2", "Claude 3 Opus", "Anthropic", 96.8, "$0.035", "200K", "Active"],
      ["3", "Gemini Ultra", "Google", 94.1, "$0.040", "32K", "Active"],
      ["4", "Mistral Large", "Mistral AI", 91.4, "$0.028", "32K", "Trial"],
      ["5", "Llama 3 70B", "Meta (OSS)", 89.7, "Free", "8K", "Active"],
      ["6", "GPT-3.5 Turbo", "OpenAI", 88.2, "$0.002", "16K", "Active"],
      ["7", "Claude 3 Haiku", "Anthropic", 87.4, "$0.001", "200K", "Active"],
      ["8", "Gemini Pro", "Google", 85.6, "$0.001", "32K", "Active"],
    ],
    search: true, sort: true, pagination: { limit: 5 },
    style: { th: { "font-size": "11px", "text-transform": "uppercase", "letter-spacing": "0.7px", "color": "var(--tmv-text-muted)", "background": "var(--tmv-body-bg)", "font-weight": "700" }, td: { "font-size": "13px", "color": "var(--tmv-text-primary)", "border-color": "var(--tmv-border-light)" } },
  }).render(document.getElementById("gridTable1"));

  new gridjs.Grid({
    columns: ["Name", "Email", "Role", "Plan", "AI Requests", "Status"],
    data: [
      ["James Miller", "james@techstart.io", "Admin", "Enterprise", "8,420", "Active"],
      ["Sarah Connor", "sarah@connor.io", "Editor", "Pro", "4,284", "Active"],
      ["Emma Wilson", "emma@design.co", "Viewer", "Starter", "940", "Active"],
      ["Alex Kim", "alex@kimtech.dev", "Admin", "Enterprise", "12,840", "Active"],
      ["Lin Zhang", "lin@datasci.ai", "Editor", "Pro", "6,120", "Trial"],
      ["David Park", "david@parkdev.io", "Admin", "Enterprise", "9,840", "Active"],
      ["Maria Santos", "maria@globalco.com", "Viewer", "Starter", "180", "Trial"],
    ],
    search: true, sort: true, pagination: { limit: 5 },
    style: { th: { "font-size": "11px", "text-transform": "uppercase", "letter-spacing": "0.7px", "color": "var(--tmv-text-muted)", "background": "var(--tmv-body-bg)", "font-weight": "700" }, td: { "font-size": "13px", "color": "var(--tmv-text-primary)", "border-color": "var(--tmv-border-light)" } },
  }).render(document.getElementById("gridTable2"));

  new gridjs.Grid({
    columns: ["Transaction ID", "Method", "Amount", "Date", "Status"],
    data: [
      ["#TXN-9012", "Credit Card", "$299.00", "Nov 30", "Success"],
      ["#TXN-9011", "Bank Transfer", "$4,200.00", "Nov 28", "Success"],
      ["#TXN-9010", "PayPal", "$1,499.00", "Nov 26", "Success"],
      ["#TXN-9009", "Credit Card", "$199.00", "Nov 24", "Refunded"],
      ["#TXN-9008", "Credit Card", "$149.00", "Nov 22", "Failed"],
      ["#TXN-9007", "Bank Transfer", "$6,400.00", "Nov 20", "Success"],
    ],
    search: true, sort: true, pagination: { limit: 5 },
    style: { th: { "font-size": "11px", "text-transform": "uppercase", "letter-spacing": "0.7px", "color": "var(--tmv-text-muted)", "background": "var(--tmv-body-bg)", "font-weight": "700" }, td: { "font-size": "13px", "color": "var(--tmv-text-primary)", "border-color": "var(--tmv-border-light)" } },
  }).render(document.getElementById("gridTable3"));
});

/* ============================================================
   18. TOOLTIPS
   ============================================================ */
function initTooltips() {
  if (typeof bootstrap !== 'undefined' && bootstrap.Tooltip) {
    document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(function (el) {
      new bootstrap.Tooltip(el);
    });
  }
}

/* ============================================================
   19. KEYBOARD SHORTCUTS
   ============================================================ */
function initKeyboardShortcuts() {
  document.addEventListener('keydown', function (e) {
    const searchInput = document.querySelector('.search-input');
    // Cmd/Ctrl + K → focus search
    if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
      e.preventDefault();
      if (searchInput) { searchInput.focus(); searchInput.select(); }
    }
    // Cmd/Ctrl + D → toggle dark mode
    if ((e.metaKey || e.ctrlKey) && e.key === 'd') {
      e.preventDefault();
      const toggleBtn = document.getElementById('themeToggle');
      if (toggleBtn) toggleBtn.click();
    }
  });
}

/* ── toggle grid/list view ─────────────────────────────────────────── */
function toggleView(v) {
  document.getElementById("viewGrid").className = "btn-admio " + (v === "grid" ? "btn-primary" : "btn-ghost") + " btn-sm";
  document.getElementById("viewList").className = "btn-admio " + (v === "list" ? "btn-primary" : "btn-ghost") + " btn-sm";
  document.getElementById("viewGridContent").style.display = v === "grid" ? "block" : "none";
  document.getElementById("viewListContent").style.display = v === "list" ? "block" : "none";
}


/* ============================================================
   20. UTILITIES
   ============================================================ */
function initPageFadeIn() {
  document.body.style.opacity = '0';
  document.body.style.transition = 'opacity 0.2s ease';
  requestAnimationFrame(function () {
    document.body.style.opacity = '1';
  });
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.appendChild(document.createTextNode(str));
  return div.innerHTML;
}

/* ── Password show/hide helper ─────────────────────────────────────────── */
window.togglePasswordVisibility = function (inputId, iconId) {
  const input = document.getElementById(inputId);
  const icon = document.getElementById(iconId);
  if (!input) return;
  const isPassword = input.type === 'password';
  input.type = isPassword ? 'text' : 'password';
  if (icon) icon.className = isPassword ? 'icon-eye-off' : 'icon-eye';
};

/* ── Copy to clipboard ─────────────────────────────────────────── */
window.copyToClipboard = function (text, toastMsg) {
  navigator.clipboard.writeText(text).then(function () {
    showToast('success', toastMsg || 'Copied to clipboard!', 'copy');
  });
};

/* ── Confirm delete helper ─────────────────────────────────────────── */
window.confirmAction = function (message, callback) {
  if (window.confirm(message || 'Are you sure?')) callback();
};

/* ── Expose for external use ─────────────────────────────────────────── */
window.showToast = showToast;
window.openModal = openModal;

/* ── Enhanced Calendar with Views & Event Popup ─────────────── */
document.addEventListener('DOMContentLoaded', function () {
  initCheckboxTables();
  initAccordions();
  initAdmioTabs();
  initPopoverDemos();
  initEditUserPage();
  initCountryProgress();
});

/* ── Checkbox Tables ─────────────────────────────────────────── */
function initCheckboxTables() {
  document.querySelectorAll('.admio-table-checkable').forEach(function (table) {
    var selectAll = table.querySelector('.select-all-cb');
    var toolbar = table.closest('.admio-card') ? table.closest('.admio-card').querySelector('.table-toolbar') : null;

    function updateToolbar() {
      var checked = table.querySelectorAll('tbody input[type="checkbox"]:checked');
      if (toolbar) {
        toolbar.classList.toggle('visible', checked.length > 0);
        var countEl = toolbar.querySelector('.table-toolbar-count');
        if (countEl) countEl.textContent = checked.length + ' row' + (checked.length > 1 ? 's' : '') + ' selected';
      }
      if (selectAll) {
        var all = table.querySelectorAll('tbody input[type="checkbox"]');
        selectAll.checked = checked.length === all.length && all.length > 0;
        selectAll.indeterminate = checked.length > 0 && checked.length < all.length;
      }
    }

    if (selectAll) {
      selectAll.addEventListener('change', function () {
        table.querySelectorAll('tbody input[type="checkbox"]').forEach(function (cb) {
          cb.checked = selectAll.checked;
          cb.closest('tr').classList.toggle('selected', cb.checked);
        });
        updateToolbar();
      });
    }
    table.querySelectorAll('tbody input[type="checkbox"]').forEach(function (cb) {
      cb.addEventListener('change', function () {
        cb.closest('tr').classList.toggle('selected', cb.checked);
        updateToolbar();
      });
    });
  });
}
/* ── Pricing ─────────────────────────────────────────── */
function switchBilling(t) { var p = { monthly: { starter: "$49", pro: "$299" }, annual: { starter: "$39", pro: "$239" } }; document.getElementById("p-starter").textContent = p[t].starter; document.getElementById("p-pro").textContent = p[t].pro; document.getElementById("monthlyBtn").className = t === "monthly" ? "btn-admio btn-primary btn-xs" : "btn-admio btn-ghost btn-xs"; document.getElementById("annualBtn").className = t === "annual" ? "btn-admio btn-primary btn-xs" : "btn-admio btn-ghost btn-xs"; document.getElementById("monthlyBtn").style.borderRadius = "100px"; document.getElementById("annualBtn").style.borderRadius = "100px"; }

/* __ GLightbox _________________________________________________ */

if (typeof GLightbox !== "undefined" && document.querySelector('.glightbox')) {
  GLightbox({
    selector: '.glightbox',
    touchNavigation: true,
    loop: true
  });
}

function filterGallery(cat, btn) {
  document.querySelectorAll("#galleryFilter .gallery-filter-btn").forEach(function (b) {
    b.classList.remove("active");
  });
  btn.classList.add("active");
  document.querySelectorAll(".gallery-item").forEach(function (item) {
    item.style.display = (cat === "all" || item.getAttribute("data-category") === cat) ? "" : "none";
  });
}
/* __ Edit users _________________________________________________ */
function previewAvatar(input) {
  if (input.files && input.files[0]) {
    var reader = new FileReader();
    reader.onload = function (e) {
      document.getElementById('avatarPreview').src = e.target.result;
    };
    reader.readAsDataURL(input.files[0]);
  }
}
/* ── Accordions ──────────────────────────────────────────────── */
function initAccordions() {
  document.querySelectorAll('.accordion-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var item = btn.closest('.accordion-item');
      var isOpen = item.classList.contains('open');
      // close siblings
      item.closest('.admio-accordion') && item.closest('.admio-accordion').querySelectorAll('.accordion-item').forEach(function (i) { i.classList.remove('open'); });
      if (!isOpen) item.classList.add('open');
    });
  });
}

/* ── Tabs ────────────────────────────────────────────────────── */
function initAdmioTabs() {
  document.querySelectorAll('.admio-tab').forEach(function (tab) {
    tab.addEventListener('click', function () {
      var container = tab.closest('[data-tab-container]') || document.body;
      container.querySelectorAll('.admio-tab').forEach(function (t) { t.classList.remove('active'); });
      container.querySelectorAll('.admio-tab-pane').forEach(function (p) { p.classList.remove('active'); });
      tab.classList.add('active');
      var pane = document.getElementById('pane-' + tab.getAttribute('data-tab'));
      if (pane) pane.classList.add('active');
    });
  });
}

/* ── Popover Demos ───────────────────────────────────────────── */
function initPopoverDemos() {
  document.querySelectorAll('[data-popover]').forEach(function (el) {
    var target = document.getElementById(el.getAttribute('data-popover'));
    if (!target) return;
    el.addEventListener('click', function (e) {
      e.stopPropagation();
      var rect = el.getBoundingClientRect();
      target.style.top = (rect.bottom + 8 + window.scrollY) + 'px';
      target.style.left = rect.left + 'px';
      target.classList.toggle('open');
    });
    document.addEventListener('click', function () { target.classList.remove('open'); });
  });
}

/* ── Edit User Inline ────────────────────────────────────────── */
function initEditUserPage() {
  var editBtns = document.querySelectorAll('[data-edit-field]');
  editBtns.forEach(function (btn) {
    btn.addEventListener('click', function () {
      var fieldId = btn.getAttribute('data-edit-field');
      var display = document.getElementById('display-' + fieldId);
      var input = document.getElementById('input-' + fieldId);
      if (!display || !input) return;
      display.style.display = 'none';
      input.style.display = 'block';
      input.focus();
      btn.style.display = 'none';
      var saveBtn = document.getElementById('save-' + fieldId);
      if (saveBtn) saveBtn.style.display = 'inline-flex';
    });
  });
  document.querySelectorAll('[data-save-field]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var fieldId = btn.getAttribute('data-save-field');
      var display = document.getElementById('display-' + fieldId);
      var input = document.getElementById('input-' + fieldId);
      if (!display || !input) return;
      display.textContent = input.value;
      display.style.display = 'block';
      input.style.display = 'none';
      btn.style.display = 'none';
      var editBtn = document.querySelector('[data-edit-field="' + fieldId + '"]');
      if (editBtn) editBtn.style.display = 'inline-flex';
      showToast('success', fieldId + ' updated!', 'circle-check');
    });
  });
}

/* ── Country Progress Bars ───────────────────────────────────── */
function initCountryProgress() {
  document.querySelectorAll('.country-row').forEach(function (row) {
    var bar = row.querySelector('.progress-fill');
    if (!bar) return;
    var w = bar.getAttribute('data-width') || bar.style.width;
    bar.style.width = '0';
    setTimeout(function () { bar.style.width = w; }, 200);
  });
}

/* ── Copy Code helper ────────────────────────────────────────── */
window.copyCode = function (id) {
  var el = document.getElementById(id);
  if (el) copyToClipboard(el.textContent.trim(), 'Code copied!');
};

/* ── Calendar Week/Day Nav, File Manager, Prompts ──────────── */
document.addEventListener('DOMContentLoaded', function () {
  initEnhancedCalendar();
  initFileManager();
  initPromptLibraryTabs();
  initAgentEditModal();
  initWorkflowEditModal();
  initApiKeyReveal();
  initSharePopup();
  initPromptEditModal();
  initTransactionsPagination();
});

/* ── Enhanced Calendar V2 — fix week/day nav & click ────────── */
function initEnhancedCalendar() {
  var grid = document.getElementById('calGrid');
  if (!grid) return;

  var MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
  var DAYS_SHORT = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  var today = new Date();
  var curMonth = new Date(today.getFullYear(), today.getMonth(), 1);
  var curWeekStart = new Date(today);
  curWeekStart.setDate(today.getDate() - today.getDay());
  var curDay = new Date(today);
  var view = 'month';

  var EVENTS = [
    { id: 1, date: new Date(today.getFullYear(), today.getMonth(), 5), color: '#7C3AED', title: 'AI Model Deployment', time: '9:00 AM', desc: 'Deploy GPT-4 fine-tuned model to production', type: 'AI & Tech' },
    { id: 2, date: new Date(today.getFullYear(), today.getMonth(), 10), color: '#06B6D4', title: 'API Review Meeting', time: '2:00 PM', desc: 'Weekly API performance and cost review', type: 'Meeting' },
    { id: 3, date: new Date(today.getFullYear(), today.getMonth(), 10), color: '#10B981', title: 'Team Standup', time: '9:00 AM', desc: 'Daily sync with engineering team', type: 'Meeting' },
    { id: 4, date: new Date(today.getFullYear(), today.getMonth(), 15), color: '#F59E0B', title: 'Investor Call', time: '11:00 AM', desc: 'Q4 performance presentation to investors', type: 'Meeting' },
    { id: 5, date: new Date(today.getFullYear(), today.getMonth(), 20), color: '#EF4444', title: 'System Maintenance', time: '10:00 PM', desc: 'Scheduled server maintenance window', type: 'Deadline' },
    { id: 6, date: new Date(today.getFullYear(), today.getMonth(), 25), color: '#3B82F6', title: 'Sprint Planning', time: '10:00 AM', desc: 'Q4 Sprint 3 planning and backlog grooming', type: 'Meeting' },
    { id: 7, date: new Date(today.getFullYear(), today.getMonth(), today.getDate()), color: '#7C3AED', title: 'AI Report Review', time: '9:00 AM', desc: 'Review weekly AI performance report', type: 'AI & Tech' }
  ];

  function dateKey(d) { return d.getFullYear() + '-' + (d.getMonth() + 1) + '-' + d.getDate(); }
  function eventsForDate(d) { var k = dateKey(d); return EVENTS.filter(function (e) { return dateKey(e.date) === k; }); }

  function renderMonth() {
    var mh = document.getElementById('calMonthYear');
    if (mh) mh.textContent = MONTHS[curMonth.getMonth()] + ' ' + curMonth.getFullYear();
    var first = new Date(curMonth.getFullYear(), curMonth.getMonth(), 1).getDay();
    var days = new Date(curMonth.getFullYear(), curMonth.getMonth() + 1, 0).getDate();
    var prev = new Date(curMonth.getFullYear(), curMonth.getMonth(), 0).getDate();
    var html = '';
    for (var i = first - 1; i >= 0; i--) html += '<div class="cal-day other-month"><div class="cal-day-num">' + (prev - i) + '</div></div>';
    for (var d = 1; d <= days; d++) {
      var dd = new Date(curMonth.getFullYear(), curMonth.getMonth(), d);
      var isToday = d === today.getDate() && curMonth.getMonth() === today.getMonth() && curMonth.getFullYear() === today.getFullYear();
      var evts = eventsForDate(dd);
      var evtHtml = evts.map(function (e) { return '<div class="cal-event" style="background:' + e.color + '" data-event-id="' + e.id + '">' + e.title + '</div>'; }).join('');
      html += '<div class="cal-day' + (isToday ? ' today' : '') + '" data-date="' + dateKey(dd) + '">' + '<div class="cal-day-num">' + d + '</div>' + evtHtml + '</div>';
    }
    var rem = (7 - ((first + days) % 7)) % 7;
    for (var n = 1; n <= rem; n++) html += '<div class="cal-day other-month"><div class="cal-day-num">' + n + '</div></div>';
    grid.innerHTML = html;
    attachMonthClicks();
  }

  function attachMonthClicks() {
    grid.querySelectorAll('.cal-day:not(.other-month)').forEach(function (day) {
      day.addEventListener('click', function (e) {
        if (e.target.classList.contains('cal-event')) return;
        openModal('addEventModal');
      });
    });
    grid.querySelectorAll('.cal-event').forEach(function (ev) {
      ev.addEventListener('click', function (e) {
        e.stopPropagation();
        var id = parseInt(ev.getAttribute('data-event-id'));
        var evt = EVENTS.find(function (x) { return x.id === id; });
        if (evt) showEventPopup(e, evt);
      });
    });
  }

  function renderWeek() {
    var mh = document.getElementById('calMonthYear');
    var endOfWeek = new Date(curWeekStart); endOfWeek.setDate(curWeekStart.getDate() + 6);
    if (mh) mh.textContent = MONTHS[curWeekStart.getMonth()] + ' ' + curWeekStart.getDate() + ' – ' + MONTHS[endOfWeek.getMonth()] + ' ' + endOfWeek.getDate() + ', ' + endOfWeek.getFullYear();
    var colStyle = 'display:grid;grid-template-columns:64px repeat(7,1fr);min-width:600px';
    var html = '<div style="' + colStyle + '">';
    // Header row with day labels
    html += '<div style="background:var(--tmv-body-bg);padding:10px;border-right:1px solid var(--tmv-border-light);border-bottom:2px solid var(--tmv-border-light)"></div>';
    for (var i = 0; i < 7; i++) {
      var d = new Date(curWeekStart); d.setDate(curWeekStart.getDate() + i);
      var isT = d.toDateString() === today.toDateString();
      html += '<div style="background:' + (isT ? 'var(--tmv-primary-xlight)' : 'var(--tmv-card-bg)') + ';text-align:center;padding:10px 4px;border-left:1px solid var(--tmv-border-light);border-bottom:2px solid var(--tmv-border-light)">' +
        '<div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;color:' + (isT ? 'var(--tmv-primary)' : 'var(--tmv-text-muted)') + '">' + DAYS_SHORT[d.getDay()] + '</div>' +
        '<div style="font-size:22px;font-weight:800;line-height:1.1;color:' + (isT ? 'var(--tmv-primary)' : 'var(--tmv-text-primary)') + '">' + d.getDate() + '</div></div>';
    }
    // Hour rows
    var hours = [7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18];
    hours.forEach(function (h) {
      var label = h < 12 ? h + ':00 AM' : (h === 12 ? '12:00 PM' : (h - 12) + ':00 PM');
      html += '<div style="background:var(--tmv-card-bg);padding:4px 8px;font-size:10px;color:var(--tmv-text-muted);text-align:right;border-top:1px solid var(--tmv-border-light);border-right:1px solid var(--tmv-border-light)">' + label + '</div>';
      for (var i = 0; i < 7; i++) {
        var d = new Date(curWeekStart); d.setDate(curWeekStart.getDate() + i);
        var evts = eventsForDate(d).filter(function (e) { var hh = parseInt(e.time); return hh === h || (e.time.includes(String(h) + ':') && h < 12); });
        var evtHtml = evts.map(function (e) { return '<div class="cal-week-event" style="background:' + e.color + ';color:#fff;border-radius:4px;padding:2px 6px;font-size:11px;font-weight:600;margin-bottom:2px;cursor:pointer" data-event-id="' + e.id + '">' + e.time + ' ' + e.title + '</div>'; }).join('');
        html += '<div style="background:var(--tmv-card-bg);border-top:1px solid var(--tmv-border-light);border-left:1px solid var(--tmv-border-light);min-height:52px;padding:2px;cursor:pointer" data-week-slot="' + dateKey(d) + '-' + h + '">' + evtHtml + '</div>';
      }
    });
    html += '</div>';
    grid.innerHTML = html;
    // Slot clicks open add event modal
    grid.querySelectorAll('[data-week-slot]').forEach(function (slot) {
      slot.addEventListener('click', function (e) {
        if (e.target.closest('.cal-week-event')) return;
        openModal('addEventModal');
      });
    });
    grid.querySelectorAll('.cal-week-event').forEach(function (ev) {
      ev.addEventListener('click', function (e) {
        e.stopPropagation();
        var id = parseInt(ev.getAttribute('data-event-id'));
        var evt = EVENTS.find(function (x) { return x.id === id; });
        if (evt) showEventPopup(e, evt);
      });
    });
  }

  function renderDay() {
    var DAYS_FULL = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
    var mh = document.getElementById('calMonthYear');
    if (mh) mh.textContent = DAYS_SHORT[curDay.getDay()] + ', ' + MONTHS[curDay.getMonth()] + ' ' + curDay.getDate() + ', ' + curDay.getFullYear();
    var isToday = curDay.toDateString() === today.toDateString();
    var html = '<div>' +
      '<div style="display:grid;grid-template-columns:72px 1fr;background:var(--tmv-body-bg);border-bottom:2px solid var(--tmv-border-light)">' +
      '<div style="border-right:1px solid var(--tmv-border-light)"></div>' +
      '<div style="padding:12px 16px;text-align:center">' +
      '<div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:' + (isToday ? 'var(--tmv-primary)' : 'var(--tmv-text-muted)') + '">' + DAYS_FULL[curDay.getDay()] + '</div>' +
      '<div style="font-size:32px;font-weight:800;line-height:1.1;color:' + (isToday ? 'var(--tmv-primary)' : 'var(--tmv-text-primary)') + '">' + curDay.getDate() + '</div>' +
      '</div>' +
      '</div>';
    var hours = [7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19];
    hours.forEach(function (h) {
      var label = h < 12 ? h + ':00 AM' : (h === 12 ? '12:00 PM' : (h - 12) + ':00 PM');
      var evts = eventsForDate(curDay).filter(function (e) { var hh = parseInt(e.time); return hh === h; });
      var evtHtml = evts.map(function (e) { return '<div style="background:' + e.color + ';color:#fff;border-radius:6px;padding:4px 10px;font-size:12px;font-weight:600;cursor:pointer" data-event-id="' + e.id + '">' + e.time + ' — ' + e.title + '</div>'; }).join('');
      var isCurrentH = curDay.toDateString() === today.toDateString() && h === today.getHours();
      html += '<div style="display:flex;gap:0;border-top:1px solid var(--tmv-border-light);cursor:pointer;' + (isCurrentH ? 'background:var(--tmv-primary-xlight);' : '') + '" data-day-slot="' + h + '">' +
        '<div style="width:72px;flex-shrink:0;padding:10px 12px;font-size:11px;font-weight:600;color:' + (isCurrentH ? 'var(--tmv-primary)' : 'var(--tmv-text-muted)') + ';border-right:1px solid var(--tmv-border-light);background:var(--tmv-body-bg)">' + label + '</div>' +
        '<div style="flex:1;min-height:56px;padding:4px 8px">' + evtHtml + '</div></div>';
    });
    html += '</div>';
    grid.innerHTML = html;
    grid.querySelectorAll('[data-day-slot]').forEach(function (slot) {
      slot.addEventListener('click', function (e) {
        if (e.target.closest('[data-event-id]')) return;
        openModal('addEventModal');
      });
    });
    grid.querySelectorAll('[data-event-id]').forEach(function (ev) {
      ev.addEventListener('click', function (e) {
        e.stopPropagation();
        var id = parseInt(ev.getAttribute('data-event-id'));
        var evt = EVENTS.find(function (x) { return x.id === id; });
        if (evt) showEventPopup(e, evt);
      });
    });
  }

  function render() {
    var headerDays = document.getElementById('calHeaderDays');
    var cardBody = grid.closest('.admio-card-body');
    if (view === 'month') {
      if (headerDays) headerDays.style.display = '';
      if (cardBody) { cardBody.style.padding = ''; cardBody.style.overflow = ''; cardBody.style.overflowX = ''; }
      grid.className = 'cal-grid';
      renderMonth();
    } else if (view === 'week') {
      if (headerDays) headerDays.style.display = 'none';
      if (cardBody) { cardBody.style.padding = '0'; cardBody.style.overflow = 'hidden'; cardBody.style.overflowX = 'auto'; }
      grid.className = '';
      renderWeek();
    } else {
      if (headerDays) headerDays.style.display = 'none';
      if (cardBody) { cardBody.style.padding = '0'; cardBody.style.overflow = 'hidden'; cardBody.style.overflowX = 'auto'; }
      grid.className = '';
      renderDay();
    }
  }
  render();

  // Prev / Next
  var prev2 = document.getElementById('calPrev');
  var next2 = document.getElementById('calNext');
  if (prev2) prev2.addEventListener('click', function () {
    if (view === 'month') curMonth = new Date(curMonth.getFullYear(), curMonth.getMonth() - 1, 1);
    else if (view === 'week') { curWeekStart = new Date(curWeekStart); curWeekStart.setDate(curWeekStart.getDate() - 7); }
    else { curDay = new Date(curDay); curDay.setDate(curDay.getDate() - 1); }
    render();
  });
  if (next2) next2.addEventListener('click', function () {
    if (view === 'month') curMonth = new Date(curMonth.getFullYear(), curMonth.getMonth() + 1, 1);
    else if (view === 'week') { curWeekStart = new Date(curWeekStart); curWeekStart.setDate(curWeekStart.getDate() + 7); }
    else { curDay = new Date(curDay); curDay.setDate(curDay.getDate() + 1); }
    render();
  });

  // View tabs
  document.querySelectorAll('.cal-view-tab').forEach(function (btn) {
    btn.addEventListener('click', function () {
      document.querySelectorAll('.cal-view-tab').forEach(function (b) { b.classList.remove('active'); });
      btn.classList.add('active');
      view = btn.getAttribute('data-view');
      render();
    });
  });

  function showEventPopup(e, evt) {
    var popup = document.getElementById('calEventPopup');
    if (!popup) return;
    popup.querySelector('.popup-title').textContent = evt.title;
    popup.querySelector('.popup-time').textContent = evt.time;
    popup.querySelector('.popup-type').textContent = evt.type;
    popup.querySelector('.popup-desc').textContent = evt.desc;
    popup.querySelector('.popup-color').style.background = evt.color;
    var x = Math.min(e.clientX, window.innerWidth - 320);
    var y = Math.min(e.clientY + 10, window.innerHeight - 260);
    popup.style.left = x + 'px'; popup.style.top = y + 'px';
    popup.classList.add('open');
    var delBtn = popup.querySelector('.popup-delete-btn');
    if (delBtn) delBtn.onclick = function () {
      var idx = EVENTS.findIndex(function (ev) { return ev.id === evt.id; });
      if (idx > -1) EVENTS.splice(idx, 1);
      popup.classList.remove('open');
      render();
      showToast('success', 'Event deleted', 'trash-2');
    };
  }
  document.addEventListener('click', function (e) {
    var popup = document.getElementById('calEventPopup');
    if (popup && popup.classList.contains('open') && !popup.contains(e.target)) popup.classList.remove('open');
  });
}

/* ── File Manager V2 ─────────────────────────────────────────── */
function initFileManager() {
  var fmMain = document.querySelector('.fm-main');
  if (!fmMain) return;

  var fmGrid = fmMain.querySelector('.fm-grid');
  var gridBtn = fmMain.querySelector('.btn-admio.btn-ghost .icon-layout-grid') ? fmMain.querySelector('.btn-admio.btn-ghost .icon-layout-grid').parentElement : null;
  var listBtn = fmMain.querySelector('.btn-admio.btn-ghost .icon-list') ? fmMain.querySelector('.btn-admio.btn-ghost .icon-list').parentElement : null;

  // Toolbar view toggle
  fmMain.querySelectorAll('.btn-admio.btn-ghost.btn-icon').forEach(function (btn) {
    btn.addEventListener('click', function () {
      fmMain.querySelectorAll('.btn-admio.btn-ghost.btn-icon').forEach(function (b) { b.style.background = ''; b.style.color = ''; });
      btn.style.background = 'var(--tmv-primary)';
      btn.style.color = '#fff';
      var icon = btn.querySelector('i');
      if (!icon) return;
      if (icon.classList.contains('icon-layout-grid') || icon.classList.contains('icon-grip')) {
        if (fmGrid) { fmGrid.className = 'fm-grid'; }
      } else if (icon.classList.contains('icon-list')) {
        if (fmGrid) { fmGrid.className = 'fm-list-view'; }
      }
    });
  });

  // Upload button
  var uploadBtn = document.querySelector('.page-header-actions .btn-admio.btn-ai');
  if (uploadBtn && uploadBtn.textContent.includes('Upload')) {
    uploadBtn.addEventListener('click', function () {
      openModal('fmUploadModal');
    });
  }

  // New Folder button
  var folderBtn = document.querySelector('.page-header-actions .btn-admio.btn-outline');
  if (folderBtn && folderBtn.textContent.includes('New Folder')) {
    folderBtn.addEventListener('click', function () {
      openModal('fmNewFolderModal');
    });
  }

  // Left sidebar tab clicks — change breadcrumb/title
  document.querySelectorAll('.fm-folder-link').forEach(function (link) {
    link.addEventListener('click', function () {
      document.querySelectorAll('.fm-folder-link').forEach(function (l) { l.classList.remove('active'); });
      link.classList.add('active');
      var name = link.textContent.trim();
      var bc = fmMain.querySelector('.fm-toolbar .fw-600');
      if (bc) bc.textContent = name;
      var prev = fmMain.querySelector('.fm-toolbar .text-sm.text-muted');
      if (prev) prev.textContent = 'My Files';
      // Show empty state for non-root sections
      if (['Shared', 'Starred', 'Recent', 'Trash'].includes(name)) {
        renderFmEmpty(fmGrid, name);
      } else {
        renderFmDefault(fmGrid, name);
      }
    });
  });

  function renderFmEmpty(grid, name) {
    if (!grid) return;
    var icons = { Shared: 'share-2', Starred: 'star', Recent: 'clock', Trash: 'trash-2' };
    grid.className = 'fm-grid';
    grid.innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:60px 20px;color:var(--tmv-text-muted)">' +
      '<i class="icon-' + (icons[name] || 'folder') + '" style="font-size:48px;opacity:0.2;margin-bottom:16px;display:block"></i>' +
      '<div style="font-size:15px;font-weight:600;margin-bottom:6px">' + name + ' is empty</div>' +
      '<div style="font-size:13px">No files found here</div></div>';
  }

  function renderFmDefault(grid, name) {
    if (!grid) return;
    grid.className = 'fm-grid';
    // Restore original items (simplified - just show folder name)
    grid.innerHTML = '<div class="fm-item"><div class="fm-icon-wrap" style="background:rgba(245,158,11,0.12)"><i class="icon-folder" style="color:#F59E0B"></i></div><div class="fm-item-name">' + name + '</div><div class="fm-item-meta">Folder · 0 files</div></div>';
    if (name === 'AI Projects' || name === 'My Files') {
      location.reload();
    }
  }
}

/* ── Prompt Library Tab Filter ───────────────────────────────── */
function initPromptLibraryTabs() {
  var filterBtns = document.querySelectorAll('.prompt-filter-btn');
  if (!filterBtns.length) return;
  var table = document.getElementById('promptsTable');
  if (!table) return;

  filterBtns.forEach(function (btn) {
    btn.addEventListener('click', function () {
      filterBtns.forEach(function (b) { b.classList.remove('btn-primary'); b.classList.add('btn-white'); });
      btn.classList.remove('btn-white'); btn.classList.add('btn-primary');
      var cat = btn.getAttribute('data-category');
      table.querySelectorAll('tbody tr').forEach(function (row) {
        if (!cat || cat === 'all') { row.style.display = ''; return; }
        var catCell = row.querySelector('[data-cat]') || row.querySelectorAll('td')[1];
        var text = catCell ? catCell.textContent.trim().toLowerCase() : '';
        row.style.display = text.includes(cat.toLowerCase()) ? '' : 'none';
      });
    });
  });
}

/* ── AI Agent Edit Modal ─────────────────────────────────────── */
function initAgentEditModal() {
  document.querySelectorAll('.agent-edit-btn').forEach(function (btn) {
    btn.addEventListener('click', function (e) {
      e.stopPropagation();
      var card = btn.closest('.admio-card');
      var title = card ? (card.querySelector('h6') || {}).textContent : '';
      var editNameInput = document.getElementById('editAgentName');
      if (editNameInput) editNameInput.value = title;
      openModal('editAgentModal');
    });
  });
}

/* ── AI Workflow Edit Modal ──────────────────────────────────── */
function initWorkflowEditModal() {
  document.querySelectorAll('.workflow-edit-btn').forEach(function (btn) {
    btn.addEventListener('click', function (e) {
      e.stopPropagation();
      var name = btn.getAttribute('data-workflow-name') || (function () {
        var card = btn.closest('.admio-card');
        var title = card ? (card.querySelector('.fw-700') || {}).textContent : '';
        return (title || '').replace(/^[^\w\u{1F300}-\u{1FAFF}]*\s*/u, '').trim();
      })();
      var input = document.getElementById('editWorkflowName');
      if (input) input.value = name;
      openModal('editWorkflowModal');
    });
  });
}

/* ── API Key View/Reveal ─────────────────────────────────────── */
function initApiKeyReveal() {
  document.querySelectorAll('.api-key-view-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var keyEl = btn.closest('tr') && btn.closest('tr').querySelector('code');
      if (!keyEl) return;
      var full = btn.getAttribute('data-key-full') || 'sk-admio-xxxx-example-full-key-value';
      if (keyEl.getAttribute('data-revealed') === '1') {
        keyEl.textContent = btn.getAttribute('data-key-masked') || keyEl.textContent;
        keyEl.setAttribute('data-revealed', '0');
        btn.querySelector('i').className = 'icon-eye';
        btn.title = 'View key';
      } else {
        btn.setAttribute('data-key-masked', keyEl.textContent);
        keyEl.textContent = full;
        keyEl.setAttribute('data-revealed', '1');
        btn.querySelector('i').className = 'icon-eye-off';
        btn.title = 'Hide key';
      }
    });
  });
}

/* ── Share Popup ─────────────────────────────────────────────── */
function initSharePopup() {
  document.querySelectorAll('.prompt-share-btn').forEach(function (btn) {
    btn.addEventListener('click', function (e) {
      e.stopPropagation();
      var name = btn.getAttribute('data-prompt-name') || (function () {
        var row = btn.closest('tr');
        return row ? (row.querySelector('.fw-600') || {}).textContent : 'Prompt';
      })();
      var el = document.getElementById('sharePromptName');
      if (el) el.textContent = name;
      openModal('sharePromptModal');
    });
  });
}

/* ── Prompt Edit Modal ───────────────────────────────────────── */
function initPromptEditModal() {
  document.querySelectorAll('.prompt-edit-btn').forEach(function (btn) {
    btn.addEventListener('click', function (e) {
      e.stopPropagation();
      var name = btn.getAttribute('data-prompt-name') || (function () {
        var row = btn.closest('tr');
        return row ? (row.querySelector('.fw-600') || {}).textContent : 'Prompt';
      })();
      var el = document.getElementById('editPromptName');
      if (el) el.value = name;
      openModal('editPromptModal');
    });
  });
}

/* ── Transactions Pagination — delegates to common initPagination ── */
function initTransactionsPagination() {
  initPagination('txTable', 'txPagination', {
    perPage: 5, itemSelector: 'tbody tr', style: 'table'
  });
}

document.addEventListener("DOMContentLoaded", function () {
  if (typeof $ !== "undefined" && $.fn.DataTable) {
    window.initDataTable("usersDataTable", {
      columnDefs: [
        { orderable: false, targets: [0, 7] },
        { searchable: false, targets: [0, 7] }
      ],
      order: [[4, "desc"]]
    });
  }
});

/* ── Ai PlayGround ───────────────────────────────────────── */
var pgResponses = [
  "Based on your November 2026 data:\n\n**Model Performance Analysis:**\n\n1. **GPT-4 Turbo** — Best accuracy (97.2%) but highest cost at $0.045/1K tokens. Best for: complex reasoning, nuanced analysis.\n\n2. **Claude 3 Opus** — Near-identical accuracy (96.8%) at $0.035/1K tokens. **Best cost-to-accuracy ratio** — 22% cheaper than GPT-4 with only 0.4% accuracy drop.\n\n3. **Llama 3 70B** — Self-hosted, near-zero marginal cost. 89.7% accuracy. Best for: high-volume, latency-sensitive tasks.\n\n**Recommendations:**\n- Route simple completions (<500 tokens) to Llama 3 → save ~$800/month\n- Use Claude 3 as primary for analysis tasks → save ~$320/month vs GPT-4\n- Reserve GPT-4 for highest-stakes outputs only\n- Projected savings: **$1,120/month (39% reduction)**",
  "Excellent question! Here's my analysis:\n\n**Top Recommendation: Claude 3 Opus**\nCost-to-accuracy ratio: **96.8% accuracy at $0.035/1K tokens = 2,766 accuracy-points per dollar**\n\nGPT-4 Turbo by comparison: 97.2% at $0.045/1K = 2,160 accuracy-points per dollar.\n\nClaude 3 delivers **28% better value** on this metric.\n\n**Action Items:**\n1. Shift 60% of chat traffic from GPT-4 → Claude 3 this week\n2. Enable intelligent routing: GPT-4 for code tasks, Claude for analysis\n3. Set up cost alerts at 70% of monthly budget\n4. Review in 30 days — target: <$2,200/month at same quality level",
];
var pgIdx = 0;
function runPlayground() {
  var input = document.getElementById("pgInput").value.trim();
  if (!input) { showToast("warning", "Please enter a message", "triangle-alert"); return; }
  var status = document.getElementById("pgStatus");
  var response = document.getElementById("pgResponse");
  var stats = document.getElementById("pgStats");
  status.textContent = "Generating…";
  response.value = "";
  var model = document.getElementById("pgModel").value;
  var delay = 800 + Math.random() * 400;
  setTimeout(function () {
    var text = pgResponses[pgIdx % pgResponses.length]; pgIdx++;
    var tokens = Math.floor(text.length / 3.5);
    var cost = (tokens * 0.00004).toFixed(4);
    status.textContent = "Complete";
    stats.textContent = "Model: " + model + " · " + tokens + " tokens · $" + cost + " · " + (delay / 1000).toFixed(1) + "s";
    response.value = text;
    showToast("success", "Response generated successfully", "circle-check");
  }, delay);
}

/* ── Ai Prompts ───────────────────────────────────────── */
(function () {
  var PER_PAGE = 8;
  var currentPage = 1;
  var activeCategory = 'all';
  var searchQuery = '';

  var tbody = document.querySelector('#promptsTable tbody');
  if (!tbody) return;
  var allRows = Array.from(tbody.querySelectorAll('tr'));

  function getVisible() {
    var q = searchQuery.toLowerCase();
    return allRows.filter(function (row) {
      var cat = row.dataset.category || '';
      var matchCat = activeCategory === 'all' || cat === activeCategory;
      var matchSearch = !q || row.textContent.toLowerCase().includes(q);
      return matchCat && matchSearch;
    });
  }

  function render() {
    var visible = getVisible();
    var total = visible.length;
    var pages = Math.max(1, Math.ceil(total / PER_PAGE));
    if (currentPage > pages) currentPage = 1;

    var start = (currentPage - 1) * PER_PAGE;
    allRows.forEach(function (r) { r.style.display = 'none'; });
    visible.slice(start, start + PER_PAGE).forEach(function (r) { r.style.display = ''; });

    renderPager(total, pages);
  }

  function renderPager(total, pages) {
    var pg = document.getElementById('promptsPaginator');
    if (!pg) return;
    if (pages <= 1 && total === 0) {
      pg.innerHTML = '<span class="text-muted text-sm">No prompts found.</span>';
      return;
    }
    if (pages <= 1) { pg.innerHTML = ''; return; }

    var s = (currentPage - 1) * PER_PAGE + 1;
    var e = Math.min(currentPage * PER_PAGE, total);
    var html = '<span class="text-muted text-sm me-auto">Showing ' + s + '&ndash;' + e + ' of ' + total + '</span>';
    html += '<nav><div class="table-pagination mb-0">';
    html += '<button class="page-btn"' + (currentPage === 1 ? ' disabled' : '') + ' data-pg="' + (currentPage - 1) + '"><i class="icon-chevron-left"></i></button>';
    for (var p = 1; p <= pages; p++) {
      html += '<button class="page-btn' + (p === currentPage ? ' active' : '') + '" data-pg="' + p + '">' + p + '</button>';
    }
    html += '<button class="page-btn"' + (currentPage === pages ? ' disabled' : '') + ' data-pg="' + (currentPage + 1) + '"><i class="icon-chevron-right"></i></button>';
    html += '</div></nav>';
    pg.innerHTML = html;
    pg.querySelectorAll('[data-pg]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var p = parseInt(btn.dataset.pg);
        if (p >= 1 && p <= pages) { currentPage = p; render(); }
      });
    });
  }

  /* Category filter buttons */
  document.querySelectorAll('.prompt-filter-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      document.querySelectorAll('.prompt-filter-btn').forEach(function (b) {
        b.classList.remove('btn-primary'); b.classList.add('btn-white');
      });
      btn.classList.remove('btn-white'); btn.classList.add('btn-primary');
      activeCategory = btn.dataset.category;
      currentPage = 1;
      render();
    });
  });

  /* Search */
  var searchEl = document.querySelector('[data-table-search="promptsTable"]');
  if (searchEl) {
    searchEl.addEventListener('input', function () {
      searchQuery = this.value.trim();
      currentPage = 1;
      render();
    });
  }

  render();
})();

/* ============================================================
   21. REUSABLE PAGINATION
   ============================================================ */
function initPagination(listId, pgId, opts) {
  var list = document.getElementById(listId);
  var pg = document.getElementById(pgId);
  if (!list || !pg) return;

  opts = opts || {};
  var perPage = opts.perPage || 5;
  var selector = opts.itemSelector || '.sr-item';
  var style = opts.style || 'bootstrap';

  var items = Array.from(list.querySelectorAll(selector));
  var total = items.length;
  var pages = Math.ceil(total / perPage);
  if (pages <= 1) return;

  var current = 1;

  function showPage(page) {
    current = page;
    items.forEach(function (item, i) {
      item.style.display = (i >= (page - 1) * perPage && i < page * perPage) ? '' : 'none';
    });
    style === 'table' ? renderTablePager() : renderBootstrapPager();
  }

  /* Bootstrap .pagination style — used on search results etc. */
  function renderBootstrapPager() {
    pg.innerHTML = '';
    function addBtn(label, target, disabled, active) {
      var li = document.createElement('li');
      li.className = 'page-item' + (disabled ? ' disabled' : '') + (active ? ' active' : '');
      var a = document.createElement('a');
      a.className = 'page-link';
      a.href = '#';
      a.innerHTML = label;
      if (!disabled) {
        a.addEventListener('click', function (e) { e.preventDefault(); showPage(target); });
      }
      li.appendChild(a);
      pg.appendChild(li);
    }
    addBtn('&laquo;', current - 1, current === 1);
    for (var p = 1; p <= pages; p++) addBtn(p, p, false, p === current);
    addBtn('&raquo;', current + 1, current === pages);
  }

  /* Site page-btn style + "Showing X–Y of Z" — used on tables */
  function renderTablePager() {
    var start = (current - 1) * perPage + 1;
    var end = Math.min(current * perPage, total);
    var html = '<span class="text-muted text-sm me-auto">Showing ' + start + '&ndash;' + end + ' of ' + total + '</span><nav><div class="table-pagination mb-0">';
    html += '<button class="page-btn"' + (current === 1 ? ' disabled' : '') + ' data-page="' + (current - 1) + '"><i class="icon-chevron-left"></i></button>';
    for (var p = 1; p <= pages; p++) {
      html += '<button class="page-btn' + (p === current ? ' active' : '') + '" data-page="' + p + '">' + p + '</button>';
    }
    html += '<button class="page-btn"' + (current === pages ? ' disabled' : '') + ' data-page="' + (current + 1) + '"><i class="icon-chevron-right"></i></button>';
    html += '</div></nav>';
    pg.innerHTML = html;
    pg.querySelectorAll('[data-page]').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.preventDefault();
        var p = parseInt(btn.getAttribute('data-page'));
        if (p >= 1 && p <= pages) showPage(p);
      });
    });
  }

  showPage(1);
}

function initAutoPagination() {
  document.querySelectorAll('[data-paginate-for]').forEach(function (pg) {
    initPagination(pg.dataset.paginateFor, pg.id, {
      perPage: parseInt(pg.dataset.perPage, 10) || 5,
      itemSelector: pg.dataset.itemSelector || '.sr-item',
      style: pg.dataset.paginateStyle || 'bootstrap'
    });
  });
}
/* ============================================================
   22. Auth 
   ============================================================ */
/* ── two steps otp  ───────────────────────────────────────── */
document.querySelectorAll(".otp-input").forEach(function (inp, i, arr) { inp.addEventListener("input", function () { this.value = this.value.replace(/[^0-9]/g, ""); if (this.value && arr[i + 1]) arr[i + 1].focus(); }); });

/* ── verify email  ───────────────────────────────────────── */
if (document.getElementById("cd")) {
  var verifySec = 598;
  var verifyTimer = setInterval(function () {
    verifySec--;
    if (verifySec <= 0) { clearInterval(verifyTimer); document.getElementById("cd").textContent = "Expired"; return; }
    var vm = Math.floor(verifySec / 60), vs = verifySec % 60;
    document.getElementById("cd").textContent = (vm < 10 ? "0" : "") + vm + ":" + (vs < 10 ? "0" : "") + vs;
  }, 1000);
}
document.querySelectorAll(".otp-input").forEach(function (inp, i, arr) { inp.addEventListener("input", function () { this.value = this.value.replace(/[^0-9]/g, ""); if (this.value && arr[i + 1]) arr[i + 1].focus(); }); inp.addEventListener("keydown", function (e) { if (e.key === "Backspace" && !this.value && arr[i - 1]) arr[i - 1].focus(); }); });


/* ============================================================
   23. Maps
   ============================================================ */
document.addEventListener("DOMContentLoaded", function () {
  var canvas = document.getElementById("worldMapCanvas");
  if (!canvas) return;
  var container = canvas.parentElement;
  canvas.width = container.offsetWidth || 700;
  canvas.height = container.offsetHeight || 380;
  var ctx = canvas.getContext("2d");
  var w = canvas.width, h = canvas.height;
  ctx.fillStyle = document.documentElement.getAttribute("data-theme") === "dark" ? "#1a1a2e" : "#EEF2FF";
  ctx.fillRect(0, 0, w, h);
  var countries = [
    { name: "USA", x: 0.18, y: 0.35, r: 0.12, opacity: 0.9 },
    { name: "Canada", x: 0.18, y: 0.22, r: 0.10, opacity: 0.35 },
    { name: "UK", x: 0.46, y: 0.27, r: 0.04, opacity: 0.7 },
    { name: "Germany", x: 0.49, y: 0.28, r: 0.04, opacity: 0.5 },
    { name: "India", x: 0.64, y: 0.40, r: 0.07, opacity: 0.65 },
    { name: "Japan", x: 0.80, y: 0.30, r: 0.05, opacity: 0.25 },
    { name: "Australia", x: 0.78, y: 0.65, r: 0.09, opacity: 0.28 },
    { name: "Brazil", x: 0.28, y: 0.58, r: 0.09, opacity: 0.15 },
    { name: "China", x: 0.71, y: 0.32, r: 0.10, opacity: 0.18 },
    { name: "Russia", x: 0.63, y: 0.18, r: 0.14, opacity: 0.12 },
    { name: "France", x: 0.47, y: 0.3, r: 0.04, opacity: 0.2 },
    { name: "Spain", x: 0.46, y: 0.34, r: 0.04, opacity: 0.15 },
    { name: "S.Africa", x: 0.52, y: 0.65, r: 0.05, opacity: 0.12 },
  ];
  countries.forEach(function (c) {
    var grd = ctx.createRadialGradient(c.x * w, c.y * h, 0, c.x * w, c.y * h, c.r * w);
    grd.addColorStop(0, "rgba(124,58,237," + c.opacity + ")");
    grd.addColorStop(1, "rgba(124,58,237,0)");
    ctx.beginPath();
    ctx.arc(c.x * w, c.y * h, c.r * w, 0, Math.PI * 2);
    ctx.fillStyle = grd;
    ctx.fill();
    if (c.opacity > 0.5) {
      ctx.fillStyle = "#fff";
      ctx.font = "bold " + Math.round(c.r * w * 0.5) + "px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText(c.name, c.x * w, c.y * h + 4);
    }
  });
  ctx.strokeStyle = "rgba(124,58,237,0.06)";
  ctx.lineWidth = 1;
  for (var gx = 0; gx < w; gx += 40) { ctx.beginPath(); ctx.moveTo(gx, 0); ctx.lineTo(gx, h); ctx.stroke(); }
  for (var gy = 0; gy < h; gy += 40) { ctx.beginPath(); ctx.moveTo(0, gy); ctx.lineTo(w, gy); ctx.stroke(); }
});

/* ── Leaflet  ───────────────────────────────────────── */
var map, markers = [], markerCount = 0;
document.addEventListener("DOMContentLoaded", function () {
  if (typeof L === 'undefined' || !document.getElementById('leafletMap')) return;
  // Main Map
  map = L.map("leafletMap").setView([20, 0], 2);
  var tiles = {
    streets: L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { attribution: "© OpenStreetMap", maxZoom: 19 }),
    topo: L.tileLayer("https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png", { attribution: "© OpenTopoMap", maxZoom: 17 }),
    satellite: L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", { attribution: "© Esri", maxZoom: 19 })
  };
  tiles.streets.addTo(map);

  document.getElementById("mapTypeSelect") && document.getElementById("mapTypeSelect").addEventListener("change", function () {
    Object.values(tiles).forEach(function (t) { map.removeLayer(t); });
    tiles[this.value].addTo(map);
  });

  // Default office markers
  var offices = [
    { lat: 37.7749, lng: -122.4194, city: "San Francisco HQ", users: 12400, color: "#7C3AED" },
    { lat: 51.5074, lng: -0.1278, city: "London Office", users: 5200, color: "#06B6D4" },
    { lat: 28.6139, lng: 77.209, city: "New Delhi Office", users: 3800, color: "#10B981" },
    { lat: 52.52, lng: 13.405, city: "Berlin Office", users: 2100, color: "#F59E0B" },
    { lat: 35.6762, lng: 139.6503, city: "Tokyo Office", users: 1800, color: "#EF4444" },
  ];
  offices.forEach(function (o) {
    var icon = L.divIcon({ className: "", html: "<div style='width:28px;height:28px;border-radius:50%;background:" + o.color + ";border:3px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,0.3);display:flex;align-items:center;justify-content:center;color:#fff;font-size:11px;font-weight:800'>" + Math.round(o.users / 1000) + "K</div>", iconSize: [28, 28], iconAnchor: [14, 14] });
    L.marker([o.lat, o.lng], { icon: icon }).addTo(map).bindPopup("<strong>" + o.city + "</strong><br>Users: " + o.users.toLocaleString() + "<br>AI Requests: " + Math.round(o.users * 1.8).toLocaleString());
  });

  // Mini maps
  var m1 = L.map("miniMap1", { zoomControl: false, attributionControl: false }).setView([37.7749, -122.4194], 13);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png").addTo(m1);
  L.marker([37.7749, -122.4194]).addTo(m1).bindPopup("San Francisco HQ").openPopup();

  var m2 = L.map("miniMap2", { zoomControl: false, attributionControl: false }).setView([51.5074, -0.1278], 13);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png").addTo(m2);
  L.marker([51.5074, -0.1278]).addTo(m2).bindPopup("London Office").openPopup();
});

function flyToCity(lat, lng, name) {
  map.flyTo([lat, lng], 8, { duration: 1.5 });
  setTimeout(function () {
    var m = L.marker([lat, lng]).addTo(map).bindPopup("<strong>" + name + "</strong>").openPopup();
    markers.push({ name: name, marker: m });
    updateMarkerList();
  }, 1500);
}

function addRandomMarker() {
  var lat = (Math.random() * 140 - 70).toFixed(4);
  var lng = (Math.random() * 360 - 180).toFixed(4);
  markerCount++;
  var m = L.marker([lat, lng]).addTo(map).bindPopup("Custom Marker #" + markerCount).openPopup();
  markers.push({ name: "Custom Marker #" + markerCount, marker: m });
  map.flyTo([lat, lng], 6);
  updateMarkerList();
  showToast("success", "Marker added at (" + lat + ", " + lng + ")", "map-pin");
}

function updateMarkerList() {
  var list = document.getElementById("markerList");
  if (!list) return;
  if (markers.length === 0) { list.innerHTML = "<div class='text-sm text-muted'>No markers added yet</div>"; return; }
  list.innerHTML = markers.map(function (m, i) {
    return "<div class='d-flex align-items-center justify-content-between py-1'><span class='text-sm'>" + m.name + "</span><button class='btn-admio btn-ghost btn-icon btn-sm' onclick='removeMarker(" + i + ")'><i class='icon-x'></i></button></div>";
  }).join("");
}

function removeMarker(i) {
  map.removeLayer(markers[i].marker);
  markers.splice(i, 1);
  updateMarkerList();
}

/* ============================================================
   DYNAMIC AVATAR GENERATOR
   Reads data-name and data-bg from .avatar-gen elements,
   renders initials and background color — no external requests.
   ============================================================ */
function initAvatars() {
  document.querySelectorAll('.avatar-gen').forEach(function (el) {
    var name = (el.dataset.name || '').trim();
    var bg   = el.dataset.bg  || '#7C3AED';
    var size = parseInt(el.dataset.size, 10) || 0;

    // Derive initials: up to 2 words
    var parts    = name.split(/\s+/).filter(Boolean);
    var initials = parts.length >= 2
      ? (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
      : (name.substring(0, 2)).toUpperCase();

    el.textContent = initials;
    el.style.background = bg.charAt(0) === '#' ? bg : '#' + bg;

    // Apply size only when no CSS class already controls it
    if (size && !el.offsetWidth) {
      el.style.width    = size + 'px';
      el.style.height   = size + 'px';
    }
    // Font size always scaled from data-size (fallback 40)
    var sz = size || parseInt(el.style.width) || 40;
    el.style.fontSize = Math.max(10, Math.round(sz * 0.38)) + 'px';
  });
}

document.addEventListener('DOMContentLoaded', initAvatars);

/* ============================================================
   INBOX ACTIONS — star / delete / archive / mark-unread
   ============================================================ */
function initInboxActions() {
  var detailHeader = document.querySelector('.inbox-detail-header');
  if (!detailHeader) return;

  /* Bind directly to every action button */
  detailHeader.querySelectorAll('[data-inbox-action]').forEach(function (btn) {
    btn.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation();
      var action   = btn.dataset.inboxAction;
      var selected = document.querySelector('.inbox-email-row.selected');
      var icon     = btn.querySelector('i');

      if (action === 'delete' || action === 'archive') {
        if (selected) {
          selected.classList.add('mail-removing');
          setTimeout(function () { selected.remove(); }, 320);
          showToast('success',
            action === 'delete' ? 'Email deleted' : 'Email archived',
            'circle-check');
        }
      }

      if (action === 'star') {
        var active = btn.classList.toggle('mail-btn-active');
        if (selected) selected.classList.toggle('mail-starred', active);
      }

      if (action === 'unread') {
        var active2 = btn.classList.toggle('mail-btn-active');
        if (selected) selected.classList.toggle('unread', active2);
      }
    });
  });

  /* Row selection — click any email row to mark it selected */
  document.querySelectorAll('.inbox-email-row').forEach(function (row) {
    row.addEventListener('click', function () {
      document.querySelectorAll('.inbox-email-row').forEach(function (r) {
        r.classList.remove('selected');
      });
      row.classList.add('selected');
      // Mobile: slide to detail panel
      var layout = document.querySelector('.inbox-layout');
      if (layout && window.innerWidth <= 768) {
        layout.classList.add('inbox-showing-detail');
      }
    });
  });

  /* Back button — slide back to email list on mobile */
  var inboxBackBtn = document.getElementById('inboxBackBtn');
  if (inboxBackBtn) {
    inboxBackBtn.addEventListener('click', function () {
      var layout = document.querySelector('.inbox-layout');
      if (layout) layout.classList.remove('inbox-showing-detail');
    });
  }
}
document.addEventListener('DOMContentLoaded', initInboxActions);

/* ============================================================
   CALL MODAL CONTROLS — mute / camera / speaker toggle
   ============================================================ */
function initCallControls() {
  document.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-call-toggle]');
    if (!btn) return;
    btn.classList.toggle('active');
  });
}
document.addEventListener('DOMContentLoaded', initCallControls);

/* ============================================================
   TEAM CHAT — mobile slide panel
   ============================================================ */
function initTeamChat() {
  var layout = document.querySelector('.chat-layout');
  if (!layout) return;

  document.querySelectorAll('.chat-list-item').forEach(function (item) {
    item.addEventListener('click', function () {
      document.querySelectorAll('.chat-list-item').forEach(function (i) {
        i.classList.remove('chat-list-item-active');
      });
      item.classList.add('chat-list-item-active');
      if (window.innerWidth <= 768) {
        layout.classList.add('chat-panel-open');
      }
    });
  });

  var backBtn = document.getElementById('chatBackBtn');
  if (backBtn) {
    backBtn.addEventListener('click', function () {
      layout.classList.remove('chat-panel-open');
    });
  }
}
document.addEventListener('DOMContentLoaded', initTeamChat);

/* ============================================================
   GLOBAL ACTION DISPATCHER
   ============================================================ */
function initGlobalActions() {
  document.addEventListener('click', function (e) {
    var el = e.target.closest('[data-action]');
    if (!el) return;

    var action   = el.dataset.action;
    var type     = el.dataset.type  || 'info';
    var msg      = el.dataset.msg   || '';
    var icon = el.dataset.icon || 'bell';
    var duration = parseInt(el.dataset.duration, 10) || 4000;

    switch (action) {

      /* ── Toast ─────────────────────────────────────────── */
      case 'toast':
        showToast(type, msg, icon, duration);
        break;

      /* ── Clipboard ─────────────────────────────────────── */
      case 'copy':
        copyToClipboard(el.dataset.copy || '', el.dataset.msg || 'Copied!');
        break;
      case 'copy-field': {
        var f = document.getElementById(el.dataset.field);
        if (f) copyToClipboard(f.value, el.dataset.msg || 'Copied!');
        break;
      }
      case 'copy-self': {
        var sp = el.querySelector('span');
        if (sp) copyToClipboard(sp.textContent.trim(), el.dataset.msg || 'Copied!');
        break;
      }

      /* ── Clear element / input ─────────────────────────── */
      case 'clear': {
        var ct = document.getElementById(el.dataset.target);
        if (ct) ct.innerHTML = '';
        showToast(type, msg, icon, duration);
        break;
      }
      case 'clear-field': {
        var cf = document.getElementById(el.dataset.target);
        if (cf) { cf.value = ''; cf.focus(); }
        break;
      }

      /* ── Modal open / submit ───────────────────────────── */
      case 'open-modal':
        if (typeof openModal === 'function') openModal(el.dataset.modal);
        if (el.dataset.closePopup) {
          var cp = document.getElementById(el.dataset.closePopup);
          if (cp) cp.classList.remove('open');
        }
        break;
      case 'modal-submit':
        if (typeof closeModal === 'function') closeModal(el.dataset.close);
        showToast(type, msg, icon, duration);
        break;

      /* ── Confirm dialog ────────────────────────────────── */
      case 'confirm':
        if (typeof confirmAction === 'function') {
          confirmAction(el.dataset.confirm, function () {
            showToast(type, msg, icon, duration);
          });
        }
        break;

      /* ── Navigation ────────────────────────────────────── */
      case 'go-back':  history.back();   break;
      case 'print':    window.print();   break;

      /* ── Dismiss overlays / alerts ─────────────────────── */
      case 'close-popup': {
        var pp = document.getElementById(el.dataset.target);
        if (pp) pp.classList.remove('open');
        break;
      }
      case 'close-alert': {
        var al = el.closest('.alert-admio');
        if (al) {
          al.style.transition = 'opacity .2s,transform .2s';
          al.style.opacity    = '0';
          al.style.transform  = 'scale(0.96)';
          setTimeout(function () { al.style.display = 'none'; }, 220);
        }
        break;
      }
      case 'close-banner': {
        var bn = el.closest('.ai-insight-banner');
        if (bn) {
          bn.style.transition = 'opacity .3s';
          bn.style.opacity    = '0';
          setTimeout(function () { bn.style.display = 'none'; }, 320);
        }
        break;
      }

      /* ── Password visibility ───────────────────────────── */
      case 'toggle-pwd':
        if (typeof togglePasswordVisibility === 'function')
          togglePasswordVisibility(el.dataset.input, el.dataset.icon);
        break;

      /* ── Calendar colour swatches ──────────────────────── */
      case 'color-swatch':
        el.parentElement.querySelectorAll('[data-action="color-swatch"]').forEach(function (s) {
          s.classList.remove('cal-swatch-active');
          s.style.outline = '';
        });
        el.classList.add('cal-swatch-active');
        el.style.outline = '3px solid var(--tmv-text-primary)';
        break;

      /* ── Page-specific function bridges ────────────────── */
      case 'gallery-filter':
        if (typeof filterGallery === 'function') filterGallery(el.dataset.filter, el);
        break;
      case 'wizard-step':
        if (typeof wizardStep === 'function') wizardStep(parseInt(el.dataset.step, 10));
        break;
      case 'run-playground':
        if (typeof runPlayground === 'function') runPlayground();
        break;
      case 'billing-switch':
        if (typeof switchBilling === 'function') switchBilling(el.dataset.billing);
        break;
      case 'view-toggle':
        if (typeof toggleView === 'function') toggleView(el.dataset.view);
        break;

      /* ── Leaflet map controls ──────────────────────────── */
      case 'map-add-marker':
        if (typeof addRandomMarker === 'function') addRandomMarker();
        break;
      case 'map-reset':
        if (window.map) window.map.setView([20, 0], 2);
        break;
      case 'map-zoom-in':
        if (window.map) window.map.zoomIn();
        break;
      case 'map-zoom-out':
        if (window.map) window.map.zoomOut();
        break;
      case 'map-fly':
        if (typeof flyToCity === 'function')
          flyToCity(parseFloat(el.dataset.lat), parseFloat(el.dataset.lng), el.dataset.city || '');
        break;
    }
  });
}


/* ============================================================
   24. Form Wizard
   ============================================================ */
var wStep = 1;
function wizardStep(dir) {
  var steps      = [null, document.getElementById('step1'), document.getElementById('step2'), document.getElementById('step3')];
  var prevBtn    = document.getElementById('wizPrev');
  var nextBtn    = document.getElementById('wizNext');
  var indicators = [null, document.getElementById('s1'), document.getElementById('s2'), document.getElementById('s3')];
  if (!steps[1]) return;
  var prevStep = wStep;
  steps[wStep].classList.add('d-none');
  wStep = Math.max(1, Math.min(3, wStep + dir));
  if (dir > 0) {
    indicators[prevStep].style.background = 'var(--tmv-success)';
    indicators[prevStep].style.color = '#fff';
    indicators[prevStep].innerHTML = '&#10003;';
  } else {
    indicators[prevStep].style.background = 'var(--tmv-border-color)';
    indicators[prevStep].style.color = 'var(--tmv-text-muted)';
    indicators[prevStep].textContent = prevStep;
  }
  steps[wStep].classList.remove('d-none');
  indicators[wStep].style.background = 'var(--tmv-primary)';
  indicators[wStep].style.color = '#fff';
  indicators[wStep].textContent = wStep;
  document.getElementById('wizardProgress').style.width = ((wStep - 1) / 2 * 100) + '%';
  if (wStep === 1) { prevBtn.classList.add('invisible'); } else { prevBtn.classList.remove('invisible'); }
  if (wStep === 3) {
    nextBtn.innerHTML = '<i class="icon-check"></i> Complete Setup';
    nextBtn.onclick = function () {
      showToast('success', 'Account created! Welcome to Admio AI!', 'sparkles', 5000);
      nextBtn.onclick = function () { wizardStep(0); };
    };
  } else {
    nextBtn.innerHTML = 'Next <i class="icon-arrow-right"></i>';
    nextBtn.onclick = function () { wizardStep(1); };
  }
}


/* ============================================================
   25. Maintenance Countdown
   ============================================================ */
(function () {
  var mhEl = document.getElementById('mh');
  if (!mhEl) return;
  var maintSec = 9000;
  setInterval(function () {
    maintSec--;
    if (maintSec < 0) maintSec = 0;
    var h = Math.floor(maintSec / 3600);
    var m = Math.floor((maintSec % 3600) / 60);
    var s = maintSec % 60;
    document.getElementById('mh').textContent = (h < 10 ? '0' : '') + h;
    document.getElementById('mm').textContent = (m < 10 ? '0' : '') + m;
    document.getElementById('ms').textContent = (s < 10 ? '0' : '') + s;
  }, 1000);
})();


/* ============================================================
   26. Gallery Upload Modal
   ============================================================ */
(function () {
  var uploadTrigger = document.getElementById('galleryUploadBtn');
  if (!uploadTrigger) return;

  var modal       = document.getElementById('galleryUploadModal');
  var closeBtn    = document.getElementById('galleryModalClose');
  var cancelBtn   = document.getElementById('galleryModalCancel');
  var dropZone    = document.getElementById('galleryDropZone');
  var fileInput   = document.getElementById('galleryFileInput');
  var browseBtn   = document.getElementById('galleryBrowseBtn');
  var previewList = document.getElementById('galleryPreviewList');
  var uploadBtn   = document.getElementById('galleryModalUpload');
  var uploadCount = document.getElementById('galleryUploadCount');
  var selectedFiles = [];

  function openModal()  { modal.classList.add('open'); document.body.style.overflow = 'hidden'; }
  function closeModal() { modal.classList.remove('open'); document.body.style.overflow = ''; resetModal(); }
  function resetModal() {
    selectedFiles = [];
    fileInput.value = '';
    previewList.innerHTML = '';
    previewList.classList.add('d-none');
    uploadBtn.disabled = true;
    uploadBtn.innerHTML = '<i class="icon-upload"></i> Upload<span class="gallery-upload-count" id="galleryUploadCount"></span>';
    uploadCount = document.getElementById('galleryUploadCount');
    document.getElementById('galleryUploadTitle').value = '';
  }

  uploadTrigger.addEventListener('click', openModal);
  closeBtn.addEventListener('click', closeModal);
  cancelBtn.addEventListener('click', closeModal);
  modal.addEventListener('click', function (e) { if (e.target === modal) closeModal(); });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && modal.classList.contains('open')) closeModal(); });

  browseBtn.addEventListener('click', function (e) { e.stopPropagation(); fileInput.click(); });
  dropZone.addEventListener('click', function () { fileInput.click(); });
  dropZone.addEventListener('dragover', function (e) { e.preventDefault(); dropZone.classList.add('drag-over'); });
  dropZone.addEventListener('dragleave', function () { dropZone.classList.remove('drag-over'); });
  dropZone.addEventListener('drop', function (e) {
    e.preventDefault(); dropZone.classList.remove('drag-over');
    handleFiles(Array.from(e.dataTransfer.files).filter(function (f) { return f.type.startsWith('image/'); }));
  });
  fileInput.addEventListener('change', function () { handleFiles(Array.from(fileInput.files)); });

  function formatSize(b) {
    if (b < 1024) return b + ' B';
    if (b < 1048576) return (b / 1024).toFixed(1) + ' KB';
    return (b / 1048576).toFixed(1) + ' MB';
  }

  function handleFiles(files) {
    files.forEach(function (file) {
      if (!file.type.startsWith('image/')) return;
      if (selectedFiles.find(function (f) { return f.name === file.name && f.size === file.size; })) return;
      selectedFiles.push(file);
      addPreviewItem(file);
    });
    updateBtn();
  }

  function addPreviewItem(file) {
    previewList.classList.remove('d-none');
    var reader = new FileReader();
    reader.onload = function (e) {
      var item = document.createElement('div');
      item.className = 'gallery-preview-item';
      item.innerHTML =
        '<img src="' + e.target.result + '" class="gallery-preview-thumb" alt="">' +
        '<div class="gallery-preview-info">' +
          '<div class="gallery-preview-name">' + file.name + '</div>' +
          '<div class="gallery-preview-size">' + formatSize(file.size) + '</div>' +
        '</div>' +
        '<button class="gallery-preview-remove" title="Remove"><i class="icon-x"></i></button>';
      item.querySelector('.gallery-preview-remove').addEventListener('click', function () {
        selectedFiles = selectedFiles.filter(function (f) { return !(f.name === file.name && f.size === file.size); });
        item.remove();
        if (selectedFiles.length === 0) previewList.classList.add('d-none');
        updateBtn();
      });
      previewList.appendChild(item);
    };
    reader.readAsDataURL(file);
  }

  function updateBtn() {
    uploadBtn.disabled = selectedFiles.length === 0;
    var cnt = document.getElementById('galleryUploadCount');
    if (cnt) cnt.textContent = selectedFiles.length > 0 ? selectedFiles.length : '';
  }

  uploadBtn.addEventListener('click', function () {
    if (selectedFiles.length === 0) return;
    var items = previewList.querySelectorAll('.gallery-preview-item');
    var delay = 0;
    items.forEach(function (item) {
      var info = item.querySelector('.gallery-preview-info');
      var st = document.createElement('div');
      st.className = 'gallery-preview-status';
      st.style.color = 'var(--tmv-primary,#7c3aed)';
      st.textContent = 'Uploading…';
      info.appendChild(st);
      setTimeout(function () { st.style.color = '#10b981'; st.textContent = '✓ Uploaded'; }, delay + 600 + Math.random() * 400);
      delay += 200;
    });
    uploadBtn.disabled = true;
    uploadBtn.innerHTML = '<i class="icon-loader"></i> Uploading…';
    var count = selectedFiles.length;
    setTimeout(function () {
      closeModal();
      showToast('success', count + ' image' + (count > 1 ? 's' : '') + ' uploaded successfully', 'image');
    }, delay + 1000);
  });
})();

/**
 * LinkNest Main Application Controller
 * Handles UI interactions, accessibility, state transitions, and client integration.
 */

import { api, ApiError } from './api.js';
import { validateUrl, validateCustomCode } from './validation.js';

// DOM Elements
const urlInput = document.getElementById('url-input');
const urlError = document.getElementById('url-error');
const customCodeInput = document.getElementById('code-input');
const customCodeError = document.getElementById('code-error');
const titleInput = document.getElementById('title-input');
const createForm = document.getElementById('create-form');
const submitBtn = document.getElementById('submit-btn');
const linksContainer = document.getElementById('links-container');
const linksCountBadge = document.getElementById('links-count');
const refreshBtn = document.getElementById('refresh-btn');
const themeToggleBtn = document.getElementById('theme-toggle-btn');
const toastContainer = document.getElementById('toast-container');

// State
let linksState = [];
let isSubmitting = false;

// Formatters
const dateTimeFormatter = new Intl.DateTimeFormat(navigator.language || 'en-US', {
  month: 'short',
  day: 'numeric',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit'
});

/**
 * Toast Notification System (Polite ARIA Live)
 */
export function showToast(message, type = 'info', durationMs = 4000) {
  if (!toastContainer) return;

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.setAttribute('role', 'alert');

  const textSpan = document.createElement('span');
  textSpan.className = 'toast-msg';
  textSpan.textContent = message;

  const closeBtn = document.createElement('button');
  closeBtn.className = 'toast-close';
  closeBtn.setAttribute('aria-label', 'Close notification');
  closeBtn.innerHTML = '&times;';
  closeBtn.addEventListener('click', () => removeToast(toast));

  toast.appendChild(textSpan);
  toast.appendChild(closeBtn);
  toastContainer.appendChild(toast);

  const timeoutId = setTimeout(() => {
    removeToast(toast);
  }, durationMs);

  function removeToast(el) {
    clearTimeout(timeoutId);
    el.style.opacity = '0';
    el.style.transform = 'translateY(8px)';
    setTimeout(() => {
      if (el.parentNode) el.parentNode.removeChild(el);
    }, 200);
  }
}

/**
 * Theme Management
 */
function initTheme() {
  const savedTheme = localStorage.getItem('linknest-theme');
  if (savedTheme === 'dark' || (!savedTheme && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
    document.documentElement.setAttribute('data-theme', 'dark');
  } else {
    document.documentElement.setAttribute('data-theme', 'light');
  }

  if (themeToggleBtn) {
    themeToggleBtn.addEventListener('click', () => {
      const current = document.documentElement.getAttribute('data-theme');
      const next = current === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      localStorage.setItem('linknest-theme', next);
    });
  }
}

/**
 * Live Client-Side Validation
 */
function validateFormInputs() {
  let isClean = true;

  // Validate Destination URL
  const urlVal = urlInput.value.trim();
  if (urlVal.length > 0) {
    const res = validateUrl(urlVal);
    if (!res.valid) {
      urlInput.classList.add('error');
      urlError.textContent = res.error;
      isClean = false;
    } else {
      urlInput.classList.remove('error');
      urlError.textContent = '';
    }
  } else {
    urlInput.classList.remove('error');
    urlError.textContent = '';
  }

  // Validate Custom Code (Alias)
  const codeVal = customCodeInput.value.trim();
  if (codeVal.length > 0) {
    const codeRes = validateCustomCode(codeVal);
    if (!codeRes.valid) {
      customCodeInput.classList.add('error');
      customCodeError.textContent = codeRes.error;
      isClean = false;
    } else {
      customCodeInput.classList.remove('error');
      customCodeError.textContent = '';
    }
  } else {
    customCodeInput.classList.remove('error');
    customCodeError.textContent = '';
  }

  return isClean;
}

/**
 * Render Links List
 */
function renderLinks(links) {
  linksCountBadge.textContent = links.length;

  if (links.length === 0) {
    linksContainer.innerHTML = `
      <div class="state-box" role="status">
        <div class="state-icon" aria-hidden="true">&#128279;</div>
        <h3 class="state-title">No shortened links yet</h3>
        <p class="state-desc">Enter a long destination URL above to create your first trackable short link.</p>
      </div>
    `;
    return;
  }

  linksContainer.innerHTML = '';
  const listWrapper = document.createElement('div');
  listWrapper.className = 'links-list';
  listWrapper.setAttribute('role', 'list');

  links.forEach(link => {
    const card = document.createElement('div');
    card.className = 'link-card';
    card.setAttribute('role', 'listitem');
    card.setAttribute('tabindex', '0');

    // Title or Fallback
    const titleHtml = link.title 
      ? `<span style="font-weight: 600; color: var(--text-main); font-size: 0.95rem;">${escapeHtml(link.title)}</span>`
      : '';

    // Relative / formatted date
    const dateStr = link.created_at ? dateTimeFormatter.format(new Date(link.created_at)) : '';

    card.innerHTML = `
      <div class="link-card-top">
        <div style="display: flex; flex-direction: column; gap: 0.2rem; min-width: 0;">
          ${titleHtml}
          <a href="${escapeHtml(link.short_url)}" target="_blank" rel="noopener noreferrer" class="short-url-link" title="Open short URL">
            <span>${escapeHtml(link.short_url)}</span>
            <span aria-hidden="true" style="font-size: 0.8rem;">&nearr;</span>
          </a>
        </div>
        <div class="link-meta-actions">
          <span class="click-pill" title="Total clicks">
            <span aria-hidden="true">&#9654;</span> ${link.click_count} ${link.click_count === 1 ? 'click' : 'clicks'}
          </span>
          <button type="button" class="copy-btn" data-url="${escapeHtml(link.short_url)}" aria-label="Copy short URL to clipboard">
            <span class="copy-icon" aria-hidden="true">&#128203;</span>
            <span class="copy-text">Copy</span>
          </button>
        </div>
      </div>
      <div class="link-card-bottom">
        <a href="${escapeHtml(link.original_url)}" target="_blank" rel="noopener noreferrer" class="destination-url" title="${escapeHtml(link.original_url)}">
          ${escapeHtml(link.original_url)}
        </a>
        <time class="link-date">${dateStr}</time>
      </div>
    `;

    // Copy Button Interaction with keyboard and accessible feedback
    const copyBtn = card.querySelector('.copy-btn');
    copyBtn.addEventListener('click', async (e) => {
      e.stopPropagation();
      const targetUrl = copyBtn.getAttribute('data-url');
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(targetUrl);
        } else {
          // Fallback execCommand
          const ta = document.createElement('textarea');
          ta.value = targetUrl;
          ta.style.position = 'fixed';
          ta.style.opacity = '0';
          document.body.appendChild(ta);
          ta.select();
          document.execCommand('copy');
          document.body.removeChild(ta);
        }
        copyBtn.classList.add('copied');
        copyBtn.querySelector('.copy-text').textContent = 'Copied!';
        showToast('Short URL copied to clipboard!', 'success', 2500);

        setTimeout(() => {
          copyBtn.classList.remove('copied');
          copyBtn.querySelector('.copy-text').textContent = 'Copy';
        }, 2000);
      } catch (err) {
        showToast('Failed to copy to clipboard.', 'error');
      }
    });

    listWrapper.appendChild(card);
  });

  linksContainer.appendChild(listWrapper);
}

/**
 * Render Skeleton Loading State
 */
function renderSkeletons() {
  linksContainer.innerHTML = `
    <div class="links-list" role="status" aria-label="Loading links">
      <div class="skeleton-card"></div>
      <div class="skeleton-card"></div>
      <div class="skeleton-card"></div>
    </div>
  `;
}

/**
 * Load Links from Backend
 */
async function loadLinks() {
  renderSkeletons();
  try {
    const data = await api.getLinks();
    linksState = Array.isArray(data) ? data : [];
    renderLinks(linksState);
  } catch (err) {
    linksContainer.innerHTML = `
      <div class="state-box" role="alert">
        <div class="state-icon" style="color: var(--danger);" aria-hidden="true">&#9888;</div>
        <h3 class="state-title">Unable to load links</h3>
        <p class="state-desc">${escapeHtml(err.message)}</p>
        <button type="button" class="btn btn-secondary" id="retry-btn">Retry</button>
      </div>
    `;
    const retryBtn = document.getElementById('retry-btn');
    if (retryBtn) retryBtn.addEventListener('click', loadLinks);
  }
}

/**
 * Form Submission
 */
createForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  if (isSubmitting) return;

  const urlVal = urlInput.value.trim();
  const codeVal = customCodeInput.value.trim();
  const titleVal = titleInput.value.trim();

  // Validate URL presence & security constraints
  const urlCheck = validateUrl(urlVal);
  if (!urlCheck.valid) {
    urlInput.classList.add('error');
    urlError.textContent = urlCheck.error;
    urlInput.focus();
    return;
  }

  // Validate custom code
  if (codeVal.length > 0) {
    const codeCheck = validateCustomCode(codeVal);
    if (!codeCheck.valid) {
      customCodeInput.classList.add('error');
      customCodeError.textContent = codeCheck.error;
      customCodeInput.focus();
      return;
    }
  }

  // Set submitting state
  isSubmitting = true;
  submitBtn.disabled = true;
  submitBtn.innerHTML = '<span class="spinner" aria-hidden="true"></span> Creating...';

  try {
    const payload = {
      original_url: urlVal,
      custom_code: codeVal.length > 0 ? codeVal : null,
      title: titleVal.length > 0 ? titleVal : null
    };

    const newLink = await api.createLink(payload);
    showToast('Link shortened successfully!', 'success');

    // Reset Form
    createForm.reset();
    urlInput.classList.remove('error');
    urlError.textContent = '';
    customCodeInput.classList.remove('error');
    customCodeError.textContent = '';

    // Prepend new link to state & re-render
    linksState.unshift(newLink);
    renderLinks(linksState);
  } catch (err) {
    if (err instanceof ApiError) {
      if (err.code === 'INVALID_URL') {
        urlInput.classList.add('error');
        urlError.textContent = err.message;
        urlInput.focus();
      } else if (err.code === 'CODE_EXISTS') {
        customCodeInput.classList.add('error');
        customCodeError.textContent = err.message;
        customCodeInput.focus();
      } else {
        showToast(err.message, 'error');
      }
    } else {
      showToast('An unexpected error occurred. Please try again.', 'error');
    }
  } finally {
    isSubmitting = false;
    submitBtn.disabled = false;
    submitBtn.innerHTML = 'Shorten Link';
  }
});

// Real-time input handlers
urlInput.addEventListener('input', validateFormInputs);
urlInput.addEventListener('blur', validateFormInputs);
customCodeInput.addEventListener('input', validateFormInputs);
customCodeInput.addEventListener('blur', validateFormInputs);

if (refreshBtn) {
  refreshBtn.addEventListener('click', () => {
    loadLinks();
    showToast('Refreshing link list...', 'info', 1500);
  });
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  loadLinks();
});

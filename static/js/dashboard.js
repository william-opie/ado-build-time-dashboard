const tableBody = document.querySelector('#buildsTable tbody');
const summary = document.getElementById('summary');
const errorBanner = document.getElementById('errorBanner');
const spinner = document.getElementById('loadingSpinner');
const form = document.getElementById('filters');
const themeToggle = document.getElementById('themeToggle');
const timezoneSelect = document.getElementById('timezoneSelect');
const defaults = document.body.dataset;
const statusInputs = Array.from(document.querySelectorAll('input[name="results"]'));
const statusLabel = document.getElementById('statusSelectionLabel');
const statusFilter = document.getElementById('statusFilter');
const statusToggle = document.getElementById('statusToggle');
const statusPanel = statusFilter?.querySelector('.status-options');
const pipelineFilterInput = document.getElementById('pipelineFilter');
const topInput = document.getElementById('topInput');
const pageSizeInput = document.getElementById('pageSizeInput');
const paginationControls = document.getElementById('paginationControls');
const prevPageButton = document.getElementById('prevPage');
const nextPageButton = document.getElementById('nextPage');
const pageIndicator = document.getElementById('pageIndicator');
const startTimeSortButton = document.getElementById('startTimeSort');
let currentPage = 1;
let totalPages = 1;
let currentBuilds = [];
let startSortDirection = 'desc';

function debounce(fn, wait = 250) {
  let timeoutId;
  return (...args) => {
    if (timeoutId) {
      clearTimeout(timeoutId);
    }
    timeoutId = setTimeout(() => fn(...args), wait);
  };
}

const PRESET_TIMEZONES = [
  { label: 'UTC', value: 'UTC' },
  { label: 'US Eastern', value: 'America/New_York' },
  { label: 'US Central', value: 'America/Chicago' },
  { label: 'US Mountain', value: 'America/Denver' },
  { label: 'US Pacific', value: 'America/Los_Angeles' },
];

const RESULT_META = {
  succeeded: { label: 'Succeeded', badgeClass: 'badge--success' },
  failed: { label: 'Failed', badgeClass: 'badge--danger' },
  partiallysucceeded: { label: 'Partially Succeeded', badgeClass: 'badge--warning' },
  canceled: { label: 'Canceled', badgeClass: 'badge--muted' },
};

const SORT_DIRECTION_LABELS = {
  desc: 'Newest → Oldest',
  asc: 'Oldest → Newest',
};

function coerceTimestamp(value) {
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : undefined;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function getSortTimestamp(build) {
  if (!build) {
    return Number.NEGATIVE_INFINITY;
  }
  return (
    coerceTimestamp(build.startTimestamp) ??
    coerceTimestamp(build.finishTimestamp) ??
    Number.NEGATIVE_INFINITY
  );
}

function sortBuildsForDisplay(builds) {
  const list = Array.isArray(builds) ? [...builds] : [];
  list.sort((a, b) => {
    const aTs = getSortTimestamp(a);
    const bTs = getSortTimestamp(b);
    if (aTs === bTs) {
      return 0;
    }
    return startSortDirection === 'desc' ? bTs - aTs : aTs - bTs;
  });
  return list;
}

function updateStartSortButton() {
  if (!startTimeSortButton) return;
  const label = SORT_DIRECTION_LABELS[startSortDirection];
  const indicator = startTimeSortButton.querySelector('.sort-indicator');
  if (indicator) {
    indicator.textContent = label;
  }
  startTimeSortButton.dataset.direction = startSortDirection;
  startTimeSortButton.setAttribute('aria-label', `Sort by start time (${label})`);
}

function toggleTheme() {
  const root = document.documentElement;
  const isDark = root.classList.toggle('dark');
  themeToggle.textContent = isDark ? '☀️' : '🌙';
  themeToggle.setAttribute('aria-pressed', String(isDark));
  localStorage.setItem('theme', isDark ? 'dark' : 'light');
}

themeToggle.addEventListener('click', toggleTheme);
const savedTheme = localStorage.getItem('theme');
if (savedTheme === 'dark') {
  document.documentElement.classList.add('dark');
  themeToggle.setAttribute('aria-pressed', 'true');
  themeToggle.textContent = '☀️';
}

function populateTimezoneOptions() {
  const localTimezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const options = [];
  if (localTimezone) {
    options.push({
      label: 'Local',
      value: localTimezone,
    });
  }
  PRESET_TIMEZONES.forEach((opt) => {
    if (!options.some((existing) => existing.value === opt.value)) {
      options.push(opt);
    }
  });
  timezoneSelect.innerHTML = '';
  options.forEach((opt, index) => {
    const option = document.createElement('option');
    option.value = opt.value;
    option.textContent = opt.label;
    option.selected = index === 0;
    timezoneSelect.appendChild(option);
  });
  if (!timezoneSelect.value) {
    timezoneSelect.value = 'UTC';
  }
}

function setLoading(isLoading) {
  spinner.hidden = !isLoading;
  spinner.classList.toggle('is-visible', isLoading);
  spinner.setAttribute('aria-busy', String(isLoading));
  form.querySelectorAll('input, button, select').forEach((el) => {
    el.disabled = isLoading;
  });
}

function showError(message) {
  errorBanner.hidden = false;
  errorBanner.textContent = message;
}

function clearError() {
  errorBanner.hidden = true;
  errorBanner.textContent = '';
}

function updatePaginationControls(page, pageSize, total) {
  if (!paginationControls || !pageIndicator || !prevPageButton || !nextPageButton) {
    return;
  }
  const safePageSize = Math.max(1, Number(pageSize) || 1);
  totalPages = Math.max(1, Math.ceil(Number(total || 0) / safePageSize));
  paginationControls.hidden = totalPages <= 1;
  pageIndicator.textContent = `Page ${page} of ${totalPages}`;
  prevPageButton.disabled = page <= 1;
  nextPageButton.disabled = page >= totalPages;
}

function updateStatusSummary() {
  const total = statusInputs.length;
  const checked = statusInputs.filter((input) => input.checked).length;
  if (!statusLabel) {
    return;
  }
  if (checked === 0) {
    statusLabel.textContent = 'None selected';
  } else if (checked === total) {
    statusLabel.textContent = 'All statuses';
  } else if (checked === 1) {
    const input = statusInputs.find((item) => item.checked);
    const meta = getResultMeta(input?.value);
    statusLabel.textContent = meta.label;
  } else {
    statusLabel.textContent = `${checked} selected`;
  }
}

function getResultMeta(result) {
  if (!result) {
    return { label: 'Unknown', badgeClass: 'badge--neutral' };
  }
  const key = String(result).toLowerCase();
  return RESULT_META[key] ?? { label: result, badgeClass: 'badge--neutral' };
}

function formatDuration(seconds) {
  if (!seconds && seconds !== 0) return '';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  return [h, m, s]
    .map((part) => String(part).padStart(2, '0'))
    .join(':');
}

function render(builds) {
  if (Array.isArray(builds)) {
    currentBuilds = builds;
  }
  const buildsToRender = sortBuildsForDisplay(currentBuilds);
  tableBody.innerHTML = '';
  buildsToRender.forEach((build) => {
    const row = document.createElement('tr');
    const statusMeta = getResultMeta(build.result);
    const buildNumber = build.buildNumber ?? '';
    const buildLink = build.webUrl
      ? `<a href="${build.webUrl}" target="_blank" rel="noreferrer">${buildNumber}</a>`
      : buildNumber;
    row.innerHTML = `
      <td>${build.pipelineName ?? ''}</td>
      <td>${build.sourceBranchDisplay ?? ''}</td>
      <td>${buildLink}</td>
      <td><span class="badge ${statusMeta.badgeClass}">${statusMeta.label}</span></td>
      <td>${build.startTime ?? ''}</td>
      <td>${formatDuration(build.durationSeconds)}</td>
    `;
    tableBody.appendChild(row);
  });
}

async function loadBuilds(page = currentPage) {
  currentPage = page;
  const formData = new FormData(form);
  formData.set('days', formData.get('days') || defaults.defaultDays);
  formData.set('top', formData.get('top') || defaults.defaultTop);
  formData.set('pageSize', formData.get('pageSize') || pageSizeInput?.value || '50');
  formData.set('timezone_name', formData.get('timezone_name') || timezoneSelect.value || 'UTC');
  formData.set('page', page);
  const params = new URLSearchParams(formData);

  setLoading(true);
  clearError();
  try {
    const response = await fetch(`/api/builds?${params.toString()}`);
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || 'Unable to load builds');
    }
    const data = await response.json();
    currentPage = data.page || 1;
    render(data.builds);
    summary.textContent = `Showing ${data.count} of ${data.total} builds (page ${data.page})`;
    updatePaginationControls(
      data.page || 1,
      data.pageSize || Number(formData.get('pageSize')) || 50,
      data.total || 0,
    );
  } catch (error) {
    console.error(error);
    showError(error.message);
    if (paginationControls) {
      paginationControls.hidden = true;
    }
  } finally {
    setLoading(false);
  }
}

form.addEventListener('submit', (event) => {
  event.preventDefault();
  loadBuilds(1);
});

timezoneSelect.addEventListener('change', () => {
  form.elements.timezone_name.value = timezoneSelect.value;
  loadBuilds();
});

topInput?.addEventListener('change', () => {
  loadBuilds(1);
});

pageSizeInput?.addEventListener('change', () => {
  const value = Number(pageSizeInput.value);
  if (Number.isNaN(value) || value <= 0) {
    pageSizeInput.value = '50';
  }
  loadBuilds(1);
});

const triggerPipelineFilter = debounce(() => loadBuilds(1), 300);
pipelineFilterInput?.addEventListener('input', () => {
  triggerPipelineFilter();
});

statusInputs.forEach((input) => {
  input.addEventListener('change', () => {
    updateStatusSummary();
    loadBuilds(1);
  });
});

function setStatusPanelState(isOpen) {
  if (!statusFilter || !statusPanel || !statusToggle) return;
  statusFilter.classList.toggle('is-open', isOpen);
  statusPanel.hidden = !isOpen;
  statusToggle.setAttribute('aria-expanded', String(isOpen));
}

statusToggle?.addEventListener('click', (event) => {
  event.preventDefault();
  const nextState = !statusFilter?.classList.contains('is-open');
  setStatusPanelState(nextState);
});

document.addEventListener('click', (event) => {
  if (!statusFilter || !statusFilter.classList.contains('is-open')) return;
  if (statusFilter.contains(event.target)) return;
  setStatusPanelState(false);
});

statusPanel?.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') {
    setStatusPanelState(false);
    statusToggle?.focus();
  }
});

setStatusPanelState(false);

prevPageButton?.addEventListener('click', () => {
  if (currentPage > 1) {
    loadBuilds(currentPage - 1);
  }
});

nextPageButton?.addEventListener('click', () => {
  if (currentPage < totalPages) {
    loadBuilds(currentPage + 1);
  }
});

startTimeSortButton?.addEventListener('click', () => {
  startSortDirection = startSortDirection === 'desc' ? 'asc' : 'desc';
  updateStartSortButton();
  render();
});

form.addEventListener('keydown', (event) => {
  const tag = event.target?.tagName;
  const isTextControl = tag === 'INPUT' || tag === 'SELECT';
  if (event.key === 'Enter' && isTextControl) {
    event.preventDefault();
    loadBuilds(1);
  }
});

// initialize defaults
populateTimezoneOptions();
form.elements.days.value = defaults.defaultDays;
form.elements.top.value = defaults.defaultTop;
if (form.elements.pageSize && !form.elements.pageSize.value) {
  form.elements.pageSize.value = '50';
}
if (!form.elements.timezone_name.value) {
  form.elements.timezone_name.value = timezoneSelect.value || 'UTC';
}
updateStatusSummary();
updateStartSortButton();
loadBuilds();

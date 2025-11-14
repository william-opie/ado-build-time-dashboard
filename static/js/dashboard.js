const tableBody = document.querySelector('#buildsTable tbody');
const summary = document.getElementById('summary');
const errorBanner = document.getElementById('errorBanner');
const spinner = document.getElementById('loadingSpinner');
const form = document.getElementById('filters');
const themeToggle = document.getElementById('themeToggle');
const timezoneSelect = document.getElementById('timezoneSelect');
const defaults = document.body.dataset;
let currentPage = 1;

const PRESET_TIMEZONES = [
  { label: 'UTC', value: 'UTC' },
  { label: 'US Eastern', value: 'America/New_York' },
  { label: 'US Central', value: 'America/Chicago' },
  { label: 'US Mountain', value: 'America/Denver' },
  { label: 'US Pacific', value: 'America/Los_Angeles' },
];

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
      label: `Local (${localTimezone})`,
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
  tableBody.innerHTML = '';
  builds.forEach((build) => {
    const row = document.createElement('tr');
    row.innerHTML = `
      <td>${build.pipelineName ?? ''}</td>
      <td>${build.sourceBranchDisplay ?? ''}</td>
      <td>${build.buildNumber ?? ''}</td>
      <td><span class="badge">${build.result ?? ''}</span></td>
      <td>${build.startTime ?? ''}</td>
      <td>${formatDuration(build.durationSeconds)}</td>
      <td>${build.webUrl ? `<a href="${build.webUrl}" target="_blank" rel="noreferrer">Open</a>` : ''}</td>
    `;
    tableBody.appendChild(row);
  });
}

async function loadBuilds(page = currentPage) {
  currentPage = page;
  const formData = new FormData(form);
  formData.set('days', formData.get('days') || defaults.defaultDays);
  formData.set('top', formData.get('top') || defaults.defaultTop);
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
  } catch (error) {
    console.error(error);
    showError(error.message);
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

// initialize defaults
populateTimezoneOptions();
form.elements.days.value = defaults.defaultDays;
form.elements.top.value = defaults.defaultTop;
if (!form.elements.timezone_name.value) {
  form.elements.timezone_name.value = timezoneSelect.value || 'UTC';
}
loadBuilds();

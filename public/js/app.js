(function () {
    const root = document.documentElement;
    const page = document.body.dataset.page;
    const savedTheme = localStorage.getItem('rayventory-theme')
        || (matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark');
    root.dataset.theme = savedTheme;

    const themeButton = document.querySelector('#theme-toggle');
    if (themeButton) {
        themeButton.textContent = savedTheme === 'dark' ? '☀' : '☾';
        themeButton.onclick = () => {
            const next = root.dataset.theme === 'dark' ? 'light' : 'dark';
            const rect = themeButton.getBoundingClientRect();
            root.style.setProperty('--theme-x', `${rect.left + rect.width / 2}px`);
            root.style.setProperty('--theme-y', `${rect.top + rect.height / 2}px`);
            const change = () => {
                root.dataset.theme = next;
                localStorage.setItem('rayventory-theme', next);
                themeButton.textContent = next === 'dark' ? '☀' : '☾';
                if (window.reloadChart) window.reloadChart();
            };

            if (document.startViewTransition) {
                document.startViewTransition(change);
            } else {
                root.classList.add('theme-changing');
                change();
                setTimeout(() => root.classList.remove('theme-changing'), 1200);
            }
        };
    }

    const toast = (message, type = 'info') => {
        const container = document.querySelector('#toast-container');
        if (!container) return;
        const element = document.createElement('div');
        element.className = `toast ${type}`;
        element.textContent = message;
        container.appendChild(element);
        setTimeout(() => element.remove(), 4200);
    };

    const apiErrorMessage = (data, status) => {
        const validation = data?.errors && typeof data.errors === 'object'
            ? Object.values(data.errors).flat().find(message => typeof message === 'string')
            : null;
        const message = data?.error || data?.result?.error || validation || data?.message;
        return typeof message === 'string' && message.trim() !== ''
            ? message
            : `Ошибка API (${status})`;
    };

    const api = async (url, options = {}) => {
        const { headers = {}, ...requestOptions } = options;
        const response = await fetch(`/api/${url}`, {
            ...requestOptions,
            headers: {
                Accept: 'application/json',
                'Content-Type': 'application/json',
                ...headers,
            },
        });

        let data;
        try {
            data = await response.json();
        } catch (error) {
            throw new Error(response.ok
                ? 'API вернул некорректный JSON'
                : `Ошибка API (${response.status})`);
        }

        const hasJsonError = data !== null
            && typeof data === 'object'
            && !Array.isArray(data)
            && Object.prototype.hasOwnProperty.call(data, 'error');
        if (!response.ok || hasJsonError || data?.success === false) {
            throw new Error(apiErrorMessage(data, response.status));
        }

        return data;
    };

    // Long-running work uses local states so navigation never gets covered.
    const showLoader = () => {};
    const hideLoader = () => {};
    const setButtonLoading = (button, state) => {
        if (!button) return;
        button.classList.toggle('is-loading', state);
        if (!button.dataset.label) button.dataset.label = button.innerHTML;
        button.innerHTML = state ? 'Выполняется...' : button.dataset.label;
    };
    const escapeHtml = value => {
        const element = document.createElement('span');
        element.textContent = value ?? '';
        return element.innerHTML;
    };
    const chartStyle = () => ({
        text: getComputedStyle(root).getPropertyValue('--muted'),
        grid: getComputedStyle(root).getPropertyValue('--grid'),
        solid: getComputedStyle(root).getPropertyValue('--solid'),
    });

    const warningText = warning => {
        if (typeof warning === 'string') return warning;
        if (warning && typeof warning === 'object') {
            return warning.message || warning.text || warning.code || JSON.stringify(warning);
        }
        return warning == null ? '' : String(warning);
    };
    const normalizeWarnings = warnings => (Array.isArray(warnings) ? warnings : warnings ? [warnings] : [])
        .map(warningText)
        .filter(Boolean);
    const notifyWarnings = (warnings, context) => {
        if (!warnings.length) return;
        const remainder = warnings.length > 1 ? ` Ещё: ${warnings.length - 1}.` : '';
        toast(`${context}: ${warnings[0]}.${remainder}`, 'warning');
    };

    let categoryChart;
    let forecastChart;
    let allStock = [];

    function categoryGraph(categories) {
        const colors = chartStyle();
        if (categoryChart) categoryChart.destroy();
        const node = document.querySelector('#category-chart');
        if (!node) return;
        categoryChart = new Chart(node, {
            type: 'doughnut',
            data: {
                labels: categories.map(item => item.category),
                datasets: [{
                    data: categories.map(item => item.val),
                    backgroundColor: ['#46e6ff', '#a78bfa', '#b9f85b', '#ffb454', '#ff6b87'],
                    borderColor: colors.solid,
                    borderWidth: 5,
                }],
            },
            options: {
                maintainAspectRatio: false,
                cutout: '72%',
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: { color: colors.text, padding: 16, font: { size: 10 } },
                    },
                },
            },
        });
    }

    function stockRow(product, inventory = false) {
        const percent = Math.min(100, Math.max(2, product.current_quantity / 4));
        const low = product.current_quantity < 50;
        const status = low
            ? '<span class="status-pill risk">Внимание</span>'
            : '<span class="status-pill">В норме</span>';
        if (inventory) {
            return `<tr><td>${escapeHtml(product.name)}</td><td>${escapeHtml(product.category)}</td><td class="stock-value">${Number(product.unit_price).toLocaleString('ru-RU')} ₸</td><td>${product.lead_time} дн.</td><td class="stock-value">${product.current_quantity} шт.</td><td>${status}</td><td><button class="edit-link" data-edit="${product.id}">изменить</button></td></tr>`;
        }
        return `<tr><td>${escapeHtml(product.name)}</td><td>${escapeHtml(product.category)}</td><td class="stock-value">${product.current_quantity} шт.</td><td><div class="stock-bar ${low ? 'low' : ''}"><span style="width:${percent}%"></span></div></td><td><button class="edit-link" data-edit="${product.id}">изменить</button></td></tr>`;
    }

    async function loadData() {
        showLoader('Синхронизация Ray OS', 'Обновляем склад, метрики и сигналы...');
        try {
            const [stats, stock, briefing] = await Promise.all([
                api('dashboard-stats'),
                api('stock'),
                api('ai-briefing'),
            ]);
            allStock = stock;
            const total = document.querySelector('#total');
            const critical = document.querySelector('#critical');
            const brief = document.querySelector('#briefing');
            const modelStatus = document.querySelector('#model-status');
            if (total) {
                total.textContent = `${Number(stats.total_value).toLocaleString('ru-RU')} ₸`;
                total.classList.remove('loading-value');
            }
            if (critical) {
                critical.textContent = `${stats.critical_count} товаров`;
                critical.classList.remove('loading-value');
            }
            if (brief) brief.textContent = briefing.briefing;
            if (modelStatus) modelStatus.textContent = stats.model_status || '—';
            const dashboardBody = document.querySelector('#dashboard-stock');
            if (dashboardBody) dashboardBody.innerHTML = stock.slice(0, 6).map(product => stockRow(product)).join('');
            const inventory = document.querySelector('#inventory-stock');
            if (inventory) renderInventory();
            const productSelect = document.querySelector('#sim-product');
            if (productSelect) {
                productSelect.innerHTML = stock
                    .map(product => `<option value="${product.id}">${escapeHtml(product.name)}</option>`)
                    .join('');
            }
            const risk = document.querySelector('#risk-index');
            if (risk) {
                risk.textContent = stats.critical_count
                    ? `${Math.min(99, Math.round(stats.critical_count / Math.max(stock.length, 1) * 100))}%`
                    : 'LOW';
            }
            categoryGraph(stats.categories);
            document.querySelectorAll('[data-edit]').forEach(element => {
                element.onclick = () => openStockModal(Number(element.dataset.edit));
            });
        } catch (error) {
            toast(error.message || 'Не удалось загрузить данные', 'error');
        } finally {
            hideLoader();
        }
    }

    function renderInventory() {
        const query = (document.querySelector('#stock-search')?.value || '').toLowerCase();
        const filter = document.querySelector('#stock-filter')?.value || 'all';
        const result = allStock.filter(product => {
            const text = `${product.name} ${product.category || ''}`.toLowerCase();
            const risk = product.current_quantity < 50;
            return text.includes(query)
                && (filter === 'all' || (filter === 'risk' && risk) || (filter === 'ok' && !risk));
        });
        const body = document.querySelector('#inventory-stock');
        if (body) body.innerHTML = result.map(product => stockRow(product, true)).join('');
        const count = document.querySelector('#result-count');
        if (count) count.textContent = `${result.length} из ${allStock.length} товаров`;
        document.querySelectorAll('[data-edit]').forEach(element => {
            element.onclick = () => openStockModal(Number(element.dataset.edit));
        });
    }

    let modalId = null;
    function openStockModal(id) {
        const product = allStock.find(item => item.id === id);
        if (!product) return;
        modalId = id;
        document.querySelector('#modal-name').textContent = product.name;
        document.querySelector('#modal-qty').value = product.current_quantity;
        document.querySelector('#stock-modal').classList.add('open');
    }
    window.closeStockModal = () => document.querySelector('#stock-modal')?.classList.remove('open');

    async function saveStock() {
        const button = document.querySelector('#modal-save');
        setButtonLoading(button, true);
        showLoader('Обновление склада', 'Сохраняем новое количество...');
        try {
            const result = await api('stock/update', {
                method: 'POST',
                body: JSON.stringify({
                    product_id: modalId,
                    quantity: Number(document.querySelector('#modal-qty').value),
                }),
            });
            if (result.success) {
                closeStockModal();
                toast('Остаток обновлён');
                loadData();
            }
        } catch (error) {
            toast(error.message || 'Ошибка обновления', 'error');
        } finally {
            setButtonLoading(button, false);
            hideLoader();
        }
    }

    const describeValue = value => {
        if (typeof value === 'string' || typeof value === 'number') return String(value);
        if (!value || typeof value !== 'object') return '';
        return String(value.label || value.status || value.level || value.name || value.score || '');
    };

    function renderForecast(data) {
        const node = document.querySelector('#simulation-chart');
        if (!node || !Array.isArray(data?.dates)) return;
        const colors = chartStyle();
        const q50 = Array.isArray(data.q50) ? data.q50 : data.demand;
        const datasets = [];
        if (Array.isArray(data.stock)) {
            datasets.push({
                label: 'Расчётный остаток',
                data: data.stock,
                borderColor: '#ffb454',
                backgroundColor: 'rgba(255,180,84,.08)',
                fill: true,
                pointRadius: 0,
                borderWidth: 2,
            });
        }
        if (Array.isArray(data.q10)) {
            datasets.push({
                label: 'Спрос, нижняя граница (q10)',
                data: data.q10,
                borderColor: '#a78bfa',
                borderDash: [3, 4],
                pointRadius: 0,
                borderWidth: 1.5,
            });
        }
        if (Array.isArray(q50)) {
            datasets.push({
                label: 'Спрос, медиана (q50)',
                data: q50,
                borderColor: '#46e6ff',
                pointRadius: 0,
                borderWidth: 2,
            });
        }
        if (Array.isArray(data.q90)) {
            datasets.push({
                label: 'Спрос, верхняя граница (q90)',
                data: data.q90,
                borderColor: '#ff6b87',
                borderDash: [3, 4],
                pointRadius: 0,
                borderWidth: 1.5,
            });
        }
        if (Array.isArray(data.safety_stock)) {
            datasets.push({
                label: 'Расчётный страховой запас',
                data: data.safety_stock,
                borderColor: '#b9f85b',
                borderDash: [6, 5],
                pointRadius: 0,
                borderWidth: 2,
            });
        }

        if (forecastChart) forecastChart.destroy();
        forecastChart = new Chart(node, {
            type: 'line',
            data: { labels: data.dates, datasets },
            options: {
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: {
                        labels: { color: colors.text, boxWidth: 12, font: { size: 10 } },
                    },
                },
                scales: {
                    x: { grid: { color: colors.grid }, ticks: { color: colors.text, maxTicksLimit: 8 } },
                    y: { grid: { color: colors.grid }, ticks: { color: colors.text } },
                },
            },
        });
        document.querySelector('#chart-empty')?.classList.add('hidden');
    }

    const simulationPayload = () => ({
        product_id: Number(document.querySelector('#sim-product').value),
        overrides: {
            is_promo: Boolean(document.querySelector('#sim-promo').checked),
        },
    });

    const applySimulationPayload = payload => {
        if (!payload) return;
        const product = document.querySelector('#sim-product');
        if (product) product.value = payload.product_id;
        const promo = document.querySelector('#sim-promo');
        if (promo) promo.checked = Boolean(payload.overrides?.is_promo);
    };

    const simulationStatus = (data, suffix = '') => {
        const model = describeValue(data?.model);
        const quality = describeValue(data?.quality);
        const warnings = normalizeWarnings(data?.warnings);
        const parts = ['Прогноз готов'];
        if (model) parts.push(`модель: ${model}`);
        if (quality) parts.push(`качество: ${quality}`);
        if (warnings.length) parts.push(`предупреждений: ${warnings.length}`);
        if (suffix) parts.push(suffix);
        return parts.join(' · ');
    };

    const finishSimulation = (data, payload, suffix = '') => {
        localStorage.setItem('rayventory-last-forecast', JSON.stringify({
            data,
            payload,
            createdAt: new Date().toISOString(),
        }));
        renderForecast(data);
        const status = document.querySelector('#simulation-status');
        if (status) status.textContent = simulationStatus(data, suffix || new Date().toLocaleTimeString('ru-RU', {
            hour: '2-digit',
            minute: '2-digit',
        }));
        notifyWarnings(normalizeWarnings(data.warnings), 'Прогноз рассчитан с предупреждением');
    };

    async function waitForJob(jobId) {
        for (let attempt = 0; attempt < 240; attempt += 1) {
            const state = await api(`jobs/${jobId}`);
            if (state.status === 'completed') {
                if (state.result?.error) throw new Error(state.result.error);
                return state.result;
            }
            if (state.status === 'failed' || state.status === 'not_found') {
                throw new Error(state.result?.error || 'Расчёт не завершён');
            }
            await new Promise(resolve => setTimeout(resolve, 700));
        }
        throw new Error('Расчёт превысил допустимое время');
    }

    async function runSimulationAsync() {
        const button = document.querySelector('#run-simulation');
        const panel = document.querySelector('.chart-panel');
        const status = document.querySelector('#simulation-status');
        setButtonLoading(button, true);
        panel?.classList.add('is-loading');
        if (status) status.textContent = 'Выполняется расчёт сценария...';
        try {
            const payload = simulationPayload();
            const started = await api('simulate/start', {
                method: 'POST',
                body: JSON.stringify(payload),
            });
            if (!started.job_id) throw new Error('API не вернул идентификатор расчёта');
            localStorage.setItem('rayventory-active-job', JSON.stringify({
                jobId: started.job_id,
                payload,
            }));
            const data = await waitForJob(started.job_id);
            localStorage.removeItem('rayventory-active-job');
            finishSimulation(data, payload);
            toast('Сценарий рассчитан');
        } catch (error) {
            if (status) status.textContent = 'Ошибка расчёта';
            toast(error.message || 'Ошибка симуляции', 'error');
        } finally {
            panel?.classList.remove('is-loading');
            setButtonLoading(button, false);
        }
    }

    async function resumeSimulation() {
        const active = localStorage.getItem('rayventory-active-job');
        if (!active || page !== 'simulator') return;
        try {
            const item = JSON.parse(active);
            applySimulationPayload(item.payload);
            document.querySelector('#simulation-status').textContent = 'Проверяем сохранённый расчёт...';
            const data = await waitForJob(item.jobId);
            localStorage.removeItem('rayventory-active-job');
            finishSimulation(data, item.payload, 'восстановлен');
        } catch (error) {
            localStorage.removeItem('rayventory-active-job');
            toast(error.message || 'Не удалось восстановить расчёт', 'error');
        }
    }

    function restoreLastForecast() {
        if (page !== 'simulator') return;
        try {
            const saved = JSON.parse(localStorage.getItem('rayventory-last-forecast') || 'null');
            if (!saved?.data?.dates?.length) return;
            applySimulationPayload(saved.payload);
            renderForecast(saved.data);
            const warnings = normalizeWarnings(saved.data.warnings);
            const time = new Date(saved.createdAt).toLocaleTimeString('ru-RU', {
                hour: '2-digit',
                minute: '2-digit',
            });
            document.querySelector('#simulation-status').textContent = simulationStatus(
                saved.data,
                `последний расчёт ${time}`,
            );
            if (warnings.length) document.querySelector('#chart-empty')?.classList.add('hidden');
        } catch (error) {
            localStorage.removeItem('rayventory-last-forecast');
        }
    }

    const reportArtifacts = data => {
        const artifacts = [];
        const seen = new Set();
        const add = (format, filename) => {
            if (typeof filename !== 'string' || filename.trim() === '') return;
            let normalizedFormat = typeof format === 'string' ? format.toLowerCase() : '';
            if (!['pdf', 'pptx'].includes(normalizedFormat)) {
                normalizedFormat = filename.toLowerCase().endsWith('.pptx') ? 'pptx'
                    : filename.toLowerCase().endsWith('.pdf') ? 'pdf' : '';
            }
            if (!normalizedFormat) return;
            const key = `${normalizedFormat}:${filename}`;
            if (seen.has(key)) return;
            seen.add(key);
            artifacts.push({ format: normalizedFormat, filename });
        };

        if (Array.isArray(data?.artifacts)) {
            data.artifacts.forEach(artifact => add(artifact?.format, artifact?.filename));
        }
        add('pdf', data?.filename);
        add('pptx', data?.presentation_filename);
        return artifacts;
    };

    function renderReportResult(data, title = 'Комплект готов') {
        const result = document.querySelector('#report-result');
        if (!result) return 0;
        const artifacts = reportArtifacts(data);
        if (!artifacts.length) return 0;
        const warnings = normalizeWarnings(data.warnings);
        const links = artifacts.map(artifact => `
            <li>
                <a class="artifact-link" target="_blank" rel="noopener" href="/download/reports/${encodeURIComponent(artifact.filename)}">
                    <span class="artifact-format">${escapeHtml(artifact.format.toUpperCase())}</span>
                    <span class="artifact-name">${escapeHtml(artifact.filename)}</span>
                    <em>Скачать ↗</em>
                </a>
            </li>
        `).join('');
        const warningMarkup = warnings.length ? `
            <div class="report-warnings">
                <b>Предупреждения модели</b>
                <ul>${warnings.map(warning => `<li>${escapeHtml(warning)}</li>`).join('')}</ul>
            </div>
        ` : '';
        result.innerHTML = `
            <span class="report-result-icon">▧</span>
            <div class="report-result-body">
                <b>${escapeHtml(title)}</b>
                <ul class="artifact-list">${links}</ul>
                ${warningMarkup}
            </div>
        `;
        return artifacts.length;
    }

    async function report(type, button) {
        const formats = Array.from(document.querySelectorAll('[data-report-format]:checked'))
            .map(input => input.value);
        const status = document.querySelector('#report-status');
        const result = document.querySelector('#report-result');
        if (!formats.length) {
            if (status) status.textContent = 'Выберите хотя бы один формат';
            toast('Выберите PDF, PPTX или оба формата', 'error');
            return;
        }

        if (status) status.textContent = 'Готовим выбранные файлы...';
        result?.classList.add('is-loading');
        setButtonLoading(button, true);
        showLoader('Генерация отчёта', 'Готовим выбранные форматы...');
        try {
            const data = await api('generate-report', {
                method: 'POST',
                keepalive: true,
                body: JSON.stringify({ type, formats }),
            });
            const artifacts = reportArtifacts(data);
            if (!artifacts.length) throw new Error('API не вернул готовые файлы');
            const warnings = normalizeWarnings(data.warnings);
            const stored = {
                artifacts,
                warnings,
                metadata: data.metadata ?? null,
                filename: data.filename ?? null,
                presentation_filename: data.presentation_filename ?? null,
                createdAt: new Date().toISOString(),
            };
            localStorage.setItem('rayventory-last-report', JSON.stringify(stored));
            const count = renderReportResult(stored);
            if (status) status.textContent = count === 1 ? 'Документ готов' : `${count} файла готовы`;
            if (warnings.length) {
                notifyWarnings(warnings, 'Файлы готовы с предупреждением');
            } else {
                toast(count === 1 ? 'Документ сформирован' : 'Комплект сформирован');
            }
        } catch (error) {
            if (status) status.textContent = 'Генерация не удалась';
            toast(error.message || 'Ошибка отчёта', 'error');
        } finally {
            result?.classList.remove('is-loading');
            setButtonLoading(button, false);
            hideLoader();
        }
    }

    function restoreLastReport() {
        const lastReport = localStorage.getItem('rayventory-last-report');
        if (page !== 'reports' || !lastReport) return;
        try {
            const item = JSON.parse(lastReport);
            const count = renderReportResult(item, 'Последний комплект');
            if (!count) throw new Error('Stored report has no artifacts');
            const status = document.querySelector('#report-status');
            if (status) status.textContent = 'Восстановлено из последней сессии';
        } catch (error) {
            localStorage.removeItem('rayventory-last-report');
        }
    }

    window.reloadChart = () => {
        if (page === 'dashboard') loadData();
        if (page === 'simulator' && forecastChart) {
            try {
                const saved = JSON.parse(localStorage.getItem('rayventory-last-forecast') || 'null');
                if (saved?.data) renderForecast(saved.data);
            } catch (error) {
                localStorage.removeItem('rayventory-last-forecast');
            }
        }
    };

    document.querySelector('#refresh-inventory')?.addEventListener('click', loadData);
    document.querySelector('#stock-search')?.addEventListener('input', renderInventory);
    document.querySelector('#stock-filter')?.addEventListener('change', renderInventory);
    document.querySelector('#modal-save')?.addEventListener('click', saveStock);
    document.querySelector('#stock-modal')?.addEventListener('click', event => {
        if (event.target.id === 'stock-modal') closeStockModal();
    });
    document.querySelector('#run-simulation')?.addEventListener('click', runSimulationAsync);
    document.querySelectorAll('.report-action').forEach(button => {
        button.addEventListener('click', () => report(button.dataset.type, button));
    });

    const revealObserver = 'IntersectionObserver' in window
        ? new IntersectionObserver(entries => entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
                revealObserver.unobserve(entry.target);
            }
        }), { threshold: 0.12 })
        : null;
    document.querySelectorAll('.panel,.metric-card,.quick-card,.report-card,.knowledge-card')
        .forEach((element, index) => {
            element.classList.add('reveal');
            element.style.transitionDelay = `${Math.min(index * 35, 280)}ms`;
            if (revealObserver) revealObserver.observe(element);
            else element.classList.add('visible');
        });

    const pulseValue = element => {
        element.classList.remove('value-pulse');
        void element.offsetWidth;
        element.classList.add('value-pulse');
    };
    document.querySelectorAll('#total,#critical,#briefing').forEach(element => {
        new MutationObserver(() => pulseValue(element))
            .observe(element, { childList: true, characterData: true, subtree: true });
    });

    let refreshTimer;
    const scheduleRefresh = () => {
        clearTimeout(refreshTimer);
        refreshTimer = setTimeout(() => {
            if (document.visibilityState === 'visible' && (page === 'dashboard' || page === 'inventory')) {
                loadData();
            }
            scheduleRefresh();
        }, 60000);
    };
    scheduleRefresh();
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') scheduleRefresh();
    });

    restoreLastReport();

    const palette = document.querySelector('#command-palette');
    const commandInput = document.querySelector('#command-search');
    let selectedCommand = 0;
    const closePalette = () => {
        palette?.classList.remove('open');
        palette?.setAttribute('aria-hidden', 'true');
    };
    const openPalette = () => {
        palette?.classList.add('open');
        palette?.setAttribute('aria-hidden', 'false');
        selectedCommand = 0;
        commandInput?.focus();
    };
    const commandButtons = () => Array.from(document.querySelectorAll('[data-command]'));
    const selectCommand = () => commandButtons()
        .filter(item => item.style.display !== 'none')
        .forEach((item, index) => item.classList.toggle('selected', index === selectedCommand));

    document.querySelector('#command-trigger')?.addEventListener('click', openPalette);
    palette?.addEventListener('click', event => {
        if (event.target === palette) closePalette();
    });
    document.querySelectorAll('[data-command]').forEach(item => {
        item.addEventListener('click', () => {
            window.location.href = item.dataset.command;
        });
    });
    commandInput?.addEventListener('input', event => {
        const query = event.target.value.toLowerCase();
        commandButtons().forEach(item => {
            item.style.display = item.textContent.toLowerCase().includes(query) ? 'grid' : 'none';
            item.classList.remove('selected');
        });
        selectedCommand = 0;
        selectCommand();
    });
    document.addEventListener('keydown', event => {
        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
            event.preventDefault();
            openPalette();
        }
        if (event.key === 'Escape') closePalette();
        if (!palette?.classList.contains('open')) return;
        const visible = commandButtons().filter(item => item.style.display !== 'none');
        if (event.key === 'ArrowDown') {
            event.preventDefault();
            selectedCommand = (selectedCommand + 1) % Math.max(visible.length, 1);
            selectCommand();
        }
        if (event.key === 'ArrowUp') {
            event.preventDefault();
            selectedCommand = (selectedCommand - 1 + Math.max(visible.length, 1))
                % Math.max(visible.length, 1);
            selectCommand();
        }
        if (event.key === 'Enter' && visible[selectedCommand]) {
            window.location.href = visible[selectedCommand].dataset.command;
        }
    });

    if (page === 'dashboard' || page === 'inventory') loadData();
    if (page === 'simulator') {
        loadData().finally(() => {
            restoreLastForecast();
            resumeSimulation();
        });
    }
})();

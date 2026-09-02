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
    let purchaseActions = [];
    let purchaseBudget = null;

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
        }
    }

    const purchaseRow = item => {
        const risk = item.stockout_date
            ? `<span class="status-pill risk">${escapeHtml(item.stockout_date)}</span>`
            : '<span class="status-pill">нет</span>';
        const quality = item.quality?.grade || 'low';
        const confidence = quality === 'high' ? 'Высокая' : quality === 'medium' ? 'Средняя' : 'Низкая';
        const basketQuantity = Number(item.basket_quantity ?? item.order_quantity);
        const limited = basketQuantity < Number(item.order_quantity);
        return `<tr data-purchase-row data-order="${basketQuantity > 0 ? 1 : 0}" data-risk="${item.stockout_date ? 1 : 0}" data-quality="${escapeHtml(quality)}">
            <td><b>${escapeHtml(item.sku || `SKU-${item.product_id}`)}</b><small class="table-subline">${escapeHtml(item.product_name)}</small></td>
            <td>${escapeHtml(item.supplier || 'Не указан')}</td>
            <td>${Number(item.on_hand).toLocaleString('ru-RU')}</td>
            <td>${Number(item.in_transit).toLocaleString('ru-RU')}</td>
            <td>${Number(item.days_cover).toLocaleString('ru-RU')} дн.</td>
            <td class="stock-value">${basketQuantity.toLocaleString('ru-RU')}<small class="table-subline">${limited ? `из ${Number(item.order_quantity).toLocaleString('ru-RU')}` : 'рекомендация'}</small></td>
            <td>${Math.round(basketQuantity * Number(item.unit_price)).toLocaleString('ru-RU')} ₸</td>
            <td>${risk}</td>
            <td><span class="confidence ${escapeHtml(quality)}">${confidence}</span></td>
            <td><button class="edit-link" data-explain="${item.product_id}">почему?</button></td>
        </tr>`;
    };

    function allocatePurchaseBudget() {
        let balance = purchaseBudget;
        purchaseActions.forEach(item => {
            const recommended = Math.max(0, Number(item.order_quantity));
            const price = Math.max(0, Number(item.unit_price));
            if (purchaseBudget === null) {
                item.basket_quantity = recommended;
            } else if (price <= 0) {
                item.basket_quantity = recommended;
            } else {
                item.basket_quantity = Math.min(recommended, Math.floor(Math.max(balance, 0) / price));
                balance -= item.basket_quantity * price;
            }
        });
        return balance;
    }

    function renderPurchaseCalendar() {
        const target = document.querySelector('#purchase-calendar');
        if (!target) return;
        const now = new Date();
        const today = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
        const groups = new Map();
        purchaseActions.filter(item => Number(item.basket_quantity) > 0).forEach(item => {
            const date = item.best_order_date && item.best_order_date > today ? item.best_order_date : today;
            if (!groups.has(date)) groups.set(date, []);
            groups.get(date).push(item);
        });
        const entries = [...groups.entries()].sort(([a], [b]) => a.localeCompare(b)).slice(0, 8);
        target.innerHTML = entries.length ? entries.map(([date, items]) => {
            const amount = items.reduce((sum, item) => sum + Number(item.basket_quantity) * Number(item.unit_price), 0);
            const label = date === today ? 'Сегодня' : new Date(`${date}T00:00:00`).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' });
            return `<article class="calendar-day ${date === today ? 'is-urgent' : ''}"><time datetime="${date}">${escapeHtml(label)}</time><b>${Math.round(amount).toLocaleString('ru-RU')} ₸</b>${items.slice(0, 4).map(item => `<div class="calendar-item"><span>${escapeHtml(item.product_name)}</span><strong>${Number(item.basket_quantity).toLocaleString('ru-RU')} шт.</strong></div>`).join('')}${items.length > 4 ? `<small>+ ещё ${items.length - 4}</small>` : ''}</article>`;
        }).join('') : '<span class="calendar-empty">При текущих настройках заказов нет.</span>';
    }

    function renderPurchaseBasket() {
        const balance = allocatePurchaseBudget();
        const basket = purchaseActions.filter(item => Number(item.basket_quantity) > 0);
        const value = basket.reduce((sum, item) => sum + Number(item.basket_quantity) * Number(item.unit_price), 0);
        document.querySelector('#basket-lines').textContent = `${basket.length} SKU`;
        document.querySelector('#basket-value').textContent = `${Math.round(value).toLocaleString('ru-RU')} ₸`;
        document.querySelector('#basket-balance').textContent = purchaseBudget === null ? 'без лимита' : `${Math.max(0, Math.round(balance)).toLocaleString('ru-RU')} ₸`;
        document.querySelector('#export-purchase-plan').disabled = basket.length === 0;
        document.querySelector('#purchase-rows').innerHTML = purchaseActions.length
            ? purchaseActions.map(purchaseRow).join('')
            : '<tr><td colspan="10">Позиции для планирования не найдены</td></tr>';
        document.querySelectorAll('[data-explain]').forEach(element => {
            element.onclick = () => explainPurchase(Number(element.dataset.explain));
        });
        renderPurchaseCalendar();
        filterPurchases();
    }

    function applyPurchaseBudget() {
        const input = document.querySelector('#purchase-budget');
        const value = Number(input?.value);
        if (!input?.value || !Number.isFinite(value) || value <= 0) {
            toast('Введите бюджет больше нуля', 'warning');
            return;
        }
        purchaseBudget = value;
        renderPurchaseBasket();
        toast('Бюджет распределён по приоритету риска');
    }

    function resetPurchaseBudget() {
        purchaseBudget = null;
        const input = document.querySelector('#purchase-budget');
        if (input) input.value = '';
        renderPurchaseBasket();
    }

    async function exportPurchasePlan() {
        const button = document.querySelector('#export-purchase-plan');
        const items = purchaseActions.filter(item => Number(item.basket_quantity) > 0)
            .map(item => ({ product_id: item.product_id, quantity: Number(item.basket_quantity) }));
        if (!items.length) return;
        setButtonLoading(button, true);
        try {
            const response = await fetch('/api/purchase-plan/export', {
                method: 'POST',
                headers: { Accept: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'Content-Type': 'application/json' },
                body: JSON.stringify({ budget: purchaseBudget, items }),
            });
            if (!response.ok) {
                const data = await response.json().catch(() => ({}));
                throw new Error(apiErrorMessage(data, response.status));
            }
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = `rayventory_purchase_plan_${new Date().toISOString().slice(0, 10)}.xlsx`;
            document.body.appendChild(link);
            link.click();
            link.remove();
            URL.revokeObjectURL(url);
            toast('Заказ сформирован в Excel');
        } catch (error) {
            toast(error.message || 'Не удалось выгрузить заказ', 'error');
        } finally {
            setButtonLoading(button, false);
        }
    }

    function filterPurchases() {
        const filter = document.querySelector('#purchase-filter')?.value || 'all';
        document.querySelectorAll('[data-purchase-row]').forEach(row => {
            row.hidden = (filter === 'order' && row.dataset.order !== '1')
                || (filter === 'risk' && row.dataset.risk !== '1')
                || (filter === 'low-quality' && row.dataset.quality === 'high');
        });
    }

    function explainPurchase(productId) {
        const item = purchaseActions.find(action => action.product_id === productId);
        if (!item) return;
        document.querySelector('#explain-name').textContent = `${item.sku || ''} · ${item.product_name}`;
        document.querySelector('#explain-content').innerHTML = `
            <p class="explain-summary">Мы берём прогноз спроса на весь срок поставки с учётом выбранного уровня риска, затем вычитаем доступный остаток и уже заказанный товар. Отрицательный результат считается нулём.</p>
            <div class="explain-equation">
                <article><small>Спрос на срок поставки</small><b>${Number(item.lead_time_demand).toLocaleString('ru-RU')}</b></article>
                <span>−</span><article><small>Остаток</small><b>${Number(item.on_hand).toLocaleString('ru-RU')}</b></article>
                <span>−</span><article><small>В пути</small><b>${Number(item.in_transit).toLocaleString('ru-RU')}</b></article>
                <span>=</span><article class="result"><small>К заказу</small><b>${Number(item.order_quantity).toLocaleString('ru-RU')}</b></article>
            </div>
            <dl class="explain-list">
                <div><dt>Срок поставки</dt><dd>${item.lead_time_days} дней</dd></div>
                <div><dt>Медианный спрос</dt><dd>${Number(item.median_lead_time_demand).toLocaleString('ru-RU')}</dd></div>
                <div><dt>Страховая поправка</dt><dd>${Number(item.safety_stock).toLocaleString('ru-RU')}</dd></div>
                <div><dt>Лучший день заказа</dt><dd>${escapeHtml(item.best_order_date || 'заказ пока не требуется')}</dd></div>
                <div><dt>Ожидаемый дефицит</dt><dd>${escapeHtml(item.stockout_date || 'не ожидается')}</dd></div>
                <div><dt>Уверенность</dt><dd>${Number(item.quality?.score || 0).toLocaleString('ru-RU')} / 100</dd></div>
            </dl>`;
        const modal = document.querySelector('#purchase-explainer');
        modal.classList.add('open');
        modal.setAttribute('aria-hidden', 'false');
    }

    async function loadPurchasePlan() {
        const button = document.querySelector('#refresh-purchases');
        setButtonLoading(button, true);
        try {
            const data = await api('purchase-plan');
            purchaseActions = data.actions || [];
            document.querySelector('#purchase-units').textContent = Number(data.portfolio.recommended_order_units).toLocaleString('ru-RU');
            document.querySelector('#purchase-value').textContent = `${Number(data.portfolio.recommended_order_value).toLocaleString('ru-RU')} ₸`;
            document.querySelector('#purchase-risk').textContent = `${data.portfolio.at_risk_skus} SKU`;
            document.querySelector('#purchase-quality').textContent = `${data.quality.score} / 100`;
            document.querySelector('#purchase-quality-note').textContent = data.quality.grade === 'high' ? 'высокая уверенность' : data.quality.grade === 'medium' ? 'средняя уверенность' : 'низкая уверенность';
            document.querySelector('#purchase-data-date').textContent = `данные на ${data.data_as_of}`;
            const evaluationAvailable = Number(data.evaluation.sku_count) > 0;
            document.querySelector('#quality-grid').innerHTML = [
                ['Полнота истории', `${data.quality.average_completeness_pct}%`],
                ['Свежесть', `${data.quality.freshness_days} дн.`],
                ['WAPE', evaluationAvailable ? `${data.evaluation.wape_pct}%` : 'н/д'],
                ['Bias', evaluationAvailable ? `${data.evaluation.bias_pct}%` : 'н/д'],
                ['Покрытие q10–q90', evaluationAvailable ? `${data.evaluation.coverage_pct}%` : 'н/д'],
                ['SKU проверено', data.evaluation.sku_count],
            ].map(([label, value]) => `<article><small>${label}</small><b>${value}</b></article>`).join('');
            const warningBox = document.querySelector('#purchase-warnings');
            if (data.warnings?.length) {
                warningBox.innerHTML = `<b>Предупреждения данных</b><ul>${data.warnings.slice(0, 8).map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ul>`;
                warningBox.classList.remove('hidden');
            } else warningBox.classList.add('hidden');
            renderPurchaseBasket();
        } catch (error) {
            toast(error.message || 'Не удалось рассчитать закупки', 'error');
            document.querySelector('#purchase-rows').innerHTML = '<tr><td colspan="10">Расчёт не выполнен</td></tr>';
        } finally {
            setButtonLoading(button, false);
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
        }
    }

    let inventoryImportPreview = null;
    async function importInventory() {
        const input = document.querySelector('#inventory-excel');
        const button = document.querySelector('#import-inventory');
        const file = input?.files?.[0];
        if (!file) return;
        if (!file.name.toLowerCase().endsWith('.xlsx')) {
            toast('Выберите файл в формате .xlsx', 'error');
            return;
        }

        const form = new FormData();
        form.append('file', file);
        setButtonLoading(button, true);
        try {
            const response = await fetch('/api/inventory/import/preview', {
                method: 'POST',
                headers: { Accept: 'application/json' },
                body: form,
            });
            const data = await response.json().catch(() => ({}));
            if (!response.ok || data.success === false || data.error) {
                throw new Error(apiErrorMessage(data, response.status));
            }
            inventoryImportPreview = { ...data.preview, fileName: file.name };
            const preview = data.preview;
            const counts = preview.counts || {};
            document.querySelector('#import-period').textContent = `История: ${preview.period.start} — ${preview.period.end} · ${preview.period.days} дней · ${preview.warehouses.join(', ')}`;
            document.querySelector('#import-preview-metrics').innerHTML = [
                ['Товаров', counts.products],
                ['Продаж', counts.sales],
                ['Остатков', counts.stocks],
                ['Поставок', counts.supplies],
                ['Дней истории', preview.period.days],
            ].map(([label, value]) => `<article><b>${Number(value || 0).toLocaleString('ru-RU')}</b><small>${label}</small></article>`).join('');
            const impactLabels = { products: 'Товары', sales: 'Продажи', stocks: 'Остатки', supplies: 'Поставки' };
            document.querySelector('#import-impact-grid').innerHTML = Object.entries(preview.impact || {}).map(([key, item]) => {
                const delta = Number(item.delta || 0);
                const deltaLabel = delta > 0 ? `+${delta}` : String(delta);
                return `<article><small>${impactLabels[key] || key}</small><b>${Number(item.current || 0).toLocaleString('ru-RU')} → ${Number(item.next || 0).toLocaleString('ru-RU')}</b><span>изменение: <em>${deltaLabel}</em></span></article>`;
            }).join('');
            document.querySelector('#import-sample-rows').innerHTML = (preview.sample || []).map(item => `<tr><td>${escapeHtml(item.sku)}</td><td>${escapeHtml(item.name)}</td><td>${escapeHtml(item.category)}</td><td>${Number(item.lead_time)} дн.</td><td>${Number(item.unit_price).toLocaleString('ru-RU')} ₸</td></tr>`).join('');
            const warnings = document.querySelector('#import-warnings');
            if (preview.warnings?.length) {
                warnings.innerHTML = `<b>Обратите внимание</b><ul>${preview.warnings.map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ul>`;
                warnings.classList.remove('hidden');
                document.querySelector('#import-quality').textContent = 'ЕСТЬ ПРЕДУПРЕЖДЕНИЯ';
                document.querySelector('#import-quality').classList.add('risk');
            } else {
                warnings.classList.add('hidden');
                document.querySelector('#import-quality').textContent = 'ГОТОВО';
                document.querySelector('#import-quality').classList.remove('risk');
            }
            document.querySelector('#import-preview').classList.remove('hidden');
            toast('Файл проверен — просмотрите сводку и подтвердите импорт');
        } catch (error) {
            toast(error.message || 'Не удалось импортировать Excel', 'error');
        } finally {
            setButtonLoading(button, false);
        }
    }

    async function confirmInventoryImport() {
        if (!inventoryImportPreview?.token) return;
        const button = document.querySelector('#confirm-inventory-import');
        setButtonLoading(button, true);
        try {
            const data = await api('inventory/import/confirm', {
                method: 'POST',
                body: JSON.stringify({
                    token: inventoryImportPreview.token,
                    file_name: inventoryImportPreview.fileName,
                }),
            });
            const counts = data.counts || {};
            toast(`Импорт завершён: ${counts.products || 0} товаров, ${counts.sales || 0} продаж`);
            if (data.warning) toast(data.warning, 'error');
            else if (data.adaptation?.evaluable) toast(`Модель проверена: WAPE ${data.adaptation.metrics.wape_pct}%`);
            inventoryImportPreview = null;
            document.querySelector('#inventory-excel').value = '';
            document.querySelector('#excel-file-name').textContent = 'Файл не выбран · максимум 20 МБ';
            document.querySelector('#import-inventory').disabled = true;
            document.querySelector('#import-preview').classList.add('hidden');
            await loadData();
        } catch (error) {
            toast(error.message || 'Не удалось подтвердить импорт', 'error');
        } finally {
            setButtonLoading(button, false);
        }
    }

    let researchExperiments = [];
    function renderExperiment(experiment) {
        if (!experiment) return;
        document.querySelector('#experiment-dataset').textContent = experiment.dataset || '—';
        document.querySelector('#experiment-series').textContent = `${Number(experiment.series_count || 0).toLocaleString('ru-RU')} временных рядов`;
        document.querySelector('#experiment-folds').textContent = experiment.rolling_folds || 1;
        document.querySelector('#experiment-champion').textContent = experiment.champion || '—';
        document.querySelector('#experiment-meta').textContent = `${experiment.experiment_id} · ${new Date(experiment.created_at).toLocaleString('ru-RU')}`;
        const results = [...(experiment.results || [])].sort((a, b) => Number(a.metrics?.wape_pct) - Number(b.metrics?.wape_pct));
        document.querySelector('#experiment-results').innerHTML = results.map((item, index) => {
            const metrics = item.metrics || {};
            return `<tr class="${index === 0 ? 'experiment-winner' : ''}"><td><b>${escapeHtml(item.model)}</b>${index === 0 ? '<span class="table-subline">лидер эксперимента</span>' : ''}</td><td>${Number(metrics.wape_pct).toLocaleString('ru-RU')}%</td><td>± ${Number(metrics.wape_pct_std || 0).toLocaleString('ru-RU')}</td><td>${Number(metrics.mae).toLocaleString('ru-RU')}</td><td>${Number(metrics.rmse).toLocaleString('ru-RU')}</td><td>${Number(metrics.bias_pct).toLocaleString('ru-RU')}%</td><td>${metrics.coverage_pct === undefined ? 'н/д' : `${Number(metrics.coverage_pct).toLocaleString('ru-RU')}%`}</td><td>${Number(item.training_seconds || 0).toLocaleString('ru-RU')} сек.</td><td>${Number(item.parameter_count || 0).toLocaleString('ru-RU')}</td></tr>`;
        }).join('') || '<tr><td colspan="9">В эксперименте нет результатов</td></tr>';
        const segmentKeys = ['smooth', 'intermittent', 'erratic', 'lumpy'];
        document.querySelector('#experiment-segments').innerHTML = results.map(item => `<tr><td><b>${escapeHtml(item.model)}</b></td>${segmentKeys.map(key => {
            const segment = item.metrics?.segments?.[key];
            const route = item.routes?.[key];
            return `<td>${segment ? `${Number(segment.wape_pct).toLocaleString('ru-RU')}% <span class="table-subline">${route ? `метод: ${escapeHtml(route)}` : `${Number(segment.windows || 0).toLocaleString('ru-RU')} окон`}</span>` : 'н/д'}</td>`;
        }).join('')}</tr>`).join('') || '<tr><td colspan="5">Сегментные метрики появятся после нового rolling-запуска.</td></tr>';
        const leader = results[0];
        document.querySelector('#experiment-note').textContent = Number(experiment.rolling_folds || 1) > 1
            ? `Рейтинг рассчитан по среднему WAPE на ${experiment.rolling_folds} последовательных окнах. Разброс показывает устойчивость результата.`
            : `${leader?.model || 'Модель'} лидирует только на одном тестовом окне. Для научного вывода запустите rolling backtesting минимум на трёх окнах.`;
    }

    async function loadExperiments() {
        try {
            const data = await api('experiments');
            researchExperiments = data.experiments || [];
            document.querySelector('#experiment-count').textContent = researchExperiments.length;
            const selector = document.querySelector('#experiment-selector');
            selector.innerHTML = researchExperiments.map(item => `<option value="${escapeHtml(item.experiment_id)}">${escapeHtml(item.experiment_id)} · ${escapeHtml(item.champion || 'без лидера')}</option>`).join('');
            if (!researchExperiments.length) {
                selector.innerHTML = '<option>Экспериментов пока нет</option>';
                document.querySelector('#experiment-results').innerHTML = '<tr><td colspan="9">Запустите исследовательский CLI, чтобы получить сравнение.</td></tr>';
                return;
            }
            renderExperiment(researchExperiments[0]);
        } catch (error) {
            toast(error.message || 'Не удалось загрузить эксперименты', 'error');
        }
    }

    async function loadModelHealth(refresh = false) {
        const button = document.querySelector('#refresh-model-health');
        setButtonLoading(button, true);
        try {
            const data = await api(`model-health${refresh ? '?refresh=1' : ''}`);
            const item = data.latest;
            const metrics = item.metrics || {};
            const evaluable = Boolean(item.evaluable);
            const freshnessLabels = { fresh: 'АКТУАЛЬНО', warning: 'УСТАРЕВАЮТ', critical: 'УСТАРЕЛИ' };
            document.querySelector('#health-freshness').textContent = `${item.freshness_days} дн.`;
            document.querySelector('#health-freshness-note').textContent = `данные на ${item.data_as_of || 'неизвестную дату'}`;
            document.querySelector('#health-wape').textContent = evaluable ? `${metrics.wape_pct}%` : 'н/д';
            document.querySelector('#health-bias').textContent = evaluable ? `${metrics.bias_pct > 0 ? '+' : ''}${metrics.bias_pct}%` : 'н/д';
            document.querySelector('#health-coverage').textContent = evaluable ? `${metrics.coverage_pct}%` : 'н/д';
            const status = document.querySelector('#health-status');
            status.textContent = freshnessLabels[item.freshness_status] || 'ПРОВЕРЕНО';
            status.classList.toggle('risk', item.freshness_status !== 'fresh');
            const change = item.comparison?.wape_change_pct;
            const comparison = change === null ? 'Это первая сохранённая оценка.' : `WAPE изменился на ${change > 0 ? '+' : ''}${change} п.п. относительно предыдущей оценки.`;
            document.querySelector('#health-summary').textContent = evaluable
                ? `${comparison} Проверено SKU: ${metrics.sku_count}.`
                : 'Истории пока недостаточно для честного backtesting. Прогноз работает, но метрики точности не публикуются.';
            document.querySelector('#health-details').innerHTML = [
                ['Модель', item.model],
                ['Дата оценки', new Date(item.evaluated_at).toLocaleString('ru-RU')],
                ['Тестовый период', `${metrics.holdout_days || 0} дней`],
                ['Наблюдений', Number(metrics.observations || 0).toLocaleString('ru-RU')],
                ['Источник', item.source || (item.trigger === 'manual' ? 'ручная проверка' : 'Excel')],
            ].map(([label, value]) => `<article><small>${label}</small><b>${escapeHtml(value)}</b></article>`).join('');
            document.querySelector('#model-health-history').innerHTML = (data.history || []).map(row => {
                const delta = row.comparison?.wape_change_pct;
                const verdicts = { improved: 'лучше', degraded: 'хуже', baseline: 'база' };
                return `<tr><td>${new Date(row.evaluated_at).toLocaleString('ru-RU')}</td><td>${escapeHtml(row.data_as_of || '—')}</td><td>${row.trigger === 'excel_import' ? 'Импорт Excel' : 'Ручная оценка'}</td><td>${row.evaluable ? `${row.metrics.wape_pct}%` : 'н/д'}</td><td>${delta === null ? '—' : `${delta > 0 ? '+' : ''}${delta} п.п.`}</td><td><span class="confidence ${row.comparison?.verdict === 'degraded' ? 'low' : row.comparison?.verdict === 'improved' ? 'high' : 'medium'}">${verdicts[row.comparison?.verdict] || 'база'}</span></td></tr>`;
            }).join('') || '<tr><td colspan="6">История пока пуста</td></tr>';
        } catch (error) {
            toast(error.message || 'Не удалось оценить модель', 'error');
        } finally {
            setButtonLoading(button, false);
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

    async function runSimulationAsync() {
        const button = document.querySelector('#run-simulation');
        const panel = document.querySelector('.chart-panel');
        const status = document.querySelector('#simulation-status');
        setButtonLoading(button, true);
        panel?.classList.add('is-loading');
        if (status) status.textContent = 'Выполняется расчёт сценария...';
        try {
            const payload = simulationPayload();
            const data = await api('simulate', {
                method: 'POST',
                body: JSON.stringify(payload),
            });
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
    document.querySelector('#inventory-excel')?.addEventListener('change', event => {
        const file = event.target.files?.[0];
        const button = document.querySelector('#import-inventory');
        inventoryImportPreview = null;
        document.querySelector('#import-preview')?.classList.add('hidden');
        document.querySelector('#excel-file-name').textContent = file
            ? `${file.name} · ${(file.size / 1024 / 1024).toFixed(1)} МБ`
            : 'Файл не выбран · максимум 20 МБ';
        if (button) button.disabled = !file;
    });
    document.querySelector('#import-inventory')?.addEventListener('click', importInventory);
    document.querySelector('#confirm-inventory-import')?.addEventListener('click', confirmInventoryImport);
    document.querySelector('#refresh-purchases')?.addEventListener('click', loadPurchasePlan);
    document.querySelector('#purchase-filter')?.addEventListener('change', filterPurchases);
    document.querySelector('#apply-purchase-budget')?.addEventListener('click', applyPurchaseBudget);
    document.querySelector('#reset-purchase-budget')?.addEventListener('click', resetPurchaseBudget);
    document.querySelector('#export-purchase-plan')?.addEventListener('click', exportPurchasePlan);
    document.querySelector('#purchase-budget')?.addEventListener('keydown', event => {
        if (event.key === 'Enter') applyPurchaseBudget();
    });
    document.querySelector('#purchase-explainer-close')?.addEventListener('click', () => {
        document.querySelector('#purchase-explainer')?.classList.remove('open');
    });
    document.querySelector('#purchase-explainer')?.addEventListener('click', event => {
        if (event.target.id === 'purchase-explainer') event.target.classList.remove('open');
    });
    document.querySelector('#refresh-model-health')?.addEventListener('click', () => loadModelHealth(true));
    document.querySelector('#experiment-selector')?.addEventListener('change', event => {
        renderExperiment(researchExperiments.find(item => item.experiment_id === event.target.value));
    });
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
        });
    }
    if (page === 'purchases') loadPurchasePlan();
    if (page === 'model-health') loadModelHealth();
    if (page === 'experiments') loadExperiments();
})();

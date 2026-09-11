(function () {
    const root = document.documentElement;
    const page = document.body.dataset.page;
    let activeBranchId = Number(localStorage.getItem('rayventory-branch-id')) || null;
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || '';
    const branchStorageKey = name => `rayventory-branch-${activeBranchId || 'default'}-${name}`;
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
        const progress = document.querySelector('#route-progress');
        progress?.classList.add('is-active');
        const response = await fetch(`/api/${url}`, {
            ...requestOptions,
            headers: {
                Accept: 'application/json',
                'Content-Type': 'application/json',
                ...(activeBranchId ? { 'X-Branch-ID': String(activeBranchId) } : {}),
                ...(csrfToken ? { 'X-CSRF-TOKEN': csrfToken } : {}),
                ...headers,
            },
        }).finally(() => setTimeout(() => progress?.classList.remove('is-active'), 180));

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
    const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;

    const animateNumber = (element, value, formatter = number => Math.round(number).toLocaleString('ru-RU')) => {
        if (!element) return;
        if (reduceMotion) {
            element.textContent = formatter(value);
            return;
        }
        const started = performance.now();
        const duration = 650;
        const frame = now => {
            const progress = Math.min(1, (now - started) / duration);
            const eased = 1 - Math.pow(1 - progress, 3);
            element.textContent = formatter(value * eased);
            if (progress < 1) requestAnimationFrame(frame);
        };
        requestAnimationFrame(frame);
    };

    function renderInventoryMap(stock) {
        const map = document.querySelector('#inventory-map');
        if (!map) return;
        const nodes = [...stock].sort((a, b) => Number(b.current_quantity) * Number(b.unit_price) - Number(a.current_quantity) * Number(a.unit_price)).slice(0, 14);
        if (!nodes.length) {
            map.innerHTML = '<p class="map-empty">В филиале пока нет товаров. Загрузите Excel на странице склада.</p>';
            return;
        }
        const positions = [[50,48],[25,26],[74,25],[20,66],[78,69],[42,18],[58,79],[36,62],[64,48],[10,43],[90,43],[33,84],[67,12],[91,78]];
        const maxValue = Math.max(...nodes.map(item => Number(item.current_quantity) * Number(item.unit_price)), 1);
        map.querySelectorAll('.map-node,.map-empty').forEach(item => item.remove());
        nodes.forEach((item, index) => {
            const quantity = Number(item.current_quantity);
            const state = quantity < 25 ? 'danger' : quantity < 50 ? 'watch' : 'ok';
            const size = 36 + Math.sqrt((quantity * Number(item.unit_price)) / maxValue) * 30;
            const button = document.createElement('button');
            button.className = `map-node ${state}`;
            button.style.cssText = `left:${positions[index][0]}%;top:${positions[index][1]}%;--node-size:${size}px;--delay:${index * 45}ms`;
            button.setAttribute('aria-label', `${item.name}: ${quantity} штук`);
            button.innerHTML = `<b>${escapeHtml(item.sku || String(item.id))}</b><small>${escapeHtml(item.name)} · ${quantity} шт.</small>`;
            button.onclick = () => {
                localStorage.setItem(branchStorageKey('selected-product'), String(item.id));
                window.location.href = '/simulator';
            };
            map.appendChild(button);
        });
    }

    function renderActivity(events, stock) {
        const stream = document.querySelector('#activity-stream');
        if (!stream) return;
        const risks = [...stock].filter(item => Number(item.current_quantity) < 50).sort((a, b) => a.current_quantity - b.current_quantity).slice(0, 3).map((item, index) => ({
            id: `risk-${item.id}`, type: 'stock', title: `${item.name}: низкий остаток`, actor: `${item.current_quantity} шт. · открыть симулятор`, created_at: null, product_id: item.id, synthetic: true, index,
        }));
        const combined = [...risks, ...(events || [])].slice(0, 7);
        if (!combined.length) {
            stream.innerHTML = '<p class="map-empty">Событий пока нет — система наблюдает за филиалом.</p>';
            return;
        }
        const icons = { import: '⇩', model: '⌁', stock: '!', system: '◇' };
        stream.innerHTML = combined.map((event, index) => {
            const time = event.created_at ? new Date(event.created_at).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' }) : 'сейчас';
            return `<button class="activity-item ${escapeHtml(event.type || 'system')}" style="--delay:${index * 55}ms" ${event.product_id ? `data-event-product="${event.product_id}"` : ''}><span class="activity-icon">${icons[event.type] || '◇'}</span><span><b>${escapeHtml(event.title)}</b><small>${escapeHtml(event.actor || 'Система')}</small></span><time>${time}</time></button>`;
        }).join('');
        stream.querySelectorAll('[data-event-product]').forEach(button => {
            button.onclick = () => {
                localStorage.setItem(branchStorageKey('selected-product'), button.dataset.eventProduct);
                window.location.href = '/simulator';
            };
        });
    }

    function updateDecisionFlow(stock, criticalCount) {
        const totalUnits = stock.reduce((sum, item) => sum + Number(item.current_quantity), 0);
        const stockLabel = document.querySelector('#flow-stock');
        const riskLabel = document.querySelector('#flow-risk');
        if (stockLabel) stockLabel.textContent = `${Math.round(totalUnits).toLocaleString('ru-RU')} ед. в контуре`;
        if (riskLabel) riskLabel.textContent = criticalCount ? `${criticalCount} SKU требуют внимания` : 'критических сигналов нет';
    }

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
            const [stats, stock, briefing, activity] = await Promise.all([
                api('dashboard-stats'),
                api('stock'),
                api('ai-briefing'),
                page === 'dashboard' ? api('activity-events').catch(() => ({ events: [] })) : Promise.resolve({ events: [] }),
            ]);
            allStock = stock;
            const total = document.querySelector('#total');
            const critical = document.querySelector('#critical');
            const brief = document.querySelector('#briefing');
            const modelStatus = document.querySelector('#model-status');
            if (total) {
                animateNumber(total, Number(stats.total_value), value => `${Math.round(value).toLocaleString('ru-RU')} ₸`);
                total.classList.remove('loading-value');
            }
            if (critical) {
                animateNumber(critical, Number(stats.critical_count), value => `${Math.round(value)} товаров`);
                critical.classList.remove('loading-value');
            }
            if (brief) brief.textContent = briefing.briefing;
            if (modelStatus) modelStatus.textContent = stats.model_status || '—';
            const dashboardBody = document.querySelector('#dashboard-stock');
            if (dashboardBody) dashboardBody.innerHTML = [...stock].sort((a, b) => a.current_quantity - b.current_quantity).slice(0, 6).map(product => stockRow(product)).join('');
            const inventory = document.querySelector('#inventory-stock');
            if (inventory) renderInventory();
            const productSelect = document.querySelector('#sim-product');
            if (productSelect) {
                productSelect.innerHTML = stock
                    .map(product => `<option value="${product.id}">${escapeHtml(product.name)}</option>`)
                    .join('');
                const selectedProduct = localStorage.getItem(branchStorageKey('selected-product'));
                if (selectedProduct && stock.some(product => String(product.id) === selectedProduct)) productSelect.value = selectedProduct;
            }
            const risk = document.querySelector('#risk-index');
            if (risk) {
                risk.textContent = stats.critical_count
                    ? `${Math.min(99, Math.round(stats.critical_count / Math.max(stock.length, 1) * 100))}%`
                    : 'LOW';
            }
            categoryGraph(stats.categories);
            const categoryCount = document.querySelector('#category-count');
            if (categoryCount) categoryCount.textContent = String(stats.categories.length);
            renderInventoryMap(stock);
            renderActivity(activity.events, stock);
            updateDecisionFlow(stock, Number(stats.critical_count));
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
                headers: { Accept: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'Content-Type': 'application/json', 'X-CSRF-TOKEN': csrfToken, ...(activeBranchId ? { 'X-Branch-ID': String(activeBranchId) } : {}) },
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
        const reasons = Array.isArray(item.reasons) ? item.reasons : [];
        const itemWarnings = normalizeWarnings(item.warnings);
        document.querySelector('#explain-content').innerHTML = `
            <p class="explain-summary">Мы берём прогноз спроса на весь срок поставки с учётом выбранного уровня риска, затем вычитаем доступный остаток и уже заказанный товар. Отрицательный результат считается нулём.</p>
            ${reasons.length ? `<div class="explain-reasons"><b>Почему система рекомендует это действие</b><ol>${reasons.map(reason => `<li>${escapeHtml(reason)}</li>`).join('')}</ol></div>` : ''}
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
            </dl>
            ${itemWarnings.length ? `<div class="report-warnings"><b>Ограничения по этому товару</b><ul>${itemWarnings.map(warning => `<li>${escapeHtml(warning)}</li>`).join('')}</ul></div>` : ''}`;
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
            const comparison = data.evaluation.comparison || {};
            const comparisonValue = evaluationAvailable && Number.isFinite(Number(comparison.baseline_wape_pct))
                ? `${Number(comparison.baseline_wape_pct).toLocaleString('ru-RU')}%`
                : 'н/д';
            const improvementValue = evaluationAvailable && Number.isFinite(Number(comparison.wape_improvement_pct))
                ? `${Number(comparison.wape_improvement_pct) > 0 ? '+' : ''}${Number(comparison.wape_improvement_pct).toLocaleString('ru-RU')} п.п.`
                : 'н/д';
            document.querySelector('#quality-grid').innerHTML = [
                ['Полнота истории', `${data.quality.average_completeness_pct}%`],
                ['Свежесть', `${data.quality.freshness_days} дн.`],
                ['WAPE', evaluationAvailable ? `${data.evaluation.wape_pct}%` : 'н/д'],
                ['Bias', evaluationAvailable ? `${data.evaluation.bias_pct}%` : 'н/д'],
                ['Покрытие q10–q90', evaluationAvailable ? `${data.evaluation.coverage_pct}%` : 'н/д'],
                ['SKU проверено', data.evaluation.sku_count],
                ['Простой недельный прогноз', comparisonValue],
                ['Выигрыш модели', improvementValue],
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
                headers: { Accept: 'application/json', 'X-CSRF-TOKEN': csrfToken, ...(activeBranchId ? { 'X-Branch-ID': String(activeBranchId) } : {}) },
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
            return `<tr class="${index === 0 ? 'experiment-winner' : ''}"><td><b>${escapeHtml(item.model)}</b>${index === 0 ? '<span class="table-subline">лидер по WAPE</span>' : ''}</td><td>${Number(metrics.wape_pct).toLocaleString('ru-RU')}%</td><td>± ${Number(metrics.wape_pct_std || 0).toLocaleString('ru-RU')}</td><td>${Number(metrics.mae).toLocaleString('ru-RU')}</td><td>${Number(metrics.rmse).toLocaleString('ru-RU')}</td><td>${Number(metrics.bias_pct).toLocaleString('ru-RU')}%</td><td>${metrics.underforecast_pct === undefined ? 'н/д' : `${Number(metrics.underforecast_pct).toLocaleString('ru-RU')}%`}</td><td>${metrics.risk_cost_pct === undefined ? 'н/д' : `${Number(metrics.risk_cost_pct).toLocaleString('ru-RU')}%`}</td><td>${metrics.coverage_pct === undefined ? 'н/д' : `${Number(metrics.coverage_pct).toLocaleString('ru-RU')}%`}</td><td>${Number(item.training_seconds || 0).toLocaleString('ru-RU')} сек.</td><td>${Number(item.parameter_count || 0).toLocaleString('ru-RU')}</td><td><button class="button secondary registry-add" data-model="${escapeHtml(item.model)}">В кандидаты</button></td></tr>`;
        }).join('') || '<tr><td colspan="12">В эксперименте нет результатов</td></tr>';
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
                document.querySelector('#experiment-results').innerHTML = '<tr><td colspan="12">Запустите исследовательский CLI, чтобы получить сравнение.</td></tr>';
                return;
            }
            renderExperiment(researchExperiments[0]);
        } catch (error) {
            toast(error.message || 'Не удалось загрузить эксперименты', 'error');
        }
    }

    async function loadModelRegistry() {
        const state = await api('models');
        const production = (state.models || []).find(item => item.id === state.production_id);
        document.querySelector('#registry-production').textContent = `PROD · ${production?.name || 'fallback'}`;
        const candidates = (state.models || []).filter(item => item.status !== 'production');
        document.querySelector('#model-registry-list').innerHTML = candidates.map(item => {
            const failed = (item.checks || []).filter(check => !check.passed);
            return `<article><div><b>${escapeHtml(item.name)}</b><span>${escapeHtml(item.status)} · ${escapeHtml(item.experiment_id || 'встроенная')}</span></div><div class="registry-state"><em class="${item.eligible ? 'registry-ready' : 'registry-blocked'}">${item.eligible ? 'готов к публикации' : 'публикация заблокирована'}</em>${item.eligible && item.status === 'candidate' ? `<button class="button primary registry-promote" data-model-id="${escapeHtml(item.id)}">Опубликовать</button>` : ''}</div>${failed.length ? `<p>${failed.map(check => escapeHtml(check.message)).join(' ')}</p>` : ''}</article>`;
        }).join('') || '<p>Кандидатов пока нет. Добавьте модель из таблицы эксперимента.</p>';
    }

    async function loadTrainingReadiness() {
        const data = await api('training-readiness');
        document.querySelector('#training-ready').textContent = data.ready ? 'ГОТОВО' : 'НУЖНЫ ДАННЫЕ';
        document.querySelector('#training-privacy').textContent = data.privacy;
        document.querySelector('#training-period').textContent = data.date_start && data.date_end
            ? `${new Date(data.date_start).toLocaleDateString('ru-RU')} — ${new Date(data.date_end).toLocaleDateString('ru-RU')}`
            : 'нет истории';
        document.querySelector('#training-span').textContent = `${Number(data.minimum_series_span_days).toLocaleString('ru-RU')} дней`;
        document.querySelector('#training-series').textContent = `${Number(data.series_eligible).toLocaleString('ru-RU')} / ${Number(data.series_total).toLocaleString('ru-RU')}`;
        document.querySelector('#training-message').textContent = data.message;
        document.querySelector('#start-local-training').disabled = !data.ready;
    }

    async function loadTrainingPipeline() {
        const data = await api('training-pipeline');
        const latest = data.latest;
        document.querySelector('#training-pipeline-status').textContent = latest
            ? `${latest.status} · ${latest.message}`
            : 'Автоматические запуски ещё не выполнялись.';
    }

    async function loadDatasetAnalysis() {
        const data = await api('dataset-analysis');
        const analysis = data.analysis;
        if (!analysis) return;
        document.querySelector('#analysis-meta').textContent = `${analysis.dataset} · ${Number(analysis.volume.rows).toLocaleString('ru-RU')} строк · ${analysis.period.days} дней`;
        document.querySelector('#analysis-zero').textContent = `${Number(analysis.demand.zero_sales_pct).toLocaleString('ru-RU')}%`;
        document.querySelector('#analysis-weekly').textContent = analysis.patterns.weekly_lag_correlation === null ? 'н/д' : Number(analysis.patterns.weekly_lag_correlation).toLocaleString('ru-RU');
        document.querySelector('#analysis-trend').textContent = `${Number(analysis.patterns.portfolio_trend_30d_pct).toLocaleString('ru-RU')}%`;
        const labels = { smooth: 'Стабильный', intermittent: 'Прерывистый', erratic: 'Хаотичный', lumpy: 'Нерегулярный' };
        document.querySelector('#analysis-types').innerHTML = Object.entries(labels).map(([key, label]) => `<article><span>${label}</span><b>${Number(analysis.demand.types[key] || 0).toLocaleString('ru-RU')} SKU</b></article>`).join('');
        const dominant = Object.entries(analysis.demand.types).sort((a, b) => b[1] - a[1])[0];
        document.querySelector('#analysis-conclusion').textContent = `Преобладающий тип спроса: ${labels[dominant?.[0]] || 'не определён'}. Анализ выполнен за ${Number(analysis.performance.analysis_seconds).toLocaleString('ru-RU')} сек.`;
    }

    async function loadTuning() {
        const data = await api('tuning');
        const tuning = data.tuning;
        if (!tuning) return;
        document.querySelector('#tuning-meta').textContent = `${tuning.tuning_id} · ${tuning.trials.length} конфигураций · ${tuning.folds} rolling-окон`;
        const best = Object.values(tuning.best_by_model || {}).sort((a, b) => a.metrics.wape_pct - b.metrics.wape_pct);
        document.querySelector('#tuning-results').innerHTML = best.map((item, index) => `<tr class="${index === 0 ? 'experiment-winner' : ''}"><td><b>${escapeHtml(item.model)}</b>${index === 0 ? '<span class="table-subline">лучший вариант</span>' : ''}</td><td>${Number(item.metrics.wape_pct).toLocaleString('ru-RU')}%</td><td>${item.parameters.hidden_size}</td><td>${item.parameters.history_days} дней</td><td>${item.parameters.learning_rate}</td><td>${Number(item.training_seconds).toLocaleString('ru-RU')} сек.</td><td>${Number(item.parameter_count).toLocaleString('ru-RU')}</td></tr>`).join('');
    }

    async function loadScenarios() {
        const data = await api('scenarios');
        const benchmark = data.benchmark;
        if (!benchmark) return;
        const labels = { seasonality: 'Сезонность', trend: 'Тренд', promotion: 'Промо', external_factors: 'Внешние факторы' };
        document.querySelector('#scenario-meta').textContent = `${benchmark.benchmark_id} · ${benchmark.series_count} рядов · ${benchmark.config.max_epochs} эпох`;
        document.querySelector('#scenario-results').innerHTML = benchmark.scenarios.map(scenario => {
            const winner = scenario.results.find(item => item.model === scenario.winner);
            const neural = scenario.results.find(item => item.model === scenario.best_neural);
            return `<tr><td><b>${labels[scenario.scenario] || escapeHtml(scenario.scenario)}</b></td><td>${escapeHtml(scenario.winner)}</td><td>${Number(winner?.metrics?.wape_pct).toLocaleString('ru-RU')}%</td><td>${escapeHtml(scenario.best_neural || '—')}</td><td>${neural ? `${Number(neural.metrics.wape_pct).toLocaleString('ru-RU')}%` : '—'}</td></tr>`;
        }).join('');
        const neuralRanking = Object.entries(benchmark.models || {}).sort((a, b) => a[1].mean_wape_pct - b[1].mean_wape_pct);
        document.querySelector('#scenario-conclusion').textContent = neuralRanking.length
            ? `Среди нейросетей лидирует ${neuralRanking[0][0]}: средний WAPE ${Number(neuralRanking[0][1].mean_wape_pct).toLocaleString('ru-RU')}%, побед в сценариях — ${neuralRanking[0][1].scenario_wins}.`
            : 'Нейросетевые результаты отсутствуют.';
    }

    async function loadResearchReport() {
        const data = await api('research-report');
        const report = data.report;
        if (!report) return;
        document.querySelector('#research-report-meta').textContent = `${report.dataset} · ${report.rolling_folds} rolling-окна`;
        document.querySelector('#research-best-neural').textContent = `ЛУЧШАЯ НС · ${String(report.best_neural).toUpperCase()}`;
        document.querySelector('#research-verdict').textContent = report.conclusion;
        document.querySelector('#research-recommendations').innerHTML = (report.recommendations || []).map((item, index) => `<article><b>${String(index + 1).padStart(2, '0')}</b> ${escapeHtml(item)}</article>`).join('');
        document.querySelector('#research-scale-results').innerHTML = (report.scalability || []).map(item => `<tr><td><b>${Number(item.series).toLocaleString('ru-RU')} рядов</b></td><td>${Number(item.rows).toLocaleString('ru-RU')}</td><td>${Number(item.wall_seconds).toLocaleString('ru-RU')} сек.</td><td>${Number(item.process_peak_memory_mb).toLocaleString('ru-RU')} МБ</td></tr>`).join('') || '<tr><td colspan="4">Нет результатов масштабирования.</td></tr>';
    }

    async function startLocalTraining(button) {
        setButtonLoading(button, true);
        try {
            const data = await api('training-pipeline', { method: 'POST', body: '{}' });
            document.querySelector('#training-pipeline-status').textContent = `${data.pipeline.status} · ${data.pipeline.message}`;
            toast(data.pipeline.message);
        } catch (error) {
            toast(error.message || 'Не удалось запустить локальный эксперимент', 'error');
        } finally {
            setButtonLoading(button, false);
        }
    }

    async function registerModelCandidate(button) {
        const experimentId = document.querySelector('#experiment-selector')?.value;
        setButtonLoading(button, true);
        try {
            const data = await api('models/candidates', {
                method: 'POST',
                body: JSON.stringify({ experiment_id: experimentId, model: button.dataset.model }),
            });
            toast(data.candidate.eligible ? 'Кандидат прошёл проверки' : 'Кандидат добавлен, публикация пока заблокирована');
            await loadModelRegistry();
        } catch (error) {
            toast(error.message || 'Не удалось зарегистрировать кандидата', 'error');
        } finally {
            setButtonLoading(button, false);
        }
    }

    async function promoteModel(button) {
        if (!window.confirm('Опубликовать кандидата в production? Текущая модель будет сохранена в архиве.')) return;
        setButtonLoading(button, true);
        try {
            await api(`models/${encodeURIComponent(button.dataset.modelId)}/promote`, {
                method: 'POST',
                body: JSON.stringify({ confirmation: 'PROMOTE' }),
            });
            toast('Новая production-модель опубликована');
            await loadModelRegistry();
        } catch (error) {
            toast(error.message || 'Публикация модели заблокирована', 'error');
        } finally {
            setButtonLoading(button, false);
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
        applyChartMode(document.querySelector('[data-chart-mode].is-active')?.dataset.chartMode || 'all');
    }

    function applyChartMode(mode) {
        if (!forecastChart) return;
        forecastChart.data.datasets.forEach(dataset => {
            const stockSeries = dataset.label.toLowerCase().includes('остаток') || dataset.label.toLowerCase().includes('запас');
            dataset.hidden = mode === 'demand' ? stockSeries : mode === 'stock' ? !stockSeries : false;
        });
        forecastChart.update();
    }

    function updateSimulationKpis(data) {
        const q50 = Array.isArray(data.q50) ? data.q50 : data.demand || [];
        const q10 = data.q10 || [];
        const q90 = data.q90 || [];
        const stock = data.stock || [];
        const sum = values => values.reduce((total, value) => total + Number(value || 0), 0);
        const demandTotal = document.querySelector('#sim-demand-total');
        const stockEnd = document.querySelector('#sim-stock-end');
        const range = document.querySelector('#sim-demand-range');
        const quality = document.querySelector('#sim-quality');
        if (demandTotal) demandTotal.textContent = `${Math.round(sum(q50)).toLocaleString('ru-RU')} ед.`;
        if (stockEnd) stockEnd.textContent = `${Math.round(Number(stock.at(-1) || 0)).toLocaleString('ru-RU')} ед.`;
        if (range) range.textContent = `${Math.round(sum(q10)).toLocaleString('ru-RU')} → ${Math.round(sum(q90)).toLocaleString('ru-RU')}`;
        if (quality) quality.textContent = `${Number(data.quality?.score || 0).toLocaleString('ru-RU')} / 100`;
        const note = document.querySelector('#sim-quality-note');
        if (note) note.textContent = data.quality?.grade === 'high' ? 'высокая уверенность' : data.quality?.grade === 'medium' ? 'средняя уверенность' : 'нужна осторожность';
        document.querySelectorAll('#simulation-kpis article').forEach((card, index) => {
            card.classList.remove('value-pulse');
            setTimeout(() => card.classList.add('value-pulse'), index * 45);
        });
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
        localStorage.setItem(branchStorageKey('last-forecast'), JSON.stringify({
            data,
            payload,
            createdAt: new Date().toISOString(),
        }));
        renderForecast(data);
        updateSimulationKpis(data);
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
        if (page !== 'simulator') return false;
        try {
            const saved = JSON.parse(localStorage.getItem(branchStorageKey('last-forecast')) || 'null');
            if (!saved?.data?.dates?.length) return false;
            applySimulationPayload(saved.payload);
            renderForecast(saved.data);
            updateSimulationKpis(saved.data);
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
            return true;
        } catch (error) {
            localStorage.removeItem(branchStorageKey('last-forecast'));
            return false;
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
                <a class="artifact-link" target="_blank" rel="noopener" href="/download/reports/${encodeURIComponent(artifact.filename)}?branch_id=${encodeURIComponent(activeBranchId || '')}">
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
            localStorage.setItem(branchStorageKey('last-report'), JSON.stringify(stored));
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
        const lastReport = localStorage.getItem(branchStorageKey('last-report'));
        if (page !== 'reports' || !lastReport) return;
        try {
            const item = JSON.parse(lastReport);
            const count = renderReportResult(item, 'Последний комплект');
            if (!count) throw new Error('Stored report has no artifacts');
            const status = document.querySelector('#report-status');
            if (status) status.textContent = 'Восстановлено из последней сессии';
        } catch (error) {
            localStorage.removeItem(branchStorageKey('last-report'));
        }
    }

    window.reloadChart = () => {
        if (page === 'dashboard') loadData();
        if (page === 'simulator' && forecastChart) {
            try {
                const saved = JSON.parse(localStorage.getItem(branchStorageKey('last-forecast')) || 'null');
                if (saved?.data) renderForecast(saved.data);
            } catch (error) {
                localStorage.removeItem(branchStorageKey('last-forecast'));
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
    document.querySelector('#experiment-results')?.addEventListener('click', event => {
        const button = event.target.closest('.registry-add');
        if (button) registerModelCandidate(button);
    });
    document.querySelector('#model-registry-list')?.addEventListener('click', event => {
        const button = event.target.closest('.registry-promote');
        if (button) promoteModel(button);
    });
    document.querySelector('#start-local-training')?.addEventListener('click', event => startLocalTraining(event.currentTarget));
    document.querySelector('#stock-modal')?.addEventListener('click', event => {
        if (event.target.id === 'stock-modal') closeStockModal();
    });
    document.querySelector('#run-simulation')?.addEventListener('click', runSimulationAsync);
    document.querySelectorAll('[data-chart-mode]').forEach(button => button.addEventListener('click', () => {
        document.querySelectorAll('[data-chart-mode]').forEach(item => item.classList.toggle('is-active', item === button));
        applyChartMode(button.dataset.chartMode);
    }));
    let simulationTimer;
    const scheduleSimulation = () => {
        if (page !== 'simulator' || !document.querySelector('#sim-product')?.value) return;
        clearTimeout(simulationTimer);
        simulationTimer = setTimeout(runSimulationAsync, 280);
    };
    document.querySelector('#sim-product')?.addEventListener('change', scheduleSimulation);
    document.querySelector('#sim-promo')?.addEventListener('change', scheduleSimulation);
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
    document.querySelectorAll('.panel,.metric-card,.quick-card,.report-card,.knowledge-card,.simulation-kpis article,.branch-command-card')
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

    document.querySelectorAll('a[href^="/"]').forEach(link => link.addEventListener('click', event => {
        if (reduceMotion || event.metaKey || event.ctrlKey || event.shiftKey || link.target === '_blank') return;
        const target = new URL(link.href, window.location.href);
        if (target.origin !== window.location.origin || target.pathname === window.location.pathname) return;
        event.preventDefault();
        document.body.classList.add('page-leaving');
        document.querySelector('#route-progress')?.classList.add('is-active');
        setTimeout(() => { window.location.href = target.href; }, 150);
    }));

    if (!reduceMotion) {
        document.querySelectorAll('[data-tilt]').forEach(card => {
            card.addEventListener('pointermove', event => {
                const rect = card.getBoundingClientRect();
                const x = (event.clientX - rect.left) / rect.width - 0.5;
                const y = (event.clientY - rect.top) / rect.height - 0.5;
                card.style.transform = `perspective(700px) rotateX(${-y * 3}deg) rotateY(${x * 4}deg) translateY(-2px)`;
            });
            card.addEventListener('pointerleave', () => { card.style.transform = ''; });
        });
    }

    const setPresentationMode = enabled => {
        document.body.classList.toggle('presentation-mode', enabled);
        if (enabled) document.documentElement.requestFullscreen?.().catch(() => {});
        else if (document.fullscreenElement) document.exitFullscreen?.().catch(() => {});
    };
    document.querySelector('#presentation-mode')?.addEventListener('click', () => setPresentationMode(true));
    document.querySelector('#presentation-exit')?.addEventListener('click', () => setPresentationMode(false));
    document.addEventListener('keydown', event => {
        if (event.key === 'Escape' && document.body.classList.contains('presentation-mode')) setPresentationMode(false);
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

    async function initializeBranch() {
        const response = await fetch('/api/branches', { headers: { Accept: 'application/json', ...(activeBranchId ? { 'X-Branch-ID': String(activeBranchId) } : {}) } });
        if (!response.ok && activeBranchId) {
            localStorage.removeItem('rayventory-branch-id');
            activeBranchId = null;
            return initializeBranch();
        }
        const data = await response.json();
        activeBranchId = Number(data.active_branch_id);
        localStorage.setItem('rayventory-branch-id', String(activeBranchId));
        const select = document.querySelector('#branch-select');
        if (select) {
            select.innerHTML = data.branches.map(branch => `<option value="${branch.id}">${escapeHtml(branch.name)}</option>`).join('');
            select.value = String(activeBranchId);
            select.onchange = () => {
                localStorage.setItem('rayventory-branch-id', select.value);
                window.location.reload();
            };
        }
    }

    async function loadUsers() {
        const [data, summary] = await Promise.all([api('users'), api('branches-summary')]);
        const table = document.querySelector('#users-table');
        if (table) table.innerHTML = data.users.map(user => `<tr><td><b>${escapeHtml(user.name)}</b><span class="table-subline">${user.is_admin ? 'Глобальный администратор' : 'Пользователь филиала'}</span></td><td>${escapeHtml(user.email)}</td><td>${user.branches.map(branch => `<span class="status-pill">${escapeHtml(branch.name)}</span>`).join(' ') || '—'}</td></tr>`).join('');
        const summaryTable = document.querySelector('#branches-summary-table');
        if (summaryTable) summaryTable.innerHTML = summary.branches.map(branch => `<tr><td><b>${escapeHtml(branch.name)}</b><span class="table-subline">${branch.users} польз.</span></td><td>${branch.products}</td><td>${Number(branch.sales_rows).toLocaleString('ru-RU')}</td><td>${Number(branch.stock_units).toLocaleString('ru-RU')}</td><td><span class="confidence ${branch.critical_count ? 'low' : 'high'}">${branch.critical_count} SKU</span></td><td>${escapeHtml(branch.last_sale_date || 'нет данных')}</td></tr>`).join('');
        const grid = document.querySelector('#branch-command-grid');
        if (grid) grid.innerHTML = summary.branches.map(branch => {
            const riskShare = branch.products ? Math.min(100, Number(branch.critical_count) / Number(branch.products) * 100) : 0;
            return `<article class="branch-command-card"><header><b>${escapeHtml(branch.name)}</b><span>${branch.users} польз.</span></header><div class="branch-command-metrics"><div><small>Капитал</small><b>${Math.round(Number(branch.stock_value)).toLocaleString('ru-RU')} ₸</b></div><div><small>SKU</small><b>${branch.products}</b></div><div><small>Риск</small><b>${branch.critical_count}</b></div></div><div class="branch-command-health" title="Доля SKU в риске"><i style="width:${riskShare}%"></i></div></article>`;
        }).join('');
    }

    document.querySelector('#user-create-form')?.addEventListener('submit', async event => {
        event.preventDefault();
        try {
            await api('users', { method: 'POST', body: JSON.stringify({
                name: document.querySelector('#new-user-name').value,
                email: document.querySelector('#new-user-email').value,
                password: document.querySelector('#new-user-password').value,
                memberships: [{ branch_id: activeBranchId, role: document.querySelector('#new-user-role').value }],
            }) });
            event.target.reset();
            await loadUsers();
            toast('Пользователь создан');
        } catch (error) { toast(error.message, 'error'); }
    });

    document.querySelector('#password-change-form')?.addEventListener('submit', async event => {
        event.preventDefault();
        try {
            await api('account/password', { method: 'POST', body: JSON.stringify({
                current_password: document.querySelector('#current-password').value,
                password: document.querySelector('#new-password').value,
                password_confirmation: document.querySelector('#new-password-confirmation').value,
            }) });
            event.target.reset();
            toast('Пароль обновлён');
        } catch (error) { toast(error.message, 'error'); }
    });

    document.querySelector('#create-branch')?.addEventListener('click', async () => {
        const name = window.prompt('Название нового филиала');
        if (!name?.trim()) return;
        try {
            const result = await api('branches', { method: 'POST', body: JSON.stringify({ name: name.trim() }) });
            localStorage.setItem('rayventory-branch-id', String(result.branch.id));
            window.location.reload();
        } catch (error) {
            toast(error.message, 'error');
        }
    });

    initializeBranch().then(() => {
        restoreLastReport();
        if (page === 'dashboard' || page === 'inventory') loadData();
        if (page === 'simulator') loadData().then(() => {
            if (!restoreLastForecast()) runSimulationAsync();
        });
        if (page === 'purchases') loadPurchasePlan();
        if (page === 'model-health') loadModelHealth();
        if (page === 'experiments') {
            loadExperiments();
            loadModelRegistry().catch(error => toast(error.message, 'error'));
            loadTrainingReadiness().catch(error => toast(error.message, 'error'));
            loadTrainingPipeline().catch(error => toast(error.message, 'error'));
            loadDatasetAnalysis().catch(error => toast(error.message, 'error'));
            loadTuning().catch(error => toast(error.message, 'error'));
            loadScenarios().catch(error => toast(error.message, 'error'));
            loadResearchReport().catch(error => toast(error.message, 'error'));
        }
        if (page === 'settings' && document.querySelector('#users-table')) loadUsers().catch(error => toast(error.message, 'error'));
    }).catch(error => toast(error.message || 'Не удалось выбрать филиал', 'error'));
})();

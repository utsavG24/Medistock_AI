// ======================================================
// MEDISTOCK - FRONTEND JAVASCRIPT
// ======================================================

const API_BASE = "http://127.0.0.1:8000";
let aiChatHistory = [];  // keeps recent Q&A turns for follow-up questions like "which?"



if (localStorage.getItem("medistock-theme") === "dark") {
    document.documentElement.classList.add("dark-mode");
}

document.addEventListener("DOMContentLoaded", async function () {
    const admin = await requireLogin();
    if (!admin) return;
    if (window.lucide) {
        lucide.createIcons();
    }
    try {
        console.log("Medistock frontend loaded");
        initSidebarToggle();
        initNotifications();
        initStatCardReveal();

        const currentPage = window.location.pathname;

        if (currentPage.includes("ai-chat.html")) {
            await loadAIChatPage();
        } else if (currentPage.includes("stock-requirement.html")) {
            await loadRequirementPage();
        } else if (currentPage.includes("expiring-stock.html")) {
            await loadExpiringPage();
        } else if (currentPage.includes("stock.html")) {
            await loadStockPage();
        } else if (currentPage.includes("analytics.html")) {
            await loadAnalyticsPage();
        } else if (currentPage.includes("settings.html")) {
            loadSettingsPage();
        } else if (currentPage.includes("medicine.html")) {
            await loadMedicinePage();
        } else {
            await loadDashboard();
        }
    } finally {
        document.body.classList.add("page-ready");
        document.body.classList.remove("app-loading");
        const loadingScreen = document.querySelector(".app-loading-screen");
        if (loadingScreen) {
            loadingScreen.addEventListener("transitionend", () => loadingScreen.remove(), { once: true });
        }
    }
});



function initStatCardReveal() {
    const cards = document.querySelectorAll(".stat-card");
    if (!cards.length) return;

    cards.forEach((card, index) => {
        card.classList.add("fade-in");
        card.style.transitionDelay = `${index * 0.08}s`;
    });

    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches || !("IntersectionObserver" in window)) {
        cards.forEach(card => card.classList.add("visible"));
        return;
    }

    const observer = new IntersectionObserver(entries => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add("visible");
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.15 });

    cards.forEach(card => observer.observe(card));
}

// ======================================================
// DASHBOARD (index.html)
// ======================================================

async function loadDashboard() {
    await updateDashboardStats();
    await loadSalesTrendChart("fy");
    await loadCurrentStockTable();
    await loadAIInsights();

    const periodSelect = document.getElementById("salesTrendPeriod");
    if (periodSelect) {
        periodSelect.addEventListener("change", () => loadSalesTrendChart(periodSelect.value));
    }
}

async function loadSalesTrendChart(period = "fy") {
    const chart = document.getElementById("salesTrendChart");
    if (!chart) return;

    try {
        const response = await fetch(`${API_BASE}/dashboard/sales-trend?period=${encodeURIComponent(period)}`);
        if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}`);

        const data = await response.json();
        const labels = data.labels || [];
        const values = data.values || [];

        if (!labels.length || !values.length) {
            chart.innerHTML = '<div class="empty-state-inline">No sales data available yet.</div>';
            return;
        }

        const maxValue = Math.max(...values, 1);
        const bars = values.map((value, index) => {
            const height = Math.max((value / maxValue) * 100, 5);
            const label = labels[index] || "";
            const formatted = `₹${Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
            const tooltip = `${label}: ${formatted}`;
            return `<span title="${escapeHTML(tooltip)}" data-tooltip="${escapeHTML(tooltip)}" aria-label="${escapeHTML(tooltip)}" role="img" tabindex="0" style="height: ${height}%;"></span>`;
        }).join("");

        const yLabels = [
            `${Math.round(maxValue)}`,
            `${Math.round(maxValue * 0.75)}`,
            `${Math.round(maxValue * 0.5)}`,
            `${Math.round(maxValue * 0.25)}`,
            "0"
        ];

        chart.innerHTML = `
            <div class="chart-y-axis">
                ${yLabels.map(label => `<span>${escapeHTML(label)}</span>`).join("")}
            </div>
            <div class="fake-chart">
                <div class="chart-line">${bars}</div>
                <div class="chart-months">${labels.map(label => `<span>${escapeHTML(label)}</span>`).join("")}</div>
            </div>
        `;
    } catch (error) {
        console.error("Error loading sales trend:", error);
        chart.innerHTML = '<div class="empty-state-inline">Unable to load sales history.</div>';
    }
}

async function loadAIChatPage() {
    initAIChat();
}

function initAIChat() {
    const form = document.getElementById("aiChatForm");
    const input = document.getElementById("aiChatInput");
    const messages = document.getElementById("aiChatMessages");
    const button = document.getElementById("aiChatSend");
    const voiceButton = document.getElementById("aiVoiceButton");
    if (!form || form.dataset.initialized) return;
    form.dataset.initialized = "true";

    const SpeechRecognitionAPI = window.SpeechRecognition || window.webkitSpeechRecognition;
    let recognition = null;

    if (SpeechRecognitionAPI && voiceButton) {
        recognition = new SpeechRecognitionAPI();
        recognition.lang = "en-IN";
        recognition.interimResults = false;
        recognition.continuous = false;

        recognition.onresult = (event) => {
            const transcript = Array.from(event.results)
                .map(result => result[0].transcript)
                .join(" ")
                .trim();

            if (transcript) {
                const existing = input.value.trim();
                input.value = existing ? `${existing} ${transcript}` : transcript;
                input.dispatchEvent(new Event("input"));
            }
        };

        recognition.onstart = () => {
            voiceButton.classList.add("is-listening");
            voiceButton.querySelector("img").classList.add("is-listening");
            voiceButton.title = "Listening... click again to stop";
        };

        recognition.onend = () => {
            voiceButton.classList.remove("is-listening");
            voiceButton.querySelector("img").classList.remove("is-listening");
            voiceButton.title = "Use voice input";
            input.focus();
        };

        recognition.onerror = () => {
            voiceButton.classList.remove("is-listening");
            voiceButton.querySelector("img").classList.remove("is-listening");
            voiceButton.title = "Voice input unavailable";
        };

        voiceButton.addEventListener("click", () => {
            if (voiceButton.classList.contains("is-listening")) {
                recognition.stop();
                return;
            }

            input.focus();
            recognition.start();
        });
    } else if (voiceButton) {
        voiceButton.disabled = true;
        voiceButton.title = "Voice input is not supported in this browser";
    }

    document.querySelectorAll("[data-chat-question]").forEach(chip => {
        chip.addEventListener("click", () => {
            input.value = chip.dataset.chatQuestion;
            input.focus();
        });
    });

    form.addEventListener("submit", async event => {
        event.preventDefault();
        const question = input.value.trim();
        if (!question) return;
        appendAIChatMessage(messages, question, "user");
        input.value = "";
        button.disabled = true;
        const loadingMessage= appendAIChatLoading(messages);
        messages.scrollTop = messages.scrollHeight;

        try {
            const response = await fetch(`${API_BASE}/ai/ask`, {
                method: "POST",
                credentials: "include",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ question, history: aiChatHistory })
            });
            const data = await response.json();
            if (loadingMessage) {
                loadingMessage.stop();
                loadingMessage.remove();
            }
            if (!response.ok) throw new Error(data.detail || "Unable to get an answer.");
            appendAIChatMessage(messages, data.answer || "No answer was returned.", "assistant");

            aiChatHistory.push({ question, answer: data.answer });
            if (aiChatHistory.length > 4) aiChatHistory.shift();
        } catch (error) {
            if (loadingMessage) {
                loadingMessage.stop();
                loadingMessage.remove();
            }

            appendAIChatMessage(messages,"Sorry, something went wrong. Please try again.","assistant error");
        } finally {
            button.disabled = false;
            input.focus();
            messages.scrollTop = messages.scrollHeight;
        }
    });
}

function appendAIChatMessage(container, text, type) {
    const message = document.createElement("div");
    message.className = `ai-chat-message ${type}`;
    message.textContent = text;
    container.appendChild(message);
}
function appendAIChatLoading(container) {
    const message = document.createElement("div");
    message.className = "ai-chat-message assistant loading";

    message.innerHTML = `
        <div class="ai-loading-content">
            <span class="ai-loading-orb"></span>

            <span class="ai-loading-text">Reviewing your complete inventory data</span>

            <span class="ai-loading-dots">
                <span></span>
                <span></span>
                <span></span>
            </span>
        </div>
    `;

    container.appendChild(message);

    const statuses = [
        "Reviewing your complete inventory data",
        "Checking stock levels",
        "Analyzing medicine records",
        "Looking for relevant patterns",
        "Preparing your answer"
    ];

    let index = 0;

    const textElement = message.querySelector(".ai-loading-text");

    const interval = setInterval(() => {
        index = (index + 1) % statuses.length;

        textElement.classList.add("changing");

        setTimeout(() => {
            if (!message.isConnected) return;

            textElement.textContent = statuses[index];
            textElement.classList.remove("changing");
        }, 180);

    }, 1800);

    message.stop = () => {
        clearInterval(interval);
    };

    return message;
}

async function loadAIInsights() {
    const container = document.getElementById("aiInsightsList");
    if (!container) return;

    try {
        const response = await fetch(`${API_BASE}/ai/insights`, { credentials: "include" });
        if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}`);
        const data = await response.json();
        const runningOutNames = data.running_out_names || [];
        const runningOutLabel = data.running_out_count === 0
            ? "No medicines are likely to run out"
            : `${data.running_out_count} medicine${data.running_out_count === 1 ? "" : "s"} may run out`;
        const runningOutDetail = runningOutNames.length
            ? `Watch: ${runningOutNames.map(escapeHTML).join(", ")}.`
            : "Based on recent demand over the last 90 days.";

        container.innerHTML = `
        <div class="ai-insight ${data.running_out_count ? "high" : "good"}">
            <div class="insight-icon">${data.running_out_count ? '<i data-lucide="triangle-alert"></i>' : '<i data-lucide="circle-check"></i>'}</div>
            <div><strong>${runningOutLabel}</strong><p>${runningOutDetail}</p></div>
        </div>
        <div class="ai-insight ${data.expiring_soon_count ? "medium" : "good"}">
            <div class="insight-icon">${data.expiring_soon_count ? '<i data-lucide="triangle-alert"></i>' : '<i data-lucide="circle-check"></i>'}</div>
            <div><strong>${data.expiring_soon_count} batch${data.expiring_soon_count === 1 ? "" : "es"} expiring soon</strong><p>Review stock expiring within 60 days.</p></div>
        </div>
        <div class="ai-insight good">
            <div class="insight-icon"><i data-lucide="circle-check"></i></div>
            <div><strong>${data.healthy_percentage}% of stock is healthy</strong><p>Current inventory is within the safe range.</p></div>
        </div>`;

        if (window.lucide) lucide.createIcons();    
    } catch (error) {
        console.error("Error loading AI insights:", error);
        container.innerHTML = `<div class="ai-status-error">AI insights are unavailable right now. Refresh to try again.</div>`;
    }
}

function initAIAsk() {
    const form = document.getElementById("aiAskForm");
    const questionInput = document.getElementById("aiQuestion");
    const answer = document.getElementById("aiAnswer");
    const button = document.getElementById("aiAskButton");
    if (!form || form.dataset.initialized) return;
    form.dataset.initialized = "true";

    document.querySelectorAll("[data-ai-question]").forEach(chip => {
        chip.addEventListener("click", () => {
            questionInput.value = chip.dataset.aiQuestion;
            questionInput.focus();
        });
    });

    form.addEventListener("submit", async event => {
        event.preventDefault();
        const question = questionInput.value.trim();
        if (!question) return;
        button.disabled = true;
        button.textContent = "...";
        answer.textContent = "Thinking...";
        answer.className = "ai-answer is-loading";

        try {
            const response = await fetch(`${API_BASE}/ai/ask`, {
                method: "POST",
                credentials: "include",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ question, history: aiChatHistory })
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.detail || "Unable to get an answer.");
            appendAIChatMessage(messages, data.answer || "No answer was returned.", "assistant");

            aiChatHistory.push({ question, answer: data.answer });
            if (aiChatHistory.length > 4) aiChatHistory.shift();
        } catch (error) {
            console.error("Error asking AI:", error);
            answer.textContent = error.message || "Unable to reach the AI service.";
            answer.className = "ai-answer is-error";
        } finally {
            button.disabled = false;
            button.textContent = "Ask";
        }
    });
}

async function updateDashboardStats() {
    try {
        const response = await fetch(`${API_BASE}/dashboard/summary`);
        if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}`);
        const data = await response.json();

        setText("totalMedicines", data.total_medicines);
        setText("totalStock", data.total_stock.toLocaleString());
        setText("lowStockCount", data.low_stock_count);
        setText("expiringSoonCount", data.expiring_soon_count);

    } catch (error) {
        console.error("Error loading dashboard summary:", error);
    }
}

async function loadCurrentStockTable() {
    const tableBody = document.getElementById("currentStockBody");
    if (!tableBody) return;

    try {
        const response = await fetch(`${API_BASE}/stock/current`);
        if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}`);
        const data = await response.json();

        // Keep the dashboard preview balanced instead of showing expiry-ordered rows only.
        renderDashboardStockRows(getDashboardPreviewRows(data), tableBody);

    } catch (error) {
        console.error("Error loading current stock:", error);
        tableBody.innerHTML = `<tr><td colspan="6" style="text-align:center;">Unable to load stock data.</td></tr>`;
    }
}

function getDashboardPreviewRows(data) {
    const groups = ["Low Stock", "Expiring Soon", "Expired", "Healthy", "Out of Stock"]
        .map(status => data
            .filter(item => item.status === status)
            .sort((a, b) => a.name.localeCompare(b.name))
        );
    const preview = [];

    while (preview.length < 10 && groups.some(group => group.length)) {
        groups.forEach(group => {
            if (group.length && preview.length < 10) preview.push(group.shift());
        });
    }

    return preview;
}

function renderDashboardStockRows(data, tableBody) {
    tableBody.innerHTML = "";

    if (data.length === 0) {
        tableBody.innerHTML = `<tr><td colspan="6" style="text-align:center;">No stock data available.</td></tr>`;
        return;
    }

    data.forEach(item => {
        const row = document.createElement("tr");
        row.innerHTML = `
            <td>
                <div class="medicine-name">
                    <div class="medicine-icon">${escapeHTML(item.name.charAt(0))}</div>
                    <div>
                        <strong>${escapeHTML(item.name)}</strong>
                    </div>
                </div>
            </td>
            <td>${escapeHTML(item.category)}</td>
            <td>${escapeHTML(item.batch_number)}</td>
            <td><strong>${escapeHTML(formatInventoryQuantity(item.stock, item))}</strong></td>
            <td>${formatDate(item.expiry_date)}</td>
            <td>${statusBadge(item.status)}</td>
        `;
        tableBody.appendChild(row);
    });
}

// ======================================================
// STOCK PAGE (stock.html)
// ======================================================

let allStock = [];
async function loadStockPage() {
    const tableBody = document.getElementById("medicineTableBody");
    if (!tableBody) return;

    try {
        const response = await fetch(`${API_BASE}/stock/current`);
        if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}`);
        allStock = await response.json();

        updateStockPageStats(allStock);
        populateCategoryFilter(allStock);
        stockCurrentPage = 1;
        renderStockPage(allStock);

    } catch (error) {
        console.error("Error loading stock page:", error);
        tableBody.innerHTML = `<tr><td colspan="8" style="text-align:center;">Unable to load stock data.</td></tr>`;
    }

    ["searchInput", "categoryFilter", "stockSortSelect", "expiryFrom", "expiryTo"].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.addEventListener(el.tagName === "INPUT" ? "input" : "change", applyStockFilters);
    });
}


function updateStockPageStats(data) {
    const uniqueMedicines = new Set(data.map(item => item.name)).size;
    const totalUnits = data.reduce((sum, item) => sum + item.stock, 0);

    const lowStockCount = data.filter(item => item.status === "Low Stock").length;
    const outOfStockCount = data.filter(item => item.status === "Out of Stock").length;

    setText("totalMedicines", uniqueMedicines);
    setText("totalUnits", totalUnits.toLocaleString());
    setText("lowStock", lowStockCount);
    setText("outOfStock", outOfStockCount);
}

function populateCategoryFilter(data) {
    const select = document.getElementById("categoryFilter");
    if (!select) return;

    const categories = [...new Set(data.map(item => item.category))].sort();
    select.innerHTML = `<option value="all">All Categories</option>`;
    categories.forEach(cat => {
        select.innerHTML += `<option value="${escapeHTML(cat)}">${escapeHTML(cat)}</option>`;
    });
}

function applyStockFilters() {
    const searchText = document.getElementById("searchInput").value.trim().toLowerCase();
    const selectedCategory = document.getElementById("categoryFilter").value;
    const sortValue = document.getElementById("stockSortSelect").value;
    const dateFrom = document.getElementById("expiryFrom").value;
    const dateTo = document.getElementById("expiryTo").value;

    let filtered = allStock.filter(item =>
        item.name.toLowerCase().includes(searchText) ||
        item.category.toLowerCase().includes(searchText) ||
        item.batch_number.toLowerCase().includes(searchText)
    );

    if (selectedCategory !== "all") filtered = filtered.filter(item => item.category === selectedCategory);
    if (dateFrom) filtered = filtered.filter(item => item.expiry_date >= dateFrom);
    if (dateTo) filtered = filtered.filter(item => item.expiry_date <= dateTo);

    filtered = sortStockData(filtered, sortValue);
    stockCurrentPage = 1;
    renderStockPage(filtered);
}

function sortStockData(data, sortValue) {
    const sorted = [...data];
    switch (sortValue) {
        case "expiry_asc": sorted.sort((a, b) => a.expiry_date.localeCompare(b.expiry_date)); break;
        case "expiry_desc": sorted.sort((a, b) => b.expiry_date.localeCompare(a.expiry_date)); break;
        case "stock_desc": sorted.sort((a, b) => b.stock - a.stock); break;
        case "stock_asc": sorted.sort((a, b) => a.stock - b.stock); break;
        case "mfg_desc": sorted.sort((a, b) => b.manufacture_date.localeCompare(a.manufacture_date)); break;
        case "mfg_asc": sorted.sort((a, b) => a.manufacture_date.localeCompare(b.manufacture_date)); break;
    }
    return sorted;
}

let stockCurrentPage = 1;
const STOCK_PAGE_SIZE = 10;
let currentFilteredStock = [];

function renderStockPage(filteredData) {
    currentFilteredStock = filteredData;
    const start = (stockCurrentPage - 1) * STOCK_PAGE_SIZE;
    renderStockTable(filteredData.slice(start, start + STOCK_PAGE_SIZE), document.getElementById("medicineTableBody"));
    renderStockPagination(filteredData.length);
}

function renderStockPagination(totalItems) {
    const container = document.getElementById("stockPagination");
    if (!container) return;
    const totalPages = Math.max(1, Math.ceil(totalItems / STOCK_PAGE_SIZE));
    container.innerHTML = `
        <button class="page-btn" onclick="goToStockPage(${stockCurrentPage - 1})" ${stockCurrentPage === 1 ? "disabled" : ""}>← Prev</button>
        <span class="page-indicator">Page ${stockCurrentPage} of ${totalPages}</span>
        <button class="page-btn" onclick="goToStockPage(${stockCurrentPage + 1})" ${stockCurrentPage === totalPages ? "disabled" : ""}>Next →</button>
    `;
}

function goToStockPage(page) {
    stockCurrentPage = page;
    renderStockPage(currentFilteredStock);
}

function renderStockTable(data, tableBody) {
    tableBody.innerHTML = "";

    if (data.length === 0) {
        tableBody.innerHTML = `<tr><td colspan="8" style="text-align:center;">Unable to load stock data.</td></tr>`;
        return;
    }

    data.forEach(item => {
        const row = document.createElement("tr");
        row.dataset.batchId = item.batch_id;
        row.innerHTML = `
            <td>
                <div class="medicine-name">
                    <div class="medicine-icon">${escapeHTML(item.name.charAt(0))}</div>
                    <div>
                        <strong>${escapeHTML(item.name)}</strong>
                        <span>${escapeHTML(item.category)}</span>
                    </div>
                </div>
            </td>
            <td>${escapeHTML(item.category)}</td>
            <td>${escapeHTML(item.batch_number)}</td>
            <td><strong>${escapeHTML(formatInventoryQuantity(item.stock, item))}</strong></td>
            <td>${escapeHTML(formatInventoryQuantity(item.reorder_level, item))}</td>
            <td>${formatDate(item.expiry_date)}</td>
            <td>${statusBadge(item.status)}</td>
            <td>
                <button class="row-action-btn sell" onclick="openActionModal(${item.batch_id}, 'sell', '${escapeHTML(item.name)}', ${item.stock}, ${item.units_per_strip || 1}, '${escapeHTML(item.unit || 'unit')}')">Sell</button>
                <button class="row-action-btn return" onclick="openActionModal(${item.batch_id}, 'customer_return', '${escapeHTML(item.name)}', ${item.stock}, ${item.units_per_strip || 1}, '${escapeHTML(item.unit || 'unit')}')">Return</button>
                <button class="row-action-btn exchange" onclick="openActionModal(${item.batch_id}, 'supplier_return', '${escapeHTML(item.name)}', ${item.stock}, ${item.units_per_strip || 1}, '${escapeHTML(item.unit || 'unit')}')">Exchange</button>
            </td>
        `;
        tableBody.appendChild(row);
    });
}

// ======================================================
// SELL / RETURN / EXCHANGE MODAL
// ======================================================

let currentAction = null;
let currentBatchId = null;
let currentMaxStock = null;

function openActionModal(batchId, action, medicineName, currentStock, unitsPerStrip = 1, unit = "unit") {
    currentAction = action;
    currentBatchId = batchId;
    currentMaxStock = currentStock;

    const titles = {
        sell: "Sell Stock",
        customer_return: "Customer Return",
        supplier_return: "Supplier Return / Exchange"
    };

    document.getElementById("actionModalTitle").textContent = titles[action];
    document.getElementById("actionModalMedicine").textContent = medicineName;
    const stripSummary = unitsPerStrip > 1
        ? ` (${Math.floor(currentStock / unitsPerStrip)} full strip${Math.floor(currentStock / unitsPerStrip) === 1 ? "" : "s"}, ${currentStock % unitsPerStrip} loose)`
        : "";
    document.getElementById("actionModalStock").textContent = `Current stock: ${currentStock} ${unit}${stripSummary}`;
    document.getElementById("actionQuantity").value = "";
    document.getElementById("actionReason").value = "";
    document.getElementById("actionReceived").value = "";

    document.getElementById("actionReasonField").style.display = action === "sell" ? "none" : "block";
    document.getElementById("actionReceivedField").style.display = action === "supplier_return" ? "block" : "none";
    document.getElementById("actionSaleUnitField").style.display = action === "sell" ? "block" : "none";
    document.getElementById("actionSaleUnit").value = "unit";
    document.getElementById("actionSaleUnit").dataset.unitsPerStrip = String(unitsPerStrip || 1);
    document.getElementById("actionSaleUnit").dataset.unit = unit;

    document.getElementById("actionMessage").textContent = "";
    document.getElementById("actionModalOverlay").style.display = "flex";
}
function closeActionModal() {
    document.getElementById("actionModalOverlay").style.display = "none";
}

async function submitAction() {
    const quantity = parseInt(document.getElementById("actionQuantity").value, 10);
    const reason = document.getElementById("actionReason").value.trim();
    const quantityReceived = parseInt(document.getElementById("actionReceived").value, 10) || 0;
    const saleUnit = document.getElementById("actionSaleUnit").value;
    const messageEl = document.getElementById("actionMessage");
    messageEl.textContent = "";
    messageEl.style.color = "#dc2626";

    if (!quantity || quantity <= 0) {
        messageEl.textContent = "Enter a quantity greater than 0.";
        return;
    }
    const unitsPerStrip = Number(document.getElementById("actionSaleUnit").dataset.unitsPerStrip || 1);
    const quantityInUnits = currentAction === "sell" && saleUnit === "strip"
        ? quantity * unitsPerStrip
        : quantity;
    if (currentAction === "sell" && quantityInUnits > currentMaxStock) {
        messageEl.textContent = `Only ${currentMaxStock} individual units available.`;
        return;
    }
    if (currentAction === "supplier_return" && quantity > currentMaxStock) {
        messageEl.textContent = `Only ${currentMaxStock} units available to return.`;
        return;
    }

    const endpoints = {
        sell: `${API_BASE}/sales`,
        customer_return: `${API_BASE}/returns/customer`,
        supplier_return: `${API_BASE}/returns/supplier`
    };

    const body = { batch_id: currentBatchId, quantity };
    if (currentAction === "sell") body.sale_unit = saleUnit;
    if (currentAction === "customer_return") body.reason = reason || null;
    if (currentAction === "supplier_return") {
        body.reason = reason || null;
        body.quantity_received = quantityReceived;
    }

    try {
        const response = await fetch(endpoints[currentAction], {
            method: "POST",
            credentials: "include",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body)
        });

        const data = await response.json();

        if (!response.ok) {
            messageEl.textContent = data.detail || "Action failed.";
            return;
        }

        closeActionModal();
        await loadStockPage();

    } catch (error) {
        console.error("Action error:", error);
        messageEl.textContent = "Unable to reach the server.";
    }
}

function statusBadge(status) {
    const map = {
        "Healthy": "good-status",
        "Low Stock": "low-status",
        "Expiring Soon": "expiry-status",
        "Expired": "expiry-status",
        "Out of Stock": "expiry-status"
    };
    const cls = map[status] || "good-status";
    return `<span class="status ${cls}">${escapeHTML(status)}</span>`;
}

function formatInventoryQuantity(quantity, item) {
    const amount = Number(quantity) || 0;
    const unit = (item.unit || "unit").trim() || "unit";
    const unitsPerStrip = Number(item.units_per_strip) || 1;
    const pluralUnit = unit.toLowerCase().endsWith("s") ? unit : `${unit}s`;
    const unitLabel = amount === 1 ? unit : pluralUnit;
    if (unitsPerStrip <= 1) return `${amount.toLocaleString()} ${unitLabel}`;

    const strips = Math.floor(amount / unitsPerStrip);
    const looseUnits = amount % unitsPerStrip;
    const stripLabel = `${strips} strip${strips === 1 ? "" : "s"}`;
    const looseUnitLabel = looseUnits === 1 ? unit : pluralUnit;
    if (looseUnits === 0) return `${stripLabel} (${amount.toLocaleString()} ${pluralUnit})`;
    if (strips === 0) return `${looseUnits} ${looseUnitLabel}`;
    return `${stripLabel} + ${looseUnits} ${looseUnitLabel}`;
}

// ======================================================
// SHARED: render a list of stock rows into a table body
// ======================================================

function renderStockTable(data, tableBody) {
    tableBody.innerHTML = "";

    if (data.length === 0) {
        tableBody.innerHTML = `<tr><td colspan="8" style="text-align:center;">Unable to load stock data.</td></tr>`;
        return;
    }

    data.forEach(item => {
        const row = document.createElement("tr");
        row.dataset.batchId = item.batch_id;

        const isExpired = item.status === "Expired";
        const sellButton = isExpired
            ? `<button class="row-action-btn sell" disabled title="Cannot sell expired stock">Sell</button>`
            : `<button class="row-action-btn sell" onclick="openActionModal(${item.batch_id}, 'sell', '${escapeHTML(item.name)}', ${item.stock}, ${item.units_per_strip || 1}, '${escapeHTML(item.unit || 'unit')}')">Sell</button>`;

        row.innerHTML = `
            <td>
                <div class="medicine-name">
                    <div class="medicine-icon">${escapeHTML(item.name.charAt(0))}</div>
                    <div>
                        <strong>${escapeHTML(item.name)}</strong>
                        <span>${escapeHTML(item.category)}</span>
                    </div>
                </div>
            </td>
            <td>${escapeHTML(item.category)}</td>
            <td>${escapeHTML(item.batch_number)}</td>
            <td><strong>${escapeHTML(formatInventoryQuantity(item.stock, item))}</strong></td>
            <td>${escapeHTML(formatInventoryQuantity(item.reorder_level, item))}</td>
            <td>${formatDate(item.expiry_date)}</td>
            <td>${statusBadge(item.status)}</td>
            <td>
                ${sellButton}
                <button class="row-action-btn return" onclick="openActionModal(${item.batch_id}, 'customer_return', '${escapeHTML(item.name)}', ${item.stock}, ${item.units_per_strip || 1}, '${escapeHTML(item.unit || 'unit')}')">Return</button>
                <button class="row-action-btn exchange" onclick="openActionModal(${item.batch_id}, 'supplier_return', '${escapeHTML(item.name)}', ${item.stock}, ${item.units_per_strip || 1}, '${escapeHTML(item.unit || 'unit')}')">Exchange</button>
            </td>
        `;
        tableBody.appendChild(row);
    });
}

// ======================================================
// ADD MEDICINE MODAL
// ======================================================

function openAddMedicine() {
    document.getElementById("addMedicineMessage").textContent = "";
    [
        "addName", "addCategory", "addManufacturer", "addUnit",
        "addUnitsPerStrip", "addPriceBasis", "addUnitPrice", "addReorderLevel", "addBatchNumber",
        "addQuantity", "addManufactureDate", "addExpiryDate"
    ].forEach(id => document.getElementById(id).value = "");

    document.getElementById("addMedicineOverlay").style.display = "flex";
}

function closeAddMedicineModal() {
    document.getElementById("addMedicineOverlay").style.display = "none";
}

async function submitAddMedicine() {
    const messageEl = document.getElementById("addMedicineMessage");
    messageEl.textContent = "";

    const payload = {
        name: document.getElementById("addName").value.trim(),
        category: document.getElementById("addCategory").value.trim(),
        manufacturer: document.getElementById("addManufacturer").value.trim(),
        unit: document.getElementById("addUnit").value.trim(),
        units_per_strip: parseInt(document.getElementById("addUnitsPerStrip").value, 10),
        price_basis: document.getElementById("addPriceBasis").value,
        unit_price: parseFloat(document.getElementById("addUnitPrice").value),
        reorder_level: parseInt(document.getElementById("addReorderLevel").value, 10),
        batch_number: document.getElementById("addBatchNumber").value.trim(),
        quantity: parseInt(document.getElementById("addQuantity").value, 10),
        manufacture_date: document.getElementById("addManufactureDate").value,
        expiry_date: document.getElementById("addExpiryDate").value
    };

    if (!payload.name || !payload.category || !payload.manufacturer || !payload.unit ||
        !payload.batch_number || !payload.manufacture_date || !payload.expiry_date) {
        messageEl.textContent = "Please fill in all fields.";
        return;
    }
    if (isNaN(payload.units_per_strip) || payload.units_per_strip < 1 ||
        isNaN(payload.unit_price) || isNaN(payload.reorder_level) || isNaN(payload.quantity)) {
        messageEl.textContent = "Units per strip, price, reorder level, and quantity must be valid numbers.";
        return;
    }
    if (payload.expiry_date <= payload.manufacture_date) {
        messageEl.textContent = "Expiry date must be after manufacture date.";
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/medicines`, {
            method: "POST",
            credentials: "include",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        const data = await response.json();

        if (!response.ok) {
            messageEl.textContent = data.detail || "Failed to add medicine.";
            return;
        }

        closeAddMedicineModal();
        await loadStockPage();  // refresh table, stats, and category dropdown

    } catch (error) {
        console.error("Add medicine error:", error);
        messageEl.textContent = "Unable to reach the server.";
    }
}

// ======================================================
// STOCK REQUIREMENT PAGE (stock-requirement.html)
// ======================================================

let allRequirements = [];
let reqCurrentPage = 1;
const REQ_PAGE_SIZE = 10;
let currentFilteredRequirements = [];

async function loadRequirementPage() {
    const tableBody = document.getElementById("requirementTableBody");
    if (!tableBody) return;

    try {
        const response = await fetch(`${API_BASE}/stock/requirement`);
        if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}`);
        allRequirements = await response.json();

        updateRequirementStats(allRequirements);
        populateRequirementCategoryFilter(allRequirements);
        reqCurrentPage = 1;
        renderRequirementPage(allRequirements);

    } catch (error) {
        console.error("Error loading stock requirement:", error);
        tableBody.innerHTML = `<tr><td colspan="8" style="text-align:center;">Unable to load stock requirement data.</td></tr>`;
    }

    ["reqSearchInput", "reqCategoryFilter", "reqSortSelect"].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.addEventListener(el.tagName === "INPUT" ? "input" : "change", applyRequirementFilters);
    });
}

function updateRequirementStats(data) {
    const count = data.length;
    const totalUnits = data.reduce((sum, item) => sum + item.suggested_order_qty, 0);
    const totalCost = data.reduce((sum, item) => sum + item.estimated_cost, 0);
    const urgentCount = data.filter(item => item.days_of_stock_left !== null && item.days_of_stock_left < 14).length;

    setText("reqCount", count);
    setText("reqTotalUnits", totalUnits.toLocaleString());
    setText("reqTotalCost", `₹${totalCost.toLocaleString(undefined, { maximumFractionDigits: 0 })}`);
    setText("reqUrgentCount", urgentCount);
}

function populateRequirementCategoryFilter(data) {
    const select = document.getElementById("reqCategoryFilter");
    if (!select) return;

    const categories = [...new Set(data.map(item => item.category))].sort();
    select.innerHTML = `<option value="all">All Categories</option>`;
    categories.forEach(cat => {
        select.innerHTML += `<option value="${escapeHTML(cat)}">${escapeHTML(cat)}</option>`;
    });
}

function applyRequirementFilters() {
    const searchText = document.getElementById("reqSearchInput").value.trim().toLowerCase();
    const selectedCategory = document.getElementById("reqCategoryFilter").value;
    const sortValue = document.getElementById("reqSortSelect").value;

    let filtered = allRequirements.filter(item =>
        item.name.toLowerCase().includes(searchText) ||
        item.category.toLowerCase().includes(searchText)
    );

    if (selectedCategory !== "all") {
        filtered = filtered.filter(item => item.category === selectedCategory);
    }

    filtered = sortRequirementData(filtered, sortValue);
    reqCurrentPage = 1;
    renderRequirementPage(filtered);
}

function sortRequirementData(data, sortValue) {
    const sorted = [...data];
    switch (sortValue) {
        case "urgency":
            sorted.sort((a, b) => {
                if (a.days_of_stock_left === null) return 1;
                if (b.days_of_stock_left === null) return -1;
                return a.days_of_stock_left - b.days_of_stock_left;
            });
            break;
        case "cost_desc": sorted.sort((a, b) => b.estimated_cost - a.estimated_cost); break;
        case "qty_desc": sorted.sort((a, b) => b.suggested_order_qty - a.suggested_order_qty); break;
        case "name": sorted.sort((a, b) => a.name.localeCompare(b.name)); break;
    }
    return sorted;
}

function renderRequirementPage(filteredData) {
    currentFilteredRequirements = filteredData;
    const start = (reqCurrentPage - 1) * REQ_PAGE_SIZE;
    renderRequirementTable(filteredData.slice(start, start + REQ_PAGE_SIZE), document.getElementById("requirementTableBody"));
    renderRequirementPagination(filteredData.length);
}

function renderRequirementPagination(totalItems) {
    const container = document.getElementById("reqPagination");
    if (!container) return;
    const totalPages = Math.max(1, Math.ceil(totalItems / REQ_PAGE_SIZE));
    container.innerHTML = `
        <button class="page-btn" onclick="goToRequirementPage(${reqCurrentPage - 1})" ${reqCurrentPage === 1 ? "disabled" : ""}>← Prev</button>
        <span class="page-indicator">Page ${reqCurrentPage} of ${totalPages}</span>
        <button class="page-btn" onclick="goToRequirementPage(${reqCurrentPage + 1})" ${reqCurrentPage === totalPages ? "disabled" : ""}>Next →</button>
    `;
}

function goToRequirementPage(page) {
    reqCurrentPage = page;
    renderRequirementPage(currentFilteredRequirements);
}

function renderRequirementTable(data, tableBody) {
    tableBody.innerHTML = "";

    if (data.length === 0) {
        tableBody.innerHTML = `<tr><td colspan="8" style="text-align:center;">Nothing needs reordering right now.</td></tr>`;
        return;
    }

    data.forEach(item => {
    const row = document.createElement("tr");
    const urgent = item.days_of_stock_left !== null && item.days_of_stock_left < 14;
    const daysLabel = item.days_of_stock_left === null ? "—" : `${item.days_of_stock_left}d`;
    const stockCell = item.fully_expired
        ? `<span class="status expiry-status">All Expired</span>`
        : formatInventoryQuantity(item.current_stock, item);

    row.innerHTML = `
        <td>
            <div class="medicine-name">
                <div class="medicine-icon">${escapeHTML(item.name.charAt(0))}</div>
                <div><strong>${escapeHTML(item.name)}</strong></div>
            </div>
        </td>
        <td>${escapeHTML(item.category)}</td>
        <td>${stockCell}</td>
        <td>${escapeHTML(formatInventoryQuantity(item.reorder_level, item))}</td>
        <td>${item.avg_daily_sales}</td>
        <td><strong>${escapeHTML(formatInventoryQuantity(item.suggested_order_qty, item))}</strong></td>
        <td>₹${item.estimated_cost.toLocaleString(undefined, { maximumFractionDigits: 2 })}</td>
        <td>${urgent ? `<span class="status low-status">${daysLabel}</span>` : daysLabel}</td>
    `;
    tableBody.appendChild(row);
});
}

// ======================================================
// UTILITIES
// ======================================================

function setText(id, value) {
    const el = document.getElementById(id);
    if (!el) return;

    if (el.closest(".stat-card") && animateStatValue(el, value)) return;
    el.textContent = value;
}

function animateStatValue(el, value) {
    const targetText = String(value);
    const match = targetText.match(/^(\D*)([\d,]+(?:\.\d+)?)(.*)$/);
    if (!match) return false;

    const [, prefix, numericText, suffix] = match;
    const target = Number(numericText.replace(/,/g, ""));
    if (!Number.isFinite(target)) return false;

    const startText = el.textContent.trim();
    const startMatch = startText.match(/^(\D*)([\d,]+(?:\.\d+)?)(.*)$/);
    const start = startMatch ? Number(startMatch[2].replace(/,/g, "")) : 0;
    const decimals = (numericText.split(".")[1] || "").length;
    const duration = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 700;
    const startedAt = performance.now();

    const render = now => {
        const progress = duration === 0 ? 1 : Math.min((now - startedAt) / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3);
        const current = start + (target - start) * eased;
        const formatted = current.toLocaleString(undefined, {
            minimumFractionDigits: decimals,
            maximumFractionDigits: decimals
        });
        el.textContent = `${prefix}${formatted}${suffix}`;
        if (progress < 1) window.requestAnimationFrame(render);
    };

    window.cancelAnimationFrame(el._statAnimationFrame);
    el._statAnimationFrame = window.requestAnimationFrame(render);
    return true;
}

function formatDate(dateString) {
    if (!dateString) return "N/A";
    const date = new Date(dateString);
    if (isNaN(date.getTime())) return "Invalid Date";
    return date.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
}

function escapeHTML(value) {
    if (value === null || value === undefined) return "";
    return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// ======================================================
// SALES ANALYTICS PAGE (analytics.html)
// ======================================================

let allTransactions = [];

async function loadAnalyticsPage() {
    const tableBody = document.getElementById("transactionsBody");
    if (!tableBody) return;

    try {
        const response = await fetch(`${API_BASE}/transactions`);
        if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}`);
        allTransactions = await response.json();

        updateFinancialYearFilterLabel();
        updateAnalyticsStats(allTransactions, getSelectedFinancialYearRange());
        txnCurrentPage = 1;
        renderTxnPage(filterTransactionsByFinancialYear(allTransactions, getSelectedFinancialYearRange()));

    } catch (error) {
        console.error("Error loading transactions:", error);
        tableBody.innerHTML = `<tr><td colspan="6" style="text-align:center;">Unable to load transactions.</td></tr>`;
    }

    ["txnSearchInput", "txnTypeFilter", "txnFinancialYearFilter", "txnSortSelect", "txnDateFrom", "txnDateTo"].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.addEventListener(el.tagName === "INPUT" ? "input" : "change", applyTxnFilters);
    });
}

function getFinancialYearRange(offset = 0) {
    const today = new Date();
    const currentStartYear = today.getMonth() >= 3
        ? today.getFullYear()
        : today.getFullYear() - 1;
    const startYear = currentStartYear + offset;
    return {
        start: `${startYear}-04-01`,
        end: `${startYear + 1}-03-31`,
        label: `FY ${startYear}-${String(startYear + 1).slice(-2)}`
    };
}

function getSelectedFinancialYearRange() {
    const selected = document.getElementById("txnFinancialYearFilter")?.value || "current";
    if (selected === "all") return null;
    return getFinancialYearRange(selected === "previous" ? -1 : 0);
}

function updateFinancialYearFilterLabel() {
    const filter = document.getElementById("txnFinancialYearFilter");
    if (!filter) return;
    const current = getFinancialYearRange(0);
    const previous = getFinancialYearRange(-1);
    filter.querySelector("option[value='current']").textContent = current.label;
    filter.querySelector("option[value='previous']").textContent = previous.label;
}

function filterTransactionsByFinancialYear(data, financialYear) {
    if (!financialYear) return data;
    return data.filter(t => t.date >= financialYear.start && t.date <= financialYear.end);
}

function updateAnalyticsStats(data, financialYear) {
    const financialYearData = filterTransactionsByFinancialYear(data, financialYear);
    const sales = financialYearData.filter(t => t.type === "Sale");
    const customerReturns = financialYearData.filter(t => t.type === "Customer Return");
    const supplierReturns = financialYearData.filter(t => t.type === "Supplier Return");

    const totalRevenue = sales.reduce((sum, t) => sum + (t.amount || 0), 0);

    setText("totalRevenue", `₹${totalRevenue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`);
    const revenueDescription = document.querySelector("#totalRevenue + small");
    if (revenueDescription) revenueDescription.textContent = financialYear
        ? `Sales revenue before costs (${financialYear.label})`
        : "Sales revenue before costs (all records)";
    setText("totalSales", sales.length);
    setText("totalCustomerReturns", customerReturns.reduce((sum, t) => sum + t.quantity, 0));
    setText("totalSupplierReturns", supplierReturns.reduce((sum, t) => sum + t.quantity, 0));
}

function applyTxnFilters() {
    const searchText = document.getElementById("txnSearchInput").value.trim().toLowerCase();
    const selectedType = document.getElementById("txnTypeFilter").value;
    const sortValue = document.getElementById("txnSortSelect").value;
    const dateFrom = document.getElementById("txnDateFrom").value;
    const dateTo = document.getElementById("txnDateTo").value;
    const financialYear = getSelectedFinancialYearRange();

    updateAnalyticsStats(allTransactions, financialYear);

    let filtered = filterTransactionsByFinancialYear(allTransactions, financialYear)
        .filter(t => t.medicine_name.toLowerCase().includes(searchText));

    if (selectedType !== "all") filtered = filtered.filter(t => t.type === selectedType);
    if (dateFrom) filtered = filtered.filter(t => t.date >= dateFrom);
    if (dateTo) filtered = filtered.filter(t => t.date <= dateTo);

    filtered = sortTxnData(filtered, sortValue);
    txnCurrentPage = 1;
    renderTxnPage(filtered);
}

function sortTxnData(data, sortValue) {
    const sorted = [...data];
    switch (sortValue) {
        case "date_desc": sorted.sort((a, b) => b.date.localeCompare(a.date)); break;
        case "date_asc": sorted.sort((a, b) => a.date.localeCompare(b.date)); break;
        case "amount_desc": sorted.sort((a, b) => (b.amount || 0) - (a.amount || 0)); break;
        case "amount_asc": sorted.sort((a, b) => (a.amount || 0) - (b.amount || 0)); break;
    }
    return sorted;
}

let txnCurrentPage = 1;
const TXN_PAGE_SIZE = 15;
let currentFilteredTxns = [];

function renderTxnPage(filteredData) {
    currentFilteredTxns = filteredData;
    const start = (txnCurrentPage - 1) * TXN_PAGE_SIZE;
    renderTransactions(filteredData.slice(start, start + TXN_PAGE_SIZE), document.getElementById("transactionsBody"));
    renderTxnPagination(filteredData.length);
}

function renderTxnPagination(totalItems) {
    const container = document.getElementById("txnPagination");
    if (!container) return;
    const totalPages = Math.max(1, Math.ceil(totalItems / TXN_PAGE_SIZE));
    container.innerHTML = `
        <button class="page-btn" onclick="goToTxnPage(${txnCurrentPage - 1})" ${txnCurrentPage === 1 ? "disabled" : ""}>← Prev</button>
        <span class="page-indicator">Page ${txnCurrentPage} of ${totalPages}</span>
        <button class="page-btn" onclick="goToTxnPage(${txnCurrentPage + 1})" ${txnCurrentPage === totalPages ? "disabled" : ""}>Next →</button>
    `;
}

function goToTxnPage(page) {
    txnCurrentPage = page;
    renderTxnPage(currentFilteredTxns);
}

function renderTransactions(data, tableBody) {
    tableBody.innerHTML = "";

    if (data.length === 0) {
        tableBody.innerHTML = `<tr><td colspan="7" style="text-align:center;">No transactions found.</td></tr>`;
        return;
    }

    data.forEach(t => {
        const row = document.createElement("tr");
        row.innerHTML = `
            <td>${txnTypeBadge(t.type)}</td>
            <td><strong>${escapeHTML(t.medicine_name)}</strong></td>
            <td>${escapeHTML(t.batch_number || "—")}</td>
            <td>${t.quantity}</td>
            <td>${t.amount !== null ? "₹" + t.amount.toFixed(2) : "—"}</td>
            <td>${t.reason ? escapeHTML(t.reason) : "—"}</td>
            <td>${formatDate(t.date)}</td>
        `;
        tableBody.appendChild(row);
    });
}

function txnTypeBadge(type) {
    const map = {
        "Sale": "good-status",
        "Customer Return": "low-status",
        "Supplier Return": "expiry-status"
    };
    const cls = map[type] || "good-status";
    return `<span class="status ${cls}">${escapeHTML(type)}</span>`;
}

// ======================================================
// EXPIRING STOCK PAGE (expiring-stock.html)
// ======================================================

let allExpiringStock = [];
let expCurrentPage = 1;
const EXP_PAGE_SIZE = 10;
let currentFilteredExpiring = [];

async function loadExpiringPage() {
    const tableBody = document.getElementById("expiringTableBody");
    if (!tableBody) return;

    try {
        const response = await fetch(`${API_BASE}/stock/current`);
        if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}`);
        const fullData = await response.json();

        allExpiringStock = fullData.filter(item =>
            item.status === "Expiring Soon" || item.status === "Expired"
        );

        updateExpiringStats(allExpiringStock);
        expCurrentPage = 1;
        renderExpiringPage(allExpiringStock);

    } catch (error) {
        console.error("Error loading expiring stock:", error);
        tableBody.innerHTML = `<tr><td colspan="8" style="text-align:center;">Unable to load expiring stock.</td></tr>`;
    }

    ["expSearchInput", "expStatusFilter", "expSortSelect"].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.addEventListener(el.tagName === "INPUT" ? "input" : "change", applyExpiringFilters);
    });
}

function updateExpiringStats(data) {
    const expiringSoon = data.filter(item => item.status === "Expiring Soon");
    const expired = data.filter(item => item.status === "Expired");
    const unitsAtRisk = data.reduce((sum, item) => sum + item.stock, 0);

    setText("expiringSoonStat", expiringSoon.length);
    setText("expiredStat", expired.length);
    setText("unitsAtRiskStat", unitsAtRisk.toLocaleString());
}

function applyExpiringFilters() {
    const searchText = document.getElementById("expSearchInput").value.trim().toLowerCase();
    const statusFilter = document.getElementById("expStatusFilter").value;
    const sortValue = document.getElementById("expSortSelect").value;

    let filtered = allExpiringStock.filter(item =>
        item.name.toLowerCase().includes(searchText) ||
        item.category.toLowerCase().includes(searchText) ||
        item.batch_number.toLowerCase().includes(searchText)
    );

    if (statusFilter !== "all") {
        filtered = filtered.filter(item => item.status === statusFilter);
    }

    filtered = sortStockData(filtered, sortValue); // reuses the sort helper from stock.html's logic
    expCurrentPage = 1;
    renderExpiringPage(filtered);
}

function renderExpiringPage(filteredData) {
    currentFilteredExpiring = filteredData;
    const start = (expCurrentPage - 1) * EXP_PAGE_SIZE;
    renderStockTable(filteredData.slice(start, start + EXP_PAGE_SIZE), document.getElementById("expiringTableBody"));
    renderExpiringPagination(filteredData.length);
}

function renderExpiringPagination(totalItems) {
    const container = document.getElementById("expiringPagination");
    if (!container) return;
    const totalPages = Math.max(1, Math.ceil(totalItems / EXP_PAGE_SIZE));
    container.innerHTML = `
        <button class="page-btn" onclick="goToExpiringPage(${expCurrentPage - 1})" ${expCurrentPage === 1 ? "disabled" : ""}>← Prev</button>
        <span class="page-indicator">Page ${expCurrentPage} of ${totalPages}</span>
        <button class="page-btn" onclick="goToExpiringPage(${expCurrentPage + 1})" ${expCurrentPage === totalPages ? "disabled" : ""}>Next →</button>
    `;
}

function goToExpiringPage(page) {
    expCurrentPage = page;
    renderExpiringPage(currentFilteredExpiring);
}

console.log("app.js loaded — connected to FastAPI backend");

// ======================================================
// SETTINGS PAGE
// ======================================================

function loadSettingsPage() {
    const savedSettings = JSON.parse(localStorage.getItem("medistock-settings") || "{}");
    const settings = {
        compactMode: false,
        lowStockAlerts: true,
        expiryAlerts: true,
        weeklySummary: false,
        ...savedSettings
    };

    Object.entries(settings).forEach(([id, value]) => {
        const input = document.getElementById(id);
        if (input) input.checked = value;
    });
    document.body.classList.toggle("compact-mode", settings.compactMode);
    updateThemeOptions();

    document.querySelectorAll(".toggle-input").forEach(input => {
        input.addEventListener("change", () => {
            settings[input.id] = input.checked;
            localStorage.setItem("medistock-settings", JSON.stringify(settings));
            document.body.classList.toggle("compact-mode", settings.compactMode);
        });
    });

    document.querySelectorAll("[data-theme-choice]").forEach(button => {
        button.addEventListener("click", () => {
            const theme = button.dataset.themeChoice;
            document.documentElement.classList.toggle("dark-mode", theme === "dark");
            localStorage.setItem("medistock-theme", theme);
            updateThemeOptions();
        });
    });

    const faqSearch = document.getElementById("faqSearch");
    if (faqSearch) faqSearch.addEventListener("input", filterFaqs);

    const copySupport = document.getElementById("copySupport");
    if (copySupport) copySupport.addEventListener("click", async () => {
        const status = document.getElementById("copyStatus");
        try {
            await navigator.clipboard.writeText("support@medistock.app");
            status.textContent = "Copied support@medistock.app";
        } catch (error) {
            status.textContent = "Email: support@medistock.app";
        }
    });

    const resetButton = document.getElementById("resetSettings");
    if (resetButton) resetButton.addEventListener("click", () => {
        localStorage.removeItem("medistock-settings");
        localStorage.removeItem("medistock-theme");
        window.location.reload();
    });
}

function updateThemeOptions() {
    const theme = localStorage.getItem("medistock-theme") || "light";
    document.querySelectorAll("[data-theme-choice]").forEach(button => {
        button.classList.toggle("selected", button.dataset.themeChoice === theme);
    });
}

function filterFaqs(event) {
    const query = event.target.value.trim().toLowerCase();
    let visibleCount = 0;
    document.querySelectorAll("#faqList details").forEach(item => {
        const matches = item.textContent.toLowerCase().includes(query);
        item.hidden = !matches;
        if (matches) visibleCount++;
    });
    document.getElementById("faqEmpty").hidden = visibleCount > 0;
}

// ======================================================
// NOTIFICATIONS
// ======================================================

function initNotifications() {
    const notificationButton = document.querySelector(".notification");
    if (!notificationButton) return;

    notificationButton.type = "button";
    notificationButton.setAttribute("aria-expanded", "false");
    notificationButton.setAttribute("aria-label", "Open notifications");
    notificationButton.addEventListener("click", toggleNotifications);

    document.addEventListener("click", event => {
        const center = document.querySelector(".notification-center");
        if (center && !center.contains(event.target) && !notificationButton.contains(event.target)) closeNotifications();
    });
    document.addEventListener("keydown", event => {
        if (event.key === "Escape") closeNotifications();
    });

    loadNotifications();
}

async function loadNotifications() {
    const button = document.querySelector(".notification");
    if (!button) return;

    let notifications = [
        { id: "welcome", title: "Welcome to Medistock", text: "Your inventory workspace is ready.", icon: "✦", tone: "good" }
    ];

    try {
        const response = await fetch(`${API_BASE}/stock/current`);
        if (response.ok) {
            const stock = await response.json();
            const lowStock = stock.filter(item => item.status === "Low Stock" || item.status === "Out of Stock");
            const expiring = stock.filter(item => item.status === "Expiring Soon" || item.status === "Expired");

            notifications = [];
            if (lowStock.length) {
                notifications.push({
                    id: "low-stock",
                    title: `${lowStock.length} stock alert${lowStock.length === 1 ? "" : "s"}`,
                    text: `${lowStock[0].name}${lowStock.length > 1 ? " and more need attention." : " needs replenishing."}`,
                    icon: "!",
                    tone: "warning"
                });
            }
            if (expiring.length) {
                notifications.push({
                    id: "expiry",
                    title: `${expiring.length} expiry alert${expiring.length === 1 ? "" : "s"}`,
                    text: `${expiring[0].name}${expiring.length > 1 ? " and more need review." : " needs an expiry review."}`,
                    icon: "⌛",
                    tone: "danger"
                });
            }
            if (!notifications.length) {
                notifications.push({ id: "all-clear", title: "All clear", text: "No urgent inventory alerts right now.", icon: "✓", tone: "good" });
            }
        }
    } catch (error) {
        console.error("Notification loading error:", error);
    }

    renderNotificationCenter(notifications);
}

function renderNotificationCenter(notifications) {
    const button = document.querySelector(".notification");
    if (!button) return;
    button.parentElement.querySelector(".notification-center")?.remove();
    const unreadIds = JSON.parse(localStorage.getItem("medistock-read-notifications") || "[]");
    const unreadCount = notifications.filter(item => !unreadIds.includes(item.id)).length;
    const center = document.createElement("div");
    center.className = "notification-center";
    center.innerHTML = `
        <div class="notification-header">
            <div><strong>Notifications</strong><span>${unreadCount ? `${unreadCount} unread` : "You're all caught up"}</span></div>
            <button type="button" class="notification-clear">Mark all read</button>
        </div>
        <div class="notification-list">
            ${notifications.map(item => `
                <button type="button" class="notification-item ${unreadIds.includes(item.id) ? "read" : ""}" data-notification-id="${item.id}">
                    <span class="notification-item-icon ${item.tone}">${item.icon}</span>
                    <span><strong>${escapeHTML(item.title)}</strong><small>${escapeHTML(item.text)}</small></span>
                    ${unreadIds.includes(item.id) ? "" : "<i></i>"}
                </button>
            `).join("")}
        </div>
    `;
    button.parentElement.classList.add("notification-wrap");
    button.parentElement.appendChild(center);
    button.querySelector(".notification-dot")?.classList.toggle("hidden", unreadCount === 0);

    center.querySelectorAll(".notification-item").forEach(item => {
        item.addEventListener("click", () => markNotificationRead(item.dataset.notificationId));
    });
    center.querySelector(".notification-clear").addEventListener("click", markAllNotificationsRead);
}

function toggleNotifications() {
    const center = document.querySelector(".notification-center");
    if (!center) return;
    const isOpen = center.classList.toggle("open");
    document.querySelector(".notification")?.setAttribute("aria-expanded", String(isOpen));
}

function closeNotifications() {
    const center = document.querySelector(".notification-center");
    if (center) center.classList.remove("open");
    document.querySelector(".notification")?.setAttribute("aria-expanded", "false");
}

function markNotificationRead(id) {
    const readIds = JSON.parse(localStorage.getItem("medistock-read-notifications") || "[]");
    if (!readIds.includes(id)) readIds.push(id);
    localStorage.setItem("medistock-read-notifications", JSON.stringify(readIds));
    closeNotifications();
    loadNotifications();
}

function markAllNotificationsRead() {
    document.querySelectorAll(".notification-item").forEach(item => item.classList.add("read"));
    localStorage.setItem("medistock-read-notifications", JSON.stringify(
        [...document.querySelectorAll(".notification-item")].map(item => item.dataset.notificationId)
    ));
    loadNotifications();
}

// ======================================================
// MEDICINE MANAGEMENT PAGE
// ======================================================

let allMedicines = [];
let medicineCurrentPage = 1;
const MEDICINE_PAGE_SIZE = 10;
let currentFilteredMedicines = [];

async function loadMedicinePage() {
    try {
        const response = await fetch(`${API_BASE}/medicines`, { credentials: "include" });
        if (!response.ok) throw new Error(`HTTP error! Status: ${response.status}`);
        allMedicines = await response.json();
        updateMedicineStats();
        populateMedicineFilters();
        renderMedicineList();
        initMedicineControls();
    } catch (error) {
        console.error("Error loading medicines:", error);
        const list = document.getElementById("medicineList");
        if (list) list.innerHTML = `<p class="medicine-empty">Unable to load medicines. Please try again.</p>`;
    }
}

function updateMedicineStats() {
    const batchCount = allMedicines.reduce((sum, medicine) => sum + medicine.batch_count, 0);
    const unitCount = allMedicines.reduce((sum, medicine) => sum + medicine.total_stock, 0);
    const reviewCount = allMedicines.filter(medicine =>
        medicine.total_stock < medicine.reorder_level || medicine.batches.some(batch => batchStatus(batch) !== "Healthy")
    ).length;
    setText("medicineCount", allMedicines.length);
    setText("batchCount", batchCount);
    setText("medicineUnits", unitCount.toLocaleString());
    setText("medicineReviewCount", reviewCount);
}

function populateMedicineFilters() {
    const categorySelect = document.getElementById("medicineCategory");
    if (!categorySelect) return;
    categorySelect.innerHTML = `<option value="all">All categories</option>`;
    [...new Set(allMedicines.map(medicine => medicine.category))].sort().forEach(category => {
        categorySelect.innerHTML += `<option value="${escapeHTML(category)}">${escapeHTML(category)}</option>`;
    });
}

function initMedicineControls() {
    if (document.body.dataset.medicineControlsReady) return;
    document.body.dataset.medicineControlsReady = "true";
    ["medicineSearch", "medicineCategory", "medicineType", "medicineStatus", "medicineSort"].forEach(id => {
        const resetAndRender = () => {
            medicineCurrentPage = 1;
            renderMedicineList();
        };
        document.getElementById(id)?.addEventListener("input", resetAndRender);
        document.getElementById(id)?.addEventListener("change", resetAndRender);
    });
    document.getElementById("addBatchButton")?.addEventListener("click", openBatchModal);
    document.getElementById("closeBatchModal")?.addEventListener("click", closeBatchModal);
    document.getElementById("batchModalOverlay")?.addEventListener("click", event => {
        if (event.target.id === "batchModalOverlay") closeBatchModal();
    });
    document.getElementById("batchForm")?.addEventListener("submit", submitBatch);
    document.getElementById("closeEditMedicineModal")?.addEventListener("click", closeEditMedicineModal);
    document.getElementById("editMedicineModalOverlay")?.addEventListener("click", event => {
        if (event.target.id === "editMedicineModalOverlay") closeEditMedicineModal();
    });
    document.getElementById("editMedicineForm")?.addEventListener("submit", submitEditMedicineDetails);
}

function renderMedicineList() {
    const list = document.getElementById("medicineList");
    if (!list) return;
    const query = document.getElementById("medicineSearch").value.trim().toLowerCase();
    const category = document.getElementById("medicineCategory").value;
    const type = document.getElementById("medicineType").value;
    const status = document.getElementById("medicineStatus").value;
    const sort = document.getElementById("medicineSort").value;
    let filtered = allMedicines.filter(medicine =>
        (medicine.name.toLowerCase().includes(query) || medicine.category.toLowerCase().includes(query) || medicine.manufacturer.toLowerCase().includes(query)) &&
        (category === "all" || medicine.category === category) &&
        (type === "all" || getMedicineType(medicine) === type) &&
        (status === "all" || (status === "active" ? medicine.is_active : !medicine.is_active))
    );
    filtered.sort((a, b) => {
        if (sort === "stock_desc") return b.total_stock - a.total_stock;
        if (sort === "stock_asc") return a.total_stock - b.total_stock;
        if (sort === "batches_desc") return b.batch_count - a.batch_count;
        return a.name.localeCompare(b.name);
    });
    currentFilteredMedicines = filtered;
    const totalPages = Math.max(1, Math.ceil(filtered.length / MEDICINE_PAGE_SIZE));
    if (medicineCurrentPage > totalPages) medicineCurrentPage = totalPages;
    const start = (medicineCurrentPage - 1) * MEDICINE_PAGE_SIZE;
    const visibleMedicines = filtered.slice(start, start + MEDICINE_PAGE_SIZE);
    setText("medicineResultCount", `${filtered.length} profile${filtered.length === 1 ? "" : "s"}`);
    document.getElementById("medicineEmpty").hidden = filtered.length > 0;
    list.innerHTML = visibleMedicines.map(renderMedicineRecord).join("");
    renderMedicinePagination(filtered.length);
    list.querySelectorAll(".batch-add-link").forEach(button => button.addEventListener("click", () => openBatchModal(Number(button.dataset.medicineId))));
    list.querySelectorAll(".edit-details-link").forEach(button => button.addEventListener("click", () => openEditMedicineModal(button.dataset)));
    list.querySelectorAll(".delete-link").forEach(button => button.addEventListener("click", () => deleteMedicine(Number(button.dataset.medicineId), button.dataset.medicineName)));
    list.querySelectorAll(".archive-link").forEach(button => button.addEventListener("click", () => archiveMedicine(Number(button.dataset.medicineId), button.dataset.medicineName, button.dataset.action)));
    list.querySelectorAll(".batch-delete").forEach(button => button.addEventListener("click", () => deleteBatch(Number(button.dataset.batchId))));
}

function renderMedicineRecord(medicine) {
    return `<details class="medicine-record">
        <summary><span class="medicine-summary-name"><span class="medicine-icon">${escapeHTML(medicine.name.charAt(0))}</span><span><strong>${escapeHTML(medicine.name)}</strong><span>${escapeHTML(medicine.category)} · ${escapeHTML(medicine.manufacturer)}</span></span></span>
            <span class="medicine-summary-value"><strong>${escapeHTML(formatInventoryQuantity(medicine.total_stock, medicine))}</strong><span>Available stock</span></span>
            <span class="medicine-summary-value"><strong>${medicine.batch_count}</strong><span>Batches</span></span>
            <span class="medicine-summary-value"><strong>₹${medicine.unit_price.toFixed(2)}</strong><span>${medicine.price_basis === "strip" ? "Strip price" : "Unit price"}</span></span>
            <span class="medicine-actions"><button type="button" class="edit-details-link" data-medicine-id="${medicine.medicine_id}" data-medicine-name="${escapeHTML(medicine.name)}" data-unit="${escapeHTML(medicine.unit)}" data-units-per-strip="${medicine.units_per_strip || 1}" data-price-basis="${medicine.price_basis || "unit"}">Edit details</button>${medicine.is_active ? `<button type="button" class="batch-add-link" data-medicine-id="${medicine.medicine_id}">+ Batch</button><button type="button" class="archive-link" data-action="archive" data-medicine-id="${medicine.medicine_id}" data-medicine-name="${escapeHTML(medicine.name)}">Archive</button>` : `<button type="button" class="archive-link" data-action="restore" data-medicine-id="${medicine.medicine_id}" data-medicine-name="${escapeHTML(medicine.name)}">Restore</button>`}<button type="button" class="delete-link" data-medicine-id="${medicine.medicine_id}" data-medicine-name="${escapeHTML(medicine.name)}">Delete</button></span>
        </summary>
        <div class="batch-details"><div class="batch-details-header"><span>Batch</span><span>Quantity</span><span>Manufactured</span><span>Expiry</span><span>Action</span></div>
            ${medicine.batches.map(batch => `<div class="batch-line"><strong>${escapeHTML(batch.batch_number)}</strong><span>${batch.quantity}</span><span>${formatDate(batch.manufacture_date)}</span><span>${formatDate(batch.expiry_date)}</span><button type="button" class="batch-delete" data-batch-id="${batch.batch_id}">Delete</button></div>`).join("")}
        </div>
    </details>`;
}

let editingMedicineId = null;

function openEditMedicineModal(details) {
    editingMedicineId = Number(details.medicineId);
    document.getElementById("editMedicineModalTitle").textContent = `Edit ${details.medicineName}`;
    document.getElementById("editMedicineUnit").value = details.unit;
    document.getElementById("editUnitsPerStrip").value = details.unitsPerStrip || 1;
    document.getElementById("editPriceBasis").value = details.priceBasis || "unit";
    document.getElementById("editMedicineMessage").textContent = "";
    document.getElementById("editMedicineModalOverlay").hidden = false;
}

function closeEditMedicineModal() {
    document.getElementById("editMedicineModalOverlay").hidden = true;
    editingMedicineId = null;
}

async function submitEditMedicineDetails(event) {
    event.preventDefault();
    const message = document.getElementById("editMedicineMessage");
    message.textContent = "";
    try {
        const response = await fetch(`${API_BASE}/medicines/${editingMedicineId}`, {
            method: "PATCH",
            credentials: "include",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                unit: document.getElementById("editMedicineUnit").value,
                units_per_strip: Number(document.getElementById("editUnitsPerStrip").value),
                price_basis: document.getElementById("editPriceBasis").value
            })
        });
        const data = await response.json();
        if (!response.ok) {
            message.textContent = data.detail || "Unable to update medicine details.";
            return;
        }
        closeEditMedicineModal();
        await loadMedicinePage();
    } catch (error) {
        message.textContent = "Unable to reach the server.";
    }
}

function batchStatus(batch) {
    if (batch.quantity === 0) return "Out of Stock";
    const days = Math.ceil((new Date(`${batch.expiry_date}T00:00:00`) - new Date()) / 86400000);
    if (days < 0) return "Expired";
    if (days <= 60) return "Expiring Soon";
    return "Healthy";
}

function openBatchModal(medicineId = null) {
    const select = document.getElementById("batchMedicine");
    select.innerHTML = allMedicines.map(medicine => `<option value="${medicine.medicine_id}" ${medicine.medicine_id === medicineId ? "selected" : ""}>${escapeHTML(medicine.name)} · ${escapeHTML(medicine.category)}</option>`).join("");
    document.getElementById("batchMessage").textContent = "";
    document.getElementById("batchForm").reset();
    if (medicineId) select.value = medicineId;
    document.getElementById("batchModalOverlay").hidden = false;
}

function closeBatchModal() {
    document.getElementById("batchModalOverlay").hidden = true;
}

async function submitBatch(event) {
    event.preventDefault();
    const message = document.getElementById("batchMessage");
    message.textContent = "";
    const medicineId = document.getElementById("batchMedicine").value;
    const payload = {
        batch_number: document.getElementById("batchNumber").value.trim(),
        quantity: parseInt(document.getElementById("batchQuantity").value, 10),
        manufacture_date: document.getElementById("batchManufactureDate").value,
        expiry_date: document.getElementById("batchExpiryDate").value
    };
    try {
        const response = await fetch(`${API_BASE}/medicines/${medicineId}/batches`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
        const data = await response.json();
        if (!response.ok) { message.textContent = data.detail || "Unable to add batch."; return; }
        closeBatchModal();
        await loadMedicinePage();
    } catch (error) { message.textContent = "Unable to reach the server."; }
}

async function deleteMedicine(medicineId, medicineName) {
    if (!window.confirm(`Delete ${medicineName}? This is only possible when it has no stock or analytics history.`)) return;
    await sendMedicineDelete(`${API_BASE}/medicines/${medicineId}`);
}

async function archiveMedicine(medicineId, medicineName, action) {
    const isRestore = action === "restore";
    const prompt = isRestore
        ? `Restore ${medicineName} to active inventory?`
        : `Archive ${medicineName}? It will be removed from active inventory and cannot be sold. Any remaining stock will stay preserved in the archived record.`;
    if (!window.confirm(prompt)) return;
    await sendMedicineDelete(`${API_BASE}/medicines/${medicineId}/${isRestore ? "restore" : "archive"}`, "POST");
}

async function deleteBatch(batchId) {
    if (!window.confirm("Delete this empty batch? Existing return history will be protected.")) return;
    await sendMedicineDelete(`${API_BASE}/batches/${batchId}`);
}

async function sendMedicineDelete(url, method = "DELETE") {
    try {
        const response = await fetch(url, { method, credentials: "include" });
        const data = await response.json();
        if (!response.ok) { window.alert(data.detail || "Unable to delete this record."); return; }
        await loadMedicinePage();
    } catch (error) { window.alert("Unable to reach the server."); }
}

function renderMedicinePagination(totalItems) {
    const container = document.getElementById("medicinePagination");
    if (!container) return;
    const totalPages = Math.max(1, Math.ceil(totalItems / MEDICINE_PAGE_SIZE));
    container.innerHTML = `
        <button class="page-btn" onclick="goToMedicinePage(${medicineCurrentPage - 1})" ${medicineCurrentPage === 1 ? "disabled" : ""}>← Prev</button>
        <span class="page-indicator">Page ${medicineCurrentPage} of ${totalPages}</span>
        <button class="page-btn" onclick="goToMedicinePage(${medicineCurrentPage + 1})" ${medicineCurrentPage === totalPages ? "disabled" : ""}>Next →</button>
    `;
}

function goToMedicinePage(page) {
    const totalPages = Math.max(1, Math.ceil(currentFilteredMedicines.length / MEDICINE_PAGE_SIZE));
    medicineCurrentPage = Math.min(Math.max(page, 1), totalPages);
    renderMedicineList();
}

// ======================================================
// SIDEBAR NAVIGATION
// ======================================================

function initSidebarToggle() {
    const sidebar = document.querySelector(".sidebar");
    if (!sidebar || document.querySelector(".sidebar-toggle")) return;

    const toggle = document.createElement("button");
    toggle.className = "sidebar-toggle";
    toggle.type = "button";
    toggle.setAttribute("aria-label", "Collapse navigation");
    toggle.setAttribute("aria-expanded", "true");
    toggle.innerHTML = "<span></span><span></span><span></span>";
    document.body.appendChild(toggle);

    const savedState = localStorage.getItem("medistock-sidebar-collapsed");
    const shouldCollapse = savedState === "true" || (savedState === null && window.innerWidth <= 700);
    setSidebarCollapsed(shouldCollapse, toggle);

    toggle.addEventListener("click", () => {
        setSidebarCollapsed(!document.body.classList.contains("sidebar-collapsed"), toggle);
    });
}

function setSidebarCollapsed(collapsed, toggle) {
    document.body.classList.toggle("sidebar-collapsed", collapsed);
    localStorage.setItem("medistock-sidebar-collapsed", String(collapsed));
    toggle.setAttribute("aria-expanded", String(!collapsed));
    toggle.setAttribute("aria-label", collapsed ? "Open navigation" : "Collapse navigation");
    toggle.classList.toggle("is-collapsed", collapsed);
}

function getMedicineType(medicine) {
    const unit = (medicine.unit || "").toLowerCase();
    const name = (medicine.name || "").toLowerCase();
    if (["injection", "vial", "ampoule"].some(value => unit.includes(value))) return "injection";
    if (unit.includes("drop") || name.includes("drop")) return "drops";
    if (unit === "bottle" || name.includes("syrup")) return "syrup";
    if (["tablet", "capsule"].some(value => unit.includes(value)) || name.includes("tablet") || name.includes("capsule")) return "tablet";
    return "other";
}
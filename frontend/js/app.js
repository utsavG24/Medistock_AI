// ======================================================
// MEDISTOCK - FRONTEND JAVASCRIPT
// ======================================================

const API_BASE = "http://127.0.0.1:8000";

document.addEventListener("DOMContentLoaded", async function () {
    const admin = await requireLogin();
    if (!admin) return;

    console.log("Medistock frontend loaded");

    const currentPage = window.location.pathname;

    if (currentPage.includes("stock.html")) {
        await loadStockPage();
    } else if (currentPage.includes("analytics.html")) {
        await loadAnalyticsPage();
    } else {
        await loadDashboard();
    }
});

// ======================================================
// DASHBOARD (index.html)
// ======================================================

async function loadDashboard() {
    await updateDashboardStats();
    await loadCurrentStockTable();
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

        // Only show the first 10 rows on the dashboard preview
        renderStockRows(data.slice(0, 10), tableBody);

    } catch (error) {
        console.error("Error loading current stock:", error);
        tableBody.innerHTML = `<tr><td colspan="6" style="text-align:center;">Unable to load stock data.</td></tr>`;
    }
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
            <td><strong>${item.stock}</strong></td>
            <td>${item.reorder_level}</td>
            <td>${formatDate(item.expiry_date)}</td>
            <td>${statusBadge(item.status)}</td>
            <td>
                <button class="row-action-btn sell" onclick="openActionModal(${item.batch_id}, 'sell', '${escapeHTML(item.name)}', ${item.stock})">Sell</button>
                <button class="row-action-btn return" onclick="openActionModal(${item.batch_id}, 'customer_return', '${escapeHTML(item.name)}', ${item.stock})">Return</button>
                <button class="row-action-btn exchange" onclick="openActionModal(${item.batch_id}, 'supplier_return', '${escapeHTML(item.name)}', ${item.stock})">Exchange</button>
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

function openActionModal(batchId, action, medicineName, currentStock) {
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
    document.getElementById("actionModalStock").textContent = `Current stock: ${currentStock}`;
    document.getElementById("actionQuantity").value = "";
    document.getElementById("actionReason").value = "";
    document.getElementById("actionReceived").value = "";

    document.getElementById("actionReasonField").style.display = action === "sell" ? "none" : "block";
    document.getElementById("actionReceivedField").style.display = action === "supplier_return" ? "block" : "none";

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
    const messageEl = document.getElementById("actionMessage");
    messageEl.textContent = "";
    messageEl.style.color = "#dc2626";

    if (!quantity || quantity <= 0) {
        messageEl.textContent = "Enter a quantity greater than 0.";
        return;
    }
    if (currentAction === "sell" && quantity > currentMaxStock) {
        messageEl.textContent = `Only ${currentMaxStock} units available.`;
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

// ======================================================
// SHARED: render a list of stock rows into a table body
// ======================================================

function renderStockRows(data, tableBody) {
    tableBody.innerHTML = "";

    if (data.length === 0) {
        tableBody.innerHTML = `<tr><td colspan="6" style="text-align:center;">No medicines found.</td></tr>`;
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
                        <span>${escapeHTML(item.category)}</span>
                    </div>
                </div>
            </td>
            <td>${escapeHTML(item.category)}</td>
            <td>${escapeHTML(item.batch_number)}</td>
            <td><strong>${item.stock}</strong></td>
            <td>${formatDate(item.expiry_date)}</td>
            <td>${statusBadge(item.status)}</td>
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
        "addUnitPrice", "addReorderLevel", "addBatchNumber",
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
    if (isNaN(payload.unit_price) || isNaN(payload.reorder_level) || isNaN(payload.quantity)) {
        messageEl.textContent = "Price, reorder level, and quantity must be valid numbers.";
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
// UTILITIES
// ======================================================

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
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

        updateAnalyticsStats(allTransactions);
        txnCurrentPage = 1;
        renderTxnPage(allTransactions);

    } catch (error) {
        console.error("Error loading transactions:", error);
        tableBody.innerHTML = `<tr><td colspan="6" style="text-align:center;">Unable to load transactions.</td></tr>`;
    }

    ["txnSearchInput", "txnTypeFilter", "txnSortSelect", "txnDateFrom", "txnDateTo"].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.addEventListener(el.tagName === "INPUT" ? "input" : "change", applyTxnFilters);
    });
}

function updateAnalyticsStats(data) {
    const sales = data.filter(t => t.type === "Sale");
    const customerReturns = data.filter(t => t.type === "Customer Return");
    const supplierReturns = data.filter(t => t.type === "Supplier Return");

    const totalRevenue = sales.reduce((sum, t) => sum + (t.amount || 0), 0);

    setText("totalRevenue", `₹${totalRevenue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`);
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

    let filtered = allTransactions.filter(t => t.medicine_name.toLowerCase().includes(searchText));

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
        tableBody.innerHTML = `<tr><td colspan="6" style="text-align:center;">No transactions found.</td></tr>`;
        return;
    }

    data.forEach(t => {
        const row = document.createElement("tr");
        row.innerHTML = `
            <td>${txnTypeBadge(t.type)}</td>
            <td><strong>${escapeHTML(t.medicine_name)}</strong></td>
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

console.log("app.js loaded — connected to FastAPI backend");
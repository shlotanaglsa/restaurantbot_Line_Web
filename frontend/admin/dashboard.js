const connectionForm = document.querySelector("#connection-form");
const notice = document.querySelector("#notice");
const orderList = document.querySelector("#order-list");
const comparisonSummary = document.querySelector("#comparison-summary");
const comparisonChart = document.querySelector("#comparison-chart");
const statusFilter = document.querySelector("#status-filter");
const salesPeriod = document.querySelector("#sales-period");
const firstPeriodDate = document.querySelector("#first-period-date");
const secondPeriodDate = document.querySelector("#second-period-date");
let menuItemNames = new Map();
const statusLabels = {
  pending: "รอทำ",
  cooking: "กำลังทำ",
  completed: "เสร็จแล้ว",
  cancelled: "ยกเลิก",
};

document.querySelector("#api-url").value =
  localStorage.getItem("restaurant-api-url") || "http://127.0.0.1:8000";
document.querySelector("#admin-key").value =
  sessionStorage.getItem("restaurant-admin-key") || "";

function localDateString(date = new Date()) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function shiftDate(value, period, amount = -1) {
  const date = new Date(`${value}T12:00:00`);
  if (period === "daily") {
    date.setDate(date.getDate() + amount);
  } else if (period === "monthly") {
    date.setDate(1);
    date.setMonth(date.getMonth() + amount);
  } else {
    date.setFullYear(date.getFullYear() + amount, 0, 1);
  }
  return localDateString(date);
}

firstPeriodDate.value = localDateString();
secondPeriodDate.value = shiftDate(firstPeriodDate.value, salesPeriod.value);

function apiUrl(path) {
  return `${localStorage.getItem("restaurant-api-url") || "http://127.0.0.1:8000"}${path}`;
}

async function request(path, options = {}) {
  const response = await fetch(apiUrl(path), {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-Admin-Api-Key": sessionStorage.getItem("restaurant-admin-key") || "",
      ...options.headers,
    },
  });
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch {
      // Keep the HTTP status message if the response is not JSON.
    }
    throw new Error(detail);
  }
  return response.status === 204 ? null : response.json();
}

function showNotice(message, isError = false) {
  notice.textContent = message;
  notice.classList.toggle("error", isError);
  notice.hidden = false;
}

function formatBaht(value) {
  return `${Number(value).toLocaleString("th-TH", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })} บาท`;
}

function renderOrders(orders) {
  orderList.replaceChildren();
  if (orders.length === 0) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "ไม่พบออเดอร์";
    orderList.append(empty);
    return;
  }

  const filter = statusFilter.value;
  const queuePositions = new Map();
  orders
    .filter((order) => ["pending", "cooking"].includes(order.status))
    .sort((first, second) =>
      new Date(first.created_at) - new Date(second.created_at) || first.id - second.id)
    .forEach((order, index) => queuePositions.set(order.id, index + 1));

  for (const status of ["pending", "cooking", "completed", "cancelled"]) {
    if (filter && filter !== status) continue;
    const statusOrders = orders
      .filter((order) => order.status === status)
      .sort((first, second) =>
        new Date(first.created_at) - new Date(second.created_at) || first.id - second.id);
    if (statusOrders.length === 0 && filter) continue;

    const group = document.createElement("section");
    group.className = `queue-column queue-${status}`;
    const heading = document.createElement("header");
    heading.className = "queue-heading";
    const title = document.createElement("h3");
    title.textContent = statusLabels[status];
    const count = document.createElement("span");
    count.textContent = `${statusOrders.length.toLocaleString("th-TH")} ออเดอร์`;
    heading.append(title, count);
    group.append(heading);
    if (statusOrders.length === 0) {
      const empty = document.createElement("p");
      empty.className = "empty-state";
      empty.textContent = "ยังไม่มีออเดอร์";
      group.append(empty);
    } else {
      statusOrders.forEach((order) =>
        group.append(createOrderCard(order, queuePositions.get(order.id))));
    }
    orderList.append(group);
  }
}

function renderStats(stats) {
  document.querySelector("#today-sales").textContent = formatBaht(stats.today_sales);
  document.querySelector("#total-sales").textContent = formatBaht(stats.total_sales);
  document.querySelector("#total-orders").textContent =
    Number(stats.total_orders).toLocaleString("th-TH");
  document.querySelector("#status-counts").textContent =
    `${stats.completed_orders} / ${stats.cooking_orders} / ${stats.pending_orders}`;
}

function periodTitle(summary) {
  const date = new Date(`${summary.start_date}T12:00:00`);
  if (summary.period === "daily") {
    return date.toLocaleDateString("th-TH", {
      day: "numeric",
      month: "long",
      year: "numeric",
    });
  }
  if (summary.period === "monthly") {
    return date.toLocaleDateString("th-TH", { month: "long", year: "numeric" });
  }
  return date.toLocaleDateString("th-TH", { year: "numeric" });
}

function createSummaryCard(title, summary) {
  const card = document.createElement("article");
  card.className = "comparison-card";
  const label = document.createElement("p");
  label.textContent = title;
  const period = document.createElement("small");
  period.textContent = periodTitle(summary);
  const total = document.createElement("strong");
  total.textContent = formatBaht(summary.total_sales);
  const orders = document.createElement("small");
  orders.textContent = `${Number(summary.order_count).toLocaleString("th-TH")} ออเดอร์ที่สำเร็จ`;
  card.append(label, total, period, orders);
  return card;
}

function renderComparison(first, second) {
  const firstTotal = Number(first.total_sales);
  const secondTotal = Number(second.total_sales);
  const difference = firstTotal - secondTotal;
  const differencePercent = secondTotal === 0
    ? (firstTotal === 0 ? "0%" : "—")
    : `${((difference / secondTotal) * 100).toLocaleString("th-TH", {
      maximumFractionDigits: 1,
    })}%`;

  comparisonSummary.replaceChildren(
    createSummaryCard("ช่วงที่ 1", first),
    createSummaryCard("ช่วงที่ 2", second),
  );
  const differenceCard = document.createElement("article");
  differenceCard.className = "comparison-card";
  const differenceLabel = document.createElement("p");
  differenceLabel.textContent = "ผลต่าง (ช่วงที่ 1 − ช่วงที่ 2)";
  const differenceValue = document.createElement("strong");
  differenceValue.textContent = `${difference >= 0 ? "+" : ""}${formatBaht(difference)}`;
  const percent = document.createElement("small");
  percent.textContent = `เปลี่ยนแปลง ${differencePercent}`;
  differenceCard.append(differenceLabel, differenceValue, percent);
  comparisonSummary.append(differenceCard);

  const maxSales = Math.max(
    ...first.buckets.map((bucket) => Number(bucket.total_sales)),
    ...second.buckets.map((bucket) => Number(bucket.total_sales)),
    0,
  );
  comparisonChart.replaceChildren();
  comparisonChart.style.setProperty("--bucket-count", String(first.buckets.length));
  first.buckets.forEach((bucket, index) => {
    const column = document.createElement("div");
    column.className = "comparison-column";
    const label = document.createElement("span");
    label.className = "comparison-label";
    label.textContent = first.period === "yearly"
      ? new Date(Number(first.start_date.slice(0, 4)), index, 1)
        .toLocaleDateString("th-TH", { month: "short" })
      : bucket.label;

    const bars = document.createElement("div");
    bars.className = "comparison-bars";
    for (const [value, className] of [
      [Number(bucket.total_sales), "first"],
      [Number(second.buckets[index]?.total_sales || 0), "second"],
    ]) {
      const bar = document.createElement("div");
      bar.className = `comparison-bar ${className}`;
      bar.style.height = maxSales > 0 ? `${(value / maxSales) * 100}%` : "0%";
      bar.title = formatBaht(value);
      bar.setAttribute(
        "aria-label",
        `${className === "first" ? "ช่วงที่ 1" : "ช่วงที่ 2"}: ${formatBaht(value)}`,
      );
      bars.append(bar);
    }
    column.append(bars, label);
    comparisonChart.append(column);
  });
}

async function loadSalesComparison() {
  const period = salesPeriod.value;
  const firstDate = firstPeriodDate.value;
  const secondDate = secondPeriodDate.value;
  if (!firstDate || !secondDate) return;
  const summaryUrl = (anchorDate) =>
    `/admin/dashboard/sales-summary?period=${encodeURIComponent(period)}&anchor_date=${encodeURIComponent(anchorDate)}`;
  try {
    const [first, second] = await Promise.all([
      request(summaryUrl(firstDate)),
      request(summaryUrl(secondDate)),
    ]);
    renderComparison(first, second);
  } catch (error) {
    showNotice(error.message, true);
  }
}

function createOrderCard(order, queuePosition) {
  const card = document.createElement("article");
  card.className = "order-card";

  const heading = document.createElement("div");
  heading.className = "order-heading";
  const identity = document.createElement("div");
  const title = document.createElement("h3");
  title.textContent = `ออเดอร์ #${order.id} · ${order.customer_name}`;
  if (queuePosition) {
    const queue = document.createElement("span");
    queue.className = "queue-number";
    queue.textContent = `คิวที่ ${queuePosition}`;
    title.append(" ", queue);
  }
  const time = document.createElement("p");
  time.className = "muted";
  time.textContent = new Date(order.created_at).toLocaleString("th-TH");
  identity.append(title, time);
  const total = document.createElement("strong");
  total.className = "order-total";
  total.textContent = formatBaht(order.total_price);
  heading.append(identity, total);

  const contact = document.createElement("p");
  contact.className = "order-meta";
  contact.textContent = `โทร ${order.phone}`;
  const address = document.createElement("p");
  address.className = "order-address";
  address.textContent = `ที่อยู่: ${order.address}`;

  const items = document.createElement("ul");
  items.className = "order-items";
  for (const item of order.items) {
    const line = document.createElement("li");
    const options = item.options.map((option) => option.option_name).join(", ");
    line.textContent =
      `${item.quantity} × ${menuItemNames.get(item.menu_item_id) || `เมนู #${item.menu_item_id}`} — ${formatBaht(item.subtotal)}` +
      (options ? ` (เพิ่ม: ${options})` : "") +
      (item.note ? ` · ${item.note}` : "");
    items.append(line);
  }

  card.append(heading, contact, address, items);
  if (order.note) {
    const note = document.createElement("p");
    note.className = "order-note";
    note.textContent = `หมายเหตุ: ${order.note}`;
    card.append(note);
  }

  const controls = document.createElement("div");
  controls.className = "order-status";
  const label = document.createElement("label");
  label.textContent = "สถานะ";
  const select = document.createElement("select");
  select.setAttribute("aria-label", `สถานะออเดอร์ ${order.id}`);
  for (const status of ["pending", "cooking", "completed", "cancelled"]) {
    const option = document.createElement("option");
    option.value = status;
    option.textContent = statusLabels[status];
    option.selected = order.status === status;
    select.append(option);
  }
  label.append(select);
  const save = document.createElement("button");
  save.className = "button-secondary";
  save.type = "button";
  save.textContent = "บันทึกสถานะ";
  save.addEventListener("click", async () => {
    save.disabled = true;
    try {
      await request(`/orders/${order.id}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status: select.value }),
      });
      showNotice(`บันทึกสถานะออเดอร์ #${order.id} แล้ว`);
      await loadDashboard();
    } catch (error) {
      showNotice(error.message, true);
    } finally {
      save.disabled = false;
    }
  });
  controls.append(label, save);
  if (order.line_linked) {
    const notify = document.createElement("button");
    notify.className = "button-secondary";
    notify.type = "button";
    notify.textContent = "ส่งสถานะทาง LINE";
    notify.addEventListener("click", async () => {
      notify.disabled = true;
      try {
        await request(`/admin/orders/${order.id}/notify`, { method: "POST" });
        showNotice(`ส่งสถานะออเดอร์ #${order.id} ทาง LINE แล้ว`);
      } catch (error) {
        showNotice(error.message, true);
      } finally {
        notify.disabled = false;
      }
    });
    controls.append(notify);
  }
  card.append(controls);
  return card;
}

async function loadOrders() {
  const orders = await request("/orders");
  renderOrders(orders);
}

async function loadDashboard() {
  try {
    const [stats, menuItems, orders] = await Promise.all([
      request("/admin/dashboard/stats?days=7"),
      request("/admin/menu"),
      request("/orders"),
    ]);
    menuItemNames = new Map(menuItems.map((item) => [item.id, item.name]));
    renderStats(stats);
    renderOrders(orders);
    await loadSalesComparison();
  } catch (error) {
    showNotice(error.message, true);
  }
}

connectionForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const apiBase = document.querySelector("#api-url").value.trim().replace(/\/+$/, "");
  const adminKey = document.querySelector("#admin-key").value;
  localStorage.setItem("restaurant-api-url", apiBase);
  sessionStorage.setItem("restaurant-admin-key", adminKey);
  showNotice("กำลังเชื่อมต่อ...");
  await loadDashboard();
});

document.querySelector("#refresh-dashboard").addEventListener("click", loadDashboard);
document.querySelector("#compare-sales").addEventListener("click", loadSalesComparison);
salesPeriod.addEventListener("change", () => {
  secondPeriodDate.value = shiftDate(firstPeriodDate.value, salesPeriod.value);
  loadSalesComparison();
});
firstPeriodDate.addEventListener("change", loadSalesComparison);
secondPeriodDate.addEventListener("change", loadSalesComparison);
statusFilter.addEventListener("change", async () => {
  try {
    await loadOrders();
  } catch (error) {
    showNotice(error.message, true);
  }
});

window.setInterval(() => {
  if (!document.hidden && sessionStorage.getItem("restaurant-admin-key")) {
    loadOrders().catch((error) => showNotice(error.message, true));
  }
}, 15000);

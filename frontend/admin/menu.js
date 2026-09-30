const connectionForm = document.querySelector("#connection-form");
const menuForm = document.querySelector("#menu-form");
const optionsList = document.querySelector("#options-list");
const menuList = document.querySelector("#menu-list");
const notice = document.querySelector("#notice");
const formHeading = document.querySelector("#form-heading");
const saveButton = document.querySelector("#save-menu");
const newItemButton = document.querySelector("#new-item");

let editingId = null;

document.querySelector("#api-url").value =
  localStorage.getItem("restaurant-api-url") || "http://127.0.0.1:8000";
document.querySelector("#admin-key").value =
  sessionStorage.getItem("restaurant-admin-key") || "";

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

function addOptionRow(option = {}) {
  const row = document.createElement("div");
  row.className = "option-row";

  const nameLabel = document.createElement("label");
  nameLabel.textContent = "ชื่อตัวเลือก";
  const nameInput = document.createElement("input");
  nameInput.className = "option-name";
  nameInput.value = option.name || "";
  nameInput.maxLength = 255;
  nameInput.required = true;
  nameLabel.append(nameInput);

  const priceLabel = document.createElement("label");
  priceLabel.textContent = "ราคาเพิ่ม";
  const priceInput = document.createElement("input");
  priceInput.className = "option-price";
  priceInput.type = "number";
  priceInput.min = "0";
  priceInput.step = "0.01";
  priceInput.value = option.price ?? "0.00";
  priceInput.required = true;
  priceLabel.append(priceInput);

  const removeButton = document.createElement("button");
  removeButton.className = "remove-option";
  removeButton.type = "button";
  removeButton.textContent = "ลบ";
  removeButton.setAttribute("aria-label", "ลบตัวเลือกนี้");
  removeButton.addEventListener("click", () => row.remove());

  row.append(nameLabel, priceLabel, removeButton);
  optionsList.append(row);
}

function resetForm() {
  editingId = null;
  menuForm.reset();
  menuForm.elements.available.checked = true;
  optionsList.replaceChildren();
  formHeading.textContent = "เพิ่มเมนู";
  saveButton.textContent = "บันทึกเมนู";
  newItemButton.hidden = true;
}

function editItem(item) {
  editingId = item.id;
  menuForm.elements.name.value = item.name;
  menuForm.elements.price.value = item.price;
  menuForm.elements.category.value = item.category;
  menuForm.elements.description.value = item.description || "";
  menuForm.elements.available.checked = item.available;
  optionsList.replaceChildren();
  item.options.forEach(addOptionRow);
  formHeading.textContent = `แก้ไขเมนู #${item.id}`;
  saveButton.textContent = "บันทึกการแก้ไข";
  newItemButton.hidden = false;
  formHeading.scrollIntoView({ behavior: "smooth", block: "center" });
}

function createMenuCard(item) {
  const card = document.createElement("article");
  card.className = "menu-card";

  const heading = document.createElement("div");
  heading.className = "menu-card-heading";
  const name = document.createElement("h3");
  name.textContent = item.name;
  const price = document.createElement("strong");
  price.textContent = `${Number(item.price).toFixed(2)} บาท`;
  heading.append(name, price);

  const meta = document.createElement("p");
  meta.className = "muted";
  meta.textContent = `${item.category} · ${item.available ? "เปิดขาย" : "ปิดขาย"}`;

  const description = document.createElement("p");
  description.textContent = item.description || "ไม่มีรายละเอียด";

  const optionSummary = document.createElement("p");
  optionSummary.className = "option-summary";
  optionSummary.textContent = item.options.length
    ? `ตัวเลือก: ${item.options.map((option) => `${option.name} (+${Number(option.price || 0).toFixed(2)})`).join(", ")}`
    : "ไม่มีตัวเลือกเสริม";

  const actions = document.createElement("div");
  actions.className = "card-actions";
  const editButton = document.createElement("button");
  editButton.className = "button-secondary";
  editButton.type = "button";
  editButton.textContent = "แก้ไข";
  editButton.addEventListener("click", () => editItem(item));
  actions.append(editButton);

  if (item.available) {
    const disableButton = document.createElement("button");
    disableButton.className = "button-danger";
    disableButton.type = "button";
    disableButton.textContent = "ปิดขาย";
    disableButton.addEventListener("click", async () => {
      if (!window.confirm(`ปิดขายเมนู "${item.name}"?`)) return;
      try {
        await request(`/admin/menu/${item.id}`, { method: "DELETE" });
        showNotice(`ปิดขาย "${item.name}" แล้ว`);
        await loadMenu();
      } catch (error) {
        showNotice(error.message, true);
      }
    });
    actions.append(disableButton);
  }

  card.append(heading, meta, description, optionSummary, actions);
  return card;
}

async function loadMenu() {
  try {
    const items = await request("/admin/menu");
    menuList.replaceChildren();
    if (items.length === 0) {
      const empty = document.createElement("p");
      empty.className = "empty-state";
      empty.textContent = "ยังไม่มีเมนู กดเพิ่มเมนูได้เลย";
      menuList.append(empty);
      return;
    }
    items.forEach((item) => menuList.append(createMenuCard(item)));
  } catch (error) {
    showNotice(error.message, true);
    menuList.replaceChildren();
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "โหลดเมนูไม่สำเร็จ ตรวจสอบ API URL และ Admin API Key";
    menuList.append(empty);
  }
}

connectionForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const apiBase = document.querySelector("#api-url").value.trim().replace(/\/+$/, "");
  const adminKey = document.querySelector("#admin-key").value;
  localStorage.setItem("restaurant-api-url", apiBase);
  sessionStorage.setItem("restaurant-admin-key", adminKey);
  showNotice("กำลังเชื่อมต่อ...");
  await loadMenu();
});

menuForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(menuForm);
  const payload = {
    name: form.get("name").trim(),
    price: Number(form.get("price")),
    category: form.get("category").trim(),
    description: form.get("description").trim() || null,
    available: menuForm.elements.available.checked,
    options: [...optionsList.querySelectorAll(".option-row")].map((row) => ({
      name: row.querySelector(".option-name").value.trim(),
      price: Number(row.querySelector(".option-price").value),
    })),
  };

  try {
    const path = editingId === null ? "/admin/menu" : `/admin/menu/${editingId}`;
    await request(path, {
      method: editingId === null ? "POST" : "PUT",
      body: JSON.stringify(payload),
    });
    showNotice(editingId === null ? "เพิ่มเมนูเรียบร้อยแล้ว" : "บันทึกการแก้ไขเรียบร้อยแล้ว");
    resetForm();
    await loadMenu();
  } catch (error) {
    showNotice(error.message, true);
  }
});

document.querySelector("#add-option").addEventListener("click", () => addOptionRow());
document.querySelector("#refresh-menu").addEventListener("click", loadMenu);
newItemButton.addEventListener("click", resetForm);

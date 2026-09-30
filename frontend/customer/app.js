const API_URL = "http://127.0.0.1:8000";
const menuList = document.querySelector("#menu-list");
const menuNotice = document.querySelector("#menu-notice");
const itemModal = document.querySelector("#item-modal");
const checkoutModal = document.querySelector("#checkout-modal");
const successModal = document.querySelector("#success-modal");
const cartBar = document.querySelector("#cart-bar");
const cart = [];
let menuData = [];
let currentItem = null;
let currentQuantity = 1;

const money = (value) =>
    `${Number(value).toLocaleString("th-TH", { maximumFractionDigits: 2 })} บาท`;

function showMenuNotice(message) {
    menuNotice.textContent = message;
    menuNotice.hidden = false;
}

function createMenuCard(item, index) {
    const card = document.createElement("article");
    card.className = "menu-card";

    const artwork = document.createElement("div");
    artwork.className = "dish-art";
    artwork.setAttribute("aria-hidden", "true");
    const illustration = document.createElement("span");
    illustration.textContent = ["🍛", "🍜", "🍳", "🥗"][index % 4];
    artwork.append(illustration);

    const content = document.createElement("div");
    content.className = "menu-card-body";
    const category = document.createElement("span");
    category.className = "menu-category";
    category.textContent = item.category;
    const name = document.createElement("h3");
    name.textContent = item.name;
    const description = document.createElement("p");
    description.className = "menu-description";
    description.textContent = item.description || "ปรุงสดใหม่ด้วยวัตถุดิบคุณภาพ";
    const bottom = document.createElement("div");
    bottom.className = "menu-card-bottom";
    const price = document.createElement("span");
    price.className = "menu-price";
    price.textContent = money(item.price);
    const choose = document.createElement("button");
    choose.className = "button button-small";
    choose.type = "button";
    choose.textContent = "+ เลือกเมนู";
    choose.addEventListener("click", () => openItemModal(item.id));
    bottom.append(price, choose);
    content.append(category, name, description, bottom);
    card.append(artwork, content);
    return card;
}

async function fetchMenu() {
    menuList.replaceChildren();
    const loading = document.createElement("p");
    loading.className = "empty-menu";
    loading.textContent = "กำลังเตรียมเมนูให้คุณ...";
    menuList.append(loading);
    try {
        const response = await fetch(`${API_URL}/menu`);
        if (!response.ok) {
            throw new Error(`โหลดเมนูไม่สำเร็จ (${response.status})`);
        }
        menuData = await response.json();
        menuList.replaceChildren();
        if (menuData.length === 0) {
            const empty = document.createElement("p");
            empty.className = "empty-menu";
            empty.textContent = "ยังไม่มีเมนูที่เปิดขาย ลองกลับมาใหม่อีกครั้งนะ";
            menuList.append(empty);
            return;
        }
        menuData
            .filter((item) => item.available !== false)
            .forEach((item, index) => menuList.append(createMenuCard(item, index)));
    } catch (error) {
        console.error("Error fetching menu:", error);
        showMenuNotice("เชื่อมต่อเมนูไม่สำเร็จ กรุณาตรวจสอบว่า backend กำลังทำงาน แล้วโหลดหน้านี้ใหม่");
        menuList.replaceChildren();
    }
}

function openItemModal(itemId) {
    currentItem = menuData.find((item) => item.id === itemId);
    if (!currentItem) return;
    currentQuantity = 1;
    document.querySelector("#modal-qty").textContent = currentQuantity;
    document.querySelector("#modal-item-name").textContent = currentItem.name;
    document.querySelector("#modal-item-price").textContent = money(currentItem.price);
    document.querySelector("#modal-note").value = "";

    const optionsList = document.querySelector("#modal-options-list");
    optionsList.replaceChildren();
    if (currentItem.options?.length) {
        currentItem.options.forEach((option) => {
            const label = document.createElement("label");
            label.className = "option-row";
            const checkbox = document.createElement("input");
            checkbox.type = "checkbox";
            checkbox.name = "modal-option";
            checkbox.value = option.id;
            const name = document.createElement("span");
            name.textContent = option.name;
            const price = document.createElement("span");
            price.className = "option-price";
            price.textContent = `+${money(option.price || 0)}`;
            label.append(checkbox, name, price);
            optionsList.append(label);
        });
    } else {
        const empty = document.createElement("p");
        empty.className = "menu-description";
        empty.textContent = "เมนูนี้ไม่มีตัวเลือกเสริม";
        optionsList.append(empty);
    }
    itemModal.hidden = false;
}

function addToCart() {
    if (!currentItem) return;
    const selectedOptions = [...document.querySelectorAll('input[name="modal-option"]:checked')]
        .map((checkbox) => currentItem.options.find((option) => option.id === Number(checkbox.value)))
        .filter(Boolean);
    const unitPrice = Number(currentItem.price) +
        selectedOptions.reduce((sum, option) => sum + Number(option.price || 0), 0);
    const note = document.querySelector("#modal-note").value.trim();

    cart.push({
        menu_item_id: currentItem.id,
        name: currentItem.name,
        quantity: currentQuantity,
        subtotal: unitPrice * currentQuantity,
        option_ids: selectedOptions.map((option) => option.id),
        options: selectedOptions.map((option) => option.name),
        note,
    });
    itemModal.hidden = true;
    updateCart();
}

function updateCart() {
    const quantity = cart.reduce((sum, item) => sum + item.quantity, 0);
    const total = cart.reduce((sum, item) => sum + item.subtotal, 0);
    document.querySelector("#cart-count").textContent = `ตะกร้า (${quantity} รายการ)`;
    document.querySelector("#cart-total").textContent = money(total);
    cartBar.hidden = cart.length === 0;
}

function renderCheckout() {
    const list = document.querySelector("#checkout-items-list");
    list.replaceChildren();
    cart.forEach((item, index) => {
        const row = document.createElement("div");
        row.className = "checkout-line";
        const description = document.createElement("div");
        const name = document.createElement("span");
        name.className = "checkout-line-name";
        name.textContent = `${item.name} × ${item.quantity}`;
        description.append(name);
        if (item.options.length || item.note) {
            const detail = document.createElement("span");
            detail.className = "checkout-line-detail";
            detail.textContent = [
                ...item.options.map((option) => `เพิ่ม ${option}`),
                ...(item.note ? [`หมายเหตุ: ${item.note}`] : []),
            ].join(" · ");
            description.append(detail);
        }
        const price = document.createElement("div");
        price.className = "checkout-line-price";
        price.textContent = money(item.subtotal);
        const remove = document.createElement("button");
        remove.className = "remove-item";
        remove.type = "button";
        remove.textContent = "ลบรายการ";
        remove.addEventListener("click", () => {
            cart.splice(index, 1);
            updateCart();
            if (!cart.length) {
                checkoutModal.hidden = true;
                return;
            }
            renderCheckout();
        });
        description.append(remove);
        row.append(description, price);
        list.append(row);
    });
    document.querySelector("#checkout-total").textContent =
        money(cart.reduce((sum, item) => sum + item.subtotal, 0));
}

function openCheckout() {
    if (!cart.length) return;
    document.querySelector("#checkout-error").hidden = true;
    renderCheckout();
    checkoutModal.hidden = false;
}

async function submitOrder(event) {
    event.preventDefault();
    if (!cart.length) return;

    const submitButton = document.querySelector("#submit-order");
    const errorMessage = document.querySelector("#checkout-error");
    const customerName = document.querySelector("#cust-name").value.trim();
    const phone = document.querySelector("#cust-phone").value.trim();
    const address = document.querySelector("#cust-address").value.trim();
    submitButton.disabled = true;
    submitButton.textContent = "กำลังส่งออเดอร์...";
    errorMessage.hidden = true;

    try {
        const response = await fetch(`${API_URL}/orders`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                customer_name: customerName,
                phone,
                address,
                items: cart.map((item) => ({
                    menu_item_id: item.menu_item_id,
                    quantity: item.quantity,
                    option_ids: item.option_ids,
                    note: item.note || null,
                })),
            }),
        });
        const data = await response.json();
        if (!response.ok) {
            const detail = typeof data.detail === "string"
                ? data.detail
                : "ตรวจสอบข้อมูลที่กรอกแล้วลองอีกครั้ง";
            throw new Error(detail);
        }

        document.querySelector("#success-order-id").textContent = `#${data.id}`;
        document.querySelector("#line-order-message").textContent = `#${data.id} ${phone}`;
        document.querySelector("#copy-feedback").textContent = "";
        cart.length = 0;
        updateCart();
        document.querySelector("#checkout-form").reset();
        checkoutModal.hidden = true;
        successModal.hidden = false;
    } catch (error) {
        errorMessage.textContent = error.message || "เชื่อมต่อเซิร์ฟเวอร์ไม่สำเร็จ กรุณาลองอีกครั้ง";
        errorMessage.hidden = false;
    } finally {
        submitButton.disabled = false;
        submitButton.innerHTML = 'ยืนยันออเดอร์ <span aria-hidden="true">→</span>';
    }
}

async function copyLineMessage() {
    const message = document.querySelector("#line-order-message").textContent;
    const feedback = document.querySelector("#copy-feedback");
    try {
        await navigator.clipboard.writeText(message);
    } catch {
        const temporaryInput = document.createElement("textarea");
        temporaryInput.value = message;
        temporaryInput.setAttribute("readonly", "");
        temporaryInput.style.position = "fixed";
        temporaryInput.style.opacity = "0";
        document.body.append(temporaryInput);
        temporaryInput.select();
        const copied = document.execCommand("copy");
        temporaryInput.remove();
        if (!copied) {
            feedback.textContent = "คัดลอกไม่สำเร็จ กรุณาเลือกข้อความแล้วคัดลอก";
            return;
        }
    }
    feedback.textContent = "คัดลอกแล้ว! เปิดแชต LINE ร้านแล้ววางข้อความเพื่อผูกออเดอร์";
}

document.querySelector("#open-checkout").addEventListener("click", openCheckout);
document.querySelector("#add-to-cart").addEventListener("click", addToCart);
document.querySelector("#checkout-form").addEventListener("submit", submitOrder);
document.querySelector("#copy-line-message").addEventListener("click", copyLineMessage);
document.querySelector("#finish-order").addEventListener("click", () => {
    successModal.hidden = true;
    window.scrollTo({ top: 0, behavior: "smooth" });
});
document.querySelectorAll("[data-quantity]").forEach((button) => {
    button.addEventListener("click", () => {
        currentQuantity = Math.max(1, currentQuantity + Number(button.dataset.quantity));
        document.querySelector("#modal-qty").textContent = currentQuantity;
    });
});
document.querySelectorAll("[data-close-item]").forEach((button) => {
    button.addEventListener("click", () => { itemModal.hidden = true; });
});
document.querySelectorAll("[data-close-checkout]").forEach((button) => {
    button.addEventListener("click", () => { checkoutModal.hidden = true; });
});
for (const modal of [itemModal, checkoutModal, successModal]) {
    modal.addEventListener("click", (event) => {
        if (event.target === modal && modal !== successModal) modal.hidden = true;
    });
}
document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
        if (!itemModal.hidden) itemModal.hidden = true;
        else if (!checkoutModal.hidden) checkoutModal.hidden = true;
    }
});

fetchMenu();

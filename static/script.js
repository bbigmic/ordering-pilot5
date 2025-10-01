const cart = [];
let total = 0;

function adjustSliderHeight() {
    const sliders = document.querySelectorAll('.item-slider');

    sliders.forEach(slider => {
        const bgImage = new Image();
        bgImage.src = getComputedStyle(slider).backgroundImage.replace(/url\(['"]?(.*?)['"]?\)/i, '$1');

        bgImage.onload = function () {
            slider.style.height = bgImage.height + 'px'; // Ustawienie wysokości na podstawie załadowanego obrazka
        };
    });
}

// Wywołanie funkcji po załadowaniu strony i po zmianie rozmiaru okna
window.addEventListener('load', adjustSliderHeight);
window.addEventListener('resize', adjustSliderHeight);


function addToCart(id, name, basePrice, containsAlcohol) {
    if (containsAlcohol) {
        const ageConfirm = document.getElementById(`age-confirm-${id}`);
        if (!ageConfirm.checked) {
            alert("Musisz potwierdzić, że masz 18 lat, aby dodać tę pozycję do koszyka.");
            return;
        }
    }

    const customizationInput = document.getElementById(`customization-${id}`);
    const takeawayCheckbox = document.getElementById(`takeaway-${id}`);
    const customization = customizationInput ? customizationInput.value : '';
    const takeaway = takeawayCheckbox ? takeawayCheckbox.checked : false;

    const takeawayFee = takeaway ? 2.35 : 0;
    const itemPrice = basePrice + takeawayFee;

    // Sprawdzamy, czy pozycja już istnieje w koszyku (z takimi samymi opcjami)
    const existingItem = cart.find(item => item.id === id && item.customization === customization && item.takeaway === takeaway);

    if (existingItem) {
        existingItem.quantity += 1;
        existingItem.totalPrice += itemPrice;
    } else {
        cart.push({ id, name, price: itemPrice, quantity: 1, totalPrice: itemPrice, customization, takeaway, containsAlcohol });
    }

    total += itemPrice; // Aktualizujemy całkowity koszt
    updateCart(); // Wywołujemy funkcję do aktualizacji widoku koszyka

    const cartToggleButton = document.getElementById("cart-toggle-btn");
    cartToggleButton.classList.add("shake");
    setTimeout(() => cartToggleButton.classList.remove("shake"), 500);
}

function removeFromCart(id, customization = '') {
    // Znajdź indeks pozycji w koszyku, biorąc pod uwagę również personalizację
    const itemIndex = cart.findIndex(item => item.id === id && item.customization === customization && item.takeaway === takeaway);
    
    if (itemIndex !== -1) {
        total -= cart[itemIndex].totalPrice;
        cart.splice(itemIndex, 1);
    }
    updateCart();
}

function updateCart() {
    const cartItemsList = document.getElementById("cart-items");
    cartItemsList.innerHTML = "";

    cart.forEach(item => {
        const takeawayText = item.takeaway ? " (Na wynos)" : "";
        const listItem = document.createElement("li");
        listItem.innerHTML = `
            ${item.name}${takeawayText} - Ilość: ${item.quantity} x ${item.price.toFixed(2)} PLN = ${item.totalPrice.toFixed(2)} PLN
            ${item.customization ? `<br><em style="color:#808080;">Personalizacja: ${item.customization}</em>` : ""}
            <button onclick="removeFromCart(${item.id}, '${item.customization}')" class="remove-btn">Usuń</button>
        `;
        cartItemsList.appendChild(listItem);
    });

    // Aktualizacja łącznej ceny na przycisku koszyka
    document.getElementById("cart-toggle-btn").innerHTML = `Pokaż Koszyk<br><span>${total.toFixed(2)} PLN 🛒</span>`;

    document.getElementById("cart-total").innerText = total.toFixed(2);
}

function submitOrder() {
    if (cart.length === 0) {
        alert("Koszyk jest pusty! Dodaj produkty przed złożeniem zamówienia.");
        return;
    }

    const urlPath = window.location.pathname;
    const tableId = urlPath.split("/").pop();

    const confirmation = window.confirm("Czy na pewno chcesz złożyć zamówienie? Wybrane dania zostaną przekazane do realizacji.");
    
    if (confirmation) {
        fetch('/order', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ table_id: parseInt(tableId), items: cart })
        })
        .then(response => response.json())
        .then(data => {
            window.location.href = `/order_status/${data.order_id}`;
        });
    }
}

function toggleCart() {
    const cart = document.getElementById("cart");
    cart.classList.toggle("show");

    const toggleBtn = document.getElementById("cart-toggle-btn");
    if (cart.classList.contains("show")) {
        toggleBtn.innerHTML = `Ukryj Koszyk<br><span>${total.toFixed(2)} PLN 🛒</span>`;
    } else {
        toggleBtn.innerHTML = `Pokaż Koszyk<br><span>${total.toFixed(2)} PLN 🛒</span>`;
    }
}

    // Funkcja do rozwijania i zwijania kategorii
    function toggleCategory(button) {
        button.classList.toggle("active");
        const panel = button.nextElementSibling;
        panel.style.display = panel.style.display === "none" ? "block" : "none";
    }

document.addEventListener("DOMContentLoaded", function () {
    const flashMessages = document.querySelectorAll(".flash-message");

    flashMessages.forEach((message) => {
        setTimeout(() => {
            message.classList.add("hide"); // Dodajemy klasę animacji
            setTimeout(() => message.remove(), 500); // Usunięcie elementu po animacji
        }, 3000); // Czas wyświetlania: 3 sekundy
    });
});




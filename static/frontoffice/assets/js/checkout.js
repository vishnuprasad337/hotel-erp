/* ============================================================
   FRONT OFFICE - CHECKOUT
   static/frontoffice/assets/js/checkout.js
============================================================ */

"use strict";

/* ============================================================
   CHECKOUT STATE
============================================================ */

let coState = {
  step: 1,
  bookingId: null,
  folioId: null,

  guestName: "",
  roomType: "",
  roomNumber: "",
  roomUnitId: null,

  guestEmail: "",

  charges: [],

  totalCharges: 0,
  totalPaid: 0,
  balanceDue: 0,

  discount: 0,
  finalBalanceDue: 0,
};

let currentCoStep = 1;

/* ============================================================
   COMMON HELPERS
============================================================ */

function checkoutGetCsrf() {
  const input = document.querySelector("[name=csrfmiddlewaretoken]");

  if (input && input.value) {
    return input.value;
  }

  const cookie = document.cookie
    .split("; ")
    .find((row) => row.startsWith("csrftoken="));

  return cookie ? decodeURIComponent(cookie.split("=")[1]) : "";
}

function checkoutFmt(value) {
  const number = parseFloat(value || 0);

  return (
    "₹" +
    number.toLocaleString("en-IN", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })
  );
}

function checkoutEscapeHtml(value) {
  const div = document.createElement("div");

  div.appendChild(document.createTextNode(String(value || "")));

  return div.innerHTML;
}

function checkoutSetLoading(button, loading, originalHtml) {
  if (!button) {
    return;
  }

  button.disabled = loading;

  if (loading) {
    button.innerHTML = `
            <i class="fas fa-spinner fa-spin"></i>
            Please wait...
        `;
  } else {
    button.innerHTML = originalHtml;
  }
}

/* ============================================================
   NOTIFICATION
============================================================ */

function checkoutToast(message, type = "success") {
  /*
   * Use existing global toast()
   * if base/frontoffice JS provides it.
   */

  if (typeof window.toast === "function" && window.toast !== checkoutToast) {
    window.toast(message, type);

    return;
  }

  /*
   * Fallback notification.
   */

  let stack = document.getElementById("checkoutToastStack");

  if (!stack) {
    stack = document.createElement("div");

    stack.id = "checkoutToastStack";

    stack.style.position = "fixed";

    stack.style.top = "20px";

    stack.style.right = "20px";

    stack.style.zIndex = "999999";

    stack.style.display = "flex";

    stack.style.flexDirection = "column";

    stack.style.gap = "10px";

    document.body.appendChild(stack);
  }

  const item = document.createElement("div");

  let background = "#16a34a";

  if (type === "error") {
    background = "#dc2626";
  } else if (type === "info") {
    background = "#2563eb";
  }

  item.style.background = background;

  item.style.color = "#ffffff";

  item.style.padding = "12px 16px";

  item.style.borderRadius = "8px";

  item.style.boxShadow = "0 8px 30px rgba(0,0,0,.18)";

  item.style.fontSize = "13px";

  item.style.fontWeight = "600";

  item.style.maxWidth = "380px";

  item.textContent = message;

  stack.appendChild(item);

  setTimeout(() => {
    item.remove();
  }, 3800);
}

/* ============================================================
   MODAL HELPERS
============================================================ */

function checkoutOpenModal(id) {
  const modal = document.getElementById(id);

  if (!modal) {
    console.error(`Checkout modal not found: ${id}`);

    return;
  }

  /*
   * Old modal system uses .open.
   */

  modal.classList.add("open");

  /*
   * Also force display because
   * new dashboard modal CSS may
   * use display:none.
   */

  modal.style.display = "grid";

  document.body.style.overflow = "hidden";
}

function checkoutCloseModal(id) {
  const modal = document.getElementById(id);

  if (!modal) {
    return;
  }

  modal.classList.remove("open");

  modal.style.display = "none";

  document.body.style.overflow = "";
}

/* ============================================================
   DASHBOARD CHECKOUT SELECTOR
============================================================ */

function openDashboardCheckout() {
  const modal = document.getElementById("dashboardCheckoutSelector");

  if (!modal) {
    console.error("dashboardCheckoutSelector not found.");

    checkoutToast("Checkout selector is not available.", "error");

    return;
  }

  modal.style.display = "flex";

  document.body.style.overflow = "hidden";
}

function closeDashboardCheckout() {
  const modal = document.getElementById("dashboardCheckoutSelector");

  if (!modal) {
    return;
  }

  modal.style.display = "none";

  document.body.style.overflow = "";
}

/* ============================================================
   START CHECKOUT
============================================================ */

function startCheckout(bookingId, guestName, roomType, roomNumber, roomUnitId) {
  const checkoutModal = document.getElementById("checkoutBillingModal");

  if (!checkoutModal) {
    console.error("checkoutBillingModal not found.");

    checkoutToast("Checkout billing modal was not found.", "error");

    return;
  }

  coState = {
    step: 1,

    bookingId: bookingId,

    folioId: null,

    guestName: guestName || "Guest",

    roomType: roomType || "",

    roomNumber: roomNumber || "",

    roomUnitId: roomUnitId || null,

    guestEmail: "",

    charges: [],

    totalCharges: 0,

    totalPaid: 0,

    balanceDue: 0,
  };

  const avatar = document.getElementById("coGuestAvatar");

  if (avatar) {
    avatar.textContent = (guestName || "G").charAt(0).toUpperCase();
  }

  const guestDisplay = document.getElementById("coGuestNameDisplay");

  if (guestDisplay) {
    guestDisplay.textContent = guestName || "Guest";
  }

  const roomDisplay = document.getElementById("coRoomDisplay");

  if (roomDisplay) {
    roomDisplay.textContent =
      (roomType || "") + (roomNumber ? ` · Room ${roomNumber}` : "");
  }

  const balance = document.getElementById("coBalanceDue");

  if (balance) {
    balance.textContent = "₹...";
  }

  const subtitle = document.getElementById("coModalSubtitle");

  if (subtitle) {
    subtitle.textContent = `Booking #${bookingId}`;
  }

  const paymentMethod = document.getElementById("coSelectedPayMethod");

  if (paymentMethod) {
    paymentMethod.value = "cash";
  }

  document.querySelectorAll(".pay-method-card").forEach((card) => {
    card.classList.remove("selected");

    if (card.dataset.method === "cash") {
      card.classList.add("selected");
    }
  });

  /*
   * Reset payment fields.
   */

  const ref = document.getElementById("coPayRef");

  const note = document.getElementById("coPayNote");

  const discount = document.getElementById("invoiceDiscount");

  const invoiceNotes = document.getElementById("invoiceNotes");

  if (ref) {
    ref.value = "";
  }

  if (note) {
    note.value = "";
  }

  if (discount) {
    discount.value = "0";
  }

  if (invoiceNotes) {
    invoiceNotes.value = "";
  }

  /*
   * Close selector first.
   */

  closeDashboardCheckout();

  /*
   * Reset checkout to step 1.
   */

  goToCoStep(1);

  /*
   * Open billing modal.
   */

  checkoutOpenModal("checkoutBillingModal");

  /*
   * Load/create folio.
   */

  initFolio(bookingId);
}

/* ============================================================
   LOAD / CREATE FOLIO
============================================================ */

async function initFolio(bookingId) {
  const roomList = document.getElementById("roomChargeList");

  if (roomList) {
    roomList.innerHTML = `
            <div
                style="
                    text-align:center;
                    padding:16px;
                    color:var(--text-3);
                    font-size:13px;
                "
            >
                <i class="fas fa-spinner fa-spin"></i>
                Loading bill...
            </div>
        `;
  }

  const aiText = document.getElementById("aiText");

  if (aiText) {
    aiText.textContent = "Loading booking charges...";
  }

  const aiActions = document.getElementById("aiActions");

  if (aiActions) {
    aiActions.innerHTML = "";
  }

  try {
    const response = await fetch(
      `/api/get-bill/?booking_id=${encodeURIComponent(bookingId)}`,
      {
        method: "GET",
        credentials: "same-origin",
        headers: {
          "X-Requested-With": "XMLHttpRequest",
        },
      },
    );

    const data = await response.json().catch(() => ({}));

    if (!response.ok || !data.success) {
      throw new Error(
        data.error ||
          data.message ||
          `Unable to load bill. HTTP ${response.status}`,
      );
    }

    /*
     * Current get_bill() response.
     */

    coState.folioId =
      data.folio_id ?? data.folio?.id ?? data.folio?.folio_id ?? null;

    coState.charges = Array.isArray(data.charges) ? data.charges : [];

    coState.totalCharges = parseFloat(data.subtotal ?? data.total_charges ?? 0);

    coState.totalPaid = parseFloat(data.total_paid ?? 0);

    coState.balanceDue = parseFloat(data.balance_due ?? 0);

    coState.guestEmail = data.guest?.email ?? data.guest_email ?? "";

    /*
     * If backend returns guest/room details,
     * keep the checkout header synchronized.
     */

    if (data.guest?.name) {
      coState.guestName = data.guest.name;
    }

    updateBillDisplay();

    renderAllChargeLists();

    /*
     * Keep existing suggestion UI.
     */
    generateAISuggestions({
      charges: coState.charges,
    });
  } catch (error) {
    console.error("Bill load error:", error);

    if (roomList) {
      roomList.innerHTML = `
                <div
                    style="
                        padding:14px;
                        color:var(--red);
                        font-size:13px;
                    "
                >
                    <i class="fas fa-exclamation-triangle"></i>
                    ${checkoutEscapeHtml(error.message)}
                </div>
            `;
    }

    if (aiText) {
      aiText.textContent = "Could not load booking data.";
    }

    checkoutToast(error.message || "Unable to load checkout bill.", "error");
  }
}

/* ============================================================
   UPDATE BILL DISPLAY
============================================================ */

function updateBillDisplay() {
  const balance = parseFloat(coState.balanceDue || 0);

  const total = parseFloat(coState.totalCharges || 0);

  const paid = parseFloat(coState.totalPaid || 0);

  setCheckoutText("coBalanceDue", checkoutFmt(balance));

  setCheckoutText("folioTotalDisplay", checkoutFmt(total));

  setCheckoutText(
    "folioBreakdownDisplay",
    `Charges: ${checkoutFmt(total)} · Paid: ${checkoutFmt(paid)}`,
  );

  const status = document.getElementById("coFolioStatus");

  if (status) {
    status.textContent = balance <= 0 ? "Settled" : "Open Folio";

    status.className = "pill " + (balance <= 0 ? "pill-green" : "pill-amber");
  }

  setCheckoutText("payTotalCharges", checkoutFmt(total));

  setCheckoutText("payAlreadyPaid", checkoutFmt(paid));

  setCheckoutText("payBalanceDue", checkoutFmt(balance));

  const amount = document.getElementById("coPayAmount");

  if (amount) {
    amount.value = balance.toFixed(2);
  }

  setCheckoutText("guestEmailDisplay", coState.guestEmail || "—");
   
   updateCheckoutDiscount(); 

}



function updateCheckoutDiscount() {
  const discountInput = document.getElementById("invoiceDiscount");

  let discount = parseFloat(discountInput?.value || 0);

  if (isNaN(discount) || discount < 0) {
    discount = 0;
  }

  // Discount cannot exceed total charges
  if (discount > coState.totalCharges) {
    discount = coState.totalCharges;

    if (discountInput) {
      discountInput.value = discount.toFixed(2);
    }
  }

  coState.discount = discount;

  const discountedTotal = Math.max(0, coState.totalCharges - discount);

  const finalBalance = Math.max(0, discountedTotal - coState.totalPaid);

  coState.finalBalanceDue = finalBalance;

  // Payment amount should now be the discounted balance
  const amountInput = document.getElementById("coPayAmount");

  if (amountInput) {
    amountInput.value = finalBalance.toFixed(2);
  }

  // Update payment screen
  setCheckoutText("payTotalCharges", checkoutFmt(discountedTotal));

  setCheckoutText("payAlreadyPaid", checkoutFmt(coState.totalPaid));

  setCheckoutText("payBalanceDue", checkoutFmt(finalBalance));

  setCheckoutText("coBalanceDue", checkoutFmt(finalBalance));
}


function setCheckoutText(id, value) {
  const element = document.getElementById(id);

  if (element) {
    element.textContent = value;
  }
}

/* ============================================================
   AI SUGGESTION
============================================================ */

function generateAISuggestions(folio) {
  const aiText = document.getElementById("aiText");

  const aiActions = document.getElementById("aiActions");

  if (!aiText || !aiActions) {
    return;
  }

  const roomCharge = (folio.charges || []).find(
    (charge) => charge.charge_type === "room",
  );

  const match = roomCharge?.description?.match(/(\d+)\s+night/i);

  const nights = match ? parseInt(match[1], 10) : 1;

  if (nights >= 3) {
    aiText.textContent = `Guest stayed ${nights} nights. Review the folio before payment.`;
  } else {
    aiText.textContent =
      "Review restaurant, laundry, minibar and other charges before checkout.";
  }

  aiActions.innerHTML = `
        <button
            type="button"
            class="ai-btn"
            onclick="switchChargeTab('minibar', null)"
        >
            <i class="fas fa-wine-glass"></i>
            Check Minibar
        </button>

        <button
            type="button"
            class="ai-btn"
            onclick="switchChargeTab('restaurant', null)"
        >
            <i class="fas fa-utensils"></i>
            Restaurant
        </button>

        <button
            type="button"
            class="ai-btn"
            onclick="
                document.getElementById('aiBox').style.display='none'
            "
        >
            Dismiss
        </button>
    `;
}

/* ============================================================
   RENDER CHARGES
============================================================ */

function renderAllChargeLists() {
  const byType = {};

  (coState.charges || []).forEach((charge) => {
    let type = charge.charge_type || "other";

    /*
     * Transport appears inside
     * the Other tab in your HTML.
     */

    if (type === "transport") {
      type = "other";
    }

    if (!byType[type]) {
      byType[type] = [];
    }

    byType[type].push(charge);
  });

  const icons = {
    room: "fa-bed",

    restaurant: "fa-utensils",

    laundry: "fa-tshirt",

    minibar: "fa-wine-glass",

    spa: "fa-spa",

    other: "fa-tag",
  };

  const types = ["room", "restaurant", "laundry", "minibar", "spa", "other"];

  types.forEach((type) => {
    const list = document.getElementById(`${type}ChargeList`);

    if (!list) {
      return;
    }

    const charges = byType[type] || [];

    if (!charges.length) {
      list.innerHTML = `
                    <div
                        style="
                            text-align:center;
                            padding:14px;
                            font-size:12px;
                            color:var(--text-3);
                        "
                    >
                        No ${type} charges yet.
                    </div>
                `;

      return;
    }

    list.innerHTML = charges
      .map((charge) => {
        const amount = charge.total ?? charge.amount ?? 0;

        const tax = charge.tax_amount ?? 0;

        const description = checkoutEscapeHtml(charge.description || "Charge");

        const date = checkoutEscapeHtml(charge.date || "");

        const addedBy = checkoutEscapeHtml(charge.added_by || "");

        const metadata = [date, addedBy].filter(Boolean).join(" · ");

        const chargeId = Number(charge.id);

        const deleteButton =
          type === "room"
            ? `
                                        <button
                                            type="button"
                                            class="charge-del"
                                            disabled
                                            title="Room charge cannot be deleted"
                                        >
                                            <i class="fas fa-lock"></i>
                                        </button>
                                    `
            : `
                                        <button
                                            type="button"
                                            class="charge-del"
                                            onclick="deleteCharge(${chargeId})"
                                            title="Remove charge"
                                        >
                                            <i class="fas fa-times"></i>
                                        </button>
                                    `;

        return `
                                <div class="charge-item">

                                    <div
                                        class="charge-icon ci-${type}"
                                    >
                                        <i
                                            class="fas ${
                                              icons[type] || "fa-tag"
                                            }"
                                        ></i>
                                    </div>

                                    <div class="charge-info">

                                        <div class="charge-name">
                                            ${description}
                                        </div>

                                        <div class="charge-meta">
                                            ${metadata}
                                        </div>

                                    </div>

                                    <div>

                                        <div class="charge-amount">
                                            ${checkoutFmt(amount)}
                                        </div>

                                        <div class="charge-tax">
                                            +${checkoutFmt(tax)} tax
                                        </div>

                                    </div>

                                    ${deleteButton}

                                </div>
                            `;
      })
      .join("");
  });
}

/* ============================================================
   DELETE CHARGE
============================================================ */

async function deleteCharge(chargeId) {
  if (!chargeId) {
    return;
  }

  if (!window.confirm("Remove this charge?")) {
    return;
  }

  try {
    const response = await fetch(`/api/billing/delete-charge/${chargeId}/`, {
      method: "DELETE",

      headers: {
        "X-CSRFToken": checkoutGetCsrf(),
      },

      credentials: "same-origin",
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      throw new Error(data.error || data.message || "Failed to remove charge.");
    }

    coState.charges = coState.charges.filter(
      (charge) => Number(charge.id) !== Number(chargeId),
    );

    const total = coState.charges.reduce((sum, charge) => {
      return sum + parseFloat(charge.total ?? charge.amount ?? 0);
    }, 0);

    coState.totalCharges = total;

    if (data.folio_balance !== undefined) {
      coState.balanceDue = parseFloat(data.folio_balance || 0);
    } else {
      coState.balanceDue = Math.max(0, total - coState.totalPaid);
    }

    updateBillDisplay();

    renderAllChargeLists();

    checkoutToast("Charge removed.");
  } catch (error) {
    console.error("Delete charge error:", error);

    checkoutToast(error.message, "error");
  }
}

/* ============================================================
   CHARGE TABS
============================================================ */

function switchChargeTab(type, button) {
  document.querySelectorAll(".charge-cat-panel").forEach((panel) => {
    panel.style.display = "none";
  });

  const panel = document.getElementById(`ctab-${type}`);

  if (panel) {
    panel.style.display = "block";
  }

  document.querySelectorAll(".charge-tab").forEach((tab) => {
    tab.classList.remove("active");
  });

  if (button) {
    button.classList.add("active");
  } else {
    document.querySelectorAll(".charge-tab").forEach((tab) => {
      const text = tab.textContent.toLowerCase();

      if (text.includes(type.substring(0, 3).toLowerCase())) {
        tab.classList.add("active");
      }
    });
  }

  hideCustomCharge();
}

/* ============================================================
   QUICK ADD CHARGE
============================================================ */

async function quickAddCharge(type, description, amount, button) {
  if (!coState.folioId) {
    checkoutToast("Folio is not loaded yet.", "error");

    return;
  }

  const numericAmount = parseFloat(amount);

  if (!numericAmount || numericAmount <= 0) {
    checkoutToast("Invalid charge amount.", "error");

    return;
  }

  /*
   * Same calculation used
   * by your old Front Office.
   */

  const tax = parseFloat((numericAmount * 0.05).toFixed(2));

  if (button) {
    button.disabled = true;

    button.style.opacity = "0.5";
  }

  try {
    const response = await fetch("/api/billing/add-charge/", {
      method: "POST",

      headers: {
        "Content-Type": "application/json",

        "X-CSRFToken": checkoutGetCsrf(),
      },

      credentials: "same-origin",

      body: JSON.stringify({
        folio_id: coState.folioId,

        charge_type: type,

        description: description,

        amount: numericAmount,

        tax_amount: tax,
      }),
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      throw new Error(data.error || data.message || "Unable to add charge.");
    }

    if (data.charge) {
      coState.charges.push({
        ...data.charge,

        charge_type: data.charge.charge_type || type,
      });
    }

    if (data.total_charges !== undefined) {
      coState.totalCharges = parseFloat(data.total_charges || 0);
    } else if (data.folio_balance !== undefined) {
      coState.totalCharges =
        coState.totalPaid + parseFloat(data.folio_balance || 0);
    } else {
      coState.totalCharges = coState.charges.reduce(
        (sum, charge) => sum + parseFloat(charge.total ?? charge.amount ?? 0),
        0,
      );
    }

    if (data.folio_balance !== undefined) {
      coState.balanceDue = parseFloat(data.folio_balance || 0);
    } else {
      coState.balanceDue = Math.max(
        0,
        coState.totalCharges - coState.totalPaid,
      );
    }

    updateBillDisplay();

    renderAllChargeLists();

    checkoutToast(
      `${description} — ${checkoutFmt(
        data.charge?.total ?? numericAmount + tax,
      )} added.`,
    );
  } catch (error) {
    console.error("Add charge error:", error);

    checkoutToast(error.message, "error");
  } finally {
    if (button) {
      button.disabled = false;

      button.style.opacity = "1";
    }
  }
}

/* ============================================================
   CUSTOM CHARGE
============================================================ */

function showCustomCharge(type) {
  const typeInput = document.getElementById("customChargeType");

  const form = document.getElementById("customChargeForm");

  const description = document.getElementById("customChargeDesc");

  if (typeInput) {
    typeInput.value = type;
  }

  if (form) {
    form.style.display = "block";
  }

  if (description) {
    description.focus();
  }
}

function hideCustomCharge() {
  const form = document.getElementById("customChargeForm");

  if (form) {
    form.style.display = "none";
  }
}

async function addCustomCharge() {
  const type = document.getElementById("customChargeType")?.value || "other";

  const description =
    document.getElementById("customChargeDesc")?.value.trim() || "";

  const amount = parseFloat(
    document.getElementById("customChargeAmt")?.value || 0,
  );

  /*
   * Your old HTML has a tax field.
   * The existing add-charge endpoint
   * accepts tax_amount.
   */

  const tax = parseFloat(
    document.getElementById("customChargeTax")?.value || 0,
  );

  if (!description) {
    checkoutToast("Enter charge description.", "error");

    return;
  }

  if (!amount || amount <= 0) {
    checkoutToast("Enter a valid charge amount.", "error");

    return;
  }

  if (!coState.folioId) {
    checkoutToast("Folio is not loaded.", "error");

    return;
  }

  try {
    const response = await fetch("/api/billing/add-charge/", {
      method: "POST",

      headers: {
        "Content-Type": "application/json",

        "X-CSRFToken": checkoutGetCsrf(),
      },

      credentials: "same-origin",

      body: JSON.stringify({
        folio_id: coState.folioId,

        charge_type: type,

        description: description,

        amount: amount,

        tax_amount: tax,
      }),
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      throw new Error(data.error || data.message || "Unable to add charge.");
    }

    if (data.charge) {
      coState.charges.push({
        ...data.charge,

        charge_type: data.charge.charge_type || type,
      });
    }

    if (data.folio_balance !== undefined) {
      coState.balanceDue = parseFloat(data.folio_balance || 0);

      coState.totalCharges = coState.totalPaid + coState.balanceDue;
    } else {
      coState.totalCharges = coState.charges.reduce(
        (sum, charge) => sum + parseFloat(charge.total ?? charge.amount ?? 0),
        0,
      );

      coState.balanceDue = Math.max(
        0,
        coState.totalCharges - coState.totalPaid,
      );
    }

    updateBillDisplay();

    renderAllChargeLists();

    document.getElementById("customChargeDesc").value = "";

    document.getElementById("customChargeAmt").value = "";

    document.getElementById("customChargeTax").value = "";

    hideCustomCharge();

    checkoutToast(`${description} added.`);
  } catch (error) {
    console.error("Custom charge error:", error);

    checkoutToast(error.message, "error");
  }
}

/* ============================================================
   CHECKOUT STEPS
============================================================ */

function goToCoStep(step) {

    // --------------------------------------------------------
    // VALIDATE BOOKING
    // --------------------------------------------------------

    if (!coState.bookingId) {
        checkoutToast(
            "Booking information is not loaded.",
            "info"
        );
        return;
    }


    // --------------------------------------------------------
    // VALIDATE STEP
    // --------------------------------------------------------

    if (step < 1 || step > 3) {
        return;
    }


    currentCoStep = step;
    coState.step = step;


    // --------------------------------------------------------
    // UPDATE PANELS
    // --------------------------------------------------------

    for (let i = 1; i <= 3; i++) {

        const panel =
            document.getElementById(
                `coPanel${i}`
            );

        if (panel) {
            panel.classList.toggle(
                "active",
                i === step
            );
        }


        // ----------------------------------------------------
        // STEPPER ITEM
        // ----------------------------------------------------

        const stepItem =
            document.getElementById(
                `coStep${i}`
            );

        if (stepItem) {

            stepItem.classList.toggle(
                "active",
                i === step
            );

            stepItem.classList.toggle(
                "done",
                i < step
            );
        }


        // ----------------------------------------------------
        // STEP CIRCLE
        // ----------------------------------------------------

        const circle =
            document.getElementById(
                `coStepCircle${i}`
            );

        if (circle) {

            if (i < step) {

                circle.innerHTML = `
                    <i
                        class="fas fa-check"
                        style="font-size:9px;"
                    ></i>
                `;

            } else {

                circle.textContent = i;

            }
        }


        // ----------------------------------------------------
        // CONNECTOR
        // ----------------------------------------------------

        if (i < 3) {

            const connector =
                document.getElementById(
                    `coConn${i}`
                );

            if (connector) {

                connector.classList.toggle(
                    "done",
                    i < step
                );
            }
        }
    }


    // --------------------------------------------------------
    // PREVIOUS BUTTON
    // --------------------------------------------------------

    const previousButton =
        document.getElementById(
            "coPrevBtn"
        );

    if (previousButton) {

        previousButton.style.display =
            step > 1
                ? "inline-flex"
                : "none";
    }


    // --------------------------------------------------------
    // NEXT BUTTON
    // --------------------------------------------------------

    const nextButton =
        document.getElementById(
            "coNextBtn"
        );

    if (nextButton) {

        nextButton.style.display =
            step < 3
                ? "inline-flex"
                : "none";
    }


    // --------------------------------------------------------
    // STEP 2 - PAYMENT
    // --------------------------------------------------------

    if (step === 2) {

        const paymentAmount =
            document.getElementById(
                "coPayAmount"
            );

        if (paymentAmount) {

            paymentAmount.value =
                Math.max(
                    0,
                    Number(
                        coState.balanceDue || 0
                    )
                ).toFixed(2);
        }
    }


    // --------------------------------------------------------
    // STEP 3 - RECEIPT
    // --------------------------------------------------------

    if (step === 3) {

        buildReceiptPreview();
    }
}


/* ============================================================
   NEXT STEP
============================================================ */

function nextCoStep() {

    if (currentCoStep < 3) {

        goToCoStep(
            currentCoStep + 1
        );
    }
}


/* ============================================================
   PREVIOUS STEP
============================================================ */

function prevCoStep() {

    if (currentCoStep > 1) {

        goToCoStep(
            currentCoStep - 1
        );
    }
}

/* ============================================================
   PAYMENT METHOD
============================================================ */

function selectPayMethod(element, method) {
  document.querySelectorAll(".pay-method-card").forEach((card) => {
    card.classList.remove("selected");
  });

  if (element) {
    element.classList.add("selected");
  }

  const hidden = document.getElementById("coSelectedPayMethod");

  if (hidden) {
    hidden.value = method;
  }
}

/* ============================================================
   RECORD PAYMENT
============================================================ */

async function recordPayment() {
  if (!coState.bookingId) {
    checkoutToast("Booking is not loaded.", "error");
    return;
  }

  const amount = parseFloat(document.getElementById("coPayAmount")?.value || 0);

  if (!amount || amount <= 0) {
    checkoutToast("Enter a valid payment amount.", "error");
    return;
  }

  /*
   * Never allow frontend payment greater
   * than the currently known balance.
   *
   * Backend should still validate this too.
   */
  if (coState.balanceDue > 0 && amount > coState.balanceDue + 0.01) {
    checkoutToast(
      `Payment cannot exceed ${checkoutFmt(coState.balanceDue)}.`,
      "error",
    );
    return;
  }

  const method =
    document.getElementById("coSelectedPayMethod")?.value || "cash";

  const reference = document.getElementById("coPayRef")?.value.trim() || "";

  const note = document.getElementById("coPayNote")?.value.trim() || "";

  const button = document.getElementById("confirmPayBtn");

  const originalHtml = button ? button.innerHTML : "";

  checkoutSetLoading(button, true, originalHtml);

  try {
    const response = await fetch("/api/record-payment/", {
      method: "POST",

      headers: {
        "Content-Type": "application/json",

        "X-CSRFToken": checkoutGetCsrf(),

        "X-Requested-With": "XMLHttpRequest",
      },

      credentials: "same-origin",

      body: JSON.stringify({
        booking_id: coState.bookingId,
        amount: amount,
        method: method,
        payment_method: method,
        reference_number: reference,
        note: note,
      }),
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok || data.success === false) {
      throw new Error(data.error || data.message || "Payment failed.");
    }

    checkoutToast(`Payment of ${checkoutFmt(amount)} recorded.`);

    /*
     * IMPORTANT:
     * Do not manually calculate final totals.
     *
     * Reload them from Django because Django
     * is the source of truth.
     */

    await initFolio(coState.bookingId);

    /*
     * Only move to receipt when payment
     * has actually settled the folio.
     */

    if (coState.balanceDue <= 0.01) {
      setTimeout(() => {
        goToCoStep(3);
      }, 300);
    } else {
      checkoutToast(`${checkoutFmt(coState.balanceDue)} still due.`, "info");
    }
  } catch (error) {
    console.error("Payment error:", error);

    checkoutToast(error.message || "Unable to record payment.", "error");
  } finally {
    checkoutSetLoading(button, false, originalHtml);
  }
}


/* ============================================================
   RECEIPT PREVIEW
============================================================ */

function buildReceiptPreview() {
  setCheckoutText("rcGuestName", coState.guestName || "—");

  setCheckoutText(
    "rcRoom",
    (coState.roomType || "") +
      (coState.roomNumber ? ` · Room ${coState.roomNumber}` : ""),
  );

  setCheckoutText(
    "rcDate",
    new Date().toLocaleDateString("en-IN", {
      day: "2-digit",

      month: "short",

      year: "numeric",
    }),
  );

  const discount = parseFloat(
    document.getElementById("invoiceDiscount")?.value || 0,
  );

  const subtotal = coState.charges.reduce((sum, charge) => {
    return sum + parseFloat(charge.amount || 0);
  }, 0);

  const tax = coState.charges.reduce((sum, charge) => {
    return sum + parseFloat(charge.tax_amount || 0);
  }, 0);

  const grandTotal = Math.max(0, subtotal + tax - discount);

  const balance = Math.max(0, grandTotal - coState.totalPaid);

  setCheckoutText("rcSubtotal", checkoutFmt(subtotal));

  setCheckoutText("rcTax", checkoutFmt(tax));

  setCheckoutText("rcDiscount", discount > 0 ? checkoutFmt(discount) : "—");

  setCheckoutText("rcGrandTotal", checkoutFmt(grandTotal));

  setCheckoutText("rcPaid", checkoutFmt(coState.totalPaid));

  setCheckoutText("rcBalance", checkoutFmt(balance));

  const chargesBody = document.getElementById("rcChargesBody");

  if (chargesBody) {
    if (!coState.charges.length) {
      chargesBody.innerHTML = `
                <div
                    class="receipt-row"
                    style="
                        color:var(--text-3);
                    "
                >
                    <span>No charges</span>
                    <span>—</span>
                </div>
            `;
    } else {
      chargesBody.innerHTML = coState.charges
        .map(
          (charge) => `
                            <div class="receipt-row">

                                <span>
                                    ${checkoutEscapeHtml(
                                      charge.description || "Charge",
                                    )}
                                </span>

                                <span>
                                    ${checkoutFmt(
                                      charge.total ??
                                        parseFloat(charge.amount || 0) +
                                          parseFloat(charge.tax_amount || 0),
                                    )}
                                </span>

                            </div>
                        `,
        )
        .join("");
    }
  }

  const invoiceNotes = document.getElementById("invoiceNotes")?.value.trim();

  setCheckoutText("rcNotes", invoiceNotes || "Thank you for your stay!");
}

/* ============================================================
   GENERATE INVOICE + COMPLETE CHECKOUT
============================================================ */

async function generateAndCheckout() {
  if (!coState.bookingId) {
    checkoutToast("Booking is not loaded.", "error");
    return;
  }

  const button = document.getElementById("generateInvoiceBtn");

  const originalHtml = button ? button.innerHTML : "";

  checkoutSetLoading(button, true, originalHtml);

  try {
    /*
     * -------------------------------------------------
     * 1. Reload bill immediately before checkout
     * -------------------------------------------------
     *
     * This prevents checkout using stale balance data.
     */

    await initFolio(coState.bookingId);

    /*
     * -------------------------------------------------
     * 2. Make sure balance is settled
     * -------------------------------------------------
     */

    if (coState.balanceDue > 0.01) {
      goToCoStep(2);

      throw new Error(
        `Balance due is ${checkoutFmt(
          coState.balanceDue,
        )}. Complete payment before checkout.`,
      );
    }

    /*
     * -------------------------------------------------
     * 3. Complete checkout
     * -------------------------------------------------
     */

    const paymentMethod =
      document.getElementById("coSelectedPayMethod")?.value || "cash";

    const checkoutResponse = await fetch("/api/check-out/", {
      method: "POST",

      headers: {
        "Content-Type": "application/json",

        "X-CSRFToken": checkoutGetCsrf(),

        "X-Requested-With": "XMLHttpRequest",
      },

      credentials: "same-origin",

      body: JSON.stringify({
        booking_id: coState.bookingId,

        payment_method: paymentMethod,

        method: paymentMethod,
      }),
    });

    const checkoutData = await checkoutResponse.json().catch(() => ({}));

    if (!checkoutResponse.ok || checkoutData.success === false) {
      throw new Error(
        checkoutData.error || checkoutData.message || "Check-out failed.",
      );
    }

    /*
     * -------------------------------------------------
     * 4. Success
     * -------------------------------------------------
     */

    checkoutToast(
      checkoutData.message || `${coState.guestName} checked out successfully.`,
    );

    checkoutCloseModal("checkoutBillingModal");

    /*
     * Backend already:
     *
     * - marks booking checked_out
     * - closes folio
     * - marks room Dirty
     * - creates housekeeping task
     *
     * Therefore no old housekeeping popup is needed.
     */

    setTimeout(() => {
      window.location.reload();
    }, 1000);
  } catch (error) {
    console.error("Checkout error:", error);

    checkoutToast(error.message || "Unable to complete checkout.", "error");
  } finally {
    checkoutSetLoading(button, false, originalHtml);
  }
}

/* ============================================================
   CLOSE MODALS WITH BACKDROP CLICK
============================================================ */

document.addEventListener("click", function (event) {
  const selector = document.getElementById("dashboardCheckoutSelector");

  if (selector && event.target === selector) {
    closeDashboardCheckout();
  }

  const checkoutModal = document.getElementById("checkoutBillingModal");

  if (checkoutModal && event.target === checkoutModal) {
    checkoutCloseModal("checkoutBillingModal");
  }
});

/* ============================================================
   ESC KEY
============================================================ */

document.addEventListener("keydown", function (event) {
  if (event.key !== "Escape") {
    return;
  }

  const selector = document.getElementById("dashboardCheckoutSelector");

  if (selector && selector.style.display !== "none") {
    closeDashboardCheckout();
  }

  const checkoutModal = document.getElementById("checkoutBillingModal");

  if (checkoutModal && checkoutModal.style.display !== "none") {
    checkoutCloseModal("checkoutBillingModal");
  }
});

/* ============================================================
   EXPOSE FUNCTIONS USED BY HTML onclick=""
============================================================ */

window.openDashboardCheckout = openDashboardCheckout;

window.closeDashboardCheckout = closeDashboardCheckout;

window.startCheckout = startCheckout;

window.switchChargeTab = switchChargeTab;

window.quickAddCharge = quickAddCharge;

window.showCustomCharge = showCustomCharge;

window.hideCustomCharge = hideCustomCharge;

window.addCustomCharge = addCustomCharge;

window.deleteCharge = deleteCharge;

window.goToCoStep = goToCoStep;

window.nextCoStep = nextCoStep;

window.prevCoStep = prevCoStep;

window.selectPayMethod = selectPayMethod;

window.recordPayment = recordPayment;

window.buildReceiptPreview = buildReceiptPreview;

window.generateAndCheckout = generateAndCheckout;

window.checkoutCloseModal = checkoutCloseModal;

/* =========================================================
   HR SHIFT MANAGEMENT
========================================================= */

let shiftWeekOffset = 0;
let shiftView = "calendar";
let shiftFilter = "all";

let weeklyShifts = [];
let allShifts = [];

let shiftDetailId = null;
let shiftModalType = "";

const SHIFT_CONFIG = window.SHIFT_CONFIG || {};
const SHIFT_URLS = SHIFT_CONFIG.urls || {};
const SHIFT_EMPLOYEES = SHIFT_CONFIG.employees || [];
const SHIFT_DEPARTMENTS = SHIFT_CONFIG.departments || [];

// const SHIFT_TIMES = {
//   Morning: {
//     start: "06:00",
//     end: "14:00",
//   },

//   Evening: {
//     start: "14:00",
//     end: "22:00",
//   },

//   Night: {
//     start: "22:00",
//     end: "06:00",
//   },
// };

const DAYS_SHORT = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

const MONTHS_SHORT = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

/* =========================================================
   CSRF
========================================================= */

function getShiftCookie(name) {
  let cookieValue = null;

  if (document.cookie && document.cookie !== "") {
    const cookies = document.cookie.split(";");

    for (let cookie of cookies) {
      cookie = cookie.trim();

      if (cookie.substring(0, name.length + 1) === name + "=") {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));

        break;
      }
    }
  }

  return cookieValue;
}

/* =========================================================
   API
========================================================= */

async function shiftFetch(url, options = {}) {
  if (!url) {
    throw new Error("Shift API URL is missing.");
  }

  const config = {
    credentials: "same-origin",
    ...options,
  };

  config.headers = {
    "X-Requested-With": "XMLHttpRequest",
    ...(config.headers || {}),
  };

  if (config.method && config.method.toUpperCase() !== "GET") {
    config.headers["X-CSRFToken"] = getShiftCookie("csrftoken");
  }

  const response = await fetch(url, config);

  let data = {};

  try {
    data = await response.json();
  } catch (error) {
    data = {};
  }

  if (!response.ok) {
    throw new Error(
      data.error || data.message || `Request failed: ${response.status}`,
    );
  }

  return data;
}

async function shiftPost(url, payload = {}) {
  return shiftFetch(url, {
    method: "POST",

    headers: {
      "Content-Type": "application/json",
    },

    body: JSON.stringify(payload),
  });
}

/* =========================================================
   HTML ESCAPE
========================================================= */

function escapeShiftHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

/* =========================================================
   DATE HELPERS
========================================================= */

function shiftDateToString(date) {
  const year = date.getFullYear();

  const month = String(date.getMonth() + 1).padStart(2, "0");

  const day = String(date.getDate()).padStart(2, "0");

  return `${year}-${month}-${day}`;
}

function getShiftWeekDates() {
  const now = new Date();

  const currentDay = now.getDay();

  const mondayDifference = currentDay === 0 ? -6 : 1 - currentDay;

  const monday = new Date(now);

  monday.setHours(12, 0, 0, 0);

  monday.setDate(now.getDate() + mondayDifference + shiftWeekOffset * 7);

  const result = [];

  for (let i = 0; i < 7; i++) {
    const current = new Date(monday);

    current.setDate(monday.getDate() + i);

    result.push(shiftDateToString(current));
  }

  return result;
}

function formatShiftDate(dateString) {
  if (!dateString) {
    return "";
  }

  const date = new Date(dateString + "T12:00:00");

  return date.getDate() + " " + MONTHS_SHORT[date.getMonth()];
}

function isShiftToday(dateString) {
  return dateString === shiftDateToString(new Date());
}

/* =========================================================
   WEEK NAVIGATION
========================================================= */

function changeShiftWeek(direction) {
  shiftWeekOffset += direction;

  loadShiftWeekly();
}

function resetShiftWeek() {
  shiftWeekOffset = 0;

  loadShiftWeekly();
}

/* =========================================================
   VIEW SWITCH
========================================================= */

function setShiftView(view, button) {
  shiftView = view;

  document.querySelectorAll(".shift-view-btn").forEach((btn) => {
    btn.classList.remove("active");
  });

  if (button) {
    button.classList.add("active");
  }

  const calendar = document.getElementById("shiftCalendarView");

  const list = document.getElementById("shiftListView");

  if (calendar) {
    calendar.style.display = view === "calendar" ? "" : "none";
  }

  if (list) {
    list.style.display = view === "list" ? "" : "none";
  }

  renderShiftView();
}

/* =========================================================
   FILTERS
========================================================= */

function setShiftFilter(filter, button) {
  shiftFilter = filter;

  document.querySelectorAll(".shift-filter-chip").forEach((btn) => {
    btn.classList.remove("active");
  });

  if (button) {
    button.classList.add("active");
  }

  renderShiftView();
}

function resetShiftFilters() {
  shiftFilter = "all";

  document.querySelectorAll(".shift-filter-chip").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.filter === "all");
  });

  const department = document.getElementById("shiftDeptFilterSel");

  const employee = document.getElementById("shiftEmpFilterSel");

  if (department) {
    department.value = "";
  }

  if (employee) {
    employee.value = "";
  }

  renderShiftView();
}

function applyShiftFilters(list) {
  const department = document.getElementById("shiftDeptFilterSel")?.value || "";

  const employee = document.getElementById("shiftEmpFilterSel")?.value || "";

  return (list || []).filter((shift) => {
    if (shiftFilter !== "all" && shift.shift !== shiftFilter) {
      return false;
    }

    if (department) {
      const shiftDepartment = String(
        shift.department_id ?? shift.departmentId ?? shift.department ?? "",
      );

      const departmentObject = SHIFT_DEPARTMENTS.find(
        (item) => String(item.id) === String(department),
      );

      const allowed = [
        String(department),
        String(departmentObject?.name || ""),
      ];

      if (!allowed.includes(shiftDepartment)) {
        return false;
      }
    }

    if (
      employee &&
      String(shift.staff_id ?? shift.employee_id ?? "") !== String(employee)
    ) {
      return false;
    }

    return true;
  });
}

/* =========================================================
   NORMALIZE SHIFT
========================================================= */

function normalizeShift(shift, date = null) {
  return {
    ...shift,

    id: shift.id ?? shift.shift_id,

    staff_id: shift.staff_id ?? shift.employee_id ?? shift.staff?.id,

    staff:
      shift.staff_name ??
      shift.employee_name ??
      shift.staff?.name ??
      shift.staff ??
      shift.employee ??
      "",

    department:
      shift.department_name ?? shift.department?.name ?? shift.department ?? "",

    department_id: shift.department_id ?? shift.department?.id ?? null,

    shift: shift.shift ?? shift.shift_type ?? shift.type ?? "",

    date: shift.date ?? shift.shift_date ?? date ?? "",

    custom_name: shift.custom_name ?? shift.name ?? "",

    custom_start: shift.custom_start ?? shift.start_time ?? "",

    custom_end: shift.custom_end ?? shift.end_time ?? "",

    custom_color: shift.custom_color ?? shift.color ?? "",
  };
}

/* =========================================================
   WEEKLY SCHEDULE
========================================================= */

async function loadShiftWeekly() {
  const dates = getShiftWeekDates();

  const label = document.getElementById("shiftWeekRangeLabel");

  if (label) {
    label.textContent =
      `${formatShiftDate(dates[0])} – ` + `${formatShiftDate(dates[6])}`;
  }

  try {
    const separator = SHIFT_URLS.weeklySchedule.includes("?") ? "&" : "?";

    const response = await shiftFetch(
      SHIFT_URLS.weeklySchedule +
        separator +
        "start_date=" +
        encodeURIComponent(dates[0]),
    );

    const raw = response.schedule ?? response.data ?? response;

    weeklyShifts = [];

    if (Array.isArray(raw)) {
      weeklyShifts = raw.map((item) => normalizeShift(item));
    } else {
      Object.keys(raw || {}).forEach((dateString) => {
        const items = raw[dateString] || [];

        if (!Array.isArray(items)) {
          return;
        }

        items.forEach((item) => {
          weeklyShifts.push(normalizeShift(item, dateString));
        });
      });
    }

    updateShiftKPIs();

    populateShiftFilters();

    renderShiftView();
  } catch (error) {
    console.error("Weekly schedule error:", error);

    const grid = document.getElementById("shiftCalendarGrid");

    if (grid) {
      grid.innerHTML = `
                <div class="shift-loading">
                    Unable to load schedule.
                    <br>
                    <small>
                        ${escapeShiftHtml(error.message)}
                    </small>
                </div>
            `;
    }
  }
}

/* =========================================================
   ALL SHIFTS
========================================================= */

async function loadShifts() {
  try {
    const response = await shiftFetch(SHIFT_URLS.getShifts);

    const list = Array.isArray(response)
      ? response
      : (response.shifts ?? response.data ?? []);

    allShifts = list.map((item) => normalizeShift(item));

    if (shiftView === "list") {
      renderShiftTable(applyShiftFilters(allShifts));
    }
  } catch (error) {
    console.error("Shift list error:", error);

    const tbody = document.getElementById("shift-tbody");

    if (tbody) {
      tbody.innerHTML = `
                <tr>
                    <td colspan="6"
                        style="
                            text-align:center;
                            padding:30px;
                        "
                    >
                        Unable to load shifts.
                    </td>
                </tr>
            `;
    }
  }
}

/* =========================================================
   KPI
========================================================= */

function updateShiftKPIs() {
  const setValue = (id, value) => {
    const element = document.getElementById(id);

    if (element) {
      element.textContent = value;
    }
  };

  setValue("shiftKpi-total", weeklyShifts.length);

  setValue(
    "shiftKpi-morning",
    weeklyShifts.filter((shift) => shift.shift === "Morning").length,
  );

  setValue(
    "shiftKpi-evening",
    weeklyShifts.filter((shift) => shift.shift === "Evening").length,
  );

  setValue(
    "shiftKpi-night",
    weeklyShifts.filter((shift) => shift.shift === "Night").length,
  );
}

/* =========================================================
   FILTER OPTIONS
========================================================= */

function populateShiftFilters() {
  const departmentSelect = document.getElementById("shiftDeptFilterSel");

  const employeeSelect = document.getElementById("shiftEmpFilterSel");

  if (departmentSelect) {
    const selected = departmentSelect.value;

    departmentSelect.innerHTML =
      `<option value="">
                All Departments
            </option>` +
      SHIFT_DEPARTMENTS.map(
        (department) => `
                    <option
                        value="${escapeShiftHtml(department.id)}"
                    >
                        ${escapeShiftHtml(department.name)}
                    </option>
                `,
      ).join("");

    departmentSelect.value = selected;
  }

  if (employeeSelect) {
    const selected = employeeSelect.value;

    employeeSelect.innerHTML =
      `<option value="">
                All Employees
            </option>` +
      SHIFT_EMPLOYEES.map(
        (employee) => `
                    <option
                        value="${escapeShiftHtml(employee.id)}"
                    >
                        ${escapeShiftHtml(employee.name)}
                    </option>
                `,
      ).join("");

    employeeSelect.value = selected;
  }
}

/* =========================================================
   EMPLOYEE SELECT
========================================================= */

function populateShiftEmployeeSelect() {
  const select = document.getElementById("shiftStaff");

  if (!select) {
    return;
  }

  select.innerHTML = `<option value="">
            Select employee
        </option>`;

  SHIFT_EMPLOYEES.forEach((employee) => {
    const option = document.createElement("option");

    option.value = employee.id;

    option.textContent = employee.department
      ? `${employee.name} — ${employee.department}`
      : employee.name;

    select.appendChild(option);
  });
}

/* =========================================================
   RENDER CURRENT VIEW
========================================================= */

function renderShiftView() {
  if (shiftView === "calendar") {
    renderShiftCalendar();
  } else {
    renderShiftTable(applyShiftFilters(allShifts));
  }
}

/* =========================================================
   CALENDAR
========================================================= */

function renderShiftCalendar() {
  const container = document.getElementById("shiftCalendarGrid");

  if (!container) {
    return;
  }

  const dates = getShiftWeekDates();

  const filtered = applyShiftFilters(weeklyShifts);

  container.innerHTML = `
        <div class="shift-week-grid">

            ${dates
              .map((dateString) => {
                const date = new Date(dateString + "T12:00:00");

                const shifts = filtered.filter(
                  (shift) => shift.date === dateString,
                );

                return `
                    <div class="
                        shift-day-column
                        ${isShiftToday(dateString) ? "today" : ""}
                    ">

                        <div class="shift-day-header">

                            <div class="shift-day-name">
                                ${DAYS_SHORT[date.getDay()]}
                            </div>

                            <div class="shift-day-date">
                                ${date.getDate()}
                            </div>

                        </div>

                        <div class="shift-day-body">

                            ${
                              shifts.length
                                ? shifts.map(renderShiftCalendarItem).join("")
                                : `
                                    <div
                                        style="
                                            padding:20px 5px;
                                            text-align:center;
                                            color:#cbd5e1;
                                            font-size:11px;
                                        "
                                    >
                                        No shifts
                                    </div>
                                `
                            }

                        </div>

                    </div>
                `;
              })
              .join("")}

        </div>
    `;
}

function renderShiftCalendarItem(shift) {
  return `
        <div
            class="shift-item"
            onclick="
                openShiftDetail(
                    ${Number(shift.id)}
                )
            "
        >

            <div class="shift-item-name">
                ${escapeShiftHtml(shift.staff || "Employee")}
            </div>

            <div class="shift-item-dept">
                ${escapeShiftHtml(shift.department || "")}
            </div>

            <div style="margin-top:7px;">

                <span class="
                    sh-badge
                    ${getShiftBadgeClass(shift.shift)}
                ">
                    ${escapeShiftHtml(getShiftLabel(shift))}
                </span>

            </div>

            <div class="shift-item-time">
                ${escapeShiftHtml(getShiftTime(shift))}
            </div>

        </div>
    `;
}

/* =========================================================
   LIST
========================================================= */

function renderShiftTable(list) {
  const tbody = document.getElementById("shift-tbody");

  if (!tbody) {
    return;
  }

  if (!list.length) {
    tbody.innerHTML = `
            <tr>
                <td
                    colspan="6"
                    style="
                        text-align:center;
                        padding:30px;
                        color:#94a3b8;
                    "
                >
                    No shifts assigned
                </td>
            </tr>
        `;

    return;
  }

  tbody.innerHTML = list
    .map(
      (shift) => `

            <tr>

                <td>
                    <strong>
                        ${escapeShiftHtml(shift.staff || "—")}
                    </strong>
                </td>

                <td>
                    ${escapeShiftHtml(shift.department || "—")}
                </td>

                <td>

                    <span class="
                        sh-badge
                        ${getShiftBadgeClass(shift.shift)}
                    ">
                        ${escapeShiftHtml(getShiftLabel(shift))}
                    </span>

                </td>

                <td>
                    ${escapeShiftHtml(getShiftTime(shift))}
                </td>

                <td>
                    ${escapeShiftHtml(shift.date || "—")}
                </td>

                <td>

                    <button
                        type="button"
                        class="shift-icon-btn"
                        onclick="
                            openShiftDetail(
                                ${Number(shift.id)}
                            )
                        "
                    >
                        <i class="fas fa-eye"></i>
                    </button>

                </td>

            </tr>

        `,
    )
    .join("");
}

function filterShiftTable() {
  const query = (
    document.getElementById("shiftTableSearch")?.value || ""
  ).toLowerCase();

  document.querySelectorAll("#shift-tbody tr").forEach((row) => {
    row.style.display = row.textContent.toLowerCase().includes(query)
      ? ""
      : "none";
  });
}

/* =========================================================
   SHIFT HELPERS
========================================================= */

function getShiftLabel(shift) {
  if (shift.shift === "Custom") {
    return shift.custom_name || "Custom";
  }

  return shift.shift || "—";
}

function getShiftTime(shift) {
  if (shift.shift === "Custom") {
    return `${shift.custom_start || shift.start_time || ""} – ${
      shift.custom_end || shift.end_time || ""
    }`;
  }

  if (shift.start_time && shift.end_time) {
    return `${shift.start_time} – ${shift.end_time}`;
  }

  return "—";
}

function getShiftBadgeClass(type) {
  const classes = {
    Morning: "sh-badge-morning",

    Evening: "sh-badge-evening",

    Night: "sh-badge-night",

    Custom: "sh-badge-custom",
  };

  return classes[type] || "sh-badge-custom";
}

/* =========================================================
   ASSIGN MODAL
========================================================= */

function openShiftModal() {
  const modal = document.getElementById("addShiftModal");

  if (!modal) {
    return;
  }

  resetShiftForm();

  const today = shiftDateToString(new Date());

  const fromDate = document.getElementById("shiftFromDate");

  const toDate = document.getElementById("shiftToDate");

  if (fromDate) {
    fromDate.value = today;
  }

  if (toDate) {
    toDate.value = today;
  }

  modal.classList.add("open");

  document.body.style.overflow = "hidden";
}

function closeShiftModal(id) {
  const modal = document.getElementById(id);

  if (modal) {
    modal.classList.remove("open");
  }

  document.body.style.overflow = "";
}

function resetShiftForm() {
  shiftModalType = "";

  const staff = document.getElementById("shiftStaff");

  const type = document.getElementById("shiftType");

  const customName = document.getElementById("customShiftName");

  if (staff) {
    staff.value = "";
  }

  if (type) {
    type.value = "";
  }

  if (customName) {
    customName.value = "";
  }

  document.querySelectorAll(".shift-type-btn-modal").forEach((button) => {
    button.classList.remove(
      "stm-morning-sel",
      "stm-evening-sel",
      "stm-night-sel",
      "stm-custom-sel",
    );
  });

  const custom = document.getElementById("customShiftBuilder");

  if (custom) {
    custom.style.display = "none";
  }
}

/* =========================================================
   SHIFT TYPE
========================================================= */

function selectModalShiftType(type, button) {
  shiftModalType = type;

  document.querySelectorAll(".shift-type-btn-modal").forEach((btn) => {
    btn.classList.remove(
      "stm-morning-sel",
      "stm-evening-sel",
      "stm-night-sel",
      "stm-custom-sel",
    );
  });

  const classMap = {
    Morning: "stm-morning-sel",

    Evening: "stm-evening-sel",

    Night: "stm-night-sel",

    Custom: "stm-custom-sel",
  };

  if (button) {
    button.classList.add(classMap[type]);
  }

  const typeInput = document.getElementById("shiftType");

  if (typeInput) {
    typeInput.value = type;
  }

  const builder = document.getElementById("customShiftBuilder");

  if (builder) {
    builder.style.display = type === "Custom" ? "block" : "none";
  }
}

/* =========================================================
   CUSTOM SHIFT TIME
========================================================= */

function minutesToTime(minutes) {
  minutes = Number(minutes) || 0;

  const hours = Math.floor(minutes / 60) % 24;

  const mins = minutes % 60;

  return String(hours).padStart(2, "0") + ":" + String(mins).padStart(2, "0");
}

function updateShiftTime(which, value) {
  const display = document.getElementById(`${which}TimeDisplay`);

  if (display) {
    display.textContent = minutesToTime(parseInt(value));
  }

  updateCustomDuration();
}

function updateCustomDuration() {
  const startElement = document.getElementById("startTimeRange");

  const endElement = document.getElementById("endTimeRange");

  if (!startElement || !endElement) {
    return;
  }

  const start = parseInt(startElement.value);

  const end = parseInt(endElement.value);

  let minutes = (end - start + 1440) % 1440;

  if (minutes === 0) {
    minutes = 1440;
  }

  const hours = minutes / 60;

  const badge = document.getElementById("customDurationBadge");

  if (badge) {
    badge.textContent = `Duration: ${hours}h`;
  }
}

/* =========================================================
   DATE RANGE
========================================================= */

function getDatesBetween(fromDate, toDate) {
  const result = [];

  const start = new Date(fromDate + "T12:00:00");

  const end = new Date(toDate + "T12:00:00");

  while (start <= end) {
    result.push(shiftDateToString(start));

    start.setDate(start.getDate() + 1);
  }

  return result;
}

/* =========================================================
   ASSIGN SHIFT
========================================================= */

async function submitShift() {
  const staffId = document.getElementById("shiftStaff")?.value;

  const fromDate = document.getElementById("shiftFromDate")?.value;

  const toDate = document.getElementById("shiftToDate")?.value;

  const type = document.getElementById("shiftType")?.value;

  if (!staffId) {
    alert("Please select an employee.");

    return;
  }

  if (!type) {
    alert("Please select a shift type.");

    return;
  }

  if (!fromDate) {
    alert("Please select From Date.");

    return;
  }

  if (!toDate) {
    alert("Please select To Date.");

    return;
  }

  if (toDate < fromDate) {
    alert("To Date cannot be before From Date.");

    return;
  }

  let customName = "";
  let customStart = "";
  let customEnd = "";
  let customColor = "";

  if (type === "Custom") {
    customName = document.getElementById("customShiftName")?.value.trim() || "";

    customStart =
      document.getElementById("startTimeDisplay")?.textContent.trim() || "";

    customEnd =
      document.getElementById("endTimeDisplay")?.textContent.trim() || "";

    customColor = document.getElementById("customShiftColor")?.value || "";

    if (!customName) {
      alert("Enter a custom shift name.");

      return;
    }
  }

  const dates = getDatesBetween(fromDate, toDate);

  if (!dates.length) {
    return;
  }

  const button = document.querySelector("#addShiftModal .shift-primary-btn");

  const oldHTML = button?.innerHTML;

  try {
    if (button) {
      button.disabled = true;

      button.innerHTML = `
                <i class="fas fa-spinner fa-spin"></i>
                Assigning...
            `;
    }

    for (const date of dates) {
      const payload = {
        staff_id: staffId,
        shift: type,
        date: date,
      };

      if (type === "Custom") {
        payload.custom_name = customName;

        payload.custom_start = customStart;

        payload.custom_end = customEnd;

        payload.custom_color = customColor;
      }

      const response = await shiftPost(SHIFT_URLS.assignShift, payload);

      if (response && response.success === false) {
        throw new Error(
          response.error || `Unable to assign shift for ${date}.`,
        );
      }
    }

    closeShiftModal("addShiftModal");

    await refreshShiftPage();
  } catch (error) {
    console.error(error);

    alert(error.message || "Unable to assign shift.");
  } finally {
    if (button) {
      button.disabled = false;

      button.innerHTML =
        oldHTML ||
        `
                    <i class="fas fa-check"></i>
                    Assign Shift
                `;
    }
  }
}

/* =========================================================
   FIND SHIFT
========================================================= */

function findShift(id) {
  return (
    weeklyShifts.find((shift) => Number(shift.id) === Number(id)) ||
    allShifts.find((shift) => Number(shift.id) === Number(id))
  );
}

/* =========================================================
   DETAILS
========================================================= */

function openShiftDetail(id) {
  const shift = findShift(id);

  if (!shift) {
    return;
  }

  shiftDetailId = shift.id;

  const subtitle = document.getElementById("sdModalSub");

  if (subtitle) {
    subtitle.textContent = `${shift.staff || "—"} · ` + `${shift.date || "—"}`;
  }

  const body = document.getElementById("sdModalBody");

  if (body) {
    body.innerHTML = `

            <div style="
                display:grid;
                gap:9px;
            ">

                ${shiftDetailRow("Employee", shift.staff)}

                ${shiftDetailRow("Department", shift.department)}

                ${shiftDetailRow("Shift", getShiftLabel(shift))}

                ${shiftDetailRow("Time", getShiftTime(shift))}

                ${shiftDetailRow("Date", shift.date)}

            </div>
        `;
  }

  const modal = document.getElementById("shiftDetailModal");

  if (modal) {
    modal.classList.add("open");

    document.body.style.overflow = "hidden";
  }
}

function shiftDetailRow(label, value) {
  return `
        <div class="shift-detail-row">

            <span>
                ${escapeShiftHtml(label)}
            </span>

            <strong>
                ${escapeShiftHtml(value || "—")}
            </strong>

        </div>
    `;
}

/* =========================================================
   DELETE SHIFT
========================================================= */

async function removeShiftFromDetail() {
  if (!shiftDetailId) {
    return;
  }

  if (!confirm("Remove this shift assignment?")) {
    return;
  }

  try {
    const response = await shiftPost(SHIFT_URLS.deleteShift, {
      shift_id: shiftDetailId,
    });

    if (response && response.success === false) {
      throw new Error(response.error || "Unable to remove shift.");
    }

    closeShiftModal("shiftDetailModal");

    shiftDetailId = null;

    await refreshShiftPage();
  } catch (error) {
    console.error(error);

    alert(error.message || "Unable to remove shift.");
  }
}

/* =========================================================
   REFRESH
========================================================= */

async function refreshShiftPage() {
  await Promise.allSettled([loadShiftWeekly(), loadShifts()]);
}

/* =========================================================
   TIMING / TEMPLATE AREA
========================================================= */

async function openShiftSettings() {
  const wrap = document.getElementById("shiftTemplatesWrap");

  if (!wrap) {
    return;
  }

  const currentlyVisible = wrap.style.display !== "none";

  if (currentlyVisible) {
    wrap.style.display = "none";

    return;
  }

  wrap.style.display = "";

  await loadShiftTemplates();

  wrap.scrollIntoView({
    behavior: "smooth",
    block: "start",
  });
}

async function loadShiftTemplates() {
  const grid = document.getElementById("shiftTemplatesGrid");

  if (!grid) {
    return;
  }

  grid.innerHTML = `
        <div class="shift-loading">
            <i class="fas fa-spinner fa-spin"></i>
            Loading timings...
        </div>
    `;

  try {
    const response = await shiftFetch(SHIFT_URLS.getTemplates);

    const rawTemplates = Array.isArray(response)
      ? response
      : (response.templates ?? response.data ?? {});

    const templates = Array.isArray(rawTemplates)
      ? rawTemplates
      : Object.values(rawTemplates);

    if (!templates.length) {
      grid.innerHTML = `
                <div class="shift-loading">
                    No custom shift templates found.
                </div>
            `;

      return;
    }

    grid.innerHTML = templates
      .map((template) => {
        const name =
          template.name ??
          template.shift_name ??
          template.title ??
          "Custom Shift";

        const start = template.start_time ?? template.start ?? "";

        const end = template.end_time ?? template.end ?? "";

        return `
                        <div class="shift-template-card">

                            <strong>
                                ${escapeShiftHtml(name)}
                            </strong>

                            <div>
                                ${escapeShiftHtml(start)}
                                –
                                ${escapeShiftHtml(end)}
                            </div>

                        </div>
                    `;
      })
      .join("");
  } catch (error) {
    console.error("Template error:", error);

    grid.innerHTML = `
            <div class="shift-loading">
                Unable to load shift timings.
            </div>
        `;
  }
}

/* =========================================================
   ESC CLOSE
========================================================= */

document.addEventListener("keydown", function (event) {
  if (event.key !== "Escape") {
    return;
  }

  document.querySelectorAll(".shift-modal-backdrop.open").forEach((modal) => {
    modal.classList.remove("open");
  });

  document.body.style.overflow = "";
});

/* =========================================================
   INITIALIZATION
========================================================= */

document.addEventListener("DOMContentLoaded", async function () {
  populateShiftEmployeeSelect();

  populateShiftFilters();

  updateCustomDuration();

  await Promise.allSettled([loadShiftWeekly(), loadShifts()]);
});

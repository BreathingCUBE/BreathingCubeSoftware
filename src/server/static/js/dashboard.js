import { mountGlowingCube } from './cube.js';

// --- CONFIGURATION ---
const API_BASE = "";

const PALETTE = [
    "#ffaa00ff", "#d65200ff", "#ff69b4ff",
    "#ff92f0ff", "#ff00ffff", "#6f00d6ff",
    "#0000ffff", "#60ffffff", "#00ff00ff"
];

// --- STATE ---
let totalSeconds = 600;
let isRunning = false;
let cubeAPI = null;
let evtSource = null;
let reconnectAttempts = 0;
const MAX_RECONNECT = 5;
let currentColor = "#ffaa00ff"; // NEW: Track color for API saves
let hasUnsavedChanges = false;
// --- DOM ELEMENTS ---
const timerDisplay = document.getElementById('timer-display');
const breathingBtn = document.getElementById('breathingBtn');
const cubeContainer = document.getElementById('cube-wrapper');
const colorMenu = document.getElementById('color-menu');
const colorTrigger = document.getElementById('color-trigger');

// NEW: Elements for Task Management
const taskSelect = document.getElementById("taskSelect");
const newTaskForm = document.getElementById("new-task-form");
const newTaskInput = document.getElementById("newTaskInput");
const saveNewTaskBtn = document.getElementById("saveNewTaskBtn");
const cancelNewTaskBtn = document.getElementById("cancelNewTaskBtn");
const saveTimerBtn = document.getElementById("saveTimerBtn");


// ======================================================
// 1. SERVER-SENT TIMER STREAM
// ======================================================

function closeTimerStream() {
    if (evtSource) {
        evtSource.close();
        evtSource = null;
    }
}

function connectTimerStream() {
    if (!timerDisplay) return;

    closeTimerStream();

    evtSource = new EventSource("/task/timer");

    evtSource.onopen = () => {
        reconnectAttempts = 0;
        timerDisplay.classList.remove('stream-error');
    };

    evtSource.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);

            // Do not overwrite while user is editing OR has unsaved changes
            if (!timerDisplay.classList.contains('editing') && !hasUnsavedChanges) {
                timerDisplay.innerText = data.display_mmss;
            }

            // Optional visual overtime indicator
            if (data.mode === "overtime") {
                timerDisplay.classList.add("overtime");
            } else {
                timerDisplay.classList.remove("overtime");
            }

        } catch (err) {
            console.error("Failed to parse timer stream:", err);
        }
    };

    evtSource.onerror = () => {
        console.error("Timer stream connection error");

        if (reconnectAttempts < MAX_RECONNECT) {
            reconnectAttempts += 1;
            closeTimerStream();
            setTimeout(connectTimerStream, 1000 * reconnectAttempts);
            timerDisplay.classList.add('stream-error');
            timerDisplay.innerText = "Reconnecting...";
        } else {
            timerDisplay.classList.add('stream-error');
            timerDisplay.innerText = "Timer unavailable";
        }
    };
}


async function syncCurrentTask() {
  if (!taskSelect) return;
  try {
    const res = await fetch(`${API_BASE}/task/current`);
    if (!res.ok) return;
    const data = await res.json();
    const current = data.current_task;

    if (current) {
      const option = [...taskSelect.options].find(opt => opt.value.toUpperCase() === current.toUpperCase());
      if (option) {
        taskSelect.value = option.value;
        await applyTaskPreset(option.value);
        return;
      }
    }

    // fallback: if no current_task, apply first real option (not create-new)
    const fallback = [...taskSelect.options].find(opt => opt.value && opt.value !== "new_task_trigger");
    if (fallback) {
      taskSelect.value = fallback.value;
      await applyTaskPreset(fallback.value);
      await setActiveTask(fallback.value);
    }
  } catch (err) {
    console.error("Failed to sync current task:", err);
  }
}

function displayToSeconds(display) {
    if (!display) return 0;
    const parts = display.split(':').map(Number);
    if (parts.length === 2) {
        return parts[0] * 60 + parts[1];
    }
    if (parts.length === 3) {
        return parts[0] * 3600 + parts[1] * 60 + parts[2];
    }
    return 0;
}

function rgbwToRgb(hexColor) {
    if (!hexColor) return '#ffffff';

    const h = hexColor.trim().toLowerCase();
    if (/^#[0-9a-f]{8}$/.test(h)) {
        return `#${h.slice(1, 7)}`;
    }
    if (/^#[0-9a-f]{6}$/.test(h)) {
        return h;
    }
    return '#ffffff';
}

async function setActiveTask(taskName) {
    if (!taskName || taskName === 'new_task_trigger') return;
    hasUnsavedChanges = false;

    try {
        closeTimerStream();
        const res = await fetch(`${API_BASE}/task/current`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ task_name: taskName })
        });

        if (!res.ok) {
            const data = await res.json().catch(() => ({}));
            console.error("Failed to set active task:", data);
            return;
        }

        timerDisplay.classList.remove('overtime');
        timerDisplay.classList.remove('stream-error');
        setTimeout(connectTimerStream, 150);

        await applyTaskPreset(taskName);
    } catch (err) {
        console.error("Error setting active task:", err);
    }
}


async function applyTaskPreset(taskName) {
    if (!taskName || taskName === 'new_task_trigger') return;

    try {
        const res = await fetch(`${API_BASE}/profile/preset/${encodeURIComponent(taskName)}`);
        if (!res.ok) return;

        const data = await res.json();
        const taskTime = Number(data.task_time || 0);
        const taskColor = data.task_color || currentColor;

        totalSeconds = taskTime;
        const mm = String(Math.floor(taskTime / 60)).padStart(2, '0');
        const ss = String(taskTime % 60).padStart(2, '0');
        timerDisplay.innerText = `${mm}:${ss}`;

        currentColor = taskColor;
        const cssColor = rgbwToRgb(taskColor);
        if (colorTrigger) colorTrigger.style.backgroundColor = cssColor;
        if (cubeAPI) cubeAPI.setColor(taskColor);

        return data;
    } catch (err) {
        console.error('Failed to apply task preset:', err);
    }
}

// ======================================================
// 2. EDIT INPUT (ATM / MICROWAVE STYLE)
// ======================================================

if (timerDisplay) {
    timerDisplay.style.cursor = "pointer";
    timerDisplay.style.position = "relative";

    timerDisplay.onclick = function() {
        if (this.classList.contains('editing')) return;

        this.classList.add('editing');

        let digitBuffer = "";

        // CLEAR the element safely and use a TextNode so we don't overwrite the input
        this.innerHTML = "";
        const textNode = document.createTextNode("00:00");
        this.appendChild(textNode);

        const input = document.createElement('input');
        input.type = 'tel'; // 'tel' forces the numeric keypad on mobile
        input.className = 'hidden-timer-input';
        input.setAttribute('autocomplete', 'off');

        // Stretch the hidden input over the timer so mobile taps register perfectly
        input.style.position = 'absolute';
        input.style.opacity = '0';
        input.style.height = '100%';
        input.style.width = '100%';
        input.style.top = '0';
        input.style.left = '0';

        this.appendChild(input);
        input.focus();

        const renderFromBuffer = () => {
            // If empty, reset to zeros
            if (!digitBuffer) {
                textNode.nodeValue = "00:00";
                return;
            }

            // Pad the string so we always have at least 4 digits for MM:SS
            const raw = digitBuffer.padStart(4, '0').padStart(6, '0');
            const h = raw.slice(-6, -4);
            const m = raw.slice(-4, -2);
            const s = raw.slice(-2);

            // Overflow to H:MM:SS only if there are hours
            if (parseInt(h, 10) > 0) {
                textNode.nodeValue = `${parseInt(h, 10)}:${m}:${s}`;
            } else {
                textNode.nodeValue = `${m}:${s}`;
            }
        };

        input.addEventListener('input', () => {
            // 1. Strip out anything that isn't a number
            let raw = input.value.replace(/\D/g, '');

            // 2. If it gets pushed past 6 digits, delete the most significant (leftmost) digit
            if (raw.length > 6) {
                raw = raw.slice(-6);
            }

            // 3. Keep the input and buffer in sync so mobile backspace works natively
            input.value = raw;
            digitBuffer = raw;

            renderFromBuffer();
        });

        const saveAndClose = () => {
            const raw = digitBuffer.padStart(6, '0');
            const h = parseInt(raw.slice(-6, -4), 10);
            const m = parseInt(raw.slice(-4, -2), 10);
            const s = parseInt(raw.slice(-2), 10);

            totalSeconds = (h * 3600) + (m * 60) + s;

            this.classList.remove('editing');
            this.innerHTML = textNode.nodeValue;


            hasUnsavedChanges = true;
            // Reveal the save button because the time was altered
            if (saveTimerBtn && taskSelect.value !== "new_task_trigger") {
                saveTimerBtn.classList.remove('hidden');

            }
        };

        // Leaving the field (blur) or pressing Enter will trigger saveAndClose
        input.addEventListener('blur', saveAndClose);
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                input.blur(); // Blur forces it to run saveAndClose
            }
        });
    };
}


// ======================================================
// TASK MANAGEMENT (CREATE, SELECT, UPDATE)
// ======================================================
let previousTaskValue = taskSelect ? taskSelect.value : "";
let openingNewTask = false;

if (taskSelect) {
    taskSelect.addEventListener("change", async (e) => {
        const selectedTask = e.target.value;
        hasUnsavedChanges = false;

        // 1. Toggle "Create New Task" UI
        if (selectedTask === "new_task_trigger") {
            openingNewTask = true;
            taskSelect.classList.add("hidden");
            newTaskForm.classList.remove("hidden");
            newTaskInput.focus();

            setTimeout(() => {
                openingNewTask = false;
            }, 250);
            return;
        }

        previousTaskValue = selectedTask;

        // 2. Set Current Task on Server and reconnect timer stream
        await setActiveTask(selectedTask);

        // Hide the save button if it was exposed from a previous task
        if (saveTimerBtn) saveTimerBtn.classList.add("hidden");
    });

    // Close new task form when clicking outside
    document.addEventListener('click', (e) => {
        if (!newTaskForm || !taskSelect) return;

        if (openingNewTask) {
            return;
        }

        if (!newTaskForm.classList.contains('hidden')) {
            if (!newTaskForm.contains(e.target) && e.target !== taskSelect) {
                newTaskForm.classList.add('hidden');
                taskSelect.classList.remove('hidden');

                // Restore previous selection so user can retry create flow
                taskSelect.value = previousTaskValue || "";
                newTaskInput.value = "";
            }
        }
    });

    newTaskForm.addEventListener('click', (e) => e.stopPropagation());
}

// 3. Cancel Creating a Task
if (cancelNewTaskBtn) {
    cancelNewTaskBtn.addEventListener("click", () => {
        newTaskForm.classList.add("hidden");
        taskSelect.classList.remove("hidden");
        taskSelect.value = previousTaskValue; // Revert to previously selected task
        newTaskInput.value = "";
    });
}

// 4. Save a BRAND NEW Task (POST)
if (saveNewTaskBtn) {
    saveNewTaskBtn.addEventListener("click", async (e) => {
        e.preventDefault(); // Prevents any accidental browser behaviors
        const taskName = newTaskInput.value.trim().toUpperCase();

        if (!taskName) return alert("Please enter a task name.");
        if (totalSeconds <= 0) return alert("Timer must be greater than 00:00.");

        try {
            // FIX: Added /api prefix
            const res = await fetch(`${API_BASE}/profile/preset`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    task_name: taskName,
                    task_time: totalSeconds,
                    task_color: currentColor
                })
            });

            // FIX: Safely check if the response is JSON before parsing
            const contentType = res.headers.get("content-type");
            let data = {};
            if (contentType && contentType.includes("application/json")) {
                data = await res.json();
            }

            if (res.ok) {
                hasUnsavedChanges = false;

                // Add to dropdown visually
                const newOption = document.createElement("option");
                newOption.value = taskName;
                newOption.textContent = taskName;
                taskSelect.insertBefore(newOption, taskSelect.lastElementChild);

                // Reset UI
                newTaskForm.classList.add("hidden");
                taskSelect.classList.remove("hidden");
                taskSelect.value = taskName;
                previousTaskValue = taskName;
                newTaskInput.value = "";

                // Visual Success Feedback
                timerDisplay.classList.add("flash-success");
                setTimeout(() => timerDisplay.classList.remove("flash-success"), 1000);

                // Set as active task
                await setActiveTask(taskName);
            } else {
                alert(data.error || `Failed to create task (Status: ${res.status}).`);
            }
        } catch (err) {
            console.error("Error creating task:", err);
            alert("Network error: Could not reach the server.");
        }
    });
}

// 5. Update EXISTING Task Time (PUT)
if (saveTimerBtn) {
    saveTimerBtn.addEventListener("click", async (e) => {
        e.preventDefault();
        const currentTask = taskSelect.value;
        if (!currentTask || currentTask === "new_task_trigger") return;

        try {
            const res = await fetch(`${API_BASE}/profile/preset`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    task_name: currentTask,
                    task_time: totalSeconds,
                    task_color: currentColor
                })
            });

            const contentType = res.headers.get("content-type");
            let data = {};
            if (contentType && contentType.includes("application/json")) {
                data = await res.json();
            }

            if (res.ok) {
                hasUnsavedChanges = false;

                // Hide button and flash success
                saveTimerBtn.classList.add("hidden");
                timerDisplay.classList.add("flash-success");
                setTimeout(() => timerDisplay.classList.remove("flash-success"), 1000);

                // Update the timer service backend
                await setActiveTask(currentTask);
            } else {
                alert(data.error || `Failed to update task (Status: ${res.status}).`);
            }
        } catch (err) {
            console.error("Error updating task:", err);
            alert("Network error: Could not reach the server.");
        }
    });
}

// ======================================================
// 3. DRIVING CONTROLS (BREATHING FOCUS UX)
// ======================================================

const timerToSeconds = () => displayToSeconds(timerDisplay?.innerText || "00:00");

if (breathingBtn) {
    breathingBtn.addEventListener('click', async () => {
        if (!cubeAPI) return;

        const nextState = cubeAPI.toggleBreathing();
        breathingBtn.textContent = nextState ? 'Pause' : 'Resume';

        const action = nextState ? 'start' : 'stop';
        const elapsed = timerToSeconds();

        try {
            await fetch(`${API_BASE}/task/control`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ action, elapsed_seconds: elapsed })
            });
        } catch (err) {
            console.error('Failed to send task.control:', err);
        }

        if (!nextState) {
            hasUnsavedChanges = false;
        }
    });
}

// ======================================================
// 4. COLOR PICKER & CUBE INIT
// ======================================================

// Initialize Cube with retry and visual status
async function initCube() {
    if (!cubeContainer) return;

    if (cubeAPI && typeof cubeAPI.destroy === 'function') {
        cubeAPI.destroy();
    }

    let attempt = 0;
    let configured = false;

    while (!configured && attempt < 3) {
        try {
            cubeAPI = mountGlowingCube(cubeContainer);
            if (cubeAPI) {
                cubeAPI.setColor(currentColor);
                configured = true;
            }
        } catch (err) {
            console.error('Cube init attempt failed', attempt + 1, err);
            attempt += 1;
            await new Promise(r => setTimeout(r, 250));
        }
    }

    if (!configured) {
        cubeContainer.innerHTML = '<div class="cube-error">Unable to load cube. Please reload.</div>';
    }
}

// Initialize Cube on DOM ready (ensures re-initialization on page navigation)
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        if (cubeContainer) initCube();
    });
} else {
    // DOM already loaded (module cached)
    if (cubeContainer) initCube();
}

// Initialize Color Picker
if (colorMenu && colorTrigger) {
    PALETTE.forEach(color => {
        const btn = document.createElement('button');
        btn.className = 'swatch';
        btn.style.backgroundColor = rgbwToRgb(color);

        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (cubeAPI) cubeAPI.setColor(color);
            colorTrigger.style.backgroundColor = rgbwToRgb(color);
            currentColor = color;
            colorMenu.classList.remove('active');
        });
        colorMenu.appendChild(btn);
    });

    colorTrigger.addEventListener('click', (e) => {
        e.stopPropagation();
        colorMenu.classList.toggle('active');
    });

    document.addEventListener('click', (e) => {
        if (!colorMenu.contains(e.target) && e.target !== colorTrigger) {
            colorMenu.classList.remove('active');
        }
    });
}


// ======================================================
// INIT
// ======================================================

connectTimerStream();
syncCurrentTask();
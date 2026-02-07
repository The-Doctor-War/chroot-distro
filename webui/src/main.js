import { exec, spawn, toast } from "kernelsu";

const LOG_DIR = "/data/local/tmp/chroot-distro-logs";
const mainContent = document.getElementById("main-content");
const settingsView = document.getElementById("settings-view");
const versionText = document.getElementById("version-text");
const toastEl = document.getElementById("toast");
const maintainerCredit = document.getElementById("maintainer-credit");
const navHome = document.getElementById("nav-home");
const navSettings = document.getElementById("nav-settings");

const helpBtn = document.getElementById("help-btn");
const clearCacheBtn = document.getElementById("clear-cache-btn");
const helpModal = document.getElementById("help-modal");
const closeHelpModalBtn = document.getElementById("close-help-modal");
const helpContent = document.getElementById("help-content");
const searchContainer = document.getElementById("search-container");
const titleContainer = document.getElementById("title-container");
const searchInput = document.getElementById("search-input");
const searchCloseBtn = document.getElementById("search-close-btn");
const searchBtn = document.getElementById("search-btn");

let allDistros = [];

const activeTerminals = new Map();
const activeWatchers = new Map();

/**
 * Get log path for distro action
 * @param {string} distroName
 * @param {string} action
 * @returns {string}
 */
function getLogPath(distroName, action) {
	return `${LOG_DIR}/${distroName}_${action}.log`;
}

/**
 * Save active task to localStorage
 * @param {string} distro
 * @param {string} action
 */
function saveActiveTask(distro, action) {
	const tasks = JSON.parse(localStorage.getItem("active_tasks") || "{}");
	tasks[distro] = { action, timestamp: Date.now() };
	localStorage.setItem("active_tasks", JSON.stringify(tasks));
}

/**
 * Remove active task from localStorage
 * @param {string} distro
 */
function removeActiveTask(distro) {
	const tasks = JSON.parse(localStorage.getItem("active_tasks") || "{}");
	delete tasks[distro];
	localStorage.setItem("active_tasks", JSON.stringify(tasks));
}

/**
 * Get active task for distro
 * @param {string} distro
 * @returns {Object|null}
 */
function getActiveTask(distro) {
	const tasks = JSON.parse(localStorage.getItem("active_tasks") || "{}");
	return tasks[distro] || null;
}

/**
 * Start watching log file and updating terminal
 * @param {string} distroName
 * @param {string} filePath
 * @param {HTMLElement} terminalOutput
 * @param {Function} onFinish
 */
async function startLogWatcher(distroName, filePath, terminalOutput, onFinish) {
	if (activeWatchers.has(distroName)) return;

	let offset = 0;
	let finishCheckCount = 0;
	const interval = setInterval(async () => {
		try {
			const { stdout } = await exec(`cat "${filePath}"`);

			if (stdout && stdout.length > offset) {
				const newContent = stdout.slice(offset);
				offset = stdout.length;
				appendTerminalLine(terminalOutput, newContent);
				finishCheckCount = 0; // Reset finish check if data is flowing
			} else {
				finishCheckCount++;
			}

			// Check if process is still running if we haven't seen data for a while
			// This is a "watchdog" style check.
			if (finishCheckCount > 10) {
				// Every 1s * 10 = 10s of no data.
				// We rely on the caller to clear the interval via onFinish or external check usually.
				// But for restored sessions, we need to know when to stop.
				const isRunning = await isProcessRunning(distroName);
				if (!isRunning) {
					clearInterval(interval);
					activeWatchers.delete(distroName);
					if (onFinish) onFinish(); // Logic to finalize UI
				}
				finishCheckCount = 0;
			}
		} catch (e) {
			// File might not exist yet or error reading
			console.warn("Log watcher error:", e);
		}
	}, 1000);

	activeWatchers.set(distroName, interval);
}

/**
 * Check if a chroot-distro process for the distro is running
 * @param {string} distroName
 * @returns {Promise<boolean>}
 */
async function isProcessRunning(distroName) {
	// Check for direct chroot-distro process or wrapper script
	const { stdout } = await exec(`ps -ef | grep -E "(chroot-distro.*(install|remove|unmount).*${distroName}|${distroName}_(install|uninstall|stop)\\.sh)" | grep -v grep`);
	return !!stdout && stdout.trim().length > 0;
}

/**
 * Show toast message
 * @param {string} message
 * @param {boolean} isError
 */
function showToast(message, isError = false) {
	try {
		toast(message);
	} catch (e) {
		toastEl.textContent = message;
		toastEl.classList.toggle("error", isError);
		toastEl.classList.add("show");
		setTimeout(() => {
			toastEl.classList.remove("show");
		}, 3000);
	}
}

/**
 * Apply ripple effect to element
 * @param {HTMLElement} element
 */
function applyRipple(element) {
	element.addEventListener("click", function (e) {
		const rect = element.getBoundingClientRect();
		const x = e.clientX - rect.left;
		const y = e.clientY - rect.top;

		const ripple = document.createElement("span");
		ripple.className = "ripple";
		ripple.style.left = x + "px";
		ripple.style.top = y + "px";

		element.appendChild(ripple);
		setTimeout(() => ripple.remove(), 600);
	});
}

/**
 * Append line to terminal
 * @param {HTMLElement} terminalOutput
 * @param {string} text
 * @param {string} type 'normal', 'error', 'success'
 */
function appendTerminalLine(terminalOutput, text, type = "normal") {
	if (!text) return;
	const lines = text.split("\n");
	lines.forEach((line) => {
		if (line.trim() === "") return;
		const div = document.createElement("div");
		div.className = `terminal-line ${type}`;
		div.textContent = line;
		terminalOutput.appendChild(div);
	});
	terminalOutput.scrollTop = terminalOutput.scrollHeight;
}

/**
 * Fetch version info
 */
async function fetchVersion() {
	try {
		const { errno, stdout } = await exec("JOSINIFY=true chroot-distro --version");
		if (errno === 0 && stdout) {
			const data = JSON.parse(stdout.trim());
			versionText.textContent = `v${data.version}`;
			if (data.maintainer) {
				maintainerCredit.textContent = `Created by ${data.maintainer}`;
			}
		}
	} catch (e) {
		console.error("Failed to fetch version:", e);
	}
}

/**
 * Fetch distributions list with running status
 * @returns {Promise<Array>}
 */
async function fetchDistros() {
	const listPromise = exec("JOSINIFY=true chroot-distro list");
	const runningPromise = exec("JOSINIFY=true chroot-distro list-running");

	const [listResult, runningResult] = await Promise.all([listPromise, runningPromise]);

	if (listResult.errno !== 0) {
		throw new Error(listResult.stderr || "Failed to fetch distributions");
	}

	const listData = JSON.parse(listResult.stdout.trim());
	let runningNames = [];

	if (runningResult.errno === 0 && runningResult.stdout) {
		try {
			const runningData = JSON.parse(runningResult.stdout.trim());
			if (runningData.running_distributions) {
				runningNames = runningData.running_distributions.map((d) => d.name);
			}
		} catch (e) {
			console.warn("Failed to parse running distros:", e);
		}
	}

	return (listData.distributions || []).map((d) => ({
		...d,
		running: runningNames.includes(d.name),
	}));
}

/**
 * Sync active tasks with UI (restore sessions)
 */
async function syncActiveTasksUI() {
	const tasks = JSON.parse(localStorage.getItem("active_tasks") || "{}");
	const distros = Object.keys(tasks);

	for (const distro of distros) {
		const task = tasks[distro];
		const card = document.getElementById(`card-${distro}`);
		if (!card) continue;

		// Visual state update
		const btn = card.querySelector(`.action-btn[data-action="${task.action}"]`);

		if (task.action === "install" || task.action === "uninstall") {
			if (btn) btn.disabled = true;

			// Add animation to button icon
			const btnIcon = btn ? btn.querySelector("svg") : null;
			if (btnIcon) {
				if (task.action === "install") {
					btnIcon.classList.add("download-anim");
				} else {
					btnIcon.classList.add("shake-anim");
				}
			}

			// Open terminal
			const terminal = card.querySelector(`#terminal-${distro}`);
			if (!terminal) continue;

			toggleTerminal(distro, card);

			const terminalOutput = terminal.querySelector(".terminal-output");
			const terminalTitle = terminal.querySelector(".terminal-title span");
			const closeBtn = terminal.querySelector(".terminal-close-btn");

			if (closeBtn) closeBtn.disabled = true;
			if (!terminal.classList.contains("open")) terminal.classList.add("open");
			terminalOutput.innerHTML = ""; // Clear "No recent logs"

			const logPath = getLogPath(distro, task.action);
			terminalTitle.textContent = `${task.action === "install" ? "Installing" : "Removing"} ${distro}...`;

			const isRunning = await isProcessRunning(distro);

			if (activeWatchers.has(distro)) {
				clearInterval(activeWatchers.get(distro));
				activeWatchers.delete(distro);
			}

			if (isRunning) {
				startLogWatcher(distro, logPath, terminalOutput, async () => {
					await handleTaskCompletion(distro, task.action, card, terminal, terminalTitle, terminalOutput, btn, closeBtn);
					if (btnIcon) btnIcon.classList.remove("download-anim", "shake-anim");
				});
			} else {
				const { stdout } = await exec(`cat "${logPath}"`);
				if (stdout) appendTerminalLine(terminalOutput, stdout);
				await handleTaskCompletion(distro, task.action, card, terminal, terminalTitle, terminalOutput, btn, closeBtn);
				if (btnIcon) btnIcon.classList.remove("download-anim", "shake-anim");
			}
		}
	}
}

/**
 * Handle task completion logic
 */
async function handleTaskCompletion(distroName, action, card, terminal, terminalTitle, terminalOutput, btn, closeBtn) {
	activeWatchers.delete(distroName); // Ensure watcher is gone
	removeActiveTask(distroName);

	const { errno, stdout } = await exec("JOSINIFY=true chroot-distro list");
	let success = false;
	if (errno === 0 && stdout) {
		const data = JSON.parse(stdout.trim());
		const distroInfo = data.distributions?.find((d) => d.name === distroName);
		if (action === "install") success = distroInfo?.installed === true;
		if (action === "uninstall") success = distroInfo?.installed === false;
	}

	if (success) {
		terminalTitle.textContent = `${distroName} ${action === "install" ? "installed" : "removed"} successfully!`;
		terminalTitle.style.color = "#4ade80";
		appendTerminalLine(terminalOutput, `✓ ${action === "install" ? "Installation" : "Removal"} completed successfully!`, "success");
		showToast(`${distroName} ${action === "install" ? "installed" : "removed"} successfully!`);

		setTimeout(async () => {
			terminal.classList.remove("open");
			if (closeBtn) closeBtn.disabled = false;
			if (btn) btn.disabled = false;
			await refreshDistroCard(distroName, card);
		}, 3000);
	} else {
		terminalTitle.textContent = "Operation failed (or checking failed)";
		terminalTitle.style.color = "#e94560";
		appendTerminalLine(terminalOutput, "✗ Operation failed.", "error");
		if (closeBtn) closeBtn.disabled = false;
		if (btn) btn.disabled = false;
	}
}

/**
 * Switch to specific view
 * @param {string} view 'home' or 'settings'
 */
function switchView(view) {
	if (view === "home") {
		mainContent.classList.remove("hidden");
		settingsView.classList.add("hidden");
		navHome.classList.add("active");
		navSettings.classList.remove("active");
		// Optional: refresh home data
	} else if (view === "settings") {
		mainContent.classList.add("hidden");
		settingsView.classList.remove("hidden");
		navHome.classList.remove("active");
		navSettings.classList.add("active");
	}
}

/**
 * Show Help Modal
 */
async function showHelp() {
	const originalText = helpBtn.querySelector("span").textContent;
	helpBtn.querySelector("span").textContent = "Loading...";
	helpBtn.disabled = true;

	try {
		const { errno, stdout, stderr } = await exec("export JOSINIFY=true && chroot-distro --help");

		let content = "";
		let json = null;

		if (stdout) {
			try {
				json = JSON.parse(stdout);
			} catch (e) {
				content = stdout;
			}
		}

		if (json && json.commands) {
			// Format as table
			const table = document.createElement("div");
			table.className = "help-table";

			json.commands.forEach((cmd) => {
				const row = document.createElement("div");
				row.className = "help-row";

				const cmdName = document.createElement("div");
				cmdName.className = "help-cmd";
				cmdName.textContent = cmd.name;

				const cmdDesc = document.createElement("div");
				cmdDesc.className = "help-desc";
				cmdDesc.textContent = cmd.description || "No description available";

				row.appendChild(cmdName);
				row.appendChild(cmdDesc);
				table.appendChild(row);
			});

			helpContent.innerHTML = "";
			helpContent.appendChild(table);
		} else {
			// Fallback to text
			if (stderr) content += "\n" + stderr;
			helpContent.textContent = content || "No output returned.";
		}

		helpModal.classList.add("open");
	} catch (e) {
		showToast("Failed to run help command", true);
		console.error(e);
	} finally {
		helpBtn.querySelector("span").textContent = originalText;
		helpBtn.disabled = false;
	}
}

/**
 * Clear Cache with Terminal Output
 */
async function clearCache() {
	let terminal = document.getElementById("cache-terminal");
	if (!terminal) {
		const container = document.createElement("div");
		container.innerHTML = createTerminalHTML("cache-clear");
		terminal = container.firstElementChild;
		terminal.id = "cache-terminal";

		const placeholder = document.getElementById("cache-terminal-container");
		if (placeholder) {
			placeholder.appendChild(terminal);
		} else {
			document.querySelector(".settings-container").appendChild(terminal);
		}
	}

	const terminalOutput = terminal.querySelector(".terminal-output");
	const terminalTitle = terminal.querySelector(".terminal-title span");
	const closeBtn = terminal.querySelector(".terminal-close-btn");

	if (terminal.classList.contains("open")) {
		terminal.classList.remove("open");
		return;
	}

	terminal.classList.add("open");
	terminalOutput.innerHTML = "";
	terminalTitle.textContent = "Clearing Cache...";

	closeBtn.onclick = () => {
		terminal.classList.remove("open");
	};

	appendTerminalLine(terminalOutput, "$ chroot-distro clear-cache");

	try {
		const process = spawn("chroot-distro", ["clear-cache"]);

		process.stdout.on("data", (data) => {
			appendTerminalLine(terminalOutput, data.toString());
		});

		process.stderr.on("data", (data) => {
			appendTerminalLine(terminalOutput, data.toString(), "error");
		});

		const exitCode = await new Promise((resolve) => {
			process.on("exit", (code) => resolve(code));
			process.on("error", (err) => {
				appendTerminalLine(terminalOutput, `Error: ${err.message}`, "error");
				resolve(1);
			});
		});

		if (exitCode === 0) {
			terminalTitle.textContent = "Cache Cleared";
			terminalTitle.style.color = "#4ade80";
			appendTerminalLine(terminalOutput, "✓ Success", "success");
		} else {
			terminalTitle.textContent = "Failed";
			terminalTitle.style.color = "#e94560";
		}
	} catch (e) {
		appendTerminalLine(terminalOutput, `Error: ${e.message}`, "error");
	}
}

/**
 * Create terminal HTML
 * @param {string} distroName
 * @returns {string}
 */
function createTerminalHTML(distroName) {
	return `
        <div class="terminal-container" id="terminal-${distroName}">
            <div class="terminal-header">
                <div class="terminal-title">
                    <span>Terminal - ${distroName}</span>
                </div>
                <button class="terminal-close-btn" title="Close terminal">✕</button>
            </div>
            <div class="terminal-output"><div class="terminal-line" style="color: #666;">No recent logs</div></div>
        </div>
    `;
}

/**
 * Create command dropdown HTML
 * @param {string} distroName
 * @returns {string}
 */
function createCommandDropdownHTML(distroName) {
	const command = `chroot-distro login ${distroName}`;
	return `
        <div class="command-dropdown" id="command-${distroName}">
            <div class="command-content">
                <span class="command-text">${command}</span>
                <button class="copy-btn" data-command="${command}">Copy</button>
            </div>
        </div>
    `;
}

const ICONS = {
	install: `<svg viewBox="0 0 24 24" class="btn-icon"><path d="M5,20H19V18H5M19,9H15V3H9V9H5L12,16L19,9Z"/></svg>`,
	start: `<svg viewBox="0 0 24 24" class="btn-icon"><path d="M8,5.14V19.14L19,12.14L8,5.14Z"/></svg>`,
	uninstall: `<svg viewBox="0 0 24 24" class="btn-icon"><path d="M19,4H15.5L14.5,3H9.5L8.5,4H5V6H19M6,19A2,2 0 0,0 8,21H16A2,2 0 0,0 18,19V7H6V19Z"/></svg>`,
	stop: `<svg viewBox="0 0 24 24" class="btn-icon"><path d="M18,18H6V6H18V18Z"/></svg>`,
};

/**
 * Create distro card element
 * @param {Object} distro
 * @returns {HTMLElement}
 */
function createDistroCard(distro) {
	const card = document.createElement("div");
	card.className = "distro-card";
	card.id = `card-${distro.name}`;

	const isInstalled = distro.installed;
	const isRunning = distro.running;

	let buttonsHTML = "";
	if (isInstalled) {
		buttonsHTML = `
            <div class="btn-container">
                <button class="action-btn start ripple-element icon-btn" data-distro="${distro.name}" data-action="start" title="Start / Copy Login Command">${ICONS.start}</button>
                ${isRunning ? `<button class="action-btn stop ripple-element icon-btn" data-distro="${distro.name}" data-action="stop" title="Stop / Unmount">${ICONS.stop}</button>` : ""}
                <button class="action-btn uninstall ripple-element icon-btn" data-distro="${distro.name}" data-action="uninstall" title="Uninstall">${ICONS.uninstall}</button>
            </div>
        `;
	} else {
		buttonsHTML = `
            <button class="action-btn ripple-element icon-btn" data-distro="${distro.name}" data-action="install" title="Install">${ICONS.install}</button>
        `;
	}

	card.innerHTML = `
        <div class="distro-card-content" data-distro="${distro.name}">
            <div class="distro-info">
                <span class="distro-name">
                    ${distro.name}
                    ${distro.version ? `<span class="distro-version">[${distro.version}]</span>` : ""}
                </span>
                <div class="status-row">
                    <span class="distro-status ${isInstalled ? "installed" : ""}">
                        <span class="status-dot ${isInstalled ? "installed" : ""}"></span>
                        ${isInstalled ? "Installed" : "Not installed"}
                    </span>
                    ${
						isRunning
							? `
                    <span class="distro-status running">
                        <span class="status-dot running"></span>
                        Running
                    </span>`
							: ""
					}
                </div>
            </div>
            ${buttonsHTML}
        </div>
        ${isInstalled ? createCommandDropdownHTML(distro.name) : ""}
        ${createTerminalHTML(distro.name)}
    `;

	const cardContent = card.querySelector(".distro-card-content");

	card.querySelectorAll(".action-btn").forEach((btn) => {
		applyRipple(btn);
		btn.addEventListener("click", (e) => {
			e.stopPropagation();
			const action = btn.dataset.action;
			handleAction(distro.name, action, btn, card);
		});
	});

	const copyBtn = card.querySelector(".copy-btn");
	if (copyBtn) {
		copyBtn.addEventListener("click", (e) => {
			e.stopPropagation();
			copyToClipboard(copyBtn.dataset.command);
		});
	}

	cardContent.addEventListener("click", (e) => {
		if (!e.target.closest(".action-btn") && !e.target.closest(".copy-btn")) {
			toggleDropdowns(distro.name, card, isInstalled);
		}
	});

	const closeBtn = card.querySelector(".terminal-close-btn");
	closeBtn.addEventListener("click", (e) => {
		e.stopPropagation();
		closeTerminal(distro.name, card);
	});

	return card;
}

/**
 * Copy text to clipboard
 * @param {string} text
 */
async function copyToClipboard(text) {
	try {
		await navigator.clipboard.writeText(text);
		showToast("Command copied to clipboard!");
	} catch (e) {
		const textarea = document.createElement("textarea");
		textarea.value = text;
		document.body.appendChild(textarea);
		textarea.select();
		document.execCommand("copy");
		document.body.removeChild(textarea);
		showToast("Command copied to clipboard!");
	}
}

/**
 * Toggle dropdowns (command dropdown for installed, terminal for not installed)
 * @param {string} distroName
 * @param {HTMLElement} card
 * @param {boolean} isInstalled
 */
function toggleDropdowns(distroName, card, isInstalled) {
	if (isInstalled) {
		const commandDropdown = card.querySelector(`#command-${distroName}`);
		if (commandDropdown) {
			commandDropdown.classList.toggle("open");
		}
	} else {
		toggleTerminal(distroName, card);
	}
}

/**
 * Toggle terminal visibility for distro
 * @param {string} distroName
 * @param {HTMLElement} card
 */
function toggleTerminal(distroName, card) {
	const terminal = card.querySelector(`#terminal-${distroName}`);
	if (terminal) {
		terminal.classList.toggle("open");
		if (terminal.classList.contains("open")) {
			setTimeout(() => {
				terminal.scrollIntoView({ behavior: "smooth", block: "nearest" });
			}, 100);
		}
	}
}

/**
 * Close terminal for distro
 * @param {string} distroName
 * @param {HTMLElement} card
 */
function closeTerminal(distroName, card) {
	const terminal = card.querySelector(`#terminal-${distroName}`);
	if (terminal) {
		terminal.classList.remove("open");
	}
}

/**
 * Handle action based on action type
 * @param {string} distroName
 * @param {string} action - 'start', 'install', or 'uninstall'
 * @param {HTMLButtonElement} btn
 * @param {HTMLElement} card
 */
async function handleAction(distroName, action, btn, card) {
	switch (action) {
		case "start":
			const command = `chroot-distro login ${distroName}`;
			await copyToClipboard(command);

			const commandDropdown = card.querySelector(`#command-${distroName}`);
			if (commandDropdown) {
				commandDropdown.classList.add("open");
			}
			break;

		case "install":
			await installWithTerminal(distroName, btn, card);
			break;

		case "stop":
			await stopWithTerminal(distroName, btn, card);
			break;

		case "uninstall":
			await uninstallWithTerminal(distroName, btn, card);
			break;
	}
}

/**
 * Stop/Unmount distribution with terminal output
 * @param {string} distroName
 * @param {HTMLButtonElement} btn
 * @param {HTMLElement} card
 */
async function stopWithTerminal(distroName, btn, card) {
	const terminal = card.querySelector(`#terminal-${distroName}`);
	const terminalOutput = terminal.querySelector(".terminal-output");
	const terminalTitle = terminal.querySelector(".terminal-title span");

	const closeBtn = terminal.querySelector(".terminal-close-btn");

	btn.disabled = true;
	const startBtn = card.querySelector('[data-action="start"]');
	if (startBtn) startBtn.disabled = true;
	const uninstallBtn = card.querySelector('[data-action="uninstall"]');
	if (uninstallBtn) uninstallBtn.disabled = true;

	closeBtn.disabled = true;
	terminalOutput.innerHTML = "";

	terminalTitle.textContent = `Stopping ${distroName}...`;
	terminalTitle.style.color = "";

	terminal.classList.add("open");
	setTimeout(() => {
		terminal.scrollIntoView({ behavior: "smooth", block: "nearest" });
	}, 100);

	appendTerminalLine(terminalOutput, `$ chroot-distro unmount ${distroName}`);
	appendTerminalLine(terminalOutput, "");

	try {
		const logPath = getLogPath(distroName, "stop");
		await exec(`mkdir -p "${LOG_DIR}" && echo "Starting stop..." > "${logPath}"`);

		const scriptPath = `${LOG_DIR}/${distroName}_stop.sh`;
		await exec(`echo 'chroot-distro unmount ${distroName} >> "${logPath}" 2>&1' > "${scriptPath}" && chmod +x "${scriptPath}"`);
		const process = spawn("sh", [scriptPath]);

		startLogWatcher(distroName, logPath, terminalOutput);

		const exitCode = await new Promise((resolve) => {
			process.on("exit", (code) => resolve(code));
			process.on("error", () => resolve(1));
		});

		if (activeWatchers.has(distroName)) {
			clearInterval(activeWatchers.get(distroName));
			activeWatchers.delete(distroName);
			const { stdout } = await exec(`cat "${logPath}"`);
			if (stdout) appendTerminalLine(terminalOutput, stdout);
		}

		activeTerminals.delete(distroName);

		const { errno, stdout } = await exec("JOSINIFY=true chroot-distro list-running");
		let stopSuccess = false;

		if (errno === 0 && stdout) {
			try {
				const data = JSON.parse(stdout.trim());
				const runningDistros = data.running_distributions || [];
				stopSuccess = !runningDistros.some((d) => d.name === distroName);
			} catch (e) {
				console.warn("Failed to parse running list:", e);
				stopSuccess = exitCode === 0;
			}
		} else {
			stopSuccess = exitCode === 0;
		}

		if (stopSuccess) {
			terminalTitle.textContent = `${distroName} stopped successfully!`;
			terminalTitle.style.color = "#4ade80";
			appendTerminalLine(terminalOutput, "", "success");
			appendTerminalLine(terminalOutput, "✓ Unmount completed successfully!", "success");

			showToast(`${distroName} stopped successfully!`);

			setTimeout(async () => {
				terminal.classList.remove("open");
				await refreshDistroCard(distroName, card);
			}, 2000);
		} else {
			terminalTitle.textContent = `Stop failed (exit code: ${exitCode})`;
			terminalTitle.style.color = "#e94560";
			appendTerminalLine(terminalOutput, "", "error");
			appendTerminalLine(terminalOutput, `✗ Unmount failed with exit code ${exitCode}`, "error");

			showToast("Stop failed", true);
			closeBtn.disabled = false;
			btn.disabled = false;
			if (startBtn) startBtn.disabled = false;
			if (uninstallBtn) uninstallBtn.disabled = false;
		}
	} catch (e) {
		console.error("Stop error:", e);

		terminalTitle.textContent = "Stop error";
		terminalTitle.style.color = "#e94560";
		appendTerminalLine(terminalOutput, `Error: ${e.message}`, "error");

		showToast(e.message, true);
		closeBtn.disabled = false;
		btn.disabled = false;
		if (startBtn) startBtn.disabled = false;
		if (uninstallBtn) uninstallBtn.disabled = false;
	}
}

/**
 * Install distribution with terminal output
 * @param {string} distroName
 * @param {HTMLButtonElement} btn
 * @param {HTMLElement} card
 */
async function installWithTerminal(distroName, btn, card) {
	const terminal = card.querySelector(`#terminal-${distroName}`);
	const terminalOutput = terminal.querySelector(".terminal-output");
	const terminalTitle = terminal.querySelector(".terminal-title span");

	const closeBtn = terminal.querySelector(".terminal-close-btn");

	btn.disabled = true;

	const btnIcon = btn.querySelector("svg");
	if (btnIcon) btnIcon.classList.add("download-anim");

	closeBtn.disabled = true;
	terminalOutput.innerHTML = "";

	terminalTitle.textContent = `Installing ${distroName}...`;
	terminalTitle.style.color = "";

	terminal.classList.add("open");
	setTimeout(() => {
		terminal.scrollIntoView({ behavior: "smooth", block: "nearest" });
	}, 100);

	appendTerminalLine(terminalOutput, `$ chroot-distro install ${distroName}`);
	appendTerminalLine(terminalOutput, "");

	try {
		const logPath = getLogPath(distroName, "install");
		await exec(`mkdir -p "${LOG_DIR}"`);

		saveActiveTask(distroName, "install");

		const scriptPath = `${LOG_DIR}/${distroName}_install.sh`;
		await exec(`echo 'chroot-distro install ${distroName} > "${logPath}" 2>&1' > "${scriptPath}" && chmod +x "${scriptPath}"`);

		const process = spawn("sh", [scriptPath]);

		startLogWatcher(distroName, logPath, terminalOutput, async () => {
			await handleTaskCompletion(distroName, "install", card, terminal, terminalTitle, terminalOutput, btn, closeBtn);
			if (btnIcon) btnIcon.classList.remove("download-anim");
		});

		const exitCode = await new Promise((resolve) => {
			process.on("exit", (code) => {
				resolve(code);
			});
			process.on("error", (err) => {
				appendTerminalLine(terminalOutput, `Error: ${err.message}`, "error");
				resolve(1);
			});
		});

		if (activeWatchers.has(distroName)) {
			clearInterval(activeWatchers.get(distroName));
			activeWatchers.delete(distroName);
			const { stdout } = await exec(`cat "${logPath}"`);
			if (stdout) appendTerminalLine(terminalOutput, stdout);
		}
		await handleTaskCompletion(distroName, "install", card, terminal, terminalTitle, terminalOutput, btn, closeBtn);
		if (btnIcon) btnIcon.classList.remove("download-anim");
	} catch (e) {
		console.error("Install error:", e);
		if (btnIcon) btnIcon.classList.remove("download-anim");

		terminalTitle.textContent = "Installation error";
		terminalTitle.style.color = "#e94560";
		appendTerminalLine(terminalOutput, `Error: ${e.message}`, "error");

		showToast(e.message, true);
		closeBtn.disabled = false;
		btn.disabled = false;
		removeActiveTask(distroName);
	}
}

/**
 * Uninstall distribution with terminal output
 * @param {string} distroName
 * @param {HTMLButtonElement} btn
 * @param {HTMLElement} card
 */
async function uninstallWithTerminal(distroName, btn, card) {
	const terminal = card.querySelector(`#terminal-${distroName}`);
	const terminalOutput = terminal.querySelector(".terminal-output");
	const terminalTitle = terminal.querySelector(".terminal-title span");

	const closeBtn = terminal.querySelector(".terminal-close-btn");

	btn.disabled = true;

	const btnIcon = btn.querySelector("svg");
	if (btnIcon) btnIcon.classList.add("shake-anim");

	const startBtn = card.querySelector('[data-action="start"]');
	if (startBtn) startBtn.disabled = true;

	closeBtn.disabled = true;
	terminalOutput.innerHTML = "";

	terminalTitle.textContent = `Removing ${distroName}...`;
	terminalTitle.style.color = "";

	terminal.classList.add("open");
	setTimeout(() => {
		terminal.scrollIntoView({ behavior: "smooth", block: "nearest" });
	}, 100);

	appendTerminalLine(terminalOutput, `$ chroot-distro remove ${distroName}`);
	appendTerminalLine(terminalOutput, "");

	try {
		const logPath = getLogPath(distroName, "uninstall");
		await exec(`mkdir -p "${LOG_DIR}"`);
		saveActiveTask(distroName, "uninstall");

		const scriptPath = `${LOG_DIR}/${distroName}_uninstall.sh`;
		await exec(`echo 'chroot-distro remove ${distroName} > "${logPath}" 2>&1' > "${scriptPath}" && chmod +x "${scriptPath}"`);

		const process = spawn("sh", [scriptPath]);

		startLogWatcher(distroName, logPath, terminalOutput, async () => {
			await handleTaskCompletion(distroName, "uninstall", card, terminal, terminalTitle, terminalOutput, btn, closeBtn);
			if (btnIcon) btnIcon.classList.remove("shake-anim");
		});

		const exitCode = await new Promise((resolve) => {
			process.on("exit", (code) => resolve(code));
			process.on("error", (err) => {
				appendTerminalLine(terminalOutput, `Error: ${err.message}`, "error");
				resolve(1);
			});
		});

		if (activeWatchers.has(distroName)) {
			clearInterval(activeWatchers.get(distroName));
			activeWatchers.delete(distroName);
			const { stdout } = await exec(`cat "${logPath}"`);
			if (stdout) appendTerminalLine(terminalOutput, stdout);
		}

		await handleTaskCompletion(distroName, "uninstall", card, terminal, terminalTitle, terminalOutput, btn, closeBtn);
		if (btnIcon) btnIcon.classList.remove("shake-anim");
	} catch (e) {
		console.error("Uninstall error:", e);
		if (btnIcon) btnIcon.classList.remove("shake-anim"); // Stop animation

		terminalTitle.textContent = "Removal error";
		terminalTitle.style.color = "#e94560";
		appendTerminalLine(terminalOutput, `Error: ${e.message}`, "error");

		showToast(e.message, true);
		closeBtn.disabled = false;
		btn.disabled = false;
		removeActiveTask(distroName);
		if (startBtn) startBtn.disabled = false;
	}
}

/**
 * Refresh distro card after install
 * @param {string} distroName
 * @param {HTMLElement} oldCard
 */
async function refreshDistroCard(distroName, oldCard) {
	try {
		const distros = await fetchDistros();
		const distroInfo = distros.find((d) => d.name === distroName);

		if (distroInfo) {
			const newCard = createDistroCard(distroInfo);
			oldCard.replaceWith(newCard);
		}
	} catch (e) {
		console.error("Failed to refresh card:", e);
	}
}

/**
 * Render error state
 * @param {string} message
 */
function renderError(message) {
	mainContent.innerHTML = `
        <div class="error-container">
            <span>${message}</span>
            <button class="action-btn ripple-element" id="retry-btn">Retry</button>
        </div>
    `;

	const retryBtn = document.getElementById("retry-btn");
	applyRipple(retryBtn);
	retryBtn.addEventListener("click", loadDistros);
}

/**
 * Render distributions to the DOM
 * @param {Array} distros
 */
function renderDistros(distros) {
	mainContent.innerHTML = "";

	const title = document.createElement("div");
	title.className = "section-title";
	title.textContent = "Available Distributions";
	mainContent.appendChild(title);

	distros.forEach((distro) => {
		const card = createDistroCard(distro);
		mainContent.appendChild(card);
	});

	if (distros.length === 0) {
		mainContent.innerHTML += `
            <div class="loading-container">
                <span>No distributions found</span>
            </div>
        `;
	}
}

/**
 * Filter distributions based on search query
 * @param {string} query
 */
function filterDistros(query) {
	const lowerQuery = query.toLowerCase();
	const filtered = allDistros.filter((d) => d.name.toLowerCase().includes(lowerQuery));
	renderDistros(filtered);
}

/**
 * Toggle search mode
 * @param {boolean} show
 */
function toggleSearch(show) {
	const refreshBtn = document.getElementById("refresh-btn");
	if (show) {
		titleContainer.classList.add("hidden");
		searchContainer.classList.remove("hidden");
		if (refreshBtn) refreshBtn.classList.add("hidden");
		searchInput.focus();
	} else {
		searchContainer.classList.add("hidden");
		titleContainer.classList.remove("hidden");
		if (refreshBtn) refreshBtn.classList.remove("hidden");
		searchInput.value = "";
		filterDistros(""); // Reset filter
	}
}

/**
 * Load and render distributions
 */
async function loadDistros() {
	mainContent.innerHTML = `
        <div class="loading-container" id="loading">
            <div class="spinner"></div>
            <span>Loading distributions...</span>
        </div>
    `;

	try {
		allDistros = await fetchDistros();
		if (!searchContainer.classList.contains("hidden") && searchInput.value) {
			filterDistros(searchInput.value);
		} else {
			renderDistros(allDistros);
		}
		await syncActiveTasksUI();
	} catch (e) {
		console.error("Failed to load distributions:", e);
		renderError("Failed to load distributions. Make sure chroot-distro is installed.");
	}
}

/**
 * Initialize the app
 */
async function init() {
	document.querySelectorAll(".ripple-element").forEach(applyRipple);

	const refreshBtn = document.getElementById("refresh-btn");
	if (refreshBtn) {
		refreshBtn.addEventListener("click", () => {
			loadDistros();
		});
	}

	if (navHome && navSettings) {
		navHome.addEventListener("click", () => switchView("home"));
		navSettings.addEventListener("click", () => switchView("settings"));
	}

	if (helpBtn) helpBtn.addEventListener("click", showHelp);
	if (closeHelpModalBtn) closeHelpModalBtn.addEventListener("click", () => helpModal.classList.remove("open"));
	if (helpModal)
		helpModal.addEventListener("click", (e) => {
			if (e.target === helpModal) helpModal.classList.remove("open");
		});
	if (clearCacheBtn) clearCacheBtn.addEventListener("click", clearCache);

	if (searchBtn) {
		searchBtn.addEventListener("click", () => toggleSearch(true));
	}
	if (searchCloseBtn) {
		searchCloseBtn.addEventListener("click", () => toggleSearch(false));
	}
	if (searchInput) {
		searchInput.addEventListener("input", (e) => filterDistros(e.target.value));
		searchInput.addEventListener("keydown", (e) => {
			if (e.key === "Escape") toggleSearch(false);
		});
	}

	if (navSettings) {
		navSettings.addEventListener("click", () => toggleSearch(false));
	}

	await fetchVersion();
	await loadDistros();
}

document.addEventListener("DOMContentLoaded", init);

import { exec, spawn } from "kernelsu";
import { toast } from "kernelsu";

// DOM Elements
const mainContent = document.getElementById("main-content");
const versionText = document.getElementById("version-text");
const toastEl = document.getElementById("toast");
const maintainerCredit = document.getElementById("maintainer-credit");

// Track active terminals
const activeTerminals = new Map();

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
 * Create terminal HTML
 * @param {string} distroName
 * @returns {string}
 */
function createTerminalHTML(distroName) {
	return `
        <div class="terminal-container" id="terminal-${distroName}">
            <div class="terminal-header">
                <div class="terminal-title">
                    <div class="spinner-small" style="display: none;"></div>
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

// Icons
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

	// Generate buttons
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
                <span class="distro-name">${distro.name}</span>
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

	// Apply ripple to all action buttons
	card.querySelectorAll(".action-btn").forEach((btn) => {
		applyRipple(btn);
		btn.addEventListener("click", (e) => {
			e.stopPropagation();
			const action = btn.dataset.action;
			handleAction(distro.name, action, btn, card);
		});
	});

	// Copy button handler
	const copyBtn = card.querySelector(".copy-btn");
	if (copyBtn) {
		copyBtn.addEventListener("click", (e) => {
			e.stopPropagation();
			copyToClipboard(copyBtn.dataset.command);
		});
	}

	// Click on card content to toggle dropdowns
	cardContent.addEventListener("click", (e) => {
		if (!e.target.closest(".action-btn") && !e.target.closest(".copy-btn")) {
			toggleDropdowns(distro.name, card, isInstalled);
		}
	});

	// Terminal close button
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
		// Fallback for older browsers
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
		// Toggle command dropdown
		const commandDropdown = card.querySelector(`#command-${distroName}`);
		if (commandDropdown) {
			commandDropdown.classList.toggle("open");
		}
	} else {
		// Toggle terminal for not installed
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
			// Copy command to clipboard and show dropdown
			const command = `chroot-distro login ${distroName}`;
			await copyToClipboard(command);

			// Open command dropdown
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
	const terminalSpinner = terminal.querySelector(".spinner-small");
	const closeBtn = terminal.querySelector(".terminal-close-btn");

	// Disable buttons
	btn.disabled = true;
	const startBtn = card.querySelector('[data-action="start"]');
	if (startBtn) startBtn.disabled = true;
	const uninstallBtn = card.querySelector('[data-action="uninstall"]');
	if (uninstallBtn) uninstallBtn.disabled = true;

	closeBtn.disabled = true;
	terminalOutput.innerHTML = "";

	// Show spinner and stopping message
	terminalSpinner.style.display = "block";
	terminalTitle.textContent = `Stopping ${distroName}...`;
	terminalTitle.style.color = "";

	// Open terminal
	terminal.classList.add("open");
	setTimeout(() => {
		terminal.scrollIntoView({ behavior: "smooth", block: "nearest" });
	}, 100);

	// Add initial line
	appendTerminalLine(terminalOutput, `$ chroot-distro unmount ${distroName}`);
	appendTerminalLine(terminalOutput, "");

	try {
		const process = spawn("chroot-distro", ["unmount", distroName]);
		activeTerminals.set(distroName, process);

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

		activeTerminals.delete(distroName);

		// Verify unmount by checking running list
		const { errno, stdout } = await exec("JOSINIFY=true chroot-distro list-running");
		let stopSuccess = false;

		if (errno === 0 && stdout) {
			try {
				const data = JSON.parse(stdout.trim());
				const runningDistros = data.running_distributions || [];
				stopSuccess = !runningDistros.some((d) => d.name === distroName);
			} catch (e) {
				console.warn("Failed to parse running list:", e);
				// Fallback: assume success if exitCode is 0
				stopSuccess = exitCode === 0;
			}
		} else {
			// Fallback if list-running command fails or returns valid empty json (which errno 0 covers)
			stopSuccess = exitCode === 0;
		}

		terminalSpinner.style.display = "none";

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
		terminalSpinner.style.display = "none";
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
	const terminalSpinner = terminal.querySelector(".spinner-small");
	const closeBtn = terminal.querySelector(".terminal-close-btn");

	// Disable button and open terminal
	btn.disabled = true;
	// Animate icon
	const btnIcon = btn.querySelector("svg");
	if (btnIcon) btnIcon.classList.add("download-anim");

	closeBtn.disabled = true;
	terminalOutput.innerHTML = "";

	// Show spinner and installing message
	terminalSpinner.style.display = "block";
	terminalTitle.textContent = `Installing ${distroName}...`;
	terminalTitle.style.color = "";

	// Smooth scroll and open terminal
	terminal.classList.add("open");
	setTimeout(() => {
		terminal.scrollIntoView({ behavior: "smooth", block: "nearest" });
	}, 100);

	// Add initial line
	appendTerminalLine(terminalOutput, `$ chroot-distro install ${distroName}`);
	appendTerminalLine(terminalOutput, "");

	try {
		// Use spawn to get real-time output
		const process = spawn("chroot-distro", ["install", distroName]);
		activeTerminals.set(distroName, process);

		process.stdout.on("data", (data) => {
			appendTerminalLine(terminalOutput, data.toString());
		});

		process.stderr.on("data", (data) => {
			appendTerminalLine(terminalOutput, data.toString(), "error");
		});

		// Wait for process to complete
		const exitCode = await new Promise((resolve) => {
			process.on("exit", (code) => {
				resolve(code);
			});
			process.on("error", (err) => {
				appendTerminalLine(terminalOutput, `Error: ${err.message}`, "error");
				resolve(1);
			});
		});

		activeTerminals.delete(distroName);

		// Check if installation succeeded by verifying with JOSINIFY
		const { errno, stdout } = await exec("JOSINIFY=true chroot-distro list");
		let installSuccess = false;

		if (errno === 0 && stdout) {
			const data = JSON.parse(stdout.trim());
			const distroInfo = data.distributions?.find((d) => d.name === distroName);
			installSuccess = distroInfo?.installed === true;
		}

		// Update terminal UI
		terminalSpinner.style.display = "none";
		if (btnIcon) btnIcon.classList.remove("download-anim"); // Stop animation

		if (installSuccess) {
			terminalTitle.textContent = `${distroName} installed successfully!`;
			terminalTitle.style.color = "#4ade80";
			appendTerminalLine(terminalOutput, "", "success");
			appendTerminalLine(terminalOutput, "✓ Installation completed successfully!", "success");

			showToast(`${distroName} installed successfully!`);

			// Auto-close terminal after 2 seconds and refresh card
			setTimeout(async () => {
				terminal.classList.remove("open");
				await refreshDistroCard(distroName, card);
			}, 2000);
		} else {
			terminalTitle.textContent = `Installation failed (exit code: ${exitCode})`;
			terminalTitle.style.color = "#e94560";
			appendTerminalLine(terminalOutput, "", "error");
			appendTerminalLine(terminalOutput, `✗ Installation failed with exit code ${exitCode}`, "error");

			showToast("Installation failed", true);
			closeBtn.disabled = false;
			btn.disabled = false;
			// btn.textContent = "Install"; // Removed text reset
		}
	} catch (e) {
		console.error("Install error:", e);
		terminalSpinner.style.display = "none";
		if (btnIcon) btnIcon.classList.remove("download-anim"); // Stop animation

		terminalTitle.textContent = "Installation error";
		terminalTitle.style.color = "#e94560";
		appendTerminalLine(terminalOutput, `Error: ${e.message}`, "error");

		showToast(e.message, true);
		closeBtn.disabled = false;
		btn.disabled = false;
		// btn.textContent = "Install"; // Removed text reset
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
	const terminalSpinner = terminal.querySelector(".spinner-small");
	const closeBtn = terminal.querySelector(".terminal-close-btn");

	// Disable buttons
	btn.disabled = true;
	btn.textContent = "Removing...";
	const startBtn = card.querySelector('[data-action="start"]');
	if (startBtn) startBtn.disabled = true;

	closeBtn.disabled = true;
	terminalOutput.innerHTML = "";

	// Show spinner and removing message
	terminalSpinner.style.display = "block";
	terminalTitle.textContent = `Removing ${distroName}...`;
	terminalTitle.style.color = "";

	// Open terminal
	terminal.classList.add("open");
	setTimeout(() => {
		terminal.scrollIntoView({ behavior: "smooth", block: "nearest" });
	}, 100);

	// Add initial line
	appendTerminalLine(terminalOutput, `$ chroot-distro remove ${distroName}`);
	appendTerminalLine(terminalOutput, "");

	try {
		const process = spawn("chroot-distro", ["remove", distroName]);
		activeTerminals.set(distroName, process);

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

		activeTerminals.delete(distroName);

		// Verify removal
		const { errno, stdout } = await exec("JOSINIFY=true chroot-distro list");
		let removeSuccess = false;

		if (errno === 0 && stdout) {
			const data = JSON.parse(stdout.trim());
			const distroInfo = data.distributions?.find((d) => d.name === distroName);
			removeSuccess = distroInfo?.installed === false;
		}

		terminalSpinner.style.display = "none";

		if (removeSuccess) {
			terminalTitle.textContent = `${distroName} removed successfully!`;
			terminalTitle.style.color = "#4ade80";
			appendTerminalLine(terminalOutput, "", "success");
			appendTerminalLine(terminalOutput, "✓ Removal completed successfully!", "success");

			showToast(`${distroName} removed successfully!`);

			setTimeout(async () => {
				terminal.classList.remove("open");
				await refreshDistroCard(distroName, card);
			}, 2000);
		} else {
			terminalTitle.textContent = `Removal failed (exit code: ${exitCode})`;
			terminalTitle.style.color = "#e94560";
			appendTerminalLine(terminalOutput, "", "error");
			appendTerminalLine(terminalOutput, `✗ Removal failed with exit code ${exitCode}`, "error");

			showToast("Removal failed", true);
			closeBtn.disabled = false;
			btn.disabled = false;
			btn.textContent = "Uninstall";
			if (startBtn) startBtn.disabled = false;
		}
	} catch (e) {
		console.error("Uninstall error:", e);
		terminalSpinner.style.display = "none";
		terminalTitle.textContent = "Removal error";
		terminalTitle.style.color = "#e94560";
		appendTerminalLine(terminalOutput, `Error: ${e.message}`, "error");

		showToast(e.message, true);
		closeBtn.disabled = false;
		btn.disabled = false;
		btn.textContent = "Uninstall";
		if (startBtn) startBtn.disabled = false;
	}
}

/**
 * Append line to terminal output
 * @param {HTMLElement} output
 * @param {string} text
 * @param {string} type
 */
function appendTerminalLine(output, text, type = "") {
	const line = document.createElement("div");
	line.className = `terminal-line ${type}`;
	line.textContent = text;
	output.appendChild(line);

	// Auto-scroll to bottom
	output.scrollTop = output.scrollHeight;
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
		const distros = await fetchDistros();
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
                    <span>No distributions available</span>
                </div>
            `;
		}
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

	await fetchVersion();
	await loadDistros();

	const refreshBtn = document.getElementById("refresh-btn");
	if (refreshBtn) {
		refreshBtn.addEventListener("click", () => {
			loadDistros();
		});
	}
}

document.addEventListener("DOMContentLoaded", init);

const $ = (id) => document.getElementById(id);
let inventory = [],
  activeConfig = null,
  captureStatus = {};

const tabButtons = [...document.querySelectorAll("[data-tab]")];

// Keep the tab buttons and their panels in sync for pointer and keyboard navigation.
function activateTab(tabName, focus = false) {
  const selectedButton = tabButtons.find(
      (button) => button.dataset.tab === tabName,
    ),
    selectedPanel = selectedButton && $("panel-" + tabName);
  if (!selectedButton || !selectedPanel) return;

  for (const button of tabButtons) {
    const selected = button === selectedButton;
    button.setAttribute("aria-selected", String(selected));
    button.tabIndex = selected ? 0 : -1;
  }

  for (const panel of document.querySelectorAll('[role="tabpanel"]')) {
    const selected = panel === selectedPanel;
    panel.hidden = !selected;
    panel.classList.toggle("active", selected);
  }

  if (focus) selectedButton.focus();
}

const pendingCameraControlChanges = new Map();
let advancedPollHandle = null,
  advancedApplyHandle = null;
const advancedDialog = $("advanced-camera-dialog");

const $ = (id) => document.getElementById(id);
let inventory = [],
  activeConfig = null,
  captureStatus = {};

const tabButtons = [...document.querySelectorAll("[data-tab]")];
const pendingCameraControlChanges = new Map();
let advancedPollHandle = null,
  advancedApplyHandle = null;
const advancedDialog = $("advanced-camera-dialog");

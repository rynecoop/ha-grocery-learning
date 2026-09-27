// Versioned entry point. All panel behavior is defined before element registration.
const _moduleQuery = (() => {
  try {
    const version = new URL(import.meta.url).searchParams.get("v");
    return version ? `?v=${encodeURIComponent(version)}` : "";
  } catch (_err) {
    return "";
  }
})();

await import(`./local-list-assist-panel-core.js${_moduleQuery}`);

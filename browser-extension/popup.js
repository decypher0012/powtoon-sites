document.querySelector("#export").addEventListener("click", async () => {
  const status = document.querySelector("#status");
  const tabs = (await chrome.tabs.query({currentWindow: true}))
    .filter(tab => /^https?:\/\//.test(tab.url || ""))
    .map(tab => ({title: tab.title || "", url: tab.url, pinned: Boolean(tab.pinned)}));
  const blob = new Blob([JSON.stringify({format: "work-launcher-browser-session", tabs}, null, 2)], {type: "application/json"});
  const url = URL.createObjectURL(blob);
  await chrome.downloads.download({url, filename: "work-launcher-session.json", saveAs: true});
  status.textContent = `Exported ${tabs.length} tabs.`;
});

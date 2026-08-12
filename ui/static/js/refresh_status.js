// Generic "start a slow background refresh, then poll its status" wiring
// for any button with data-start-url / data-status-url attributes, paired
// with a sibling <span> whose id is "<button-id>" with "-btn" replaced by
// "-status". Used for the mod-weightings and priority-rankings refreshes
// on the config page.

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-start-url]').forEach(btn => {
    const statusEl = document.getElementById(btn.id.replace('-btn', '-status'));

    function poll() {
      fetch(btn.dataset.statusUrl)
        .then(r => r.json())
        .then(data => {
          if (data.status === 'running') {
            statusEl.textContent = 'Running…';
            btn.disabled = true;
            setTimeout(poll, 3000);
          } else if (data.status === 'done') {
            statusEl.textContent = 'Done.';
            btn.disabled = false;
          } else if (data.status === 'error') {
            statusEl.textContent = 'Failed — see server console for details.';
            btn.disabled = false;
          } else {
            btn.disabled = false;
          }
        });
    }

    btn.addEventListener('click', () => {
      statusEl.textContent = 'Starting…';
      btn.disabled = true;
      fetch(btn.dataset.startUrl, { method: 'POST' }).then(poll);
    });

    poll(); // pick up an in-progress refresh if the page was reloaded
  });
});

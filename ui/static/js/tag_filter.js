// Filter the character grid by tag — purely a display:none toggle on
// tiles, independent of sort order and selection state. A tile matches if
// it has ANY of the checked tags (OR across everything checked). The
// picker itself is a native <dialog> popup so it never crowds the toolbar.

document.addEventListener('DOMContentLoaded', () => {
  const toggleBtn = document.getElementById('tag-filter-toggle');
  const modal = document.getElementById('tag-filter-modal');
  const closeBtn = document.getElementById('tag-filter-close');
  const clearBtn = document.getElementById('tag-filter-clear');
  const countEl = document.getElementById('tag-filter-count');
  const grid = document.getElementById('char-grid');
  if (!toggleBtn || !modal || !grid) return;

  const tiles = Array.from(grid.querySelectorAll('.char-tile[data-tags]'));
  const tileTags = new Map(tiles.map(t => [t, new Set(JSON.parse(t.dataset.tags))]));
  const checkboxes = Array.from(modal.querySelectorAll('.tag-filter-checkbox'));

  function applyFilter() {
    const checked = checkboxes.filter(cb => cb.checked).map(cb => cb.value);

    tiles.forEach(tile => {
      const matches = checked.length === 0 || checked.some(tag => tileTags.get(tile).has(tag));
      tile.style.display = matches ? '' : 'none';
    });

    if (checked.length > 0) {
      countEl.textContent = checked.length;
      countEl.hidden = false;
    } else {
      countEl.hidden = true;
    }
  }

  toggleBtn.addEventListener('click', () => modal.showModal());
  closeBtn.addEventListener('click', () => modal.close());

  // click on the ::backdrop (the dialog element itself, outside its content box)
  modal.addEventListener('click', (e) => {
    if (e.target === modal) modal.close();
  });

  checkboxes.forEach(cb => cb.addEventListener('change', applyFilter));

  clearBtn.addEventListener('click', () => {
    checkboxes.forEach(cb => { cb.checked = false; });
    applyFilter();
  });
});

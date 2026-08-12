// Client-side re-ordering of the character grid — sorts by whatever
// pre-computed value is in each tile's data-sort-values JSON, without a
// page reload (so selection/lock state never gets disturbed).

document.addEventListener('DOMContentLoaded', () => {
  const grid = document.getElementById('char-grid');
  const select = document.getElementById('sort-select');
  const dirBtn = document.getElementById('sort-direction');
  if (!grid || !select || !dirBtn) return;

  const tiles = Array.from(grid.querySelectorAll('.char-tile[data-sort-values]'));
  const values = new Map(tiles.map(t => [t, JSON.parse(t.dataset.sortValues)]));

  function defaultDirectionFor(key) {
    return key === 'name' ? 'asc' : 'desc';
  }

  function applySort() {
    const key = select.value;
    const dir = dirBtn.dataset.dir;
    const sign = dir === 'asc' ? 1 : -1;

    const sorted = tiles.slice().sort((a, b) => {
      const va = values.get(a)[key];
      const vb = values.get(b)[key];
      if (va < vb) return -1 * sign;
      if (va > vb) return 1 * sign;
      return values.get(a).name.localeCompare(values.get(b).name);
    });

    sorted.forEach(tile => grid.appendChild(tile));
  }

  function updateDirButtonLabel() {
    dirBtn.textContent = dirBtn.dataset.dir === 'asc' ? '↑ Low to high' : '↓ High to low';
  }

  select.addEventListener('change', () => {
    dirBtn.dataset.dir = defaultDirectionFor(select.value);
    updateDirButtonLabel();
    applySort();
  });

  dirBtn.addEventListener('click', () => {
    dirBtn.dataset.dir = dirBtn.dataset.dir === 'asc' ? 'desc' : 'asc';
    updateDirButtonLabel();
    applySort();
  });

  select.value = 'name';
  dirBtn.dataset.dir = 'asc';
  updateDirButtonLabel();
  applySort();
});

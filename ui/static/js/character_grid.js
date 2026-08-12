// Three-state toggle per character tile: none -> selected -> locked -> none.
// "Locked" means the solver keeps that character's current mods untouched.

document.addEventListener('DOMContentLoaded', () => {
  const tiles = Array.from(document.querySelectorAll('.char-tile[data-char-id]'));
  const summary = document.getElementById('selection-summary');

  const NEXT_STATE = { none: 'selected', selected: 'locked', locked: 'none' };

  function setState(tile, state) {
    tile.dataset.state = state;
    tile.querySelector('input[type="hidden"]').value = state;
  }

  function cycle(tile) {
    setState(tile, NEXT_STATE[tile.dataset.state]);
    updateSummary();
  }

  function updateSummary() {
    const selected = tiles.filter(t => t.dataset.state === 'selected' || t.dataset.state === 'locked').length;
    const locked = tiles.filter(t => t.dataset.state === 'locked').length;
    if (summary) summary.textContent = `${selected} selected, ${locked} locked`;
  }

  tiles.forEach(tile => {
    tile.addEventListener('click', () => cycle(tile));
    tile.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        cycle(tile);
      }
    });
  });

  // Select-all cycles the whole grid through the same 3 states as an
  // individual tile: 1st click selects everything, 2nd locks everything,
  // 3rd clears everything, then repeats.
  const selectAllBtn = document.getElementById('select-all');
  let bulkState = 'selected';
  if (selectAllBtn) {
    selectAllBtn.addEventListener('click', () => {
      tiles.forEach(t => setState(t, bulkState));
      bulkState = NEXT_STATE[bulkState];
      updateSummary();
    });
  }

  const clearAllBtn = document.getElementById('clear-all');
  if (clearAllBtn) {
    clearAllBtn.addEventListener('click', () => {
      tiles.forEach(t => setState(t, 'none'));
      bulkState = 'selected';
      updateSummary();
    });
  }

  updateSummary();
});

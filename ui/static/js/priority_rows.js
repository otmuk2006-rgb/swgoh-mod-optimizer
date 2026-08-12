// Dynamic "add override row" UI for per-character priority overrides on the
// config page. SELECTED_CHAR_IDS / SELECTED_CHAR_NAMES are inlined by the template.

document.addEventListener('DOMContentLoaded', () => {
  const container = document.getElementById('priority-rows');
  const addBtn = document.getElementById('add-priority-row');
  if (!container || !addBtn) return;

  function addRow() {
    const row = document.createElement('div');
    row.className = 'priority-row';
    row.innerHTML = `
      <input type="text" name="priority_char" list="selected-char-list"
             placeholder="Character ID (e.g. GLLEIA)">
      <input type="number" name="priority_value" min="0" max="1" step="0.05" placeholder="0.0–1.0">
      <button type="button" class="btn btn-secondary small" data-remove>Remove</button>
    `;
    row.querySelector('[data-remove]').addEventListener('click', () => row.remove());
    container.appendChild(row);
  }

  addBtn.addEventListener('click', addRow);
});

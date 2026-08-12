// Before / after tab toggle on the character detail page.

document.addEventListener('DOMContentLoaded', () => {
  const tabs = document.querySelectorAll('.tab-btn');
  if (!tabs.length) return;

  tabs.forEach(btn => {
    btn.addEventListener('click', () => {
      const target = btn.dataset.tab;

      tabs.forEach(b => b.classList.toggle('active', b === btn));

      document.querySelectorAll('[data-tab-panel]').forEach(cell => {
        cell.hidden = cell.dataset.tabPanel !== target;
      });
    });
  });
});

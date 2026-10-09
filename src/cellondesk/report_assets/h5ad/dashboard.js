// Navigation is the only coordinator; each view owns its controls and rendering.
const tabButtons = [...document.querySelectorAll('nav [role=tab]')];
function activateTab(button) {
  tabButtons.forEach(item => {
    const active = item === button;
    item.classList.toggle('active', active);
    item.setAttribute('aria-selected', String(active));
    item.tabIndex = active ? 0 : -1;
    $(item.dataset.tab).hidden = !active;
  });
  window.scrollTo(0, 0);
}
tabButtons.forEach((button, index) => {
  button.addEventListener('click', () => activateTab(button));
  button.addEventListener('keydown', event => {
    let next;
    if (event.key === 'ArrowRight') next = (index + 1) % tabButtons.length;
    if (event.key === 'ArrowLeft') next = (index + tabButtons.length - 1) % tabButtons.length;
    if (event.key === 'Home') next = 0;
    if (event.key === 'End') next = tabButtons.length - 1;
    if (next !== undefined) { event.preventDefault(); activateTab(tabButtons[next]); tabButtons[next].focus(); }
  });
});
drawEmbedding();
drawComposition();
drawQC();

document.addEventListener("DOMContentLoaded", () => {
  const search = document.getElementById("knowledgeSearch");
  const filters = [...document.querySelectorAll(".knowledge-filter")];
  const cards = [...document.querySelectorAll(".knowledge-result")];
  const noResults = document.getElementById("knowledgeNoResults");
  if (!search || !filters.length || !cards.length || !noResults) return;

  let activeFilter = "all";
  function render() {
    const query = search.value.trim().toLowerCase();
    let visible = 0;
    cards.forEach((card) => {
      const matchesFilter = activeFilter === "all" || card.dataset.domain === activeFilter;
      const matchesSearch = card.textContent.toLowerCase().includes(query);
      const show = matchesFilter && matchesSearch;
      card.hidden = !show;
      if (show) visible += 1;
    });
    noResults.hidden = visible > 0;
  }

  filters.forEach((button) => {
    button.addEventListener("click", () => {
      activeFilter = button.dataset.filter;
      filters.forEach((item) => {
        const selected = item === button;
        item.classList.toggle("active", selected);
        item.setAttribute("aria-pressed", String(selected));
      });
      render();
    });
  });
  search.addEventListener("input", render);
});

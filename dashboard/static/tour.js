// Guided tour of the top navigation. Starts when the page URL has ?tour=1.
(function () {
  if (!new URLSearchParams(window.location.search).has("tour")) return;

  const steps = [
    ["overview", "Overview", "Your home page. It shows how many jobs were found and applied to, and what is still left to set up."],
    ["cv", "CV", "Upload your CV here. The tool reads your skills from it."],
    ["profile", "Profile", "Your details. Check the skills list, because it decides which jobs match you."],
    ["roles", "Roles", "The job titles you want. Add, change or switch them off at any time."],
    ["answers", "Answers", "Saved answers for the questions recruiters ask while applying."],
    ["jobs", "Jobs", "Every job the tool finds, with its match score and what happened to it."],
    ["settings", "Settings", "Your Google Sheet link and the daily apply limit."],
  ];

  let index = 0;

  const backdrop = document.createElement("div");
  backdrop.className = "tour-backdrop";

  const pop = document.createElement("div");
  pop.className = "tour-pop";
  pop.setAttribute("role", "dialog");
  pop.setAttribute("aria-labelledby", "tour-title");

  const count = document.createElement("span");
  count.className = "tour-count";
  const title = document.createElement("h2");
  title.id = "tour-title";
  const text = document.createElement("p");
  const buttons = document.createElement("div");
  buttons.className = "tour-buttons";

  const skip = button("Skip tour", "link", end);
  const back = button("Back", "btn ghost", () => show(index - 1));
  const next = button("Next", "btn", () => (index === steps.length - 1 ? end() : show(index + 1)));
  buttons.append(skip, back, next);
  pop.append(count, title, text, buttons);

  function button(label, className, onClick) {
    const element = document.createElement("button");
    element.type = "button";
    element.className = className;
    element.textContent = label;
    element.addEventListener("click", onClick);
    return element;
  }

  function clearTarget() {
    document.querySelectorAll(".tour-target").forEach((node) => node.classList.remove("tour-target"));
  }

  function place() {
    const target = document.querySelector(".tour-target");
    if (!target) return;
    const rect = target.getBoundingClientRect();
    const maxLeft = document.documentElement.clientWidth - pop.offsetWidth - 16;
    pop.style.top = `${rect.bottom + window.scrollY + 12}px`;
    pop.style.left = `${Math.max(16, Math.min(rect.left + window.scrollX, maxLeft))}px`;
  }

  function show(newIndex) {
    index = newIndex;
    const [key, heading, body] = steps[index];
    const target = document.querySelector(`[data-tour="${key}"]`);
    if (!target) return end();

    clearTarget();
    target.classList.add("tour-target");
    count.textContent = `${index + 1} of ${steps.length}`;
    title.textContent = heading;
    text.textContent = body;
    back.hidden = index === 0;
    next.textContent = index === steps.length - 1 ? "Finish" : "Next";
    place();
    next.focus();
  }

  function onKey(event) {
    if (event.key === "Escape") end();
  }

  function end() {
    clearTarget();
    document.body.classList.remove("tour-on");
    backdrop.remove();
    pop.remove();
    window.removeEventListener("resize", place);
    document.removeEventListener("keydown", onKey);
    // Drop ?tour=1 so a reload does not start the tour again.
    window.history.replaceState(null, "", window.location.pathname);
  }

  backdrop.addEventListener("click", end);
  window.addEventListener("resize", place);
  document.addEventListener("keydown", onKey);
  document.body.classList.add("tour-on");
  document.body.append(backdrop, pop);
  show(0);
})();

// Theme toggle and motion. Everything here is decoration: with this file missing the pages
// still work, in the light theme, with nothing hidden.
(function () {
  const root = document.documentElement;
  const THEME_KEY = "nja-theme";

  // --- light / dark toggle (the choice is remembered in this browser) ---
  const toggle = document.querySelector("[data-theme-toggle]");
  function showTheme(theme) {
    if (theme === "dark") root.dataset.theme = "dark";
    else delete root.dataset.theme;
    if (!toggle) return;
    const label = theme === "dark" ? "Switch to light theme" : "Switch to dark theme";
    toggle.setAttribute("aria-label", label);
    toggle.setAttribute("aria-pressed", String(theme === "dark"));
    toggle.title = label;
  }
  showTheme(root.dataset.theme === "dark" ? "dark" : "light");
  if (toggle) {
    toggle.addEventListener("click", () => {
      const next = root.dataset.theme === "dark" ? "light" : "dark";
      root.classList.add("theme-switching");
      showTheme(next);
      try {
        localStorage.setItem(THEME_KEY, next);
      } catch (error) {
        // Private windows may refuse storage; the theme then lasts for this page only.
      }
      window.setTimeout(() => root.classList.remove("theme-switching"), 400);
    });
  }

  // --- sending a form: the button shows it is working until the next page arrives ---
  document.addEventListener("submit", (event) => {
    const button = event.submitter || event.target.querySelector("button");
    if (button && button.classList.contains("btn")) {
      // Not disabled: a disabled button would drop its own name and value from the form.
      button.classList.add("busy");
      button.setAttribute("aria-busy", "true");
    }
  });

  // --- "Copy" buttons: <button data-copy="id-of-the-text-box"> ---
  document.addEventListener("click", (event) => {
    const button = event.target.closest ? event.target.closest("[data-copy]") : null;
    if (!button) return;
    const source = document.getElementById(button.dataset.copy);
    if (!source) return;
    const done = () => {
      const label = button.textContent;
      button.textContent = "Copied";
      window.setTimeout(() => (button.textContent = label), 2000);
    };
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(source.value).then(done, () => source.select());
    } else {
      source.select(); // no clipboard access: the text is selected, ready for Ctrl+C
    }
  });

  // Coming back with the browser's Back button must not show a button still "working".
  window.addEventListener("pageshow", (event) => {
    if (!event.persisted) return;
    document.querySelectorAll(".btn.busy").forEach((button) => {
      button.classList.remove("busy");
      button.removeAttribute("aria-busy");
    });
  });

  // --- "Saved." folds away after a few seconds; errors and warnings stay ---
  const saved = document.querySelector(".banner.ok");
  if (saved) {
    window.setTimeout(() => {
      saved.style.height = `${saved.offsetHeight}px`; // a fixed starting height, so it can glide to 0
      window.requestAnimationFrame(() => saved.classList.add("leaving"));
      window.setTimeout(() => saved.remove(), 500);
    }, 6000);
  }

  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

  // A page that reloads itself every few seconds (search or apply in progress) would replay
  // every entrance again and again, so it gets none.
  const reloading = Boolean(document.querySelector('meta[http-equiv="refresh"]'));
  window.addEventListener("pagereveal", (event) => {
    if (reloading && event.viewTransition) event.viewTransition.skipTransition();
  });

  // --- scrolling: panels rise into place as they come into view ---
  if (!reloading && "IntersectionObserver" in window) {
    const panels = document.querySelectorAll(".page > h1, .page > .lead, .page > .empty, .card, .tile");
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          const panel = entry.target;
          panel.classList.add("in-view");
          observer.unobserve(panel);
          // Once it has arrived, drop the entrance classes so the panel's own hover motion
          // is not slowed down by the entrance timing.
          window.setTimeout(() => {
            panel.classList.remove("reveal", "in-view");
            panel.style.removeProperty("--reveal-delay");
          }, 1300);
        }
      },
      // threshold 0: any sliver counts. A share of the panel would never be reached by a very
      // tall one (a long jobs table), which would then stay invisible.
      { rootMargin: "0px 0px -6% 0px", threshold: 0 }
    );
    root.classList.add("reveal-on");
    let inFirstScreen = 0;
    panels.forEach((panel) => {
      panel.classList.add("reveal");
      // Only what is on screen at load is staggered; panels reached by scrolling appear at once.
      if (panel.getBoundingClientRect().top < window.innerHeight) {
        panel.style.setProperty("--reveal-delay", `${Math.min(inFirstScreen++, 8) * 55}ms`);
      }
      observer.observe(panel);
    });
  }

  // --- scrolling: the top bar firms up once the page has moved ---
  const bar = document.querySelector(".topbar");
  if (bar) {
    const onScroll = () => bar.classList.toggle("scrolled", window.scrollY > 8);
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  // --- pointer: a soft light follows the cursor across the panel under it ---
  if (window.matchMedia("(hover: hover) and (pointer: fine)").matches) {
    let pending = null;
    document.addEventListener(
      "pointermove",
      (event) => {
        pending = event;
        window.requestAnimationFrame(() => {
          if (!pending) return;
          const panel = pending.target.closest ? pending.target.closest(".card, .tile") : null;
          if (panel) {
            const box = panel.getBoundingClientRect();
            panel.style.setProperty("--mx", `${pending.clientX - box.left}px`);
            panel.style.setProperty("--my", `${pending.clientY - box.top}px`);
          }
          pending = null;
        });
      },
      { passive: true }
    );
  }

  // --- overview numbers count up to their value ---
  if (!reloading) {
    document.querySelectorAll(".tile-value").forEach((tile) => {
      const node = tile.firstChild;
      if (!node || node.nodeType !== Node.TEXT_NODE) return;
      const target = parseInt(node.textContent, 10);
      if (!Number.isFinite(target) || target <= 0) return;
      const tail = node.textContent.replace(/^\s*\d+/, "");
      const started = performance.now();
      const duration = 700;
      const step = (now) => {
        const progress = Math.min(1, (now - started) / duration);
        const eased = 1 - Math.pow(1 - progress, 3);
        node.textContent = `${Math.round(target * eased)}${tail}`;
        if (progress < 1) window.requestAnimationFrame(step);
      };
      window.requestAnimationFrame(step);
    });
  }
})();

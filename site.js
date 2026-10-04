(() => {
  "use strict";

  document.documentElement.classList.add("js");

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const clock = document.getElementById("desktop-clock");
  const updateClock = () => {
    if (!clock) return;
    clock.textContent = new Intl.DateTimeFormat([], {
      hour: "2-digit",
      minute: "2-digit"
    }).format(new Date());
  };
  updateClock();
  window.setInterval(updateClock, 30000);

  document.querySelectorAll("[data-scroll-target]").forEach((button) => {
    button.addEventListener("click", () => {
      const target = document.querySelector(button.dataset.scrollTarget || "");
      if (target) {
        target.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "start" });
      }
    });
  });

  const stage = document.getElementById("desktop-stage");
  if (stage && !reducedMotion) {
    stage.addEventListener("pointermove", (event) => {
      const rect = stage.getBoundingClientRect();
      const x = Math.max(0, Math.min(100, ((event.clientX - rect.left) / rect.width) * 100));
      const y = Math.max(0, Math.min(100, ((event.clientY - rect.top) / rect.height) * 100));
      stage.style.setProperty("--pointer-x", `${x}%`);
      stage.style.setProperty("--pointer-y", `${y}%`);
    });
  }

  const heroMochi = document.getElementById("hero-mochi");
  const heroMochiImg = document.getElementById("hero-mochi-img");
  const heroSpeech = document.getElementById("hero-speech");
  const heroIdle = "animation-gifs/idle.gif";
  const heroPhrases = [
    "hi. i live here now.",
    "double-click energy, single-click budget.",
    "i have no productivity advice for you.",
    "you can move me. i will allow it.",
    "did you save your work?",
    "linux is my natural habitat."
  ];
  const reactions = [
    { src: "animation-gifs/bounce.gif", alt: "Mochi bouncing", duration: 1100 },
    { src: "animation-gifs/squish.gif", alt: "Mochi squishing", duration: 1000 }
  ];
  let heroReactionTimer = null;
  let phraseIndex = 0;

  const setHeroReaction = () => {
    if (!heroMochiImg || !heroSpeech) return;
    const reaction = reactions[Math.floor(Math.random() * reactions.length)];
    heroMochiImg.src = `${reaction.src}?r=${Date.now()}`;
    heroMochiImg.alt = reaction.alt;
    phraseIndex = (phraseIndex + 1) % heroPhrases.length;
    heroSpeech.textContent = heroPhrases[phraseIndex];

    window.clearTimeout(heroReactionTimer);
    heroReactionTimer = window.setTimeout(() => {
      heroMochiImg.src = heroIdle;
      heroMochiImg.alt = "Mochi idling";
    }, reaction.duration);
  };

  if (heroMochi && stage) {
    let pointerId = null;
    let startX = 0;
    let startY = 0;
    let startLeft = 0;
    let startTop = 0;
    let moved = false;

    heroMochi.addEventListener("pointerdown", (event) => {
      if (event.button !== undefined && event.button !== 0) return;
      pointerId = event.pointerId;
      moved = false;
      const mochiRect = heroMochi.getBoundingClientRect();
      const stageRect = stage.getBoundingClientRect();
      startX = event.clientX;
      startY = event.clientY;
      startLeft = mochiRect.left - stageRect.left;
      startTop = mochiRect.top - stageRect.top;
      heroMochi.setPointerCapture(pointerId);
    });

    heroMochi.addEventListener("pointermove", (event) => {
      if (pointerId !== event.pointerId) return;
      const dx = event.clientX - startX;
      const dy = event.clientY - startY;
      if (!moved && Math.hypot(dx, dy) < 6) return;
      moved = true;
      heroMochi.classList.add("dragging");

      const stageRect = stage.getBoundingClientRect();
      const width = heroMochi.offsetWidth;
      const height = heroMochi.offsetHeight;
      const nextLeft = Math.max(0, Math.min(stageRect.width - width, startLeft + dx));
      const nextTop = Math.max(0, Math.min(stageRect.height - height, startTop + dy));

      heroMochi.style.left = `${nextLeft}px`;
      heroMochi.style.top = `${nextTop}px`;
      heroMochi.style.bottom = "auto";
    });

    const finishPointer = (event) => {
      if (pointerId !== event.pointerId) return;
      if (heroMochi.hasPointerCapture(pointerId)) {
        heroMochi.releasePointerCapture(pointerId);
      }
      heroMochi.classList.remove("dragging");
      pointerId = null;
      if (!moved) setHeroReaction();
    };

    heroMochi.addEventListener("pointerup", finishPointer);
    heroMochi.addEventListener("pointercancel", finishPointer);
    heroMochi.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        setHeroReaction();
      }
    });
  }

  const pocketDropzone = document.getElementById("pocket-dropzone");
  const pocketList = document.getElementById("pocket-list");
  const pocketCount = document.getElementById("pocket-count");
  const pocketWindowTitle = document.getElementById("pocket-window-title");
  const pocketClear = document.getElementById("pocket-clear");
  const pocketStatus = document.getElementById("pocket-status");
  const pocketMochiImg = document.getElementById("pocket-mochi-img");
  const pocketItems = [];
  let pocketAnimationTimer = null;

  const renderPocket = () => {
    const count = pocketItems.length;
    if (pocketCount) pocketCount.textContent = `Pocket · ${count}`;
    if (pocketWindowTitle) pocketWindowTitle.textContent = `Pocket · ${count}`;
    if (pocketClear) pocketClear.disabled = count === 0;
    if (!pocketList) return;

    pocketList.replaceChildren();
    if (count === 0) {
      const empty = document.createElement("p");
      empty.className = "empty-pocket";
      empty.innerHTML = "Nothing here yet.<br><span>Mochi has room for ten things in the real app.</span>";
      pocketList.appendChild(empty);
      return;
    }

    pocketItems.forEach((name, index) => {
      const row = document.createElement("div");
      row.className = "pocket-row";

      const type = document.createElement("span");
      type.className = "mini-type";
      type.textContent = name.endsWith("/") ? "DIR" : name.includes("://") || name.includes("dev.to") ? "URL" : "FILE";

      const label = document.createElement("span");
      label.textContent = name;
      label.title = name;

      const remove = document.createElement("button");
      remove.type = "button";
      remove.setAttribute("aria-label", `Remove ${name} from demo Pocket`);
      remove.textContent = "×";
      remove.addEventListener("click", () => {
        pocketItems.splice(index, 1);
        renderPocket();
      });

      row.append(type, label, remove);
      pocketList.appendChild(row);
    });
  };

  const animatePocketMochi = (status) => {
    if (!pocketMochiImg || !pocketStatus) return;
    pocketMochiImg.src = `animation-gifs/bounce.gif?r=${Date.now()}`;
    pocketMochiImg.alt = "Mochi reacting to a Pocket item";
    pocketStatus.textContent = status;
    window.clearTimeout(pocketAnimationTimer);
    pocketAnimationTimer = window.setTimeout(() => {
      pocketMochiImg.src = "animation-gifs/idle.gif";
      pocketMochiImg.alt = "Mochi waiting for a Pocket item";
      pocketStatus.textContent = "drop something on Mochi";
    }, 1200);
  };

  const addPocketItem = (rawName) => {
    const name = String(rawName || "").trim();
    if (!name) return;

    if (pocketItems.includes(name)) {
      animatePocketMochi("already holding that one");
      return;
    }

    if (pocketItems.length >= 5) {
      pocketItems.shift();
    }
    pocketItems.push(name);
    renderPocket();
    animatePocketMochi(`kept ${name}`);
  };

  document.querySelectorAll(".fake-file").forEach((card) => {
    const name = card.dataset.pocketItem || "item";

    card.addEventListener("dragstart", (event) => {
      if (!event.dataTransfer) return;
      event.dataTransfer.effectAllowed = "copy";
      event.dataTransfer.setData("text/plain", name);
    });

    const addButton = card.querySelector(".add-pocket-button");
    if (addButton) {
      addButton.addEventListener("click", () => addPocketItem(name));
    }

    card.addEventListener("keydown", (event) => {
      if ((event.key === "Enter" || event.key === " ") && event.target === card) {
        event.preventDefault();
        addPocketItem(name);
      }
    });
  });

  if (pocketDropzone) {
    const enter = (event) => {
      event.preventDefault();
      pocketDropzone.classList.add("drag-over");
      if (event.dataTransfer) event.dataTransfer.dropEffect = "copy";
    };

    pocketDropzone.addEventListener("dragenter", enter);
    pocketDropzone.addEventListener("dragover", enter);
    pocketDropzone.addEventListener("dragleave", (event) => {
      if (!pocketDropzone.contains(event.relatedTarget)) {
        pocketDropzone.classList.remove("drag-over");
      }
    });

    pocketDropzone.addEventListener("drop", (event) => {
      event.preventDefault();
      pocketDropzone.classList.remove("drag-over");
      const files = Array.from(event.dataTransfer?.files || []);
      if (files.length) {
        files.slice(0, 5).forEach((file) => addPocketItem(file.name));
        return;
      }
      addPocketItem(event.dataTransfer?.getData("text/plain"));
    });
  }

  if (pocketClear) {
    pocketClear.addEventListener("click", () => {
      pocketItems.length = 0;
      renderPocket();
      if (pocketStatus) pocketStatus.textContent = "Pocket cleared";
    });
  }

  renderPocket();

  const emotePreview = document.getElementById("emote-preview");
  const emoteName = document.getElementById("emote-name");
  document.querySelectorAll(".emote-button").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".emote-button").forEach((candidate) => {
        candidate.classList.toggle("active", candidate === button);
      });
      if (emotePreview) {
        const src = button.dataset.src || "animation-gifs/idle.gif";
        emotePreview.src = `${src}?r=${Date.now()}`;
        emotePreview.alt = `Mochi ${button.dataset.emote || "animation"} preview`;
      }
      if (emoteName) emoteName.textContent = button.dataset.emote || "idle";
    });
  });

  const copyButton = document.getElementById("copy-install");
  const copyStatus = document.getElementById("copy-status");
  const installText = [
    "git clone https://github.com/miflow13/mochi-desktop.git",
    "cd mochi-desktop",
    "./install.sh"
  ].join("\n");

  const fallbackCopy = (text) => {
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "absolute";
    textarea.style.left = "-9999px";
    document.body.appendChild(textarea);
    textarea.select();
    const copied = document.execCommand("copy");
    textarea.remove();
    return copied;
  };

  if (copyButton) {
    copyButton.addEventListener("click", async () => {
      let copied = false;
      try {
        if (navigator.clipboard?.writeText) {
          await navigator.clipboard.writeText(installText);
          copied = true;
        } else {
          copied = fallbackCopy(installText);
        }
      } catch {
        copied = fallbackCopy(installText);
      }

      if (copyStatus) {
        copyStatus.textContent = copied ? "copied ✓" : "select the commands above to copy";
        window.setTimeout(() => {
          copyStatus.textContent = "current main · v0.4 alpha line";
        }, 1800);
      }
    });
  }

  const revealNodes = Array.from(document.querySelectorAll(".reveal"));
  if (reducedMotion || !("IntersectionObserver" in window)) {
    revealNodes.forEach((node) => node.classList.add("visible"));
  } else {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("visible");
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12 }
    );
    revealNodes.forEach((node) => observer.observe(node));
  }
})();

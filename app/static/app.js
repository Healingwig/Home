/* Interacciones del recetario: checklist persistente, temporizadores,
   modo cocina a pantalla completa y pantalla siempre encendida. */

(() => {
  "use strict";

  const article = document.querySelector(".recipe");
  const recipeId = article?.dataset.recipeId;

  // --- Refresco automático mientras se procesa la receta -------------------
  const pending = document.querySelector("[data-poll]");
  if (pending) {
    setTimeout(() => window.location.reload(), 5000);
  }

  const toast = (message) => {
    const el = document.createElement("div");
    el.className = "toast";
    el.textContent = message;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 2600);
  };

  // --- Checklist persistida en el propio dispositivo -----------------------
  if (recipeId) {
    const storageKey = `receta:${recipeId}:marcados`;
    let checked = new Set();
    try {
      checked = new Set(JSON.parse(localStorage.getItem(storageKey) || "[]"));
    } catch (_) { /* almacenamiento no disponible o corrupto */ }

    document.querySelectorAll("[data-check]").forEach((input) => {
      const key = input.dataset.check;
      input.checked = checked.has(key);
      input.closest(".step")?.classList.toggle("done", input.checked);
      input.addEventListener("change", () => {
        input.checked ? checked.add(key) : checked.delete(key);
        input.closest(".step")?.classList.toggle("done", input.checked);
        try {
          localStorage.setItem(storageKey, JSON.stringify([...checked]));
        } catch (_) { /* modo privado */ }
      });
    });
  }

  // --- Copiar la lista de la compra ---------------------------------------
  const copyButton = document.getElementById("copy-shopping");
  const shoppingNode = document.getElementById("shopping-data");
  if (copyButton && shoppingNode) {
    copyButton.addEventListener("click", async () => {
      const text = JSON.parse(shoppingNode.textContent);
      try {
        await navigator.clipboard.writeText(text);
        toast("Lista copiada al portapapeles");
      } catch (_) {
        window.prompt("Copia la lista:", text);
      }
    });
  }

  // --- Temporizadores ------------------------------------------------------
  let alarmContext = null;
  const beep = () => {
    try {
      alarmContext = alarmContext || new (window.AudioContext || window.webkitAudioContext)();
      const now = alarmContext.currentTime;
      [0, 0.35, 0.7].forEach((offset) => {
        const osc = alarmContext.createOscillator();
        const gain = alarmContext.createGain();
        osc.frequency.value = 880;
        gain.gain.setValueAtTime(0.001, now + offset);
        gain.gain.exponentialRampToValueAtTime(0.25, now + offset + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.001, now + offset + 0.25);
        osc.connect(gain).connect(alarmContext.destination);
        osc.start(now + offset);
        osc.stop(now + offset + 0.3);
      });
    } catch (_) { /* sin audio disponible */ }
    if (navigator.vibrate) navigator.vibrate([300, 150, 300]);
  };

  const formatClock = (seconds) => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${String(s).padStart(2, "0")}`;
  };

  const startCountdown = (seconds, render, onDone) => {
    let remaining = seconds;
    render(formatClock(remaining));
    const handle = setInterval(() => {
      remaining -= 1;
      if (remaining <= 0) {
        clearInterval(handle);
        render("¡Listo!");
        beep();
        onDone?.();
        return;
      }
      render(formatClock(remaining));
    }, 1000);
    return handle;
  };

  document.querySelectorAll("button.timer").forEach((button) => {
    const seconds = Number(button.dataset.seconds);
    const label = button.textContent;
    let handle = null;
    button.addEventListener("click", () => {
      if (handle) {
        clearInterval(handle);
        handle = null;
        button.textContent = label;
        return;
      }
      handle = startCountdown(seconds, (text) => { button.textContent = `⏲ ${text}`; }, () => {
        handle = null;
        setTimeout(() => { button.textContent = label; }, 8000);
      });
    });
  });

  // --- Modo cocina ---------------------------------------------------------
  const overlay = document.getElementById("cook-overlay");
  const stepsNode = document.getElementById("steps-data");
  if (!overlay || !stepsNode) return;

  const steps = JSON.parse(stepsNode.textContent);
  if (!steps.length) return;

  const nodes = {
    title: document.getElementById("cook-title"),
    instruction: document.getElementById("cook-instruction"),
    ingredients: document.getElementById("cook-ingredients"),
    tip: document.getElementById("cook-tip"),
    progress: document.getElementById("cook-progress"),
    timer: document.getElementById("cook-timer"),
    timerValue: document.getElementById("cook-timer-value"),
    timerStart: document.getElementById("cook-timer-start"),
  };

  let index = 0;
  let wakeLock = null;
  let cookTimer = null;

  const requestWakeLock = async () => {
    try {
      wakeLock = await navigator.wakeLock?.request("screen");
    } catch (_) { /* el navegador puede denegarlo */ }
  };

  const releaseWakeLock = () => {
    wakeLock?.release?.().catch(() => {});
    wakeLock = null;
  };

  const render = () => {
    const step = steps[index];
    nodes.title.textContent = `${step.number}. ${step.title}`;
    nodes.instruction.textContent = step.instruction;
    nodes.ingredients.textContent = (step.ingredients || []).join(" · ");
    nodes.tip.textContent = step.tip ? `💡 ${step.tip}` : "";
    nodes.progress.textContent = `Paso ${index + 1} de ${steps.length}`;

    clearInterval(cookTimer);
    cookTimer = null;
    if (step.timer_seconds) {
      nodes.timer.hidden = false;
      nodes.timerValue.textContent = formatClock(step.timer_seconds);
      nodes.timerStart.textContent = "Iniciar";
    } else {
      nodes.timer.hidden = true;
    }
  };

  const move = (delta) => {
    index = Math.min(steps.length - 1, Math.max(0, index + delta));
    render();
  };

  const open = () => {
    overlay.hidden = false;
    document.body.style.overflow = "hidden";
    render();
    requestWakeLock();
  };

  const close = () => {
    overlay.hidden = true;
    document.body.style.overflow = "";
    clearInterval(cookTimer);
    releaseWakeLock();
  };

  document.getElementById("cook-mode").addEventListener("click", open);
  document.getElementById("cook-close").addEventListener("click", close);
  document.getElementById("cook-prev").addEventListener("click", () => move(-1));
  document.getElementById("cook-next").addEventListener("click", () => {
    if (index === steps.length - 1) return close();
    move(1);
  });

  nodes.timerStart.addEventListener("click", () => {
    if (cookTimer) {
      clearInterval(cookTimer);
      cookTimer = null;
      nodes.timerStart.textContent = "Iniciar";
      nodes.timerValue.textContent = formatClock(steps[index].timer_seconds);
      return;
    }
    nodes.timerStart.textContent = "Parar";
    cookTimer = startCountdown(
      steps[index].timer_seconds,
      (text) => { nodes.timerValue.textContent = text; },
      () => { cookTimer = null; nodes.timerStart.textContent = "Iniciar"; },
    );
  });

  document.addEventListener("keydown", (event) => {
    if (overlay.hidden) return;
    if (event.key === "ArrowRight" || event.key === " ") { event.preventDefault(); move(1); }
    if (event.key === "ArrowLeft") move(-1);
    if (event.key === "Escape") close();
  });

  // Deslizar entre pasos con el dedo (útil con las manos llenas de harina).
  let touchStartX = null;
  overlay.addEventListener("touchstart", (event) => { touchStartX = event.changedTouches[0].clientX; }, { passive: true });
  overlay.addEventListener("touchend", (event) => {
    if (touchStartX === null) return;
    const delta = event.changedTouches[0].clientX - touchStartX;
    if (Math.abs(delta) > 60) move(delta < 0 ? 1 : -1);
    touchStartX = null;
  }, { passive: true });

  // iOS suelta el wake lock al volver de otra app.
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && !overlay.hidden) requestWakeLock();
  });
})();

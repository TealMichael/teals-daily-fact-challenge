from __future__ import annotations

"""Reusable student widgets for interactive curriculum questions.

v2.24.0 adds a touch-friendly drag-to-order component while keeping all
question values in Python/Streamlit state. The component receives labels only;
it never handles student identity, names, or external data.
"""

from functools import lru_cache
from collections import Counter

import streamlit as st

from curriculum_question_types import clean_text


_ORDER_HTML = """
<div class="tdfc-order-wrap">
  <div id="tdfc-order-instruction" class="tdfc-order-instruction"></div>
  <div id="tdfc-order-list" class="tdfc-order-list" role="list" aria-label="Draggable number tiles"></div>
  <div class="tdfc-order-hint">Drag the tiles. Keyboard: focus a tile and use arrow keys.</div>
</div>
"""

_ORDER_CSS = """
.tdfc-order-wrap {
  width: 100%;
  font-family: var(--st-font);
  color: var(--st-text-color);
}
.tdfc-order-instruction {
  font-size: 0.98rem;
  font-weight: 650;
  margin: 0 0 0.55rem 0;
}
.tdfc-order-list {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.65rem;
  min-height: 3.7rem;
  padding: 0.6rem;
  border: 1px solid color-mix(in srgb, var(--st-text-color) 18%, transparent);
  border-radius: 0.75rem;
  background: color-mix(in srgb, var(--st-secondary-background-color) 70%, transparent);
}
.tdfc-order-tile {
  appearance: none;
  border: 2px solid color-mix(in srgb, var(--st-primary-color) 62%, var(--st-text-color));
  border-radius: 0.72rem;
  background: var(--st-background-color);
  color: var(--st-text-color);
  min-width: 5.1rem;
  min-height: 3.15rem;
  padding: 0.62rem 0.9rem;
  font-family: var(--st-font);
  font-size: 1.22rem;
  font-weight: 750;
  line-height: 1;
  text-align: center;
  cursor: grab;
  user-select: none;
  touch-action: none;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}
.tdfc-order-tile:focus-visible {
  outline: 3px solid var(--st-primary-color);
  outline-offset: 2px;
}
.tdfc-order-tile.is-dragging {
  cursor: grabbing;
  opacity: 0.78;
  transform: scale(1.035);
  box-shadow: 0 5px 14px rgba(0,0,0,0.16);
}
.tdfc-order-hint {
  font-size: 0.78rem;
  opacity: 0.72;
  margin-top: 0.42rem;
}
@media (max-width: 640px) {
  .tdfc-order-list { gap: 0.5rem; padding: 0.5rem; }
  .tdfc-order-tile {
    min-width: 4.65rem;
    min-height: 3rem;
    padding: 0.58rem 0.7rem;
    font-size: 1.12rem;
  }
}
"""

_ORDER_JS = r"""
export default function({ parentElement, data, setStateValue }) {
  const list = parentElement.querySelector("#tdfc-order-list");
  const instruction = parentElement.querySelector("#tdfc-order-instruction");
  const requested = Array.isArray(data?.items) ? data.items.map((value) => String(value)) : [];
  instruction.textContent = data?.instruction ? String(data.instruction) : "Drag the tiles into order.";

  function currentOrder() {
    return Array.from(list.querySelectorAll(".tdfc-order-tile")).map((tile) => tile.dataset.value || "");
  }

  function emitOrder() {
    setStateValue("order", currentOrder());
  }

  function sameOrder(a, b) {
    if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length) return false;
    return a.every((value, index) => String(value) === String(b[index]));
  }

  function repositionFromPointer(active, clientX, clientY) {
    const siblings = Array.from(list.querySelectorAll(".tdfc-order-tile")).filter((el) => el !== active);
    let before = null;
    for (const sibling of siblings) {
      const rect = sibling.getBoundingClientRect();
      const rowMid = rect.top + rect.height / 2;
      const colMid = rect.left + rect.width / 2;
      if (clientY < rowMid || (clientY <= rect.bottom && clientX < colMid)) {
        before = sibling;
        break;
      }
    }
    if (before) list.insertBefore(active, before);
    else list.appendChild(active);
  }

  function wireTile(tile) {
    let activePointer = null;

    tile.addEventListener("pointerdown", (event) => {
      if (event.button !== undefined && event.button !== 0) return;
      activePointer = event.pointerId;
      tile.classList.add("is-dragging");
      try { tile.setPointerCapture(event.pointerId); } catch (_) {}
      event.preventDefault();
    });

    tile.addEventListener("pointermove", (event) => {
      if (activePointer !== event.pointerId) return;
      repositionFromPointer(tile, event.clientX, event.clientY);
      event.preventDefault();
    });

    const finishPointer = (event) => {
      if (activePointer !== event.pointerId) return;
      tile.classList.remove("is-dragging");
      try { tile.releasePointerCapture(event.pointerId); } catch (_) {}
      activePointer = null;
      emitOrder();
      event.preventDefault();
    };
    tile.addEventListener("pointerup", finishPointer);
    tile.addEventListener("pointercancel", finishPointer);

    tile.addEventListener("keydown", (event) => {
      const previous = tile.previousElementSibling;
      const next = tile.nextElementSibling;
      if ((event.key === "ArrowLeft" || event.key === "ArrowUp") && previous) {
        list.insertBefore(tile, previous);
        emitOrder();
        tile.focus();
        event.preventDefault();
      } else if ((event.key === "ArrowRight" || event.key === "ArrowDown") && next) {
        list.insertBefore(next, tile);
        emitOrder();
        tile.focus();
        event.preventDefault();
      }
    });
  }

  const rendered = currentOrder();
  if (!sameOrder(rendered, requested)) {
    list.replaceChildren();
    requested.forEach((label, index) => {
      const tile = document.createElement("button");
      tile.type = "button";
      tile.className = "tdfc-order-tile";
      tile.dataset.value = label;
      tile.dataset.tileIndex = String(index);
      tile.setAttribute("role", "listitem");
      tile.setAttribute("aria-label", `Number tile ${label}. Drag or use arrow keys to reorder.`);
      tile.textContent = label;
      wireTile(tile);
      list.appendChild(tile);
    });
  }
}
"""


def _same_multiset(left, right) -> bool:
    try:
        return Counter(clean_text(item) for item in left) == Counter(clean_text(item) for item in right)
    except Exception:
        return False


@lru_cache(maxsize=1)
def _order_component():
    components = getattr(st, "components", None)
    v2 = getattr(components, "v2", None)
    factory = getattr(v2, "component", None)
    if not callable(factory):
        return None
    return factory(
        name="tdfc_order_tiles",
        html=_ORDER_HTML,
        css=_ORDER_CSS,
        js=_ORDER_JS,
    )


def render_order_tiles(
    items,
    *,
    key: str,
    initial_order=None,
    instruction: str = "Drag the tiles into order.",
) -> list[str]:
    """Render a persistent drag-to-order widget and return the current order."""
    original = [str(item or "").strip() for item in items]
    initial = [str(item or "").strip() for item in (initial_order or original)]
    if len(initial) != len(original) or not _same_multiset(initial, original):
        initial = list(original)

    renderer = _order_component()
    if renderer is None:
        # The production app is pinned to Streamlit 1.61.1, which includes
        # components v2. This fallback keeps imports/tests safe on older tools.
        st.warning("Drag-to-order is unavailable in this browser session. Refresh the page and try again.")
        return initial

    state = st.session_state.get(key, {})
    current = initial
    try:
        candidate = state.get("order", initial)
        candidate = [str(item or "").strip() for item in candidate]
        if len(candidate) == len(original) and _same_multiset(candidate, original):
            current = candidate
    except Exception:
        pass

    result = renderer(
        data={"items": current, "instruction": str(instruction or "")},
        default={"order": current},
        key=key,
        on_order_change=lambda: None,
    )
    try:
        order = [str(item or "").strip() for item in result.order]
        if len(order) == len(original) and _same_multiset(order, original):
            return order
    except Exception:
        pass
    return current

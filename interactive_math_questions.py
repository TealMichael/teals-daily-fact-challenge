from __future__ import annotations

"""Reusable student widgets for interactive curriculum questions.

v2.24.3 hardens the Order Tiles interaction for real classroom browsers.
Desktop mouse input uses native HTML drag/drop, touch/pen uses pointer-based
reordering, and every tile can also be selected and moved with visible arrow
buttons or a physical keyboard. The component receives labels only; it never
handles student identity, names, or external data.
"""

from functools import lru_cache
from collections import Counter

import streamlit as st

from curriculum_question_types import clean_text


_ORDER_HTML = """
<div class="tdfc-order-wrap">
  <div id="tdfc-order-instruction" class="tdfc-order-instruction"></div>
  <div id="tdfc-order-list" class="tdfc-order-list" role="list" aria-label="Number tiles to reorder"></div>
  <div class="tdfc-order-controls" aria-label="Move selected tile">
    <button id="tdfc-order-left" type="button" class="tdfc-order-move" disabled>← Move</button>
    <button id="tdfc-order-right" type="button" class="tdfc-order-move" disabled>Move →</button>
  </div>
  <div class="tdfc-order-hint">Drag the tiles. If needed, tap a tile and use Move ← / →.</div>
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
  -webkit-user-select: none;
  touch-action: none;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}
.tdfc-order-tile:hover {
  border-color: var(--st-primary-color);
}
.tdfc-order-tile:focus-visible {
  outline: 3px solid var(--st-primary-color);
  outline-offset: 2px;
}
.tdfc-order-tile.is-selected {
  border-color: var(--st-primary-color);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--st-primary-color) 22%, transparent);
}
.tdfc-order-tile.is-dragging {
  cursor: grabbing;
  opacity: 0.62;
  transform: scale(1.035);
  box-shadow: 0 5px 14px rgba(0,0,0,0.16);
}
.tdfc-order-controls {
  display: flex;
  gap: 0.55rem;
  margin-top: 0.55rem;
}
.tdfc-order-move {
  appearance: none;
  border: 1px solid color-mix(in srgb, var(--st-text-color) 24%, transparent);
  border-radius: 0.55rem;
  background: var(--st-secondary-background-color);
  color: var(--st-text-color);
  min-height: 2.35rem;
  padding: 0.35rem 0.78rem;
  font: inherit;
  font-size: 0.9rem;
  font-weight: 650;
  cursor: pointer;
}
.tdfc-order-move:disabled {
  opacity: 0.42;
  cursor: default;
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
  .tdfc-order-move {
    flex: 1 1 0;
    min-height: 2.65rem;
  }
}
"""

_ORDER_JS = r"""
export default function({ parentElement, data, setStateValue }) {
  const list = parentElement.querySelector("#tdfc-order-list");
  const instruction = parentElement.querySelector("#tdfc-order-instruction");
  const moveLeft = parentElement.querySelector("#tdfc-order-left");
  const moveRight = parentElement.querySelector("#tdfc-order-right");
  const requested = Array.isArray(data?.items) ? data.items.map((value) => String(value)) : [];
  instruction.textContent = data?.instruction ? String(data.instruction) : "Drag the tiles into order.";

  let selectedTile = null;
  let mouseDragging = null;
  let pointerDragging = null;
  let pointerId = null;

  function tiles() {
    return Array.from(list.querySelectorAll(".tdfc-order-tile"));
  }

  function currentOrder() {
    return tiles().map((tile) => tile.dataset.value || "");
  }

  function emitOrder() {
    setStateValue("order", currentOrder());
  }

  function sameOrder(a, b) {
    if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length) return false;
    return a.every((value, index) => String(value) === String(b[index]));
  }

  function refreshMoveButtons() {
    if (!selectedTile || !list.contains(selectedTile)) {
      moveLeft.disabled = true;
      moveRight.disabled = true;
      return;
    }
    moveLeft.disabled = !selectedTile.previousElementSibling;
    moveRight.disabled = !selectedTile.nextElementSibling;
  }

  function selectTile(tile) {
    tiles().forEach((candidate) => candidate.classList.toggle("is-selected", candidate === tile));
    selectedTile = tile && list.contains(tile) ? tile : null;
    refreshMoveButtons();
  }

  // Reorder relative to the tile under the pointer. This avoids the old
  // row-midpoint bug where a horizontal drag could remain pinned in place
  // whenever the pointer was in the upper half of a flex row.
  function reorderAtPoint(active, clientX, clientY) {
    if (!active || !list.contains(active)) return;

    const siblings = tiles().filter((tile) => tile !== active);
    if (!siblings.length) return;

    const root = parentElement.getRootNode ? parentElement.getRootNode() : document;
    let hit = null;
    try {
      const rawHit = root && typeof root.elementFromPoint === "function"
        ? root.elementFromPoint(clientX, clientY)
        : document.elementFromPoint(clientX, clientY);
      hit = rawHit && rawHit.closest ? rawHit.closest(".tdfc-order-tile") : null;
    } catch (_) {}

    if (hit && hit !== active && list.contains(hit)) {
      const rect = hit.getBoundingClientRect();
      const sameRow = clientY >= rect.top - 6 && clientY <= rect.bottom + 6;
      const before = sameRow
        ? clientX < rect.left + rect.width / 2
        : clientY < rect.top + rect.height / 2;
      if (before) list.insertBefore(active, hit);
      else list.insertBefore(active, hit.nextElementSibling);
      refreshMoveButtons();
      return;
    }

    // Pointer may be in a gap between flex items. Use the closest tile center
    // and then insert on the appropriate side of it.
    let closest = null;
    let closestDistance = Infinity;
    for (const sibling of siblings) {
      const rect = sibling.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;
      const dx = clientX - cx;
      const dy = clientY - cy;
      const distance = dx * dx + dy * dy;
      if (distance < closestDistance) {
        closest = sibling;
        closestDistance = distance;
      }
    }
    if (!closest) return;
    const rect = closest.getBoundingClientRect();
    const sameRow = clientY >= rect.top - 12 && clientY <= rect.bottom + 12;
    const before = sameRow
      ? clientX < rect.left + rect.width / 2
      : clientY < rect.top + rect.height / 2;
    if (before) list.insertBefore(active, closest);
    else list.insertBefore(active, closest.nextElementSibling);
    refreshMoveButtons();
  }

  function finishDrag(tile) {
    if (!tile) return;
    tile.classList.remove("is-dragging");
    selectTile(tile);
    emitOrder();
  }

  function wireTile(tile) {
    // Desktop/laptop mouse: use native HTML drag/drop so the browser supplies
    // the familiar ghost tile and reliable mouse movement behavior.
    tile.draggable = true;
    tile.addEventListener("dragstart", (event) => {
      mouseDragging = tile;
      selectTile(tile);
      tile.classList.add("is-dragging");
      try {
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData("text/plain", tile.dataset.value || "tile");
      } catch (_) {}
    });
    tile.addEventListener("dragend", () => {
      const active = mouseDragging;
      mouseDragging = null;
      finishDrag(active);
    });

    // Touch and pen: native HTML drag/drop is inconsistent, so use Pointer
    // Events. Mouse pointers intentionally use the native path above.
    tile.addEventListener("pointerdown", (event) => {
      selectTile(tile);
      if (event.pointerType === "mouse") return;
      if (event.button !== undefined && event.button !== 0) return;
      pointerDragging = tile;
      pointerId = event.pointerId;
      tile.classList.add("is-dragging");
      try { tile.setPointerCapture(event.pointerId); } catch (_) {}
      event.preventDefault();
    });

    tile.addEventListener("pointermove", (event) => {
      if (pointerDragging !== tile || pointerId !== event.pointerId) return;
      reorderAtPoint(tile, event.clientX, event.clientY);
      event.preventDefault();
    });

    const finishPointer = (event) => {
      if (pointerDragging !== tile || pointerId !== event.pointerId) return;
      try { tile.releasePointerCapture(event.pointerId); } catch (_) {}
      pointerDragging = null;
      pointerId = null;
      finishDrag(tile);
      event.preventDefault();
    };
    tile.addEventListener("pointerup", finishPointer);
    tile.addEventListener("pointercancel", finishPointer);

    tile.addEventListener("click", () => selectTile(tile));

    tile.addEventListener("keydown", (event) => {
      const previous = tile.previousElementSibling;
      const next = tile.nextElementSibling;
      if ((event.key === "ArrowLeft" || event.key === "ArrowUp") && previous) {
        list.insertBefore(tile, previous);
        selectTile(tile);
        emitOrder();
        tile.focus();
        event.preventDefault();
      } else if ((event.key === "ArrowRight" || event.key === "ArrowDown") && next) {
        list.insertBefore(next, tile);
        selectTile(tile);
        emitOrder();
        tile.focus();
        event.preventDefault();
      }
    });
  }

  list.ondragover = (event) => {
    if (!mouseDragging) return;
    event.preventDefault();
    try { event.dataTransfer.dropEffect = "move"; } catch (_) {}
    reorderAtPoint(mouseDragging, event.clientX, event.clientY);
  };
  list.ondrop = (event) => {
    if (!mouseDragging) return;
    event.preventDefault();
    reorderAtPoint(mouseDragging, event.clientX, event.clientY);
  };

  moveLeft.onclick = () => {
    if (!selectedTile) return;
    const previous = selectedTile.previousElementSibling;
    if (!previous) return;
    list.insertBefore(selectedTile, previous);
    emitOrder();
    refreshMoveButtons();
    selectedTile.focus();
  };
  moveRight.onclick = () => {
    if (!selectedTile) return;
    const next = selectedTile.nextElementSibling;
    if (!next) return;
    list.insertBefore(next, selectedTile);
    emitOrder();
    refreshMoveButtons();
    selectedTile.focus();
  };

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
      tile.setAttribute("aria-label", `Number tile ${label}. Drag it, tap and use Move buttons, or use arrow keys to reorder.`);
      tile.textContent = label;
      wireTile(tile);
      list.appendChild(tile);
    });
    selectedTile = null;
  }
  refreshMoveButtons();
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

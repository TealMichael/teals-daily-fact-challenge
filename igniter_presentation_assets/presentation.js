export default function({parentElement, data, setTriggerValue}) {
  const root = parentElement.querySelector('#igniter-stage');
  if (!root) return;
  const byId = id => root.querySelector('#' + id);
  // DOM-local only: no storage, cookies, shared state, or reveal events sent to Python.
  const reset = root.dataset.identity !== data.identity;
  root.dataset.identity = data.identity;
  root.dataset.scoped = data.scoped ? 'true' : 'false';
  byId('class-name').textContent = data.className || '';
  byId('lesson-date').textContent = data.date || '';
  ['one', 'two'].forEach((word, i) => {
    byId('question-' + word).innerHTML = data.cards[i].content;
    const answer = byId('answer-' + word), button = byId('reveal-' + word);
    answer.innerHTML = '<span class="answer-label">Answer ' + (i+1) + '</span>' + data.cards[i].answer;
    if (reset) answer.hidden = true;
    const update = () => {button.textContent = (answer.hidden ? 'Show' : 'Hide') + ' Answer ' + (i+1); button.setAttribute('aria-expanded', String(!answer.hidden));};
    update();
    button.onclick = () => {answer.hidden = !answer.hidden; update();};
  });
  const fullscreen = byId('fullscreen');
  const isFull = () => !!(document.fullscreenElement || root.getRootNode()?.fullscreenElement);
  fullscreen.onclick = async () => {
    try {
      if (isFull()) await document.exitFullscreen();
      else if (root.requestFullscreen) await root.requestFullscreen();
      else throw new Error('unavailable');
      fullscreen.textContent = isFull() ? 'Exit full screen' : 'Full screen';
      byId('screen-status').textContent = '';
    } catch (_) {
      byId('screen-status').textContent = 'Theater view is active. This browser does not allow full screen here.';
    }
  };
  // Rebind handlers on every component rerender, matching the existing Order Tiles fix.
  ['previous', 'next', 'today', 'exit'].forEach(action => {
    const control = byId(action);
    if (action !== 'exit') control.hidden = !!data.scoped;
    if (action === 'exit') control.textContent = data.scoped ? 'Close window' : 'Dashboard';
    control.onclick = async () => {
      if (isFull()) {try {await document.exitFullscreen();} catch (_) {}}
      if (data.scoped) {
        if (action === 'exit') {
          window.close();
          byId('screen-status').textContent = 'You can close this presentation window. Your dashboard is still open.';
        }
        return;
      }
      setTriggerValue('action', {action, identity: data.identity});
    };
  });
  root.onfullscreenchange = () => {fullscreen.textContent = isFull() ? 'Exit full screen' : 'Full screen';};
}

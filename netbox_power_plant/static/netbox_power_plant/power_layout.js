(function () {
  var ACTIVE_CLASS = 'is-trace-active';
  var DIMMED_CLASS = 'is-trace-dimmed';
  var HAS_ACTIVE_CLASS = 'has-active-trace';

  function closest(element, selector) {
    return element && element.closest ? element.closest(selector) : null;
  }

  function traceKeysFor(element) {
    return (element.dataset.traceKeys || '').split(/\s+/).filter(Boolean);
  }

  function clearTrace() {
    document.querySelectorAll('[data-power-layout-map]').forEach(function (container) {
      delete container.dataset.activeTraceKey;
      container.classList.remove(HAS_ACTIVE_CLASS);
    });

    document.querySelectorAll('.' + ACTIVE_CLASS + ', .' + DIMMED_CLASS).forEach(function (element) {
      element.classList.remove(ACTIVE_CLASS, DIMMED_CLASS);
    });
  }

  function setTraceState(element, isActive) {
    element.classList.toggle(ACTIVE_CLASS, isActive);
    element.classList.toggle(DIMMED_CLASS, !isActive);
  }

  function activateTrace(container, key) {
    if (!key) {
      clearTrace();
      return;
    }

    clearTrace();
    container.dataset.activeTraceKey = key;
    container.classList.add(HAS_ACTIVE_CLASS);

    container.querySelectorAll('[data-power-map-item]').forEach(function (element) {
      setTraceState(element, traceKeysFor(element).indexOf(key) !== -1);
    });

    document.querySelectorAll('[data-power-trace-key]').forEach(function (element) {
      setTraceState(element, element.dataset.powerTraceKey === key);
    });
  }

  function layoutMapFor(trigger) {
    return closest(trigger, '[data-power-layout-map]') || document.querySelector('[data-power-layout-map]');
  }

  function nestedInteractiveElement(target, trigger) {
    var control = closest(target, 'a, button, input, select, textarea, summary, [role="button"], [role="link"]');
    return Boolean(control && control !== trigger);
  }

  function handleTraceClick(event) {
    var trigger = closest(event.target, '[data-power-trace-key]');
    if (trigger) {
      if (nestedInteractiveElement(event.target, trigger)) {
        return;
      }

      var container = layoutMapFor(trigger);
      if (!container) {
        return;
      }

      event.preventDefault();
      activateTrace(container, trigger.dataset.powerTraceKey);
      return;
    }

    var map = closest(event.target, '[data-power-layout-map]');
    if (
      map &&
      closest(event.target, '.card-body') &&
      !closest(event.target, '[data-power-map-item]')
    ) {
      clearTrace();
    }
  }

  function handleTraceFocus(event) {
    var trigger = closest(event.target, '[data-power-trace-key]');
    if (!trigger) {
      return;
    }

    var container = layoutMapFor(trigger);
    if (!container) {
      return;
    }

    activateTrace(container, trigger.dataset.powerTraceKey);
  }

  function handleTraceKeydown(event) {
    if (event.key === 'Escape') {
      if (document.querySelector('[data-power-layout-map].' + HAS_ACTIVE_CLASS)) {
        event.preventDefault();
        clearTrace();
      }
      return;
    }

    var trigger = closest(event.target, '[data-power-trace-key]');
    if (
      !trigger ||
      nestedInteractiveElement(event.target, trigger) ||
      (event.key !== 'Enter' && event.key !== ' ' && event.key !== 'Spacebar')
    ) {
      return;
    }

    var container = layoutMapFor(trigger);
    if (!container) {
      return;
    }

    event.preventDefault();
    activateTrace(container, trigger.dataset.powerTraceKey);
  }

  document.addEventListener('click', handleTraceClick);
  document.addEventListener('focusin', handleTraceFocus);
  document.addEventListener('keydown', handleTraceKeydown);
}());

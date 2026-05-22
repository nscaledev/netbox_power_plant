(function () {
  var SELECTED_CLASS = 'is-selected';
  var HAS_SELECTION_CLASS = 'has-selection';
  var UNSAVED_CLASS = 'has-unsaved-geometry';
  var MIN_GEOMETRY_SIZE = 0.001;
  var dragState = null;

  function closest(element, selector) {
    return element && element.closest ? element.closest(selector) : null;
  }

  function text(value, fallback) {
    return value || fallback || '-';
  }

  function number(value, fallback) {
    var parsed = parseFloat(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function formatNumber(value) {
    return Number(value).toFixed(3);
  }

  function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
  }

  function frameGeometry(container) {
    return {
      width: number(container.dataset.frameWidth, 0),
      height: number(container.dataset.frameHeight, 0),
      units: container.dataset.frameUnits || ''
    };
  }

  function geometryFromObject(object, prefix) {
    prefix = prefix || 'edit';
    return {
      x: number(object.dataset[prefix + 'X'], 0),
      y: number(object.dataset[prefix + 'Y'], 0),
      width: number(object.dataset[prefix + 'Width'], 0),
      depth: number(object.dataset[prefix + 'Depth'], 0)
    };
  }

  function geometryFromForm(form) {
    return {
      x: number(fieldValue(form, 'x'), NaN),
      y: number(fieldValue(form, 'y'), NaN),
      width: number(fieldValue(form, 'width'), NaN),
      depth: number(fieldValue(form, 'depth'), NaN)
    };
  }

  function fieldValue(form, name) {
    var field = form.querySelector('[data-spatial-geometry-field="' + name + '"]');
    return field ? field.value : '';
  }

  function validGeometry(geometry, frame) {
    return (
      Number.isFinite(geometry.x) &&
      Number.isFinite(geometry.y) &&
      Number.isFinite(geometry.width) &&
      Number.isFinite(geometry.depth) &&
      geometry.x >= 0 &&
      geometry.y >= 0 &&
      geometry.width > 0 &&
      geometry.depth > 0 &&
      geometry.x + geometry.width <= frame.width &&
      geometry.y + geometry.depth <= frame.height
    );
  }

  function geometriesMatch(first, second) {
    return (
      Math.abs(first.x - second.x) < 0.0005 &&
      Math.abs(first.y - second.y) < 0.0005 &&
      Math.abs(first.width - second.width) < 0.0005 &&
      Math.abs(first.depth - second.depth) < 0.0005
    );
  }

  function setField(panel, name, value) {
    var field = panel.querySelector('[data-spatial-detail-field="' + name + '"]');
    if (field) {
      field.textContent = text(value);
    }
  }

  function setLink(panel, href) {
    var link = panel.querySelector('[data-spatial-detail-link]');
    if (!link) {
      return;
    }

    if (href) {
      link.hidden = false;
      link.href = href;
    } else {
      link.hidden = true;
      link.removeAttribute('href');
    }
  }

  function setGeometryInput(form, name, value) {
    var field = form.querySelector('[data-spatial-geometry-field="' + name + '"]');
    if (field) {
      field.value = value || '';
    }
  }

  function setApprovalInput(form, name, value) {
    var field = form.querySelector('[data-spatial-approval-field="' + name + '"]');
    if (field) {
      field.value = value || '';
    }
  }

  function setPreviewState(form, message, isUnsaved) {
    var state = form.querySelector('[data-spatial-geometry-preview-state]');
    if (!state) {
      return;
    }
    state.textContent = message;
    state.classList.toggle('text-danger', Boolean(isUnsaved));
    state.classList.toggle('text-secondary', !isUnsaved);
  }

  function setGeometryInputs(form, geometry) {
    setGeometryInput(form, 'x', formatNumber(geometry.x));
    setGeometryInput(form, 'y', formatNumber(geometry.y));
    setGeometryInput(form, 'width', formatNumber(geometry.width));
    setGeometryInput(form, 'depth', formatNumber(geometry.depth));
  }

  function geometryText(container, geometry, suffix) {
    var frame = frameGeometry(container);
    var units = frame.units ? ' ' + frame.units : '';
    return (
      formatNumber(geometry.x) + ', ' +
      formatNumber(geometry.y) + ' / ' +
      formatNumber(geometry.width) + ' x ' +
      formatNumber(geometry.depth) + units +
      (suffix || '')
    );
  }

  function mainRect(object) {
    return object.querySelector('.spatial-review-shape');
  }

  function resizeHandle(object) {
    return object.querySelector('.spatial-review-edit-handle');
  }

  function positionResizeHandle(object, geometry) {
    var handle = resizeHandle(object);
    if (!handle) {
      return;
    }
    var handleWidth = number(handle.getAttribute('width'), 6);
    var handleHeight = number(handle.getAttribute('height'), 6);
    handle.setAttribute('x', formatNumber(geometry.x + geometry.width - (handleWidth / 2)));
    handle.setAttribute('y', formatNumber(geometry.y + geometry.depth - (handleHeight / 2)));
  }

  function applyGeometry(container, object, geometry, options) {
    options = options || {};
    var rect = mainRect(object);
    if (!rect) {
      return;
    }

    rect.setAttribute('x', formatNumber(geometry.x));
    rect.setAttribute('y', formatNumber(geometry.y));
    rect.setAttribute('width', formatNumber(geometry.width));
    rect.setAttribute('height', formatNumber(geometry.depth));
    positionResizeHandle(object, geometry);

    object.dataset.editX = formatNumber(geometry.x);
    object.dataset.editY = formatNumber(geometry.y);
    object.dataset.editWidth = formatNumber(geometry.width);
    object.dataset.editDepth = formatNumber(geometry.depth);

    var suffix = options.preview ? ' (unsaved)' : '';
    object.dataset.geometry = geometryText(container, geometry, suffix);
    object.classList.toggle(UNSAVED_CLASS, Boolean(options.preview));

    if (object.classList.contains(SELECTED_CLASS)) {
      var form = container.querySelector('[data-spatial-review-geometry-form]');
      var panel = container.querySelector('[data-spatial-review-detail]');
      if (form) {
        setGeometryInputs(form, geometry);
        setPreviewState(
          form,
          options.preview
            ? 'Previewing unsaved geometry. Check the confirmation box and save when it looks right.'
            : 'Showing saved geometry.',
          options.preview
        );
      }
      if (panel) {
        setField(panel, 'geometry', object.dataset.geometry);
      }
    }
  }

  function resetObjectGeometry(container, object) {
    if (!object || object.dataset.spatialReviewKind !== 'space') {
      return;
    }
    applyGeometry(container, object, geometryFromObject(object, 'saved'), { preview: false });
  }

  function resetUnsavedGeometry(container, exceptObject) {
    container.querySelectorAll('.' + UNSAVED_CLASS).forEach(function (object) {
      if (object !== exceptObject) {
        resetObjectGeometry(container, object);
      }
    });
  }

  function selectedSpace(container) {
    var object = container.querySelector('.' + SELECTED_CLASS);
    return object && object.dataset.spatialReviewKind === 'space' ? object : null;
  }

  function resetGeometryForm(container) {
    var form = container.querySelector('[data-spatial-review-geometry-form]');
    if (!form) {
      return;
    }

    var fieldset = form.querySelector('[data-spatial-geometry-fieldset]');
    var selectedLabel = form.querySelector('[data-spatial-geometry-selected-label]');
    var confirm = form.querySelector('[data-spatial-geometry-field="confirm"]');
    if (fieldset) {
      fieldset.disabled = true;
    }
    if (selectedLabel) {
      selectedLabel.textContent = 'Select a space to edit geometry.';
    }
    ['spaceId', 'x', 'y', 'width', 'depth'].forEach(function (name) {
      setGeometryInput(form, name, '');
    });
    if (confirm) {
      confirm.checked = false;
    }
    setPreviewState(form, 'Drag a selected space to move it, or drag its handle to resize it.', false);
  }

  function updateGeometryForm(container, object) {
    var form = container.querySelector('[data-spatial-review-geometry-form]');
    if (!form) {
      return;
    }

    var fieldset = form.querySelector('[data-spatial-geometry-fieldset]');
    var selectedLabel = form.querySelector('[data-spatial-geometry-selected-label]');
    var confirm = form.querySelector('[data-spatial-geometry-field="confirm"]');
    var isSpace = object.dataset.spatialReviewKind === 'space';

    if (fieldset) {
      fieldset.disabled = !isSpace;
    }
    if (selectedLabel) {
      selectedLabel.textContent = isSpace
        ? 'Editing ' + text(object.dataset.label)
        : 'Select a space to edit geometry.';
    }
    if (!isSpace) {
      resetGeometryForm(container);
      return;
    }

    setGeometryInput(form, 'spaceId', object.dataset.objectId);
    setGeometryInputs(form, geometryFromObject(object));
    if (confirm) {
      confirm.checked = false;
    }
    setPreviewState(
      form,
      object.classList.contains(UNSAVED_CLASS)
        ? 'Previewing unsaved geometry. Check the confirmation box and save when it looks right.'
        : 'Drag this space to move it, or drag its handle to resize it.',
      object.classList.contains(UNSAVED_CLASS)
    );
  }

  function resetApprovalForm(container) {
    var form = container.querySelector('[data-spatial-review-approval-form]');
    if (!form) {
      return;
    }

    var fieldset = form.querySelector('[data-spatial-approval-fieldset]');
    var selectedLabel = form.querySelector('[data-spatial-approval-selected-label]');
    var confirm = form.querySelector('[data-spatial-approval-field="confirm"]');
    if (fieldset) {
      fieldset.disabled = true;
    }
    if (selectedLabel) {
      selectedLabel.textContent = 'Select a corrected space to approve.';
    }
    setApprovalInput(form, 'spaceId', '');
    setApprovalInput(form, 'notes', '');
    if (confirm) {
      confirm.checked = false;
    }
  }

  function updateApprovalForm(container, object) {
    var form = container.querySelector('[data-spatial-review-approval-form]');
    if (!form) {
      return;
    }

    var fieldset = form.querySelector('[data-spatial-approval-fieldset]');
    var selectedLabel = form.querySelector('[data-spatial-approval-selected-label]');
    var confirm = form.querySelector('[data-spatial-approval-field="confirm"]');
    var isCorrectedSpace = (
      object.dataset.spatialReviewKind === 'space' &&
      object.dataset.geometryReviewState === 'operator_corrected'
    );

    if (fieldset) {
      fieldset.disabled = !isCorrectedSpace;
    }
    if (selectedLabel) {
      selectedLabel.textContent = isCorrectedSpace
        ? 'Approving ' + text(object.dataset.label)
        : 'Select a corrected space to approve.';
    }
    if (!isCorrectedSpace) {
      setApprovalInput(form, 'spaceId', '');
      if (confirm) {
        confirm.checked = false;
      }
      return;
    }
    setApprovalInput(form, 'spaceId', object.dataset.objectId);
    if (confirm) {
      confirm.checked = false;
    }
  }

  function resetPanel(container) {
    var panel = container.querySelector('[data-spatial-review-detail]');
    if (!panel) {
      return;
    }

    panel.classList.add('spatial-review-empty-detail');
    setField(panel, 'label', panel.dataset.emptyTitle || 'Select a space');
    setField(
      panel,
      'kind',
      panel.dataset.emptyDescription || 'Click a rendered space or placement to review its details.'
    );
    setField(panel, 'status', '');
    setField(panel, 'reviewState', '');
    setField(panel, 'confidence', '');
    setField(panel, 'geometry', '');
    setLink(panel, '');
    resetGeometryForm(container);
    resetApprovalForm(container);
  }

  function clearSelection(container) {
    container.classList.remove(HAS_SELECTION_CLASS);
    container.querySelectorAll('.' + SELECTED_CLASS).forEach(function (element) {
      element.classList.remove(SELECTED_CLASS);
      element.setAttribute('aria-pressed', 'false');
    });
    resetUnsavedGeometry(container);
    resetPanel(container);
  }

  function selectObject(container, object) {
    var panel = container.querySelector('[data-spatial-review-detail]');
    if (!panel) {
      return;
    }

    resetUnsavedGeometry(container, object);
    container.querySelectorAll('.' + SELECTED_CLASS).forEach(function (element) {
      element.classList.remove(SELECTED_CLASS);
      element.setAttribute('aria-pressed', 'false');
    });

    container.classList.add(HAS_SELECTION_CLASS);
    object.classList.add(SELECTED_CLASS);
    object.setAttribute('aria-pressed', 'true');

    panel.classList.remove('spatial-review-empty-detail');
    setField(panel, 'label', object.dataset.label);
    setField(panel, 'kind', object.dataset.kindLabel);
    setField(panel, 'status', object.dataset.statusLabel || object.dataset.boundaryStatusLabel);
    setField(panel, 'reviewState', object.dataset.reviewState);
    setField(panel, 'confidence', object.dataset.confidence);
    setField(panel, 'geometry', object.dataset.geometry);
    setLink(panel, object.dataset.href);
    updateGeometryForm(container, object);
    updateApprovalForm(container, object);
  }

  function modelPoint(container, event) {
    var svg = container.querySelector('[data-spatial-review-svg]');
    var plane = container.querySelector('[data-spatial-coordinate-plane]');
    if (!svg || !plane || !plane.getScreenCTM()) {
      return null;
    }

    var point = svg.createSVGPoint ? svg.createSVGPoint() : new DOMPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    return point.matrixTransform(plane.getScreenCTM().inverse());
  }

  function startDrag(event, container, object) {
    var form = container.querySelector('[data-spatial-review-geometry-form]');
    if (!form || object.dataset.spatialReviewKind !== 'space') {
      return;
    }

    var point = modelPoint(container, event);
    if (!point) {
      return;
    }

    var handle = closest(event.target, '[data-spatial-drag-handle]');
    dragState = {
      container: container,
      object: object,
      mode: handle && handle.dataset.spatialDragHandle === 'resize' ? 'resize' : 'move',
      startPoint: point,
      startGeometry: geometryFromObject(object),
      moved: false
    };
    if (event.target.setPointerCapture && event.pointerId !== undefined) {
      event.target.setPointerCapture(event.pointerId);
    }
  }

  function updateDrag(event) {
    if (!dragState) {
      return;
    }
    var point = modelPoint(dragState.container, event);
    if (!point) {
      return;
    }

    var frame = frameGeometry(dragState.container);
    var dx = point.x - dragState.startPoint.x;
    var dy = point.y - dragState.startPoint.y;
    var start = dragState.startGeometry;
    var geometry;
    if (dragState.mode === 'resize') {
      geometry = {
        x: start.x,
        y: start.y,
        width: clamp(start.width + dx, MIN_GEOMETRY_SIZE, frame.width - start.x),
        depth: clamp(start.depth + dy, MIN_GEOMETRY_SIZE, frame.height - start.y)
      };
    } else {
      geometry = {
        x: clamp(start.x + dx, 0, frame.width - start.width),
        y: clamp(start.y + dy, 0, frame.height - start.depth),
        width: start.width,
        depth: start.depth
      };
    }

    dragState.moved = true;
    event.preventDefault();
    applyGeometry(dragState.container, dragState.object, geometry, { preview: true });
  }

  function endDrag() {
    if (!dragState) {
      return;
    }
    if (dragState.moved) {
      dragState.container.dataset.spatialDragSuppressed = '1';
    }
    dragState = null;
  }

  function handlePointerdown(event) {
    var object = closest(event.target, '[data-spatial-review-object]');
    if (!object) {
      return;
    }

    var container = closest(object, '[data-spatial-review-map]');
    if (!container) {
      return;
    }

    selectObject(container, object);
    startDrag(event, container, object);
  }

  function handleClick(event) {
    var object = closest(event.target, '[data-spatial-review-object]');
    if (object) {
      var container = closest(object, '[data-spatial-review-map]');
      if (!container) {
        return;
      }

      if (container.dataset.spatialDragSuppressed === '1') {
        delete container.dataset.spatialDragSuppressed;
        event.preventDefault();
        return;
      }

      event.preventDefault();
      selectObject(container, object);
      return;
    }

    var map = closest(event.target, '[data-spatial-review-map]');
    if (
      map &&
      closest(event.target, '[data-spatial-review-canvas]') &&
      !closest(event.target, '[data-spatial-review-object]')
    ) {
      clearSelection(map);
    }
  }

  function handleKeydown(event) {
    if (event.key === 'Escape') {
      document.querySelectorAll('[data-spatial-review-map].' + HAS_SELECTION_CLASS).forEach(clearSelection);
      return;
    }

    if (event.key !== 'Enter' && event.key !== ' ' && event.key !== 'Spacebar') {
      return;
    }

    var object = closest(event.target, '[data-spatial-review-object]');
    if (!object) {
      return;
    }

    var container = closest(object, '[data-spatial-review-map]');
    if (!container) {
      return;
    }

    event.preventDefault();
    selectObject(container, object);
  }

  function handleGeometryInput(event) {
    var form = closest(event.target, '[data-spatial-review-geometry-form]');
    if (!form) {
      return;
    }
    var container = closest(form, '[data-spatial-review-map]');
    var object = container ? selectedSpace(container) : null;
    if (!container || !object) {
      return;
    }

    var geometry = geometryFromForm(form);
    var frame = frameGeometry(container);
    if (!validGeometry(geometry, frame)) {
      setPreviewState(form, 'Geometry must be positive and fit inside the frame.', true);
      return;
    }

    var saved = geometryFromObject(object, 'saved');
    applyGeometry(container, object, geometry, { preview: !geometriesMatch(geometry, saved) });
  }

  function handleResetPreview(event) {
    var button = closest(event.target, '[data-spatial-geometry-reset]');
    if (!button) {
      return;
    }
    var container = closest(button, '[data-spatial-review-map]');
    var object = container ? selectedSpace(container) : null;
    if (!container || !object) {
      return;
    }
    event.preventDefault();
    resetObjectGeometry(container, object);
    updateGeometryForm(container, object);
  }

  function initializeObject(object) {
    if (object.dataset.spatialReviewKind !== 'space') {
      return;
    }
    object.dataset.savedX = object.dataset.editX;
    object.dataset.savedY = object.dataset.editY;
    object.dataset.savedWidth = object.dataset.editWidth;
    object.dataset.savedDepth = object.dataset.editDepth;
    positionResizeHandle(object, geometryFromObject(object));
  }

  function initializeMap(container) {
    container.querySelectorAll('[data-spatial-review-object]').forEach(initializeObject);
    resetPanel(container);
  }

  document.addEventListener('pointerdown', handlePointerdown);
  document.addEventListener('pointermove', updateDrag);
  document.addEventListener('pointerup', endDrag);
  document.addEventListener('pointercancel', endDrag);
  document.addEventListener('click', handleClick);
  document.addEventListener('keydown', handleKeydown);
  document.addEventListener('input', handleGeometryInput);
  document.addEventListener('click', handleResetPreview);

  document.querySelectorAll('[data-spatial-review-map]').forEach(initializeMap);
}());

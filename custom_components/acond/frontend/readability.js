/** Text wrapping for the Polish Acond dashboard. No services, states or cards are replaced. */
(() => {
  if (window.__acondReadability) return;
  window.__acondReadability = true;

  const marker = "data-acond-readable";
  const styleId = "acond-readable-style";
  const host = `:host([${marker}])`;
  const wrap = "white-space:normal!important;text-overflow:clip!important;overflow:visible!important;overflow-wrap:anywhere!important;-webkit-line-clamp:unset!important;line-clamp:unset!important;";
  const markdown = `${host} pre{white-space:pre-wrap!important;overflow-wrap:anywhere!important;} ${host} code{white-space:inherit!important;overflow-wrap:anywhere!important;word-break:normal!important;} ${host} table{display:table!important;table-layout:fixed!important;width:100%!important;max-width:100%!important;min-width:0!important;} ${host} th,${host} td{white-space:normal!important;overflow-wrap:anywhere!important;min-width:0!important;} ${host} table:has(th:nth-child(3)) th:first-child{width:44%;} ${host} table:has(th:nth-child(3)) th:nth-child(2){width:18%;}`;
  const rules = {
    "ha-card": `${host} .card-header,${host} .card-header .name{${wrap}line-height:1.4!important;}`,
    "hui-entities-card": `${host} .card-header,${host} .card-header .name,${host} .name{${wrap}line-height:1.4!important;}`,
    "hui-entity-card": `${host} .name,${host} .value,${host} .measurement{${wrap}min-width:0;} ${host} .name{flex:1;} ${host} .info{white-space:normal!important;overflow-wrap:anywhere!important;display:block!important;} ${host} ha-card{height:auto!important;min-height:100%;}`,
    "ha-attribute-value": `${host}{white-space:normal!important;overflow-wrap:anywhere!important;}`,
    "hui-horizontal-stack-card": `${host} #root{display:grid!important;grid-template-columns:repeat(auto-fit,minmax(min(140px,100%),1fr))!important;gap:8px!important;}`,
    "hui-generic-entity-row": `${host} .info,${host} .info>*{${wrap}min-width:0;} ${host} .info{flex:1 1 0!important;line-height:1.4;padding-block:8px;} ${host} .row{min-height:48px;} ${host} .value{min-width:64px;max-width:48%;flex-shrink:0;} ${host} .state{white-space:normal!important;overflow-wrap:anywhere;}`,
    "ha-tile-info": `${host} .primary span,${host} .secondary span,${host} ::slotted([slot=primary]),${host} ::slotted([slot=secondary]){${wrap}} ${host} .info{min-height:auto!important;} ${host} .primary{min-height:auto!important;}`,
    "hui-tile-card": `${host}{height:auto!important;min-height:min-content!important;} ${host} ha-card{height:auto!important;min-height:100%;} ${host} ha-tile{padding-block:6px;box-sizing:border-box;}`,
    "hui-button-card": `${host} span,${host} #name,${host} .name,${host} .ellipsis{${wrap}line-height:1.4!important;max-width:calc(100% - 16px);min-width:0;box-sizing:border-box;} ${host} ha-card{min-height:100%;box-sizing:border-box;}`,
    "hui-glance-card": `${host} .entities{display:grid!important;grid-template-columns:repeat(auto-fit,minmax(min(145px,100%),1fr))!important;} ${host} .entity{width:auto!important;min-width:0!important;box-sizing:border-box;} ${host} .name,${host} .state,${host} .entity>div{${wrap}height:auto!important;line-height:1.4!important;}`,
    "hui-heading-card": `${host} .title,${host} .title>*,${host} .heading{${wrap}height:auto!important;}`,
    "hui-section-row": `${host} .label{${wrap}}`,
    "ha-chart-legend": `${host} .name,${host} .label,${host} .legend-label,${host} button{${wrap}}`,
    "ha-chart-base": `${host} .chart-legend .label{${wrap}line-height:1.4!important;} ${host} .chart-legend li{height:auto!important;min-height:28px;align-items:center;}`,
    "ha-markdown": markdown,
    "ha-markdown-element": markdown,
  };

  let observers = [];
  let observed = new WeakSet();
  let waiting = new WeakSet();
  const styled = new Set();
  const markdownSheets = new Map();
  const pending = new Set();
  let frame = 0;
  const active = () => /^\/acond-dashboard(?:\/|$)/.test(location.pathname);

  function insideDashboard(element) {
    for (let node = element; node; node = node.parentElement || node.getRootNode()?.host) {
      if (node.localName === "hui-root") return true;
    }
    return false;
  }

  function visit(element) {
    if (!(element instanceof Element) || element.id === styleId) return;
    const root = element.shadowRoot;
    // Extra modules can run before HA's custom elements have been upgraded.
    // Attaching a shadow root is not observable from its parent document.
    if (!root && element.namespaceURI === "http://www.w3.org/1999/xhtml"
        && element.localName.includes("-") && !waiting.has(element)) {
      waiting.add(element);
      const reference = new WeakRef(element);
      customElements.whenDefined(element.localName).then(async () => {
        const node = reference.deref();
        if (!node?.isConnected || !active()) return;
        await node.updateComplete;
        pending.add(node);
        if (!frame) frame = requestAnimationFrame(flush);
      }).catch(() => {}); // Original component render failures must not affect controls.
    }
    if (root) {
      if (rules[element.localName] && insideDashboard(element)) {
        element.setAttribute(marker, "");
        if (element.localName.startsWith("ha-markdown")) {
          // HA replaces Markdown's innerHTML, removing appended <style> nodes.
          // An adopted stylesheet survives content rerenders on the same root.
          let sheet = markdownSheets.get(element);
          if (!sheet) {
            sheet = new CSSStyleSheet();
            sheet.replaceSync(rules[element.localName]);
            markdownSheets.set(element, sheet);
          }
          if (!root.adoptedStyleSheets.includes(sheet)) {
            root.adoptedStyleSheets = [...root.adoptedStyleSheets, sheet];
          }
        } else if (!root.getElementById(styleId)) {
          const style = document.createElement("style");
          style.id = styleId;
          style.textContent = rules[element.localName];
          root.append(style);
        }
        styled.add(element);
      }
      watch(root);
      for (const child of root.children) visit(child);
    }
    for (const child of element.children) visit(child);
  }

  function flush() {
    frame = 0;
    if (!active()) return stop();
    const nodes = [...pending];
    pending.clear();
    for (const node of nodes) visit(node);
  }

  function watch(root) {
    if (observed.has(root)) return;
    observed.add(root);
    const observer = new MutationObserver((records) => {
      if (!active()) return stop();
      for (const record of records) {
        for (const node of record.addedNodes) {
          if (node instanceof Element && node.id !== styleId) pending.add(node);
        }
      }
      if (pending.size && !frame) frame = requestAnimationFrame(flush);
    });
    observer.observe(root, { childList: true, subtree: true });
    observers.push(observer);
  }

  function stop() {
    if (frame) cancelAnimationFrame(frame);
    frame = 0;
    for (const observer of observers) observer.disconnect();
    observers = [];
    observed = new WeakSet();
    waiting = new WeakSet();
    pending.clear();
    for (const element of styled) {
      element.removeAttribute(marker);
      element.shadowRoot?.getElementById(styleId)?.remove();
    }
    styled.clear();
    for (const [element, sheet] of markdownSheets) {
      const root = element.shadowRoot;
      if (root) root.adoptedStyleSheets = root.adoptedStyleSheets.filter(s => s !== sheet);
    }
    markdownSheets.clear();
  }

  function update() {
    // Release observers on old views and remove styling before every navigation.
    stop();
    if (!active()) return stop();
    watch(document);
    visit(document.documentElement);
  }

  window.addEventListener("location-changed", update);
  window.addEventListener("popstate", update);
  update();
})();

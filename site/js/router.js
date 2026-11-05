// The address bar is the state: #/map?contest=cw:123&city=carson. Links can be shared and the back button works.
export function parseHash() {
  const [path, qs = ""] = location.hash.replace(/^#\/?/, "").split("?");
  return { view: path || "overview", params: Object.fromEntries(new URLSearchParams(qs)) };
}
export function hashFor(view, params = {}) {
  const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString();
  return `#/${view}${qs ? "?" + qs : ""}`;
}
export function navigate(view, params = {}, { replace = false } = {}) {
  const target = hashFor(view, params);
  if (replace) { history.replaceState(null, "", target); window.dispatchEvent(new HashChangeEvent("hashchange")); }
  else location.hash = target;
}

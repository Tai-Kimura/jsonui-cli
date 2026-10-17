// Loads the view: /app.js (live) or /app.js?mode=demo when the page was opened with ?demo=1.
// The server concatenates web/js/ in a fixed order for the mode (jui_cli/viz/bundle.py).
const demo = new URLSearchParams(location.search).get('demo') === '1';
import(demo ? '/app.js?mode=demo' : '/app.js');

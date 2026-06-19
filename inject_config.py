"""
inject_config.py
1. Adds <script src="../config.js"></script> to every screen's <head>
2. Replaces hardcoded 'http://localhost:8000' with window.TRAFFICGUARD_API_BASE
   in every JS variable assignment (const API_BASE = ...)
"""
import os, re

BASE = r'c:\Users\DELL\Desktop\Traffic Guard 2.0\stitch_trafficguard_ai_dashboard\stitch_trafficguard_ai_dashboard'

SCREENS = [
    'live_feed_light_mode',
    'analytics_light_mode',
    'dispatch_dark_mode',
    'map_view_light_mode',
    'upload_analyze',
    'trafficguard_ai_global_theme_system',
    'live_feed_dark_mode',
    'trafficguard_ai_traffic_enforcement_system',
    'evidence_modal_light_mode',
]

CONFIG_SCRIPT = '<script src="../config.js"></script>\n'

for screen in SCREENS:
    path = os.path.join(BASE, screen, 'code.html')
    if not os.path.exists(path):
        print(f'SKIP {screen}')
        continue

    text = open(path, encoding='utf-8').read()
    changed = False

    # 1. Inject config.js before </head> if not already there
    if 'config.js' not in text:
        text = text.replace('</head>', CONFIG_SCRIPT + '</head>', 1)
        changed = True

    # 2. Replace hardcoded localhost API_BASE declarations
    # Patterns: const API_BASE = "http://localhost:8000"
    #           const API = 'http://localhost:8000'
    #           const API_BASE_TES = 'http://localhost:8000'
    text, n1 = re.subn(
        r"""(const\s+API(?:_BASE(?:_\w+)?)?\s*=\s*)['"]http://localhost:8000['"]""",
        r'\1(window.TRAFFICGUARD_API_BASE || "http://localhost:8000")',
        text
    )
    if n1:
        changed = True

    # 3. Replace bare string 'http://localhost:8000' in fetch() and ws:// calls
    # fetch(`http://localhost:8000/...`) -> fetch(`${window.TRAFFICGUARD_API_BASE}/...`)
    text, n2 = re.subn(
        r'`http://localhost:8000(/[^`]*)`',
        r'`${window.TRAFFICGUARD_API_BASE || "http://localhost:8000"}\1`',
        text
    )
    if n2:
        changed = True

    # 4. Replace WebSocket ws://localhost:8000 -> dynamic ws/wss based on location
    text, n3 = re.subn(
        r"""['"]ws://localhost:8000/ws/violations['"]""",
        '(window.location.protocol === "https:" ? "wss" : "ws") + "://" + '
        '(window.TRAFFICGUARD_API_BASE || "http://localhost:8000").replace(/^https?:\\/\\//, "") + "/ws/violations"',
        text
    )
    if n3:
        changed = True

    if changed:
        open(path, 'w', encoding='utf-8').write(text)
        print(f'OK  {screen} (config_js={"yes" if "config.js" in text else "no"} api={n1} fetch={n2} ws={n3})')
    else:
        print(f'--  {screen} (no changes)')

print('\nDone.')

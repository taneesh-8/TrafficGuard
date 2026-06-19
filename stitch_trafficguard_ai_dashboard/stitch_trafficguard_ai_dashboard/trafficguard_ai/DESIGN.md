---
name: TrafficGuard AI
colors:
  surface: '#fcf9f8'
  surface-dim: '#dcd9d9'
  surface-bright: '#fcf9f8'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f6f3f2'
  surface-container: '#f0eded'
  surface-container-high: '#eae7e7'
  surface-container-highest: '#e5e2e1'
  on-surface: '#1b1c1c'
  on-surface-variant: '#424754'
  inverse-surface: '#303030'
  inverse-on-surface: '#f3f0ef'
  outline: '#727786'
  outline-variant: '#c2c6d6'
  surface-tint: '#0059c8'
  primary: '#0056c3'
  on-primary: '#ffffff'
  primary-container: '#1f6feb'
  on-primary-container: '#fefcff'
  inverse-primary: '#afc6ff'
  secondary: '#705d00'
  on-secondary: '#ffffff'
  secondary-container: '#fcd400'
  on-secondary-container: '#6e5c00'
  tertiary: '#006b22'
  on-tertiary: '#ffffff'
  tertiary-container: '#00872d'
  on-tertiary-container: '#f7fff1'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#d9e2ff'
  primary-fixed-dim: '#afc6ff'
  on-primary-fixed: '#001944'
  on-primary-fixed-variant: '#004299'
  secondary-fixed: '#ffe16d'
  secondary-fixed-dim: '#e9c400'
  on-secondary-fixed: '#221b00'
  on-secondary-fixed-variant: '#544600'
  tertiary-fixed: '#83fc8b'
  tertiary-fixed-dim: '#67df72'
  on-tertiary-fixed: '#002105'
  on-tertiary-fixed-variant: '#005318'
  background: '#fcf9f8'
  on-background: '#1b1c1c'
  surface-variant: '#e5e2e1'
typography:
  headline-h1:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '700'
    lineHeight: 32px
    letterSpacing: -0.02em
  headline-h2:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 24px
    letterSpacing: -0.01em
  headline-h3:
    fontFamily: Inter
    fontSize: 15px
    fontWeight: '600'
    lineHeight: 20px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  body-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
  plate-display:
    fontFamily: JetBrains Mono
    fontSize: 16px
    fontWeight: '700'
    lineHeight: 24px
    letterSpacing: 0.1em
  label-caps:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '700'
    lineHeight: 16px
    letterSpacing: 0.05em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  header_height: 64px
  accent_bar: 3px
  gutter: 16px
  margin_mobile: 16px
  margin_desktop: 24px
  container_max_width: 1440px
---

## Brand & Style
The design system is engineered for high-stakes operational environments, specifically for the Bengaluru Traffic Police. It draws inspiration from a **Corporate / Modern** aesthetic, prioritizing clarity, trust, and rapid information processing. The style is utilitarian yet sophisticated, mirroring the efficiency of top-tier Indian e-commerce platforms while maintaining the authoritative posture required for law enforcement.

The visual narrative is built on three pillars:
1. **Utility First:** Every pixel serves a purpose in monitoring and enforcement.
2. **Institutional Trust:** A palette that signifies official capacity and reliability.
3. **High Scannability:** Clear visual hierarchies to help officers identify violations and vehicle details in milliseconds.

## Colors
This design system utilizes a structured palette optimized for both day-shift and night-shift operations.

- **Primary Blue (#2874F0):** Used for primary actions, navigation highlights, and active states to convey authority.
- **Accent Yellow (#FFD700):** Reserved for critical focus areas, alerts, and highlighting specific enforcement data.
- **Semantic Colors:** Success (Green), Danger (Red), and Warning (Orange) are strictly mapped to violation severity and system status.
- **Neutral Grays:** Derived from a "Blue-Gray" scale to reduce eye strain during long monitoring sessions.

## Typography
The typography system uses **Inter** for all UI elements to ensure maximum legibility across different resolutions. For technical data—specifically vehicle license plates and chassis numbers—**JetBrains Mono** (or Roboto Mono) is used to provide unambiguous character recognition (e.g., distinguishing '0' from 'O').

- **Headlines:** Use tight letter spacing for a modern, compact feel.
- **Plate Display:** Increased letter spacing and monospaced alignment for instant recognition of vehicle IDs.
- **Labels:** Uppercase labels are used for metadata descriptions to create clear separation from user-generated or system-retrieved data.

## Layout & Spacing
The layout follows a **Fluid Grid** model with strict vertical rhythm. 

- **Header:** A fixed 64px global navigation bar anchors the experience, featuring a 3px primary blue accent bar at its base.
- **Grid:** A 12-column grid system for desktop, collapsing to 1 column for mobile enforcement.
- **Padding:** A base unit of 8px is used. Most cards and containers utilize 16px (2 units) of internal padding to maintain a clean, e-commerce-inspired density.
- **Breakpoints:** 
  - Mobile: < 768px (Fluid, 16px margins)
  - Tablet: 768px - 1024px (Fluid, 24px margins)
  - Desktop: > 1024px (Max-width 1440px, centered)

## Elevation & Depth
The system utilizes **Tonal Layers** and subtle shadows to differentiate the background from actionable surfaces.

- **Level 0 (Background):** #F1F3F6 (Light) / #0D1117 (Dark). Used for the base canvas.
- **Level 1 (Cards/Panels):** Pure white (Light) / #161B22 (Dark). These containers use a 1px border (#E0E0E0) and a subtle 0 2px 4px rgba(0,0,0,0.05) shadow in light mode.
- **Level 2 (Modals/Popovers):** Higher elevation with a more pronounced shadow (0 8px 16px rgba(0,0,0,0.1)) to draw focus for immediate violation validation.

In Dark Mode, depth is achieved through slightly lighter surface colors rather than heavy shadows to maintain contrast and accessibility.

## Shapes
A hybrid shape strategy is employed to balance approachability with administrative rigor:

- **Cards & Containers:** 8px (rounded-lg) for a modern, dashboard feel.
- **Action Elements (Buttons/Inputs):** 4px (soft) to emphasize precision and functional utility.
- **Status Badges:** 2px or fully square for a more "official" document/stamp appearance.

## Components

### Buttons
- **Primary:** Background #2874F0, Text #FFFFFF, 4px radius. 
- **Secondary:** Border 1px #2874F0, Text #2874F0.
- **Standard Height:** 36px for all input-adjacent actions.

### Input Fields
- **Styling:** 1px border #E0E0E0, 4px radius, 36px height.
- **Active State:** 1px solid #2874F0 with a subtle glow.

### Severity Badges
Used for violation categorization:
- **High:** Red background, white text. Bold weight.
- **Medium:** Orange background, white text.
- **Low:** Yellow background, dark text (#212121).

### Cards
- **Padding:** 16px uniform.
- **Border:** 1px solid #E0E0E0.
- **Header:** Optional subtle gray background (#F8F9FA) for the card header area to separate title from content.

### Icons
- **System:** Use Lucide icons at 18px or 20px scale.
- **Stroke Width:** 2px for clarity.
- **Coloring:** Match the text color (Primary or Muted) unless used as a status indicator.
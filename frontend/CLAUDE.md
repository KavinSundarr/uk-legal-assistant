# Frontend Development Guidelines
# UK Legal Assistant — Senior Web Developer Workflow

## Standing Instructions — Read Before Every Task

1. Read this entire CLAUDE.md file first
2. Read ISSUES.md if it exists — check all open issues
3. Complete your assigned phase
4. Append your report to ISSUES.md
5. Never delete existing ISSUES.md content
6. Flag if your changes might affect a previously 
   reported open issue

## Project Context
This is the frontend for UK Legal Assistant — an AI-powered 
legal information tool for the UK public. Users include 
immigrants, international students, drivers, tenants, and 
workers. Many users are in stressful situations and need 
to trust this tool immediately.

## Design Philosophy
- Trustworthy and professional — NOT flashy or playful
- Government-service inspired (like gov.uk) but warmer
- Clean, spacious, and readable
- Every design decision should increase user trust
- Mobile first — many users will be on phones

## Brand Guidelines
Primary colour:    #1d70b8  (UK Gov blue)
Secondary colour:  #003078  (Dark navy)
Accent colour:     #00703c  (Gov green — for success states)
Warning colour:    #d4351c  (Gov red — for disclaimers)
Background:        #f3f2f1  (Light warm grey)
Card background:   #ffffff  (Pure white)
Text primary:      #0b0c0c  (Near black)
Text secondary:    #505a5f  (Mid grey)

Typography:
- Font: Inter (Google Fonts) — clean, readable, trustworthy
- Headings: 700 weight
- Body: 400 weight, 1.6 line height
- Never use decorative or script fonts

Spacing system: 4px base unit (4, 8, 12, 16, 24, 32, 48, 64px)

## Component Standards

### Cards
- White background
- Subtle border: 1px solid #e0e0e0
- Border radius: 8px
- Box shadow: 0 2px 8px rgba(0,0,0,0.08)
- Hover: shadow deepens, subtle border colour change
- Never use heavy drop shadows or glows

### Buttons
- Primary: #1d70b8 background, white text
- Hover: #003078 (darken, no animation gimmicks)
- Border radius: 6px
- Padding: 12px 24px
- Font weight: 600
- Clear focus states for accessibility

### Category Cards
- Grid layout 4 columns desktop, 2 columns mobile
- Icon + label, clean and simple
- Selected state: blue border + light blue background
- Hover: subtle lift (transform: translateY(-2px))

### Chat Messages
- User messages: right aligned, blue background #1d70b8
- Assistant messages: left aligned, white with border
- Avatar: scales icon, not emoji
- Timestamp on each message
- Source citations collapsible below each answer

### Input Area
- Prominent, always visible at bottom
- Clear placeholder text
- Character counter
- Send button right aligned

## What Agents Must Do

### Agent 1 — Layout Agent
Responsible for: overall page structure, grid system,
responsive breakpoints, spacing consistency
Reports: any layout that breaks on mobile

### Agent 2 — Component Agent  
Responsible for: individual UI components (cards, buttons,
chat bubbles, inputs), hover states, active states
Reports: any component that looks inconsistent

### Agent 3 — Typography Agent
Responsible for: font loading, sizes, weights, line heights,
colour contrast (WCAG AA minimum), readability
Reports: any text that fails contrast check

### Agent 4 — UX Agent
Responsible for: user flow, loading states, error states,
empty states, accessibility (tab order, aria labels)
Reports: any interaction that could confuse a stressed user

## Specific Issues to Fix (Priority Order)

1. CRITICAL — Visual hierarchy is flat
   Headers and body text look the same weight
   Fix: proper typographic scale h1>h2>h3>body

2. CRITICAL — Category cards look basic
   Plain boxes with no depth or interactivity
   Fix: proper hover states, selected states, icons larger

3. HIGH — Chat interface lacks polish
   Message bubbles are unstyled
   Fix: proper bubble design, avatars, timestamps, spacing

4. HIGH — No loading states
   User has no feedback while API is processing
   Fix: animated typing indicator, skeleton screens

5. HIGH — Mobile layout broken
   Categories overflow on small screens
   Fix: proper responsive grid

6. MEDIUM — Input area looks like a textarea
   Not prominent enough, no visual weight
   Fix: prominent card with shadow, better send button

7. MEDIUM — Sources section hidden/unclear
   Users dont know sources exist
   Fix: clear expandable source cards below each answer

8. LOW — No empty state design
   First load looks incomplete
   Fix: proper welcome state with example questions visible

## Code Standards
- Semantic HTML (nav, main, section, article, aside)
- CSS custom properties for all colours and spacing
- No inline styles
- BEM naming convention for CSS classes
- Vanilla JS only — no frameworks
- All interactions must work without JS (progressive enhancement)
- Comments on every JS function explaining what it does
- Error handling on every API call

## Accessibility Requirements
- All images have alt text
- All interactive elements keyboard accessible
- Focus visible on all interactive elements
- ARIA labels on icon-only buttons
- Colour contrast minimum 4.5:1 for normal text
- 3:1 for large text

## Performance Requirements  
- No external CSS frameworks (no Bootstrap/Tailwind)
- Maximum 2 external font requests
- Images optimised
- JS deferred or at bottom of body
- First meaningful paint under 2 seconds

## Reporting Format
After each change agent must report:
AGENT: [name]
CHANGED: [what was changed]
TESTED: [what was verified]
ISSUE FOUND: [any new issues discovered]
STATUS: Complete / Needs Review

## Issue Tracking & Memory System

After completing each phase, append a report to a file 
called ISSUES.md in this directory using this exact format:

---
## [PHASE NAME] — [DATE]
### Agent: [Agent name]

### Changes Made
- [list every file changed]
- [list every change made]

### Issues Found
- [ISSUE-001] Description of issue | Status: Open/Fixed
- [ISSUE-002] Description of issue | Status: Open/Fixed

### Issues Fixed This Phase
- [ISSUE-XXX] What was fixed and how

### Known Limitations
- [anything that cannot be fixed right now and why]

### Next Phase Dependencies
- [anything the next phase needs to know before starting]
---

Before starting ANY phase, read ISSUES.md first.
Check if any open issues from previous phases 
affect the work you are about to do.
If you find a fix for a previously reported issue 
update its status to Fixed in ISSUES.md.
Never delete old entries — only append new ones.
This gives us a complete history of every decision made.
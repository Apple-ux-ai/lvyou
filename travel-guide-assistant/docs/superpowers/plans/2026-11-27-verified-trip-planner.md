# Verified trip planner

Goal: move the local itinerary from text suggestions to a dated, editable plan that explains what it can verify.

- Prove Osaka Castle admission, seasonal closure, and shared attraction-cap cases in tests. Keep dated official facts in a small independent catalog; never treat an unmatched stop as a verified or free stop.
- Extend the existing itinerary JSON with optional trip settings and stop fields; preserve old activities and transport notes.
- Add planner checks against the authoritative catalog, date/time editing, keyboard/mobile reordering and a printable plan. Test the full save/reopen flow and document limits.
- Review as a traveler on desktop and mobile. Publish changes in a review branch, not main.

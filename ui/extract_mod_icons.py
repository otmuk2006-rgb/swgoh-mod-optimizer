# Mod shape (square/arrow/diamond/triangle/circle/cross) and mod set
# (health/offense/.../tenacity) icon assets in ui/static/img/mods/ — a
# one-off manual capture, same story as the gear/relic ring assets in
# extract_assets.py: not from ae2 (its mod-shape asset only ever downloaded
# as a blank white mask — Unity-side these are composited from multiple
# layers, not a flat texture ae2 can pull), so reverse-engineered from
# swgoh.gg's rendered mods page via Selenium instead.
#
# RENDERING MECHANISM — three real layers, all verified via getComputedStyle
# across many real equipped mod cards (never guessed from how a screenshot
# looked):
#
#   1. `.stat-mod-icon-shape__shape` — the chrome body art (the big
#      gold/silver 3D-relief frame most of the icon's visual weight comes
#      from). Directly compared its computed background-image across many
#      real cards varying tier AND dots independently: for a fixed dots
#      count the image is byte-identical across every tier (1 through 5),
#      and it only ever takes ONE of two forms — a "standard" look (dots
#      1–5) and a distinct "max" look (dots 6, the gold-plated one). This
#      layer is NOT tier-tinted at all — a first pass at this file
#      wrongly assumed it was just a fancier version of the outline mask
#      and skipped capturing it; that produced mod icons that were
#      basically invisible (thin thing outline, no body), which is what
#      prompted re-deriving this from scratch.
#   2. `.stat-mod-icon-shape__outline` — the thin rim mask. Confirmed
#      byte-identical mask image across every tier/dots combination for a
#      given shape; only its `background-color` changes, and that IS
#      tier-driven (see RGB table below).
#   3. `.stat-mod-icon-shape__set` — the set glyph badge. Same story as
#      the outline: fixed mask shape per set, `background-color` driven by
#      tier (confirmed: `stat-mod-icon-shape--set-1` rendered
#      rgb(255,255,255) at tier-1 and rgb(146,65,255) at tier-4 on the
#      exact same DOM element).
#
# Exact tier colours (getComputedStyle, not eyeballed from a screenshot):
#   tier 1 (grey)   rgb(255, 255, 255)
#   tier 2 (green)  rgb(152, 253, 51)
#   tier 3 (blue)   rgb(0, 189, 254)
#   tier 4 (purple) rgb(146, 65, 255)
#   tier 5 (gold)   rgb(255, 204, 51)
#
# NUMBERING GOTCHA: swgoh.gg has its own internal slot-N / set-N numbering
# for these CSS modifier classes, and it does NOT match this project's own
# SLOT_MAP / SET_MAP digit conventions (scraping/user_mod_data.py, sourced
# from Comlink's definitionId digits). Confirmed by direct visual inspection
# of the decoded masks — do not assume digit equivalence between the two.
#
#   swgoh.gg slot -> this project's shape name (by visual shape):
#     2=square  3=arrow  4=diamond  5=triangle  6=circle  7=cross
#     (slot 1 never observed — likely unused/reserved)
#
#   swgoh.gg set -> this project's set name (by visual glyph):
#     1=health (cross/syringe)      2=offense (plain burst)
#     3=defense (shield)            4=speed (running figure)
#     5=critical_damage ("2x" burst) 6=critical_chance ("!" burst)
#     7=potency (crosshair/reticle) 8=tenacity (raised fist)
#   Note sets 5/6 are swapped relative to this project's own SET_MAP digits
#   (which has 5=critical_chance, 6=critical_damage) — another confirmation
#   the two numbering schemes are independent and must never be assumed
#   equivalent by digit alone.
#
# CAPTURE SOURCE: https://swgoh.gg/p/846927846/mods/ (a real player's mods
# page — real equipped mod cards gave the tier-colour verification above;
# the page's own set/shape *filter legend* — `.stat-mod-set-def-icon`,
# always renders all 8 sets regardless of what that player actually owns —
# gave the two set masks (potency, tenacity) missing from their roster).
# Both sources' mask assets were confirmed byte-identical (same base64
# content) for every set that appeared in both places, so the filter legend
# is a reliable stand-in for sets a given player doesn't happen to have.
#
# ae2 (swgoh-ae2, see extract_assets.py) was tried again for these before
# falling back to swgoh.gg — it turns out the game genuinely does have
# assets named `ui_charactermods_component_square` etc, but fetching any of
# them 500s with "Could not find file ...tex.ui_charactermods_component_
# square.png" — i.e. there's no flat baked texture behind that name at all,
# it's a Unity prefab assembled live from sub-elements at runtime. Confirms
# these can't be extracted as flat images by design, not just a gap in ae2's
# catalog.
#
# This is a one-off capture, not an ongoing pipeline — swgoh.gg is
# Cloudflare-protected and these assets change rarely. Final files:
#   ui/static/img/mods/shapes/{square,arrow,diamond,triangle,circle,cross}.webp
#     — outline masks, plain alpha (no colour baked in), tinted at render
#     time via CSS mask-image + background-color (tier)
#   ui/static/img/mods/shapes/{square,arrow,diamond,triangle,circle,cross}_
#   {standard,max}.webp
#     — shape-fill chrome body art, full colour already baked in, used as
#     a plain background-image, NOT tinted. "standard" = dots 1–5,
#     "max" = dots 6.
#   ui/static/img/mods/sets/{health,offense,defense,speed,critical_damage,
#                             critical_chance,potency,tenacity}.webp
#     — set glyph masks, plain alpha, tinted at render time same as the
#     outline (tier).
# See .mod-shape-fill / .mod-shape-outline / .mod-set-icon in
# ui/static/css/style.css for how the three layers stack. Reference copy of
# the tier/set/shape mapping, plus the exact tier RGB values above, also
# live in data/processed/mod_icon_assets.json.
#
# A circuit-board "loadout panel" background (matching swgoh.gg's own
# per-character unit page) was tried and then removed by request — kept to
# the plain 2x3 card grid instead. If revisited, swgoh.gg's version lives
# at `/p/<allycode>/unit/<CHAR_ID>/` under `.stat-mod-equipment-set-card`,
# a single background PNG plus a small sprite sheet for level-15 line-glow
# overlays, with slot positions available via getComputedStyle.

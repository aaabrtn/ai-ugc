# AI UGC Content SOP — Fashion Try-On Video Generation
**KLIQMGMT — Google Omni Fashion Framework**

This SOP defines the non-negotiable rules every generation prompt must follow. These exist because specific failure modes have occurred in testing — each rule below is tied to a real, observed problem. Deviating from this SOP is how glitches, unusable renders, and wasted generations happen.

---

## 1. Hard Anatomy & Physics Rules (zero tolerance)

These exist specifically to prevent hand detachment, duplicate phones, and other instantly-unusable glitches.

1. **One hand, one phone, always attached.** Exactly one hand holds the phone at all times. That hand's grip is continuous and unbroken for the entire 10 seconds — it never floats, drifts, separates, hands off, or becomes independent of her hand. The phone is a solid object under normal gravity and human hand mechanics.
2. **Never both hands free.** If the phone-holding hand is doing anything, the prompt must say so explicitly (gripping, angled toward face). The free hand is the only one available for touching fabric, hair, etc.
3. **No full turn, ever.** Maximum rotation in any direction is a **three-quarter turn**. A full 180° / full-back-turn is physically impossible in a selfie POV — a human arm cannot keep the phone aimed at her own face while fully turned away. This is not a style choice, it's an anatomical hard limit.
4. **No duplicate/extra limbs, ever.** Anatomy stays completely consistent frame to frame. No extra arms, hands, or duplicated body parts.
5. **Distance before turning.** She stands at a natural arm's-length-plus from the mirror before any turn begins. Standing too close to the mirror increases the risk of arm-detachment artifacts during rotation.
6. **Write physics in positive terms.** Never phrase constraints as negation ("her hand doesn't detach"). Diffusion/video models reinforce whatever concept is named — so write what the body *does* ("her hand stays gripping the phone throughout"), not what it must avoid doing.
7. **Anti-detachment language repeats every cut, not once.** The grip/attachment rule must be restated in each individual cut's description, not just once at the top of the prompt. A single top-level mention is not enough to hold through 5 hard cuts of fast movement.
8. **No watermarks, no AI-tool branding.** Every prompt explicitly prohibits watermarks, logos, or visible generation-tool branding in the output.

---

## 2. The Locked 5-Cut Jump-Skip Structure (every 10s video)

This is the default pacing skeleton. Hard jump-cuts every 2 seconds, 5 total, no smooth transitions between them — this replicates TikTok-style fast editing.

| Cut | Time | Beat |
|---|---|---|
| 1 | 0–2s | **Opening hook** — video starts already mid-motion, as if caught mid-action. She walks quickly toward the mirror, then catches herself and steps back slightly, settling into a hip roll. Never opens static. |
| 2 | 2–4s | Three-quarter turn, one side — shows the garment's fit over the hip/silhouette. |
| 3 | 4–6s | Three-quarter turn, opposite side — shows the other side / back detail (open back, hardware, etc.) without ever rotating fully away. |
| 4 | 6–8s | Front-facing — shimmy/bounce, free hand touches/feels the fabric naturally. |
| 5 | 8–10s | Front-facing — spin-in-place snap (within the three-quarter limit), settles, holds on a bright final beat. |

- Movement pace across all 5 cuts: **~1.2x natural speed** — energetic, TikTok-fast, but not frantic or glitchy.
- Each cut is a hard jump — no cross-fades, no smoothing between poses.

---

## 3. Face-Cover Rule (permanent, every cut)

- She holds her phone directly over her face for the **entire** video. Her full face is never revealed, in any cut.
- Only hair, jawline, neck, and body are visible.
- The phone naturally partially obscuring her face is the *desired* look, not something to minimize — lean into it.
- This must be written as a natural, physically grounded action (her arm genuinely positioned to hold the phone up), not an artificial "block the face" instruction.

---

## 4. Fabric-Touch Rule

- She naturally touches/feels the garment at some point (fabric, texture, hem, tie, hardware) using her **free** hand only.
- This should read as an unconscious, natural gesture — not a deliberate close-up or zoom. No macro/zoomed shots of the fabric. She just feels it in the course of moving, and the texture reads through that natural contact.
- Only include hand gestures that have a physical reason (adjusting the garment, touching hair, feeling fabric) — generic "hand movement" with no cause reads as fake. This rule exists because hand gestures in reference/talking videos are speech-driven; in a silent video they need their own physical justification.

---

## 5. Silence Rule

- **Zero audio track.** No voiceover, no ambient sound, no room tone — fully silent pipeline.
- Her mouth never moves, at any point, in any cut. Lips stay fully still throughout.
- No subtitles, no on-screen text, no captions.

---

## 6. Setting & Camera Consistency

- **Same mirror, same room, every single cut** — background must be 100% visually identical across all 5 cuts. Zero drift. Only her pose, angle, and movement change between cuts.
- Camera reads as propped casually and imperfectly — off-centre, slightly awkward angle, not a perfectly centred or professional composition.
- Ordinary, unenhanced room lighting — never studio-quality, never perfect.
- Obvious, visible camera wobble that reacts to her body movement (weight shifts, steps) — not a subtle micro-shake. The wobble should feel like a handheld phone genuinely reacting to a moving body.

---

## 7. Authenticity / Imperfection Rule

This is the core philosophy underneath everything else: **realism comes from imperfection, not polish.**

- No glitches, no stickers, no effects, no props, no studio lighting, no "professional" feel of any kind.
- Natural, lived-in setting — not staged or art-directed.
- Natural skin, natural asymmetry, natural imperfections (a stray hair, an imperfect angle, uneven light) — these are what make the video read as authentic rather than AI-generated. Don't smooth these out.
- Baseline restlessness even in "still" beats — small weight shifts, tiny steps. Real amateur footage is never fully static; if a moment reads as posed or frozen, it breaks the illusion.
- Tone: she looks cute, she looks confident/sexy in a natural way — but this comes from genuine, unconscious body language and energy, not overt performance or posing for camera.

---

## 8. Framing Rules

- Full outfit must be visible head-to-toe (or full garment length) — never crop out the lower half of the garment.
- **Never show ankles or below** — no feet, shoes, or footwear at any point. Crop above the ankle, always.
- Outfit is the primary visual subject of the video — not her face (which is covered anyway), not the room.

---

## 9. Garment Accuracy Rule

- Garment description in every prompt must be **precise and product-accurate** — colour, material/texture, fit, hardware, trims, and any loose/free-moving elements (drapes, ties, ruffles) described concretely and specifically. Generic or approximate garment language causes visual drift from the actual product.
- Describe construction details (buckles, rings, ties, ruffle tiers) as **concrete physical objects** with position, size, and behaviour — not as abstract garment-construction jargon. Jargon renders unreliably; physical, spatial description renders correctly.
- Any loose/hanging fabric element (a drape, tie, sash) must be explicitly described as moving independently from the fitted parts of the garment, so the model knows what should move freely versus what stays fixed.
- Full outfit head-to-toe visibility is mandatory in every prompt (see Section 8).

---

## 10. Content Boundaries (non-negotiable, no exceptions)

- Reference garments must be genuine **outerwear** — dresses, rompers, tops, sets meant to be worn out of the house. **Lingerie, sleepwear, or underwear-adjacent garments are never used in this framework**, regardless of framing, caption, or stated intent (including "internal use only"). This is a hard content-category boundary, not a wording problem to prompt around.
- Persona used in any live/client-facing output must be an approved, consent-cleared persona (e.g. Genie1, consent ref on file). Any other likeness pulled from a reference image is for internal prompt-structure testing only and is never cleared for output regardless of how the outfit or scene is dressed up.
- If a generation is blocked by a safety filter, the response is to examine *why* — not to reword language to slip past the filter. If the underlying content is the issue (garment category, sexualized framing), the fix is changing the content, not the wording.

---

## 11. Platform-Specific Notes

- `@[name]` element-lock tag syntax is **Kling-specific only** — never use `@` tags in Omni-Flash / Google Omni Fashion Framework prompts. Persona is described naturally in prose there instead.
- Garment analysis, identity/scene lock, and motion choreography live in separate pipeline nodes — never mixed into a single monolithic prompt block.
- Garment analysis runs once per SKU and is stored to the Products library — it is not re-run per video.
- Identity protection: approved persona reference images override any person visible in garment reference/product images. Prompts must explicitly instruct the model to ignore the identity of anyone shown in garment reference photos.

---

## 12. Known Failure Combinations — Do Not Use

- **Walking + mirror + turning away, combined in one motion** — this combination reliably breaks generation: causes POV camera switches and duplicate-phone artifacts. Never combine all three in a single continuous beat.
- Full back-turn in selfie POV — see Section 1, Rule 3.
- Standing right up against the mirror while initiating a turn — see Section 1, Rule 5.

---

## Quick Pre-Send Checklist

Before sending any prompt, confirm:

- [ ] One phone, one gripping hand, restated per cut
- [ ] No turn exceeds three-quarter rotation
- [ ] Opening cut starts mid-motion, not static
- [ ] All 5 cuts are hard jumps, ~2s each, ~1.2x pace
- [ ] Face covered by phone in every cut
- [ ] Free hand touches fabric naturally at some point (no zoom)
- [ ] Zero audio, mouth never moves, no captions/text
- [ ] Background identical across every cut
- [ ] Garment described precisely, with real product detail
- [ ] Ankles/feet never shown
- [ ] No lingerie/sleepwear garments, no non-cleared persona
- [ ] No watermark/branding anywhere in prompt or expected output

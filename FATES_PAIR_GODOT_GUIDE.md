# FATE'S PAIR — Godot Learning Guide + Build Steps

> Game for zoubair & his gf. Godot 4.7, Forward Plus, Jolt Physics, Mixamo "Ch15" character.
> Main project lives at: `D:\gameproject\fate's-pair`
> Full technical reference: `FATES_PAIR_PLAYER_REBUILD_PLAN.md` (on the Desktop)

---

## PART 1 — GODOT THINGS YOU NEED TO LEARN

These are the fundamentals in the order you'll actually use them. Don't try to learn everything at once — learn just enough to complete the current build step, then come back for the next.

### 1. Nodes & the Scene Tree
- Everything in Godot is a **Node**. A game is a tree of nodes.
- Examples: `CharacterBody3D`, `Camera3D`, `Skeleton3D`, `AnimationPlayer`, `Timer`, `MeshInstance3D`.
- Nodes have **properties** (e.g. `velocity`), **methods** (e.g. `move_and_slide()`), and **signals** (e.g. `body_entered`).
- Learn: how to add nodes, rename them, parent them, and set properties in the Inspector.

### 2. Scenes (.tscn) & Instancing
- A **scene** is a saved node tree — your player, your floor, your grenade are each their own scene.
- You can **instance** a scene inside another (e.g. `world.tscn` contains an instance of `player.tscn`).
- Scenes are text files — you can read them. That's how we debug "why is my camera inside the floor".

### 3. Signals
- The way nodes talk to each other without hard-coding references.
- E.g. `Timer.timeout` → reload is done. `Area3D.body_entered` → grenade hit someone.
- Connect them in the editor (Node tab → Signals) or in code with `signal_name.connect(...)`.

### 4. `_ready()` vs `_process(delta)` vs `_physics_process(delta)`
- `_ready()`: runs once when the node enters the tree. Setup stuff here (get node refs, connect signals).
- `_process(delta)`: runs every **rendered frame**. Use for camera, UI, anything visual.
- `_physics_process(delta)`: runs at a **fixed 60Hz**. Use for anything physics — movement, jumping, gravity. **Player movement goes here. Always.**
- `delta` = time since last frame. Multiply speeds by it (`velocity * delta`) to stay framerate-independent.

### 5. Input Map & Actions
- Don't check raw keys in scripts. Define **actions** in Project Settings → Input Map (`move_forward`, `jump`, `fire`, `reload`...).
- Then read them: `Input.get_vector("left", "right", "forward", "back")`, `Input.is_action_just_pressed("jump")`.
- Action names are strings — a typo like `"forword"` silently breaks the game. Watch your spelling (ours is misspelled right now, we'll fix it).

### 6. Vector Math Basics
- `Vector3(x, y, z)` — position, direction, velocity. All the same type in Godot.
- Godot 3D: **forward is -Z**. X is right, Y is up.
- `transform.basis` = the node's rotation matrix. `transform.basis * Vector3(...)` rotates a direction to face the way the node faces.
- To convert world velocity into "which way am I moving relative to my own facing": `transform.basis.inverse() * velocity`. We use this to feed the animation blend.

### 7. CharacterBody3D & `move_and_slide()`
- The node for a player that moves and collides (as opposed to RigidBody3D = physics-driven, StaticBody3D = immovable).
- Pattern:
  ```gdscript
  func _physics_process(delta):
      if not is_on_floor():
          velocity += get_gravity() * delta
      # modify velocity...
      move_and_slide()
  ```
- `is_on_floor()`, `is_on_wall()` are your ground/wall checks.

### 8. AnimationPlayer
- Plays one animation clip at a time on a skeleton (or any node).
- `anim_player.play("Walking")`, `anim_player.queue("Jump")`, connect `animation_finished`.
- Used early for simple cases; the real character uses AnimationTree instead.

### 9. AnimationTree (the big one)
- The advanced animation system. Tree root = **AnimationNodeStateMachine** (states + transitions, e.g. FullBody ⇄ Jump).
- Inside a state you can use:
  - **BlendSpace2D** — blend between clips based on a 2D value (our locomotion: X = strafe, Y = forward/back speed). ⚠️ Set **Sync = Cyclic Mutable** for locomotion or footsteps feel sticky on diagonals.
  - **AnimationNodeBlendTree** — mix multiple animations at once with weights (upper body aim over lower body walk).
  - **AnimationNodeOneShot** — fire an animation once on top of everything (gunshot, reload, grenade toss).
- Script drives it via paths: `anim_tree.set("parameters/FullBody/Locomotion/blend_position", Vector2(x, y))`.

### 10. BoneAttachment3D
- Attaches a node to a specific skeleton bone (e.g. camera to `mixamorig_Head`, gun to `mixamorig_RightHand`).
- Child of Skeleton3D, set `bone_name`, then add your Camera3D / weapon mesh as its child.
- ⚠️ Only safe after the upper/lower body split is working — otherwise hip lean from leg animations shakes your view.

### 11. Physics Layers & Collision
- Every object has a collision layer + mask (bitmasks). Layer = what it IS. Mask = what it DETECTS.
- Set up layers: `1 = world`, `2 = player`, `3 = enemy`, `4 = grenade`, etc.
- Raycast from camera: `camera.project_ray_origin()` + `project_ray_normal()` → `PhysicsRayQueryParameters3D` → `get_world_3d().direct_space_state.intersect_ray(...)`.

### 12. Timers & Tweens
- `Timer` node — countdown that fires `timeout`. Use for: reload cooldown, grenade fuse, fire rate.
- `Tween` — animate a value smoothly over time. Use for: UI fades, camera shake, pickup feedback.

### 13. Shaders (just enough)
- A shader = code that runs on the GPU per-pixel/per-vertex.
- We already have gdshader files (fireball, trail, ball). You don't need to master these — learn to *apply* them to a material and tweak exposed variables from scripts via `material.set_shader_parameter("name", value)`.

### 14. Exporting the Game
- Project → Export. Windows preset → your .exe. For a 2-player game you'll eventually need networking (Godot's High-Level Multiplayer API / ENet) — but that's a **much later** step. Build single-player first, then add multiplayer.

---

## PART 2 — MIXAMO → GODOT PIPELINE (memorize this)

Every single clip follows the exact same recipe. No exceptions.

**Download settings (on mixamo.com):**
- Format: **FBX Binary**, FPS: **30**, Keyframe Reduction: **None**
- Character download: **With Skin** (just once — the mesh)
- Every animation clip: **Without Skin**
- Movement clips: enable **"In Place"** (Walking, Running, strafes, backwards) so the character doesn't drift across the floor
- Trim jump anticipation/crouch frames before downloading if possible

**Import in Godot:**
1. Drag the `.fbx` into the project (put clips in `animations/player/`).
2. Select it → Import tab → **Advanced Import Settings** → set **Import As: Animation Library** → Reimport. ⚠️ If you skip this, "Load Library" will reject the file.
3. In `player.tscn`, select the AnimationPlayer → Animation Libraries → **Load Library** → pick the reimported file.
4. In the Animation panel, drag the player's real `Skeleton3D` node onto the loaded track list → **Replace** (retargets the clip to our skeleton).

⚠️ Don't drag an animation `.fbx` into the scene tree as a node — it creates a stray skeleton/AnimationPlayer that double-writes to your bones and causes violent shaking.

**Clips we need (all Mixamo, "Ch15"):**

| Clip | Purpose | In Place? |
|---|---|---|
| BreathingIdle | center of blend space | no |
| Walking | basic move | yes |
| Running | sprint | yes |
| Walking Backwards | backward move | yes |
| Left/Right Strafe Walking | slow strafe | yes |
| Left/Right Strafe | fast strafe | yes |
| Jump | airborne | no (trim anticipation) |
| RifleIdle | aiming pose (upper body) | no |
| firing rifle | one-shot upper body | no |
| reloading | one-shot upper body | no |
| toss grenade | one-shot upper body | no |

**Current status:** `walking.fbx`, `Left/Right Strafe Walking.fbx`, `Walking Backwards.fbx` are downloaded but **imported as scenes, not Animation Libraries** — they need the re-import treatment. BreathingIdle, Running, Jump, RifleIdle still need downloading.

---

## PART 3 — BUILD THE GAME, STEP BY STEP

Target scene hierarchy:

```
player (CharacterBody3D)  ← player.gd
├── playercollision (CollisionShape3D — capsule)
├── character (Node3D — 180° flip for Mixamo forward axis)
│   ├── Skeleton3D (65 bones, mixamorig_*)
│   │   ├── Ch15 (MeshInstance3D)
│   │   └── HeadCamera (BoneAttachment3D, mixamorig_Head)
│   │       └── Camera3D          ← only after step 6!
│   ├── AnimationPlayer
│   └── AnimationTree
```

Build **in this order**, fully test each stage before the next:

1. **Bare scene + character import** — mesh/skeleton in, capsule collision, camera as plain child of player (NOT bone-attached). ✅ *Mostly done in D:\gameproject\fate's-pair*
2. **WASD + mouse-look + jump, zero animation** — capsule only, no mesh. Fix the `forword` typo → `forward`, use the `JUMP` action not `ui_accept`, add mouse look (yaw on body, pitch clamped). Smooth velocity with `move_toward()`.
3. **BreathingIdle + Walking** — import both as Animation Library, load into AnimationPlayer, play Walking when moving, Idle when stopped. Proves the whole import/retarget pipeline works before adding complexity.
4. **Add Jump as a state machine** — FullBody ⇄ Jump, transitions `Immediate` + `Advance Mode = Disabled` on both, script-driven `travel()` only. Landing detected via `is_on_floor()` change, not animation length.
5. **Full BlendSpace2D** — Run, WalkingBackwards, both strafe tiers. Sync = **Cyclic Mutable**. Test every direction incl. diagonals.
6. **Upper/lower body split** — FullBody BlendTree: Locomotion + RifleIdle → Blend2 (amount 1.0). Filter **includes Hips** (the whole spine chain's parent!) + spine + arms. Legs NOT filtered. Test strafing has zero lean/wobble.
7. **Camera onto Head bone** — BoneAttachment3D on `mixamorig_Head`. Head pitch in script must be **absolute** (compute from `get_bone_rest()`, never multiply onto previous frame's value — that caused the 360° spin).
8. **Weapon model** — BoneAttachment3D on `mixamorig_RightHand`, hand-tune local transform so it sits in the grip.
9. **Fire + reload** — two `AnimationNodeOneShot`s (each with its own upper-body filter) after Blend2. Ammo, fire-rate cooldown, raycast from camera center, muzzle flash + sound. Fire while walking must NOT freeze the legs.
10. **Grenade throw** — third OneShot (GrenadeToss) + separate grenade scene: `RigidBody3D` + sphere collision + mesh, launched in camera forward+up arc, `Timer` fuse ~3s, `Area3D` explosion check, VFX, `queue_free()`. Spawn the grenade at the release point in the swing (short Timer after the animation starts), not instantly on keypress.
11. **Polish** — acceleration tuning, crossfade timing, jump anticipation trim, pitch range, muzzle flash/impact VFX.
12. **Movement + combat basics done → move on to Items.**

---

## PART 4 — HARD-WON LESSONS (don't repeat these!)

1. **Mixamo settings:** FBX Binary, 30fps, no keyframe reduction. Character = With Skin, clips = Without Skin, movement = In Place.
2. **Import As: Animation Library**, or Load Library rejects the file.
3. Never instance animation `.fbx` files into the scene — stray skeletons cause double-writers.
4. **Never let AnimationPlayer and AnimationTree both process physics** — that double-writer caused violent shaking, twice.
5. Script-driven state transitions need **Advance Mode = Disabled**. "Auto" fires every frame → oscillation.
6. Jump→Landing is physics-determined — detect `is_on_floor()` explicitly, never rely on clip length.
7. **Jump input must be event-queued** (`_unhandled_input` + bool consumed once in `_physics_process`), not polled with `is_action_just_pressed()` — framerate dips cause double-fires.
8. Jump clips have anticipation frames — trim on Mixamo or use Start Offset, or the capsule lifts before the mesh visibly does.
9. **Hips must be in the upper-body filter.** Filtering Spine→Head but leaving Hips on locomotion lets baked lean propagate through the whole chain.
10. BlendSpace **Sync = Cyclic Mutable** for locomotion, or diagonal footsteps feel sticky.
11. Bone overrides in script must be **absolute, not accumulating** — never multiply a quaternion onto last frame's output.
12. Camera stays a plain child of player until hip-lean is neutralized (lesson 9) — much easier to debug.
13. "not a valid AnimationLibrary" = it's a plain Animation resource, not a Library. Fix at the source (Import As), don't extract manually.

---

## PART 5 — WHAT WE DO RIGHT NOW (immediate action list)

1. **Re-import the 4 existing clips** as Animation Library (they're currently scenes). Test Load Library works.
2. **Download the missing clips** from Mixamo with the exact settings: `BreathingIdle`, `Running`, `Jump`, `RifleIdle` (then later: `firing rifle`, `reloading`, `toss grenade` — those may exist in the old beta project, check `C:\Users\book\Desktop\Lydia-workspace\fate's-pair-beta`).
3. **Fix the input map** — rename `forword` → `forward`, add `sprint`, keep `JUMP` and use it in code instead of `ui_accept`.
4. **Upgrade player.gd** (stage 2): mouse look, clamped pitch, `move_toward()` acceleration, event-queued jump, `just_landed` detection.
5. **Rebuild player.tscn** to the target hierarchy with AnimationPlayer (stage 3): Idle + Walking only. Verify the pipeline end-to-end.
6. Then follow Part 3 steps 4 → 12, testing each one before moving on.

---

## PART 6 — RESOURCES

- Godot docs: https://docs.godotengine.org/en/stable/
- AnimationTree docs: https://docs.godotengine.org/en/stable/tutorials/animation/animation_tree.html
- Mixamo: https://www.mixamo.com
- CharacterBody3D: https://docs.godotengine.org/en/stable/classes/class_characterbody3d.html
- Input Map: https://docs.godotengine.org/en/stable/tutorials/inputs/input_examples.html

**Golden rule:** one system at a time. Test it. Then add the next. That's the whole secret to not going insane.

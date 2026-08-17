# Fate's Pair — Development Roadmap
### "Operation: Last Dance" — An Online Co-op Love Story Shooter

> Built for two players (you + your gf), **online co-op over the internet**.
> Engine: **Godot 4.x** (use 4.3+ for the best 3D + Terrain3D support)

---

## 🎯 The Vision (Recap)

Two married soldiers, Elias "El" Vance and Kiera "Kite" Vance, keep their marriage secret.
Shot down behind enemy lines, 72 hours to exfil, and Kiera is bleeding internally.
The game is a love story told through **suppression, flanking, and medical aid**.

**Core design pillars:**
1. Complementary loadouts (Breacher + Recon) → forces communication
2. Tactical Ping system → no wallhacks, real callouts
3. Suppression mechanic → realistic firefights
4. Medical Buddy system → the emotional core (you physically save her)
5. No regenerating health → shared stakes

---

## 🌐 Online Co-op: The Big Picture

Since this is **online** (not split-screen), you need a networking layer on top of everything.
Here's how it works at a high level:

- **One player is the HOST** (you), the other is the CLIENT (your gf).
- The host runs the authoritative game world (enemies, physics, health).
- The client sends inputs to the host and receives world updates.
- Godot has this **built in** via `MultiplayerSpawner`, `MultiplayerSynchronizer`, and `RPC` calls — you don't need a server, just one of you hosting.

---

## 📚 What You Need to Learn (Godot Skills, In Order)

### Phase 0 — Godot Basics (don't skip)
- Scene tree & nodes (how everything is organized)
- `_ready()`, `_process(delta)`, `_physics_process(delta)` lifecycle
- Signals (Godot's event system — like events in JS)
- `@export` variables (expose stuff in the Inspector)
- Input map (define actions like "move", "shoot", "ping")
- Instancing scenes with `preload()` and `load()`

**Resources:** Official Godot docs + "Godot 4 for Beginners" tutorials (Brackeys / GDQuest on YouTube).

### Phase 1 — 3D Character Controller
- `CharacterBody3D` + `CollisionShape3D` (capsule)
- `move_and_slide()` for movement
- Camera control (mouse look)
- Gravity, jumping
- **Godot 4 note:** use `Input.get_vector()` for smooth WASD movement

### Phase 2 — First-Person Shooting
- Raycast shooting (`RayCast3D` or physics query)
- Hitscan vs. projectile (hitscan is simpler + better for this game)
- Ammo system (magazine + reserve)
- Recoil / spread / crosshair
- Weapon switching

### Phase 3 — Enemy AI (Volk soldiers)
- Basic state machine: Idle → Patrol → Alert → Combat → Suppressed
- Navigation: `NavigationAgent3D` + `NavigationRegion3D`
- Line-of-sight detection (RayCast to player)
- **Suppression logic:** if shots pass near them → enter "Suppressed" state (duck, stop shooting)

### Phase 4 — ONLINE MULTIPLAYER (the big one)
- **High-Level Multiplayer API** (`MultiplayerAPI`, `multiplayer.peer_connected`)
- Hosting (server) vs. connecting (client)
- `MultiplayerSpawner` — auto-spawn player scenes on all peers
- `MultiplayerSynchronizer` — sync position, rotation, health across the network
- **RPCs** (`@rpc` annotation) — call functions on the other player's machine
- **How to play together:** one of you hosts, the other connects via IP (or IP + port). Works over the internet if you port-forward OR use a VPN like Radmin/ZeroTier/Hamachi so you don't have to mess with router settings.

### Phase 5 — The Medical Buddy System (the heart, now networked)
- Health per player (no regen), synced over network
- Field Dressing (self-applied, stops bleeding)
- Morphine (can ONLY be applied by the **other** player) → this is an **RPC** (you call it on her machine)
- Interaction prompt when standing near a downed/limping teammate
- Screen effects: gray vignette when badly hurt, blood splatter on edges

### Phase 6 — Tactical Ping System (now networked)
- Player 2 aims → presses ping → places a red diamond marker in the world
- The marker is **synced** so both players see it (via `MultiplayerSynchronizer` or RPC)
- Player 1 only sees it if facing that direction (dot product check on camera forward vs. marker direction)

### Phase 7 — Mission Structure & UI
- Mission objectives (HUD top: compass + objective markers)
- Ammo counter (bottom right)
- Minimalist HUD (no damage numbers)
- Mission flow: objective → dialogue → next objective

### Phase 8 — Story, Dialogue & Polish
- Dialogue system (subtitles + voice lines)
- The couple banter lines from your story
- Sound design (gunshots, footsteps, winter wind)
- Vignette / post-processing for mood

---

## 🛠️ Recommended Project Structure

```
fates-pair/
├── project.godot
├── scenes/
│   ├── player/
│   │   ├── player.tscn          (shared scene, spawned for both players)
│   │   ├── first_person_camera.tscn
│   │   └── weapons/
│   │       ├── m4.tscn          (Breacher)
│   │       └── mk14.tscn        (Recon)
│   ├── enemies/
│   │   └── volk_soldier.tscn
│   ├── levels/
│   │   ├── mission1_crash_site.tscn
│   │   ├── mission2_farmhouse.tscn
│   │   ├── mission3_frozen_bridge.tscn
│   │   └── mission4_monastery.tscn
│   └── ui/
│       ├── hud.tscn
│       ├── main_menu.tscn
│       └── lobby.tscn           (host / join screen)
├── scripts/
│   ├── player/
│   │   ├── player_controller.gd
│   │   ├── health_system.gd
│   │   ├── weapon_system.gd
│   │   └── interaction_system.gd
│   ├── enemies/
│   │   ├── enemy_ai.gd
│   │   └── suppression.gd
│   ├── systems/
│   │   ├── network_manager.gd   (host/join logic)
│   │   ├── medical_system.gd
│   │   └── ping_system.gd
│   └── ui/
│       └── hud.gd
├── assets/
│   ├── models/    (Quaternius + Mixamo)
│   ├── textures/
│   ├── audio/
│   └── animations/
└── addons/        (Terrain3D, etc.)
```

---

## ✅ Build Order (The "Playable at Every Step" Plan)

### Step 1 — Get a character moving locally (1-2 days)
- Player scene with CharacterBody3D, capsule collision, camera, WASD + mouse look
- **Test:** you can walk around a room. ✅

### Step 2 — Add shooting locally (2-3 days)
- Raycast shooting, ammo, crosshair, simple hit detection
- **Test:** you can shoot targets. ✅

### Step 3 — ONLINE MULTIPLAYER foundation (3-5 days) ← the big technical hurdle
- Set up `MultiplayerSpawner` + `MultiplayerSynchronizer` so two players spawn in the same world
- Host/join menu (IP + port, or via a VPN like Radmin/ZeroTier so you don't port-forward)
- Sync position + rotation of both players
- **Test:** you AND your gf are both walking around the same map on your own computers. ✅ **← huge milestone, celebrate here**

### Step 4 — Networked shooting (2-3 days)
- Sync health and damage over the network
- Both players can shoot and damage enemies (host-authoritative)
- **Test:** you shoot an enemy, she sees it die on her screen. ✅

### Step 5 — Add enemies (3-5 days)
- Volk soldier with basic AI + navigation + line of sight
- Health + death (host-authoritative, synced)
- **Test:** you can fight and kill enemies together. ✅

### Step 6 — Suppression mechanic (2-3 days)
- Enemies duck when shot near
- **Test:** you suppress, she flanks. ✅

### Step 7 — Medical Buddy system over the network (3-4 days)
- Health, field dressings, morphine (partner-only via **RPC**)
- Interaction prompt + "El, I need a push!" callout
- **Test:** she gets hurt, you run to her and inject her — the injection happens on her machine. ✅ **← the emotional core, the soul of the game**

### Step 8 — Tactical Ping system over the network (2 days)
- Ping marker synced to both players + direction-based visibility
- **Test:** she pings, you only see it when facing her callout. ✅

### Step 9 — Mission 1: Crash Site (tutorial) (3-4 days)
- Weapons pickup, initial ambush, couple dialogue
- **Test:** full playable mission online. ✅

### Step 10 — Mission 2: Farmhouse (stealth/sniper) (4-5 days)
- Overwatch + basement breach, ping-based callouts
- **Test:** full playable mission online. ✅

### Step 11 — Mission 3: Frozen Bridge (defend) (3-4 days)
- Wave defense + defuse objective
- **Test:** full playable mission online. ✅

### Step 12 — Mission 4: Monastery (final stand) (4-5 days)
- The morphine choice, carry mechanic, extraction
- **Test:** the full ending online. ✅ **← emotional payoff**

### Step 13 — Polish (ongoing)
- Sound, music, UI, post-processing, difficulty tuning
- The "Worth it." ending sequence

---

## 🎮 Controls Plan (each player uses their own keyboard+mouse)

| Action | Both Players (keyboard + mouse) |
|--------|-------------------------------|
| Move   | WASD                          |
| Look   | Mouse                         |
| Fire   | Left click                    |
| Aim    | Right click                   |
| Reload | R                             |
| Ping   | Q (or middle mouse)           |
| Interact | E                          |
| Crouch | Ctrl                          |
| Sprint | Shift                         |

Since it's online, **each player has their own full keyboard + mouse** — no input conflicts like split-screen. Much cleaner.

---

## 🧠 Key Godot Nodes You'll Use

| System | Node |
|--------|------|
| Player body | `CharacterBody3D` |
| Collision | `CollisionShape3D` (capsule) |
| Camera | `Camera3D` |
| Shooting | `RayCast3D` + custom script |
| Enemy AI | `CharacterBody3D` + `NavigationAgent3D` |
| Nav mesh | `NavigationRegion3D` |
| Terrain | `Terrain3D` (addon) |
| Health bar | `ProgressBar` (UI) |
| **Spawn players** | `MultiplayerSpawner` |
| **Sync state** | `MultiplayerSynchronizer` |
| **Remote calls** | `@rpc` (RPC) functions |
| **Networking** | `ENetConnection` (built-in) |
| Dialogue | `Label` + `Timer` / custom system |
| Post-processing | `WorldEnvironment` + `Vignette` |

---

## 🌍 How You Two Will Actually Play Together

You have **three options** to connect over the internet:

1. **Port forwarding (most "proper"):** The host sets up port forwarding on their router for the game port (e.g. UDP 9999). The client connects via the host's public IP. Works but fiddly with routers.
2. **VPN tool (easiest, recommended):** Both of you install **Radmin VPN**, **ZeroTier**, or **Hamachi**. It creates a virtual LAN so you connect to each other by a simple private IP — no router config needed. **This is the easiest way for a 2-player game.**
3. **Steam / dedicated server:** Overkill for a 2-player game, skip this for now.

**Recommendation:** Use Radmin or ZeroTier. You'll both get a virtual IP, and the client just types the host's virtual IP into the join screen. Done.

---

## ⚠️ Common Pitfalls to Avoid

1. **Don't build all 4 missions at once.** Build ONE mission end-to-end first, then copy the structure.
2. **Networking is the hardest part — don't skip Step 3.** Get two players in the same world *before* building anything else on top. Everything after is easier.
3. **Keep the host authoritative.** The host owns enemies, physics, and health. The client just sends inputs. This prevents cheating and desync.
4. **Don't over-scope the AI.** Start with simple "patrol → detect → shoot" before adding suppression.
5. **Save the story/dialogue for last.** Get the gameplay fun first, then layer the emotional writing on top.
6. **Back up your project** (git or just zip it) — losing progress on a project this personal hurts.

---

## 🏁 The "Worth It" Ending (your goal)

The final scene: both critically injured, one morphine left, one of you carries the other to the chopper while shooting one-handed. They're both stable, but the marriage gets reported. Kiera, groggy: **"Worth it."**

That's the payoff. Every mechanic you build serves that moment. Build it step by step, and you'll get there.

---

## 📅 Suggested Timeline (casual, evenings/weekends)

- **Week 1-2:** Steps 1-3 (moving + shooting + online multiplayer foundation) ← the big milestone
- **Week 3-4:** Steps 4-6 (networked shooting + enemies + suppression)
- **Week 5-6:** Step 7 (medical buddy system over the network) ← the heart
- **Week 7-8:** Steps 8-9 (ping + mission 1 online)
- **Week 9-12:** Missions 2-4
- **Ongoing:** Polish, sound, story

Total: roughly **3-4 months** to a complete, playable, emotional online game. That's realistic and achievable.

---

*"You are not superheroes. You are two highly trained operators who love each other. This is a love story told through the click of a magazine reload and the whisper of a sniper round."*

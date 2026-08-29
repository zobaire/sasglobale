extends CharacterBody3D

## FATE'S PAIR — player controller (THIRD-PERSON SHOOTER)
##
## Simple setup, exactly like the guide says:
##  - The Camera3D is a PLAIN CHILD of the player. Nothing attached to the
##    head, no bone rig — basic default.
##  - The mouse drives the camera: yaw spins it around the player, pitch
##    tilts it up/down. The pitch is CLAMPED so the player can never leave
##    the frame — look all the way up and your character slides to the
##    bottom edge and stays there. Ghost Recon style.
##  - The body turns to face where you aim (with a little lag so it looks
##    natural instead of snapping).
##  - Movement is camera-relative: W runs away from the camera, D strafes
##    right on screen, S walks toward the camera.
##
## IMPORTANT (guide lesson 4): the AnimationTree owns the skeleton. The
## AnimationPlayer is only the tree's animation SOURCE — never play clips
## on it directly while the tree is active, or the skeleton gets
## double-written and the whole character (and your view) shakes.

const SPEED = 2.5
const RUN_SPEED = 5.0

# Turn-in-place: the body chases the camera yaw. A little lag feels
# natural (you're aiming, not admiring the turn).
const TURN_SPEED_IDLE := 5.0    # rad/s when standing still
const TURN_SPEED_MOVING := 10.0 # rad/s while moving
const TURN_DEADZONE := 0.02     # rad — stop chasing when this close

# --- Procedural turn animation (code only — no animation clips) ---
# The body already chases the camera yaw; these constants give the turn
# some physical body language so a rotation reads as the character
# actually turning: the visual LEANS into the turn like a real person
# and PLANTS down a touch when a hard turn starts, then springs back.
const TURN_HARD_ANGLE := deg_to_rad(30.0)  # yaw error that counts as a "hard" turn
const TURN_LEAN_MAX := 0.10                # rad — max roll into the turn (~6 deg)
const TURN_LEAN_SPEED := 8.0               # how fast the lean builds / fades
const TURN_DIP_MAX := 0.04                 # meters — how far the visual plants down
const TURN_DIP_SPEED := 6.0                # how fast the plant recovers

# AnimationTree parameter paths (BlendTree -> Locomotion BlendSpace2D).
const LOCOMOTION_BLEND_PARAM := "parameters/BlendTree/Locomotion/blend_position"

# --- Run To Stop one-shot ---
const RUN_SPEED_THRESHOLD := 3.5
const STOP_SPEED_THRESHOLD := 1.0
const ONE_SHOT_REQUEST_PARAM := "parameters/BlendTree/OneShot/request"
const ONE_SHOT_ACTIVE_PARAM := "parameters/BlendTree/OneShot/active"

# --- Third-person camera (simple, Ghost Recon style) ---
const CAM_DISTANCE := 3.0        # how far the camera sits behind the player
const CAM_ZOOM_DISTANCE := 1.6   # target distance while holding C (cameraplus)
const CAM_ZOOM_SPEED := 8.0      # how fast the zoom eases in/out
const CAM_PIVOT_HEIGHT := 1.2    # orbit pivot: the camera swings around the chest
const CAM_LOOK_HEIGHT := 1.55    # the point on the player the camera frames (head)
const CAM_FRAME_KEEP := 0.55     # fraction of the half-FOV kept between the head
								 # and the screen edge — raise it for a wider
								 # up-look range, lower it for a tighter frame

@export var camera: Camera3D
@export var animation_player: AnimationPlayer  # kept for scene compat — the tree owns animation
@export var animation_tree: AnimationTree
@export var mouse_sensitivity: float = 0.002

var _camera_yaw := 0.0    # where the mouse points, horizontally
var _camera_pitch := 0.0  # where the mouse points, vertically (up = positive)
var _cam_distance := CAM_DISTANCE
var _blend_pos := Vector2.ZERO  # smoothed value fed to the Locomotion blend space
var _was_running := false       # true while the player is above run speed
var _run_dir := Vector2.ZERO    # blend-space direction of the last run (for the stop clip)
var _visual: Node3D = null      # node that receives the turn body language
var _visual_base_y := 0.0       # its original height, so the dip can stack on it
var _visual_base_z := 0.0       # its original roll, so the lean can stack on it
var _turn_lean := 0.0           # current lean (rad); sign follows the turn direction
var _turn_dip := 0.0            # current plant dip (meters)
var _was_turning_hard := false  # edge-trigger so the dip only fires once per turn


func _ready() -> void:
	# Start the camera wherever the body is already facing.
	_camera_yaw = rotation.y
	# Mouse capture is owned by the GameStartUI driver: it keeps the cursor
	# VISIBLE while the title screen is up (so you can click START) and
	# locks it CAPTURED when the game starts. ESC below toggles between
	# the two. (Running world.tscn directly: press ESC once to capture.)
	if camera == null:
		camera = find_child("Camera3D", true, false) as Camera3D
	if camera:
		camera.make_current()
	# Procedural-turn target: the capsule mesh today, the animated
	# character's body later. Falls back to the player root if no mesh.
	_visual = find_child("MeshInstance3D", true, false) as Node3D
	if _visual == null:
		_visual = self
	_visual_base_y = _visual.position.y
	_visual_base_z = _visual.rotation.z
	if animation_tree:
		animation_tree.active = true
	# NOTE: no animation_player.current_animation here. The AnimationTree
	# drives the skeleton; touching the AnimationPlayer at the same time
	# double-writes the bones and shakes the character (guide lesson 4).


func _input(event: InputEvent) -> void:
	# Mouse look lives in _input (NOT _unhandled_input) on purpose: _input
	# fires BEFORE the GUI phase, so no full-screen Control can swallow the
	# motion events and freeze the camera — that exact bug froze the camera
	# after the title UI was destroyed (a full-screen Control eats every
	# mouse event by default). The capture-mode guard keeps this dead while
	# the title screen is up.
	if event is InputEventMouseMotion and Input.get_mouse_mode() == Input.MOUSE_MODE_CAPTURED:
		_camera_yaw -= event.relative.x * mouse_sensitivity
		_camera_pitch = clampf(
			_camera_pitch - event.relative.y * mouse_sensitivity,
			deg_to_rad(-80.0),
			deg_to_rad(80.0)
		)


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("ui_cancel"):
		# ESC toggles the mouse between captured (aiming) and visible.
		if Input.get_mouse_mode() == Input.MOUSE_MODE_CAPTURED:
			Input.set_mouse_mode(Input.MOUSE_MODE_VISIBLE)
		else:
			Input.set_mouse_mode(Input.MOUSE_MODE_CAPTURED)


func _physics_process(delta: float) -> void:
	# Gravity (keeps the capsule grounded).
	if not is_on_floor():
		velocity += get_gravity() * delta

	# Movement is CAMERA-relative, not body-relative: W runs away from the
	# camera, D strafes right on screen, S walks toward the camera. If we
	# used the body basis here, you'd drift sideways while the body is
	# still catching up to the aim — the classic TPS "wobbly strafe" feel.
	var input_dir := Input.get_vector("left", "right", "forward", "down")
	var moving := input_dir.length() > 0.0
	var yaw_basis := Basis(Vector3.UP, _camera_yaw)
	var direction := (yaw_basis * Vector3(input_dir.x, 0, input_dir.y)).normalized()

	# Sprint: hold Shift to run at RUN_SPEED, otherwise walk at SPEED.
	var target_speed := RUN_SPEED if Input.is_action_pressed("sprint") else SPEED
	if direction:
		velocity.x = direction.x * target_speed
		velocity.z = direction.z * target_speed
	else:
		velocity.x = move_toward(velocity.x, 0, target_speed)
		velocity.z = move_toward(velocity.z, 0, target_speed)

	move_and_slide()

	# --- Body yaw chases the camera yaw (smooth turn, no snapping) ---
	var turn_speed := TURN_SPEED_MOVING if moving else TURN_SPEED_IDLE
	var yaw_diff := wrapf(_camera_yaw - rotation.y, -PI, PI)
	if absf(yaw_diff) > TURN_DEADZONE:
		rotation.y += clampf(yaw_diff, -turn_speed * delta, turn_speed * delta)

	# --- Procedural turn animation (code only — no animation clips) ---
	# How hard are we turning? 0..1, based on how far the camera is ahead
	# of the body. Looking right gives a NEGATIVE yaw_diff here.
	var turn_sign := signf(yaw_diff)
	var turn_intensity := clampf(absf(yaw_diff) / TURN_HARD_ANGLE, 0.0, 1.0)

	# Lean INTO the turn. rotation.z positive = lean left (character faces
	# -Z), so a right turn gets a negative lean. The lean builds while the
	# body is catching the camera and fades to zero once it settles — the
	# capsule now visibly "turns" instead of spinning on a turntable.
	var target_lean := turn_intensity * TURN_LEAN_MAX * turn_sign
	_turn_lean = lerpf(_turn_lean, target_lean, 1.0 - exp(-TURN_LEAN_SPEED * delta))
	_visual.rotation.z = _visual_base_z + _turn_lean

	# Plant: when a hard turn starts while standing still, dip the visual
	# down a touch, then spring back — the character "steps into" the turn.
	# Only applied to a child mesh, not the body root (we don't want to
	# shove the physics body through the floor).
	var turning_hard := (not moving) and turn_intensity > 0.5 and absf(yaw_diff) > TURN_DEADZONE
	if turning_hard and not _was_turning_hard:
		_turn_dip = TURN_DIP_MAX
	_was_turning_hard = turning_hard
	_turn_dip = lerpf(_turn_dip, 0.0, 1.0 - exp(-TURN_DIP_SPEED * delta))
	if _visual != self:
		_visual.position.y = _visual_base_y - _turn_dip

	# --- Feed velocity into the AnimationTree's Locomotion BlendSpace2D ---
	# The blend space is character-relative: +Y = forward, -Y = backward,
	# X = strafe. World-space velocity must be converted to the body's
	# local space first, otherwise the blend breaks as soon as the player
	# rotates.
	if animation_tree:
		var local_vel: Vector3 = global_transform.basis.inverse() * velocity
		# Godot's forward is -Z but the blend space's "walk forward" point
		# is at +Y, so negate Z. X maps straight across (right strafe = +X).
		var target_blend := Vector2(local_vel.x, -local_vel.z)
		_blend_pos = _blend_pos.lerp(target_blend, 0.2)
		animation_tree.set(LOCOMOTION_BLEND_PARAM, _blend_pos)

		# --- Run To Stop ---
		# When the player decelerates from a run to a standstill, play the
		# Run To Stop clip once so they ease into the idle pose instead of
		# snapping to it. If they take off again mid-clip, abort it so the
		# run animation takes over immediately.
		var horiz_speed := Vector2(velocity.x, velocity.z).length()
		var is_running := horiz_speed > RUN_SPEED_THRESHOLD
		if is_running:
			_run_dir = _blend_pos  # remember which way we were running
		# The Run To Stop clip is a FORWARD decel animation (Mixamo baked it
		# facing forward). Only fire it when the player was running mostly
		# forward — if they stop from a strafe, the blend eases back to idle
		# on its own instead of snapping the body around.
		var ran_forward := _run_dir.y > 3.0 and absf(_run_dir.x) < 1.0
		if _was_running and horiz_speed < STOP_SPEED_THRESHOLD and ran_forward:
			animation_tree.set(ONE_SHOT_REQUEST_PARAM, AnimationNodeOneShot.ONE_SHOT_REQUEST_FIRE)
		elif is_running and animation_tree.get(ONE_SHOT_ACTIVE_PARAM):
			animation_tree.set(ONE_SHOT_REQUEST_PARAM, AnimationNodeOneShot.ONE_SHOT_REQUEST_ABORT)
		_was_running = is_running


func _process(delta: float) -> void:
	if camera == null:
		return

	# --- Position: the camera orbits behind the player on a fixed pivot ---
	# Yaw spins the orbit around the player. Hold C (cameraplus) to zoom in.
	var target_distance := CAM_ZOOM_DISTANCE if Input.is_action_pressed("cameraplus") else CAM_DISTANCE
	_cam_distance = lerpf(_cam_distance, target_distance, 1.0 - exp(-CAM_ZOOM_SPEED * delta))
	var pivot := global_position + Vector3.UP * CAM_PIVOT_HEIGHT
	var offset := Vector3(0, 0, _cam_distance).rotated(Vector3.UP, _camera_yaw)
	camera.global_position = pivot + offset

	# --- View: point at the player's head, mouse pitch on top, clamped so
	#     the head can never leave the frame ---
	# base_pitch = the angle that centers the head on screen. The mouse
	# pitch is clamped to base_pitch ± (CAM_FRAME_KEEP × half-FOV), so at
	# the extremes the head is still CAM_FRAME_KEEP of a half-FOV away
	# from the screen edge — your character is ALWAYS on screen.
	var head := global_position + Vector3.UP * CAM_LOOK_HEIGHT
	var to_head := head - camera.global_position
	var base_pitch := atan2(to_head.y, Vector2(to_head.x, to_head.z).length())
	var half_fov := deg_to_rad(camera.fov) * 0.5
	var pitch := clampf(
		_camera_pitch,
		base_pitch - half_fov * CAM_FRAME_KEEP,
		base_pitch + half_fov * CAM_FRAME_KEEP
	)
	var yaw := atan2(-to_head.x, -to_head.z)
	camera.global_rotation = Vector3(pitch, yaw, 0.0)

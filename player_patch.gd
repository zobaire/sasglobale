extends CharacterBody3D

## FATE'S PAIR — player controller (THIRD-PERSON SHOOTER)
## The mouse drives a camera yaw/pitch, and the camera orbits behind the
## player. The BODY chases the camera yaw with a limited turn speed, so you
## SEE the character turn to face where you aim. Movement is camera-relative:
## W always runs away from the camera, S toward it, D strafes right on screen.
## The camera has a raycast pull-in so it doesn't clip through walls.

const SPEED = 2.5
const RUN_SPEED = 5.0
const JUMP_VELOCITY = 4.5

# Turn-in-place tuning. In TPS the body should track the aim fairly quickly
# (you're shooting, not admiring the turn), but a little lag feels natural.
const TURN_SPEED_IDLE := 5.0    # rad/s when standing still
const TURN_SPEED_MOVING := 10.0 # rad/s while moving
const TURN_DEADZONE := 0.02     # rad — stop chasing when this close

# How far to push the Locomotion blend on X when turning in place.
# Your strafe points live at ±2.5 (walking) and ±5 (full strafe) in the
# blend space, so 2.5 gives a clean shuffle into the turn.
const IDLE_TURN_BLEND_X := 2.5

# Parameter path into the AnimationTree. This mirrors the node path inside
# the tree: StateMachine -> BlendTree -> Locomotion (BlendSpace2D).
# If you restructure the tree (e.g. add a Fullbody layer), update this path!
const LOCOMOTION_BLEND_PARAM := "parameters/BlendTree/Locomotion/blend_position"

# --- Run To Stop transition ---
# Horizontal speed above this counts as "running" (walk = 2.5, run = 5.0).
const RUN_SPEED_THRESHOLD := 3.5
# Below this speed the player is "stopped" -> fire the Run To Stop clip.
const STOP_SPEED_THRESHOLD := 1.0
# Parameter paths into the AnimationTree's OneShot node.
const ONE_SHOT_REQUEST_PARAM := "parameters/BlendTree/OneShot/request"
const ONE_SHOT_ACTIVE_PARAM := "parameters/BlendTree/OneShot/active"

# --- Third-person camera ---
const CAM_DISTANCE := 2.0   # how far behind the player it sits
const CAM_PIVOT_HEIGHT := 1.35  # orbit pivot: camera swings around the chest
const CAM_MIN_HEIGHT := 0.4     # camera never sinks below this (above the feet)
const CAM_PITCH_FOLLOW := 0.55  # how much of the aim pitch the camera POSITION follows
const CAM_ZOOM_FACTOR := 0.5    # cameraplus zooms in to this fraction of CAM_DISTANCE
const CAM_ZOOM_SPEED := 8.0     # how fast the zoom eases in/out (higher = snappier)
const CAM_NUDGE := 0.25     # how far to pull the camera out of a wall
const CAM_FOLLOW_SPEED := 10.0  # higher = snappier follow

# The Camera3D to control. Drag it in the Inspector, or it auto-finds one.
@export var camera: Camera3D
@export var animation_player: AnimationPlayer
@export var animation_tree :  AnimationTree
@export var mouse_sensitivity: float = 0.002

@export_range(-89.0, 89.0) var max_pitch: float = 85.0

var _pitch := 0.0
var _camera_yaw := 0.0  # where the mouse points; the body chases this
var _jump_pressed := false
var _blend_pos := Vector2.ZERO  # smoothed value fed to the Locomotion blend space
var _was_running := false       # true while the player is above run speed
var _run_dir := Vector2.ZERO    # blend-space direction of the last run (for the stop clip)
var _cam_smooth := Vector3.ZERO # smoothed camera position
var _cam_distance := CAM_DISTANCE  # smoothed camera distance (zoom target follows it)
var barehand = true

func _ready() -> void:
	# Start the camera looking wherever the body is already facing.
	_camera_yaw = rotation.y
	# Lock the mouse so we can aim with it (ESC releases it)
	Input.set_mouse_mode(Input.MOUSE_MODE_CAPTURED)
	if camera == null:
		camera = find_child("Camera3D", true, false) as Camera3D
	if camera:
		# The scene shipped with the camera mounted at the character's neck
		# (FPS style). For TPS we move it out to orbit behind the player.
		camera.reparent(self, false)
		camera.make_current()
		var pivot := global_position + Vector3.UP * CAM_PIVOT_HEIGHT
		_cam_smooth = pivot + Vector3(0, 0, CAM_DISTANCE)
		camera.global_position = _cam_smooth
		camera.global_rotation = Vector3(_pitch, _camera_yaw, 0.0)
	if animation_tree:
		animation_tree.active = true
	if animation_player == null:
		print(' please select animation player')
	else:
		animation_player.current_animation = "Idle/mixamo_com"


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion and Input.get_mouse_mode() == Input.MOUSE_MODE_CAPTURED:
		# Yaw goes to the camera; the body chases it in _physics_process.
		# Pitch stays on the camera as before.
		_camera_yaw -= event.relative.x * mouse_sensitivity
		_pitch = clamp(
			_pitch - event.relative.y * mouse_sensitivity,
			deg_to_rad(-max_pitch),
			deg_to_rad(max_pitch)
		)
	elif event.is_action_pressed("ui_cancel"):
		# ESC toggles mouse capture
		if Input.get_mouse_mode() == Input.MOUSE_MODE_CAPTURED:
			Input.set_mouse_mode(Input.MOUSE_MODE_VISIBLE)
		else:
			Input.set_mouse_mode(Input.MOUSE_MODE_CAPTURED)


func _physics_process(delta: float) -> void:
	# Gravity
	if not is_on_floor():
		velocity += get_gravity() * delta

	# Jump (consumed once per physics tick)
	if _jump_pressed and is_on_floor():
		velocity.y = JUMP_VELOCITY
	_jump_pressed = false

	# Movement is CAMERA-relative, not body-relative: W runs away from the
	# camera, D strafes right on screen, S walks toward the camera. If we
	# used the body basis here, you'd drift sideways while the body is still
	# catching up to the aim — the classic TPS "wobbly strafe" feel.
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
	var turn_amount := 0.0  # -1..1, how hard we're turning this frame
	if absf(yaw_diff) > TURN_DEADZONE:
		var max_step := turn_speed * delta
		var step := clampf(yaw_diff, -max_step, max_step)
		rotation.y += step
		turn_amount = step / max_step
		
	# --- Feed velocity into the AnimationTree's Locomotion BlendSpace2D ---
	# The blend space is character-relative: +X = strafe right, +Y = forward.
	# World-space velocity must be converted to the body's local space first,
	# otherwise the blend breaks as soon as the player rotates.
	if animation_tree:
		var local_vel: Vector3 = global_transform.basis.inverse() * velocity
		# Godot's forward is -Z but the blend space's "walk forward" point is
		# at +Y, so negate Z. X maps straight across (right strafe = +X).
		var target_blend := Vector2(local_vel.x, -local_vel.z)
		print(target_blend)
		# Idle + turning: shuffle into the strafe pose so the player visibly
		# turns left/right instead of just standing there while the body spins.
		if not moving and absf(turn_amount) > 0.05:
			target_blend.x = turn_amount * IDLE_TURN_BLEND_X
		# Smooth it a touch so the animation eases instead of snapping.
		
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
		# on its own instead of snapping the body around to face forward.
		var ran_forward := _run_dir.y > 3.0 and absf(_run_dir.x) < 1.0
		if _was_running and horiz_speed < STOP_SPEED_THRESHOLD and ran_forward:
			animation_tree.set(ONE_SHOT_REQUEST_PARAM, AnimationNodeOneShot.ONE_SHOT_REQUEST_FIRE)
		elif is_running and animation_tree.get(ONE_SHOT_ACTIVE_PARAM):
			animation_tree.set(ONE_SHOT_REQUEST_PARAM, AnimationNodeOneShot.ONE_SHOT_REQUEST_ABORT)
		_was_running = is_running


func _process(delta: float) -> void:
	if camera == null:
		return
	# --- Third-person camera ---
	# Ghost Recon style: when you look up/down, the camera POSITION orbits
	# around the player's chest (damped), not just tilts in place — so the
	# character stays in frame while you aim at the sky or the floor.
	# +Z offset means "behind the aim", so it orbits as the mouse turns.
	# Hold "cameraplus" (C by default) to zoom the camera in; release to
	# glide back out. Smoothly eased so it doesn't snap between distances.
	var target_distance := CAM_DISTANCE * CAM_ZOOM_FACTOR if Input.is_action_pressed("cameraplus") else CAM_DISTANCE
	_cam_distance = lerpf(_cam_distance, target_distance, 1.0 - exp(-CAM_ZOOM_SPEED * delta))
	var pivot := global_position + Vector3.UP * CAM_PIVOT_HEIGHT
	var orbit_pitch := _pitch * CAM_PITCH_FOLLOW
	var offset := Vector3(0, 0, _cam_distance).rotated(Vector3.RIGHT, orbit_pitch).rotated(Vector3.UP, _camera_yaw)
	var target_pos := pivot + offset
	# Never let the orbit sink the camera into the floor at extreme angles.
	if target_pos.y < global_position.y + CAM_MIN_HEIGHT:
		target_pos.y = global_position.y + CAM_MIN_HEIGHT

	# Raycast from the player's head toward the camera; if something blocks
	# the view, pull the camera forward so it hugs the wall instead of
	# clipping through it.
	var space := get_world_3d().direct_space_state
	var query := PhysicsRayQueryParameters3D.create(
		global_position + Vector3.UP * CAM_PIVOT_HEIGHT,
		target_pos
	)
	query.exclude = [get_rid()]  # don't hit our own capsule
	var hit := space.intersect_ray(query)
	if hit:
		var dir := (target_pos - global_position).normalized()
		target_pos = hit.position + dir * CAM_NUDGE

	# Smooth follow so the camera glides instead of snapping around.
	var follow := 1.0 - exp(-CAM_FOLLOW_SPEED * delta)
	_cam_smooth = _cam_smooth.lerp(target_pos, follow)
	camera.global_position = _cam_smooth
	camera.global_rotation = Vector3(_pitch, _camera_yaw, 0.0)

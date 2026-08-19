extends CharacterBody3D

## FATE'S PAIR — player.gd (Build Step 7)
## ============================================================
## The camera rides the HEAD BONE (mixamorig_Head) through a
## BoneAttachment3D, so it shakes with the head/hair movement
## from animations — exactly what we want for step 7.
##
## If you placed a Camera3D in the player scene, the script picks
## it up and reparents it onto the head bone. If none exists, it
## spawns one in code.
##
## Mouse look:
##   - YAW   -> rotates the whole player body (left/right)
##   - PITCH -> clamped to +-80deg, applied every frame as an
##              ABSOLUTE value. Never chained onto last frame's
##              rotation — that caused the 360deg spin bug.
##
## PITCH_ON_BONE:
##   false (default) -> pitch rotates the Camera3D node itself.
##                      Safe, never fights the animation tree.
##   true            -> pitch rotates the head BONE (computed
##                      absolute from the base pose). Use this
##                      if you want the head mesh to visibly
##                      look up/down. If the animation keeps
##                      stomping it, raise set_process_priority.

const SPEED := 5.0
const JUMP_VELOCITY := 4.5
const MOUSE_SENSITIVITY := 0.0025
const PITCH_LIMIT := deg_to_rad(80.0)
const HEAD_BONE_NAME := "mixamorig_Head"
const PITCH_ON_BONE := false

var _skeleton: Skeleton3D
var _head_bone := -1
var _head_pose_base := Quaternion.IDENTITY
var _head_attachment: BoneAttachment3D
var _camera: Camera3D
var _pitch := 0.0


func _ready() -> void:
	_setup_head_camera()
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	# Make sure our _process runs after the AnimationPlayer so a
	# bone-pitch override can't be stomped by the animation tree.
	set_process_priority(100)


func _setup_head_camera() -> void:
	# 1. Find the skeleton (deep search — survives node path changes)
	_skeleton = find_child("Skeleton3D", true, false) as Skeleton3D
	if _skeleton == null:
		push_error("player.gd: no Skeleton3D found — camera can't attach to the head")
		return

	# 2. Find the head bone (exact name, fallback: any bone containing "Head")
	_head_bone = _skeleton.find_bone(HEAD_BONE_NAME)
	if _head_bone == -1:
		for i in _skeleton.get_bone_count():
			if "Head" in _skeleton.get_bone_name(i):
				_head_bone = i
				break
	if _head_bone == -1:
		push_error("player.gd: no head bone found on the skeleton")
		return

	# Base pose = scene-level bone override, captured ONCE at spawn.
	# Pitch is composed on top every frame -> absolute, never accumulating.
	_head_pose_base = _skeleton.get_bone_pose_rotation(_head_bone)

	# 3. BoneAttachment3D on the head bone (created in code —
	#    no manual editor steps needed)
	_head_attachment = _skeleton.get_node_or_null("HeadCamera") as BoneAttachment3D
	if _head_attachment == null:
		_head_attachment = BoneAttachment3D.new()
		_head_attachment.name = "HeadCamera"
		_head_attachment.bone_name = _skeleton.get_bone_name(_head_bone)
		_skeleton.add_child(_head_attachment)

	# 4. Camera: use the Camera3D you placed in the scene (player.tscn)
	#    if one exists, otherwise spawn one in code as a fallback.
	_camera = find_child("Camera3D", true, false) as Camera3D
	if _camera == null:
		_camera = Camera3D.new()
		_camera.name = "Camera3D"
		_head_attachment.add_child(_camera)
	else:
		# Reparent the scene camera onto the head bone so it rides the
		# head/hair animation. It keeps its world position on reparent.
		_camera.reparent(_head_attachment)
	_camera.current = true
	_camera.near = 0.05                  # don't clip through the hair/head mesh
	_camera.position = Vector3(0, 0.12, 0)  # eye level — tune this!


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion and Input.get_mouse_mode() == Input.MOUSE_MODE_CAPTURED:
		# Yaw on the body, pitch clamped (no flipping)
		rotate_y(-event.relative.x * MOUSE_SENSITIVITY)
		_pitch = clampf(_pitch - event.relative.y * MOUSE_SENSITIVITY, -PITCH_LIMIT, PITCH_LIMIT)
	elif event.is_action_pressed("ui_cancel"):
		# ESC toggles mouse capture — handy while testing
		Input.mouse_mode = (
			Input.MOUSE_MODE_VISIBLE
			if Input.get_mouse_mode() == Input.MOUSE_MODE_CAPTURED
			else Input.MOUSE_MODE_CAPTURED
		)


func _process(_delta: float) -> void:
	_apply_head_pitch()


func _apply_head_pitch() -> void:
	if _head_bone == -1 or _camera == null:
		return
	if PITCH_ON_BONE:
		var pitch_q := Quaternion(Vector3.RIGHT, _pitch)
		# Absolute: base pose * pitch, computed fresh every frame
		_skeleton.set_bone_pose_rotation(_head_bone, _head_pose_base * pitch_q)
	else:
		# Absolute rotation on the camera node — nothing can fight this
		_camera.rotation = Vector3(_pitch, 0, 0)


func _physics_process(delta: float) -> void:
	# Gravity
	if not is_on_floor():
		velocity += get_gravity() * delta

	# Jump — use the JUMP action if it exists, fall back to ui_accept
	var jump_pressed: bool = (
		Input.is_action_just_pressed("JUMP") if InputMap.has_action("JUMP")
		else Input.is_action_just_pressed("ui_accept")
	)
	if jump_pressed and is_on_floor():
		velocity.y = JUMP_VELOCITY

	# Movement (note: "forward", not the old "forword" typo)
	var input_dir := Input.get_vector("left", "right", "forword", "down")
	var direction := (transform.basis * Vector3(input_dir.x, 0, input_dir.y)).normalized()
	if direction:
		velocity.x = direction.x * SPEED
		velocity.z = direction.z * SPEED
	else:
		velocity.x = move_toward(velocity.x, 0, SPEED)
		velocity.z = move_toward(velocity.z, 0, SPEED)

	move_and_slide()

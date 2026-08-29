extends CharacterBody3D

var Walking_Speed = 2.5
var Running_Speed = 5.0
var Target_Speed = Walking_Speed
var Acceleration = 4.0
var pitch :float = 0.0
var  yaw : float = 0.0
var _blend_pos := Vector2.ZERO
var  IsArmed = false

# AnimationTree parameter paths (BlendTree -> Locomotion BlendSpace2D).
const LOCOMOTION_BLEND_PARAM := "parameters/BlendTree/Locomotion/blend_position"
const BLEND_NODE_PARAM := "parameters/BlendTree/Blend2/blend_amount"

@export var Camera_Node: Camera3D
@export var Animation_Player: AnimationPlayer
@export var Animation_Tree : AnimationTree
@export var BoneTargeter : CCDIK3D
# Sensitivity in DEGREES per pixel (easier to reason about than radians).
# 0.1 deg/px = a full 360° spin needs 3600px of mouse movement (~3 mousepad sweeps).
# The old value (0.01 RADIANS per pixel) needed only 628px per spin — way too hot.
@export var sensitivity := 0.1
@export var camera_root : Node3D
@export var camera_pitch : Node3D


func _ready() -> void:
	if camera_root == null:
		push_warning("camera_root is not set!")
	if camera_pitch == null:
		push_warning("camera_pitch is not set!") 
	# Capture mouse on start
	Input.set_mouse_mode(Input.MOUSE_MODE_CAPTURED)
	# Initialize yaw from the actual node rotation
	yaw = camera_root.rotation.y  # Use camera_root, not self
	pitch = rad_to_deg(camera_pitch.rotation.x)
	
func _physics_process(delta: float) -> void:
	var input_dir := Input.get_vector("left", "right", "forward", "down")
	var direction := (transform.basis * Vector3(input_dir.x, 0, input_dir.y)).normalized()
	if direction:
		velocity.x = direction.x * Target_Speed
		velocity.z = direction.z * Target_Speed
	else:
		# Use a separate deceleration value, not Target_Speed
		var deceleration = 7.0  # Higher = faster stopping
		velocity.x = move_toward(velocity.x, 0, deceleration * delta)
		velocity.z = move_toward(velocity.z, 0, deceleration * delta)
		
	if AnimationTree :
		var local_vel: Vector3 = global_transform.basis.inverse() * velocity
		# Godot's forward is -Z but the blend space's "walk forward" point
		# is at +Y, so negate Z. X maps straight across (right strafe = +X).
		var target_blend := Vector2(local_vel.x, -local_vel.z)
		_blend_pos = _blend_pos.lerp(target_blend, 0.2)
		Animation_Tree.set(LOCOMOTION_BLEND_PARAM, _blend_pos)
		if IsArmed : 
			Animation_Tree.set(BLEND_NODE_PARAM,1.0)
		else :
			Animation_Tree.set(BLEND_NODE_PARAM,0.0)
			
	move_and_slide()

func _process(delta: float) -> void:
	#sprint logic
	
	if Input.is_action_pressed("sprint") and is_on_floor():
		Target_Speed = move_toward(Target_Speed, Running_Speed, Acceleration * delta)
	else:
		Target_Speed = move_toward(Target_Speed, Walking_Speed, Acceleration * delta)
		
	if Input.is_action_just_pressed("Escap") and Input.MOUSE_MODE_CAPTURED :
		get_tree().quit()

func _input(event: InputEvent) -> void:
	if event is InputEventMouseMotion:
		if Input.get_mouse_mode() != Input.MOUSE_MODE_CAPTURED:
			return
		yaw -= deg_to_rad(event.relative.x * sensitivity)
		pitch = clampf(pitch - event.relative.y * sensitivity, -40.0, 80.0)
		yaw = wrapf(yaw, -TAU, TAU)
		camera_pitch.rotation.x = deg_to_rad(pitch)
		self.rotation.y = yaw  # yaw is kept in radians

func SetArmaedStatus(state : bool) -> void :
	IsArmed = state

extends SceneTree

func _init() -> void:
	var scene: PackedScene = load("res://scenes/player.tscn")
	if scene == null:
		print("FAILED TO LOAD player.tscn")
		quit(1)
		return
	var player := scene.instantiate()
	print("instantiated: ", player)
	print("Camera_Node = ", player.get("Camera_Node"))
	print("Animation_Player = ", player.get("Animation_Player"))
	print("Animation_Tree = ", player.get("Animation_Tree"))
	print("camera_root = ", player.get("camera_root"))
	print("camera_pitch = ", player.get("camera_pitch"))
	print("children: ", player.get_children())
	player.free()
	quit(0)

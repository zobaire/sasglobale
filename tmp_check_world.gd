extends SceneTree

func _init() -> void:
	var scene: PackedScene = load("res://scenes/world.tscn")
	if scene == null:
		print("FAILED TO LOAD world.tscn")
		quit(1)
		return
	var world := scene.instantiate()
	var player := world.get_node_or_null("Player")
	print("world instantiated, Player = ", player)
	if player:
		print("Camera_Node = ", player.get("Camera_Node"))
		print("Animation_Player = ", player.get("Animation_Player"))
		print("Animation_Tree = ", player.get("Animation_Tree"))
		print("camera_root = ", player.get("camera_root"))
		print("camera_pitch = ", player.get("camera_pitch"))
		print("children: ", player.get_children())
		print("scene_file_path: ", player.scene_file_path)
	world.free()
	quit(0)

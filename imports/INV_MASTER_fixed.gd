extends Node
## Central inventory - autoloaded as "INV_MASTER", so ANY script can call
## INV_MASTER.xxx from anywhere. One instance for the whole game.

signal inventory_changed   # UI listens to this to refresh itself

# item_id -> count  e.g. {"Weapon_Glock": 1, "Medkit": 2}
var items: Dictionary = {}
# item_id of the gun currently in the player's hand. "" = nothing equipped.
var equipped_weapon: String = ""

var _equipped_node: Node3D = null   # the actual weapon node currently in the hand

# --- Pickup (called by pickup_item.gd) ----------------------------------------

func pickup(world_item: RigidBody3D) -> void:
	var id: String = world_item.item_id
	var display_name: String = world_item.item_name

	# Weapons go straight into the hand (equip). Everything else goes in the bag.
	if id.begins_with("Weapon_"):
		if _equip_weapon(world_item):
			# Equipped successfully -> we own it now, count it.
			items[id] = items.get(id, 0) + 1
			print("Equipped: ", display_name, " (x", items[id], ")")
			inventory_changed.emit()
			return

		# Equip failed (no player / no hand node) -> don't destroy the item,
		# keep it in the bag instead.
		items[id] = items.get(id, 0) + 1
		print("Stored: ", display_name, " (x", items[id], ")")
		inventory_changed.emit()
		world_item.queue_free()
		return

	# Non-weapon item -> just add to the bag and remove from the world.
	items[id] = items.get(id, 0) + 1
	print("Picked up: ", display_name, " (x", items[id], ")")
	inventory_changed.emit()
	world_item.queue_free()

# --- Frame update ---------------------------------------------------------------

func _process(_delta: float) -> void:
	# "Toss" action (G key) - only works if we're actually holding something.
	if Input.is_action_just_pressed("Toss") and equipped_weapon != "":
		Toss(_equipped_node)

# --- Toss / drop ------------------------------------------------------------------

## Throw the equipped weapon back into the world.
## Returns true if the toss actually happened.
func Toss(item: Node3D) -> bool:
	if item == null or equipped_weapon == "":
		return false

	var player := get_tree().get_first_node_in_group("player")
	if player == null:
		return false

	# Drop it to the ground and REMOVE it from inventory (we no longer own it).
	if not _drop_weapon(item, false):
		return false

	player.SetArmaedStatus(false)   # hand is empty -> leave the "armed" pose
	equipped_weapon = ""
	_equipped_node = null
	inventory_changed.emit()
	return true

## Low-level drop logic - shared by Toss (remove from inventory) and by
## weapon swap (keep in inventory; the old gun is just on the ground now).
func _drop_weapon(item: Node3D, keep_in_inventory: bool) -> bool:
	var player := get_tree().get_first_node_in_group("player")
	if player == null:
		return false

	# 1) Reparent the gun from the hand back into the world scene.
	item.get_parent().remove_child(item)
	player.get_parent().add_child(item)

	# 2) Place it ~1.5 m in front of the player and lift it slightly
	#    so it doesn't clip the floor the instant it spawns.
	#    (In Godot, -Z is "forward" by default.)
	item.global_position = player.global_position - player.global_transform.basis.z * 1.5
	item.global_position.y += 0.3

	# 3) Re-enable physics and give it a little throw velocity + spin.
	if item is RigidBody3D:
		var body := item as RigidBody3D
		body.freeze = false
		body.linear_velocity = -player.global_transform.basis.z * 4.0 + Vector3(0, 2.5, 0)
		body.angular_velocity = Vector3(
			randf_range(-2.0, 2.0), randf_range(-2.0, 2.0), randf_range(-2.0, 2.0)
		)

	var collision := item.get_node_or_null("Gun_Collision")
	if collision:
		collision.disabled = false   # let it collide with the floor again

	var area := item.get_node_or_null("Area3D")
	if area:
		area.monitoring = true       # let the player trigger pickup again

	# 4) Reset the pickup flag so this SAME instance can be grabbed again later.
	if item.has_method("SetPickupStatus"):
		item.SetPickupStatus(false)

	# 5) Inventory bookkeeping - only when we're really tossing it away.
	if not keep_in_inventory and equipped_weapon != "":
		items[equipped_weapon] = items.get(equipped_weapon, 0) - 1
		if items[equipped_weapon] <= 0:
			items.erase(equipped_weapon)
		print("Dropped weapon. Remaining: ", items.get(equipped_weapon, 0))

	return true

# --- Equip -----------------------------------------------------------------------

func _equip_weapon(world_item: RigidBody3D) -> bool:
	var player := get_tree().get_first_node_in_group("player")
	if player == null:
		return false

	# The hand mount. The "Pistol" node already has the correct position AND
	# rotation baked in (see player.tscn), so the gun just needs to sit inside
	# it with an IDENTITY local transform - no extra math needed.
	var hand := player.get_node_or_null("character/Skeleton3D/BoneAttachment3D/Pistol")
	if hand == null:
		push_error("INV_MASTER: Pistol mount node not found on the player!")
		return false

	# Already holding a weapon? Drop it FIRST (swap) so the hand is free.
	# keep_in_inventory = true -> the old gun stays owned, it just lands on
	# the ground in front of us.
	if _equipped_node != null:
		_drop_weapon(_equipped_node, true)

	# Move the gun from the world into the hand.
	world_item.get_parent().remove_child(world_item)
	hand.add_child(world_item)

	# KEY FIX: reset the local transform to IDENTITY.
	# Without this the gun keeps its old WORLD position as its local one,
	# so it would float meters away from the hand instead of snapping
	# exactly onto the Pistol node's position/rotation.
	world_item.transform = Transform3D.IDENTITY

	# Freeze physics while it's in the hand - a RigidBody3D would otherwise
	# keep simulating gravity and jitter/fall inside the hand.
	world_item.freeze = true

	# Turn OFF collision + pickup detection while it's in the hand.
	var collision := world_item.get_node_or_null("Gun_Collision")
	if collision:
		collision.disabled = true

	var area := world_item.get_node_or_null("Area3D")
	if area:
		area.monitoring = false

	# Mark this instance as consumed so it stops reacting to the Equip key.
	if world_item.has_method("SetPickupStatus"):
		world_item.SetPickupStatus(true)

	player.SetArmaedStatus(true)              # switch to the armed animation state
	equipped_weapon = world_item.item_id
	_equipped_node = world_item
	return true

# --- Queries ----------------------------------------------------------------------

func get_count(id: String) -> int:
	return items.get(id, 0)

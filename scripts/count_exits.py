"""Count exit directions across all area JSON files."""
import json, glob
from collections import Counter

dir_counts = Counter()
room_with_up = 0
room_with_down = 0
room_with_both = 0
total_rooms = 0
total_exits = 0
areas_with_ud = []

for f in sorted(glob.glob('data/areas/*.json')):
    with open(f) as fh:
        data = json.load(fh)
    rooms = data.get('rooms', [])
    area_name = data.get('name', f)
    area_up = 0
    area_down = 0
    for room in rooms:
        total_rooms += 1
        exits = room.get('exits', {})
        if isinstance(exits, list):
            continue  # skip malformed
        has_up = 'up' in exits
        has_down = 'down' in exits
        for d in exits:
            dir_counts[d] += 1
            total_exits += 1
        if has_up:
            room_with_up += 1
            area_up += 1
        if has_down:
            room_with_down += 1
            area_down += 1
        if has_up and has_down:
            room_with_both += 1
    if area_up or area_down:
        areas_with_ud.append((area_name, area_up, area_down, len(rooms)))

print(f"=== ROM 2.4 World Exit Statistics ===\n")
print(f"Total rooms:  {total_rooms}")
print(f"Total exits:  {total_exits}\n")

print("Direction breakdown:")
planar = 0
vertical = 0
for d in ['north', 'east', 'south', 'west', 'up', 'down']:
    c = dir_counts.get(d, 0)
    pct = c / total_exits * 100 if total_exits else 0
    tag = "  ← 3D" if d in ('up', 'down') else ""
    print(f"  {d:8s}: {c:5d}  ({pct:5.1f}%){tag}")
    if d in ('up', 'down'):
        vertical += c
    else:
        planar += c

print(f"\nPlanar (N/E/S/W): {planar} ({planar/total_exits*100:.1f}%)")
print(f"Vertical (U/D):   {vertical} ({vertical/total_exits*100:.1f}%)")

print(f"\n--- Room-level stats ---")
print(f"Rooms with up exit:    {room_with_up} ({room_with_up/total_rooms*100:.1f}%)")
print(f"Rooms with down exit:  {room_with_down} ({room_with_down/total_rooms*100:.1f}%)")
print(f"Rooms with both U & D: {room_with_both} ({room_with_both/total_rooms*100:.1f}%)")

print(f"\n--- Areas with up/down exits ---")
print(f"{'Area':<40s} {'Up':>4s} {'Down':>4s} {'Rooms':>6s}")
print("-" * 58)
for name, up, down, rooms in sorted(areas_with_ud, key=lambda x: -(x[1]+x[2])):
    print(f"{name:<40s} {up:4d} {down:4d} {rooms:6d}")

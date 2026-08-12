from swgoh_comlink import SwgohComlink

comlink = SwgohComlink(url="http://localhost:3000")

# Sanity check: doesn't require an ally code, confirms comlink can reach the game APIs
metadata = comlink.get_game_metadata()
print("Metadata check OK, keys:", list(metadata.keys())[:5])

# Replace with a real ally code to fetch player mod data
ALLY_CODE = "000000000"
if ALLY_CODE != "000000000":
    player = comlink.get_player(allycode=ALLY_CODE)
    print("Player name:", player.get("name"))
    print("Mod count:", len(player.get("rosterUnit", [])))
else:
    print("Set ALLY_CODE to your actual ally code to test get_player().")

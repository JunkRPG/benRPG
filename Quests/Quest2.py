import json
import os
import random

# Directory paths (adjust these if needed to match your project's structure)
QUESTS_DIR = "quests/"
DECKS_DIR = "decks/"

# Ensure directories exist
os.makedirs(QUESTS_DIR, exist_ok=True)
os.makedirs(DECKS_DIR, exist_ok=True)

def create_quest_template():
    """Create a new Quest Card template and save it as a JSON file."""
    print("\n=== Creating a New Quest Card Template ===")
    
    # Input quest text with placeholders
    print("Enter the quest text using curly braces for placeholders (e.g., {npc}, {location}).")
    text = input("Quest text: ")
    
    # Input placeholders and their card types
    placeholders = {}
    print("\nDefine each placeholder in the text and its card type.")
    while True:
        placeholder = input("Enter a placeholder (e.g., npc) or 'done' to finish: ")
        if placeholder.lower() == 'done':
            break
        if placeholder not in text:
            print(f"Warning: '{placeholder}' not found in quest text. Please ensure it matches.")
        card_type = input(f"Card type for '{placeholder}' (e.g., NPC, Location, Enemy): ").capitalize()
        placeholders[placeholder] = card_type
    
    # Input rewards
    rewards = {}
    initial_reward = input("\nInitial reward (e.g., 10 for 10 gems, or 0 if none): ")
    completion_reward = input("Completion reward (e.g., 20 for 20 gems, or 0 if none): ")
    rewards["initial"] = int(initial_reward) if initial_reward.isdigit() else 0
    rewards["completion"] = int(completion_reward) if completion_reward.isdigit() else 0
    
    # Input costs
    costs = {}
    hire_cost = input("\nCost to start the quest (e.g., 5 for 5 gems, or 0 if none): ")
    costs["start_cost"] = int(hire_cost) if hire_cost.isdigit() else 0
    
    # Input mechanics (customize these based on your game)
    mechanics = []
    print("\nAdd mechanics (e.g., spawn_enemy_per_turn, travel_hexes).")
    while True:
        mechanic = input("Mechanic (or 'done' to finish): ")
        if mechanic.lower() == 'done':
            break
        mechanics.append(mechanic)
    
    # Input success conditions
    success_conditions = []
    print("\nAdd success conditions (e.g., npc_reaches_location, enemy_defeated).")
    while True:
        condition = input("Success condition (or 'done' to finish): ")
        if condition.lower() == 'done':
            break
        success_conditions.append(condition)
    
    # Input failure conditions
    failure_conditions = []
    print("\nAdd failure conditions (e.g., npc_dies, turns_exceed_10).")
    while True:
        condition = input("Failure condition (or 'done' to finish): ")
        if condition.lower() == 'done':
            break
        failure_conditions.append(condition)
    
    # Create the template dictionary
    template = {
        "text": text,
        "placeholders": placeholders,
        "rewards": rewards,
        "costs": costs,
        "mechanics": mechanics,
        "success": success_conditions,
        "failure": failure_conditions
    }
    
    # Save to JSON file
    quest_name = input("\nEnter a name for this quest template (e.g., escort_mission): ")
    filename = os.path.join(QUESTS_DIR, f"{quest_name}.json")
    with open(filename, "w") as f:
        json.dump(template, f, indent=4)
    print(f"Quest template '{quest_name}' saved to {filename}")

def load_deck(card_type):
    """Load a deck from a JSON file based on the card type."""
    deck_path = os.path.join(DECKS_DIR, f"{card_type}.json")
    if not os.path.exists(deck_path):
        print(f"Error: Deck '{card_type}.json' not found in {DECKS_DIR}. Please create it first.")
        return []
    with open(deck_path, "r") as f:
        deck = json.load(f)
    if not deck:
        print(f"Warning: Deck '{card_type}.json' is empty.")
    return deck

def generate_final_quest():
    """Generate a final quest by filling in a template with cards from decks."""
    print("\n=== Generating a Final Quest ===")
    quest_name = input("Enter the name of the quest template (e.g., escort_mission): ")
    template_path = os.path.join(QUESTS_DIR, f"{quest_name}.json")
    if not os.path.exists(template_path):
        print(f"Error: Quest template '{quest_name}.json' not found in {QUESTS_DIR}")
        return
    
    with open(template_path, "r") as f:
        template = json.load(f)
    
    final_quest = {
        "text": template["text"],
        "placeholders": {},
        "rewards": template["rewards"],
        "costs": template["costs"],
        "mechanics": template["mechanics"],
        "success": template["success"],
        "failure": template["failure"]
    }
    
    # Fill in placeholders with random cards from decks
    for placeholder, card_type in template["placeholders"].items():
        deck = load_deck(card_type)
        if not deck:
            final_quest["placeholders"][placeholder] = {"name": f"[{card_type} Missing]"}
        else:
            card = random.choice(deck)
            final_quest["placeholders"][placeholder] = card
            final_quest["text"] = final_quest["text"].replace("{" + placeholder + "}", card["name"])
    
    # Display the final quest
    print("\n=== Final Quest ===")
    print(f"Quest: {final_quest['text']}")
    print(f"Initial Reward: {final_quest['rewards']['initial']} gems")
    print(f"Completion Reward: {final_quest['rewards']['completion']} gems")
    print(f"Cost to Start: {final_quest['costs']['start_cost']} gems")
    print("Mechanics:", ", ".join(final_quest["mechanics"]) or "None")
    print("Success Conditions:", ", ".join(final_quest["success"]) or "None")
    print("Failure Conditions:", ", ".join(final_quest["failure"]) or "None")
    print("\nPlaceholders Filled:")
    for placeholder, card in final_quest["placeholders"].items():
        print(f"  {placeholder}: {card['name']}")

def main():
    """Main menu for the Quest Card Maker."""
    print("Welcome to the Quest Card Maker!")
    while True:
        print("\n=== Menu ===")
        print("1. Create a new Quest Card template")
        print("2. Generate a final quest from a template")
        print("3. Exit")
        choice = input("Choose an option (1-3): ")
        if choice == "1":
            create_quest_template()
        elif choice == "2":
            generate_final_quest()
        elif choice == "3":
            print("Goodbye!")
            break
        else:
            print("Invalid choice. Please enter 1, 2, or 3.")

if __name__ == "__main__":
    main()

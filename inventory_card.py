class InventoryCard:
    def __init__(self, card_data):
        self.card_data = card_data
        self.states = card_data.get("states", 1)
        self.current_state = 1 if self.states >= 1 else None

    def get_current_data(self):
        return self.get_state_data(self.current_state)

    def get_state_data(self, state):
        if state == 1:
            return {k: v for k, v in self.card_data["data"].items() if not k.startswith("2nd_state_")}
        elif state == 2:
            return {k.replace("2nd_state_", ""): v for k, v in self.card_data["data"].items() if k.startswith("2nd_state_")}
        return {}

    def toggle_state(self):
        if self.states == 2:
            self.current_state = 3 - self.current_state

    def is_two_state(self):
        return self.states == 2

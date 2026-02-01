import tkinter as tk
from tkinter import filedialog, messagebox, Toplevel
import json
import os
from PIL import Image, ImageTk, ImageGrab

class CardTemplateMaker:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Card Template Maker")
        # Make full-screen (Windows: 'zoomed', macOS/Linux: '-fullscreen')
        self.root.state('zoomed')  # Works on Windows; use attributes('-fullscreen', True) for cross-platform
        self.root.attributes('-fullscreen', False)  # Optional: Toggle for testing
        
        # Card dimensions (5:7 ratio)
        self.card_width = 300
        self.card_height = 420
        
        # Workspace dimensions (larger than card, e.g., screen size or fixed large area)
        self.workspace_width = 1920  # Adjust based on screen size if needed
        self.workspace_height = 1080
        
        self.current_card_data = None
        self.current_layout = {}
        self.selected_element = None
        self.images = {}
        
        self.setup_main_menu()
        
    def setup_main_menu(self):
        for widget in self.root.winfo_children():
            widget.destroy()
            
        tk.Button(self.root, text="Design Card Layout", 
                 command=self.setup_design_interface).pack(pady=10)
        tk.Button(self.root, text="Settings", 
                 command=lambda: messagebox.showinfo("Settings", "Settings placeholder")).pack(pady=10)
        tk.Button(self.root, text="Quit", 
                 command=self.root.quit).pack(pady=10)
    
    def setup_design_interface(self):
        for widget in self.root.winfo_children():
            widget.destroy()
            
        # Left frame for controls
        self.left_frame = tk.Frame(self.root, width=200)
        self.left_frame.pack(side=tk.LEFT, fill=tk.Y)
        
        # Main frame for canvas and properties
        self.main_frame = tk.Frame(self.root)
        self.main_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Left panel buttons
        tk.Button(self.left_frame, text="Import Card Info", 
                 command=self.import_card_info).pack(pady=5)
        tk.Button(self.left_frame, text="Save Layout", 
                 command=self.save_layout).pack(pady=5)
        tk.Button(self.left_frame, text="Save Card Image", 
                 command=self.save_card_image).pack(pady=5)
        
        # Canvas with workspace size, scrollable if needed
        self.canvas = tk.Canvas(self.main_frame, width=self.workspace_width, 
                              height=self.workspace_height, bg='gray')  # Gray for workspace
        self.canvas.pack(pady=20, fill=tk.BOTH, expand=True)
        
        # Center the card on the workspace
        self.card_x = (self.workspace_width - self.card_width) // 2
        self.card_y = (self.workspace_height - self.card_height) // 2
        self.canvas.create_rectangle(self.card_x, self.card_y, 
                                   self.card_x + self.card_width, 
                                   self.card_y + self.card_height, 
                                   fill='white', outline='black', tags="card")
        
        # Properties panel
        self.properties_frame = tk.Frame(self.main_frame)
        self.properties_frame.pack(pady=10, fill=tk.X)
        
        # Bind canvas events
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_drop)
    
    def import_card_info(self):
        cards_dir = os.path.join(os.getcwd(), "cards")
        if not os.path.exists(cards_dir):
            messagebox.showerror("Error", "Cards folder not found!")
            return
            
        json_files = [f for f in os.listdir(cards_dir) if f.endswith('.json')]
        if not json_files:
            messagebox.showerror("Error", "No JSON files found in cards folder!")
            return
            
        dialog = Toplevel(self.root)
        dialog.title("Select Card JSON")
        dialog.geometry("300x400")
        
        listbox = tk.Listbox(dialog)
        listbox.pack(pady=10, fill=tk.BOTH, expand=True)
        
        for file in json_files:
            listbox.insert(tk.END, file)
            
        def on_select():
            selection = listbox.curselection()
            if selection:
                file_path = os.path.join(cards_dir, json_files[selection[0]])
                self.load_card_data(file_path)
                dialog.destroy()
                
        tk.Button(dialog, text="Import", command=on_select).pack(pady=5)
    
    def load_card_data(self, file_path):
        try:
            with open(file_path, 'r') as f:
                self.current_card_data = json.load(f)
                
            self.current_layout = {}
            # Start positioning on the card, then overflow to the right
            x_start = self.card_x + 20
            y_start = self.card_y + 20
            x_offset = x_start
            y_offset = y_start
            
            for key in self.current_card_data.get("data", {}).keys():
                if "image" in key.lower() or "file" in key.lower():
                    layout = {
                        'x': x_offset,
                        'y': y_offset,
                        'width': 100,
                        'height': 100
                    }
                    y_offset += 110
                    if y_offset + 100 > self.card_y + self.card_height:
                        x_offset += 120  # Move right outside card
                        y_offset = y_start  # Reset Y to top
                else:
                    layout = {
                        'x': x_offset,
                        'y': y_offset,
                        'font': ('Arial', 12),
                        'size': 12,
                        'show_key': True
                    }
                    y_offset += 30
                    if y_offset + 30 > self.card_y + self.card_height:
                        x_offset += 150  # Move right outside card
                        y_offset = y_start  # Reset Y to top
                self.current_layout[key] = layout
                
            print("Loaded keys in self.current_layout:", list(self.current_layout.keys()))
            self.update_card_preview()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load card data: {str(e)}")
    
    def update_card_preview(self):
        self.canvas.delete("all")
        self.images.clear()
        # Redraw card background
        self.canvas.create_rectangle(self.card_x, self.card_y, 
                                   self.card_x + self.card_width, 
                                   self.card_y + self.card_height, 
                                   fill='white', outline='black', tags="card")
        
        if self.current_card_data and self.current_layout:
            for key, layout in self.current_layout.items():
                if key in self.current_card_data["data"]:
                    value = str(self.current_card_data["data"][key])
                    tag = f"element_{key}"
                    print(f"Creating canvas item with tag: {tag}")
                    if "image" in key.lower() or "file" in key.lower():
                        if os.path.exists(value):
                            try:
                                img = Image.open(value)
                                img = img.resize((layout['width'], layout['height']), Image.Resampling.LANCZOS)
                                tk_img = ImageTk.PhotoImage(img)
                                self.canvas.create_image(layout['x'], layout['y'], 
                                                       image=tk_img, anchor='nw', tags=(tag,))
                                self.images[tag] = tk_img
                            except Exception as e:
                                self.canvas.create_text(layout['x'], layout['y'], 
                                                      text=f"Image Error: {value}",
                                                      anchor='nw', tags=(tag,))
                    else:
                        text = f"{key}: {value}" if layout['show_key'] else value
                        self.canvas.create_text(layout['x'], layout['y'], 
                                              text=text, font=layout['font'],
                                              anchor='nw', tags=(tag,))
        self.print_canvas_items()
    
    def print_canvas_items(self):
        print("Current canvas items:")
        for item in self.canvas.find_all():
            tags = self.canvas.gettags(item)
            print(f"Item {item}: tags = {tags}")
    
    def on_canvas_click(self, event):
        items = self.canvas.find_closest(event.x, event.y)
        if items:
            tags = self.canvas.gettags(items[0])
            print("Clicked item tags:", tags)
            if tags and tags[0].startswith("element_"):
                self.selected_element = tags[0].replace("element_", "")
                print("Selected element:", self.selected_element)
                if self.selected_element in self.current_layout:
                    layout = self.current_layout[self.selected_element]
                    if "image" in self.selected_element.lower() or "file" in self.selected_element.lower():
                        self.show_image_properties(layout)
                    else:
                        self.show_text_properties(layout)
                else:
                    print(f"Warning: Selected element '{self.selected_element}' not found in self.current_layout")
                    self.selected_element = None
    
    def on_drag(self, event):
        if self.selected_element and self.selected_element in self.current_layout:
            self.current_layout[self.selected_element]['x'] = max(0, min(event.x, self.workspace_width))
            self.current_layout[self.selected_element]['y'] = max(0, min(event.y, self.workspace_height))
            self.update_card_preview()
        else:
            print(f"Warning: Cannot drag '{self.selected_element}' - not in self.current_layout")
    
    def on_drop(self, event):
        self.selected_element = None
    
    def show_text_properties(self, layout):
        for widget in self.properties_frame.winfo_children():
            widget.destroy()
            
        self.show_key_var = tk.BooleanVar(value=layout['show_key'])
        tk.Checkbutton(self.properties_frame, text="Show Key", 
                      variable=self.show_key_var,
                      command=self.update_selected_element).pack()
    
    def show_image_properties(self, layout):
        for widget in self.properties_frame.winfo_children():
            widget.destroy()
            
        tk.Label(self.properties_frame, text="Width:").pack()
        self.width_entry = tk.Entry(self.properties_frame)
        self.width_entry.insert(0, str(layout['width']))
        self.width_entry.pack()
        
        tk.Label(self.properties_frame, text="Height:").pack()
        self.height_entry = tk.Entry(self.properties_frame)
        self.height_entry.insert(0, str(layout['height']))
        self.height_entry.pack()
        
        tk.Button(self.properties_frame, text="Apply", 
                 command=self.update_image_size).pack()
    
    def update_selected_element(self):
        if self.selected_element and "image" not in self.selected_element.lower():
            self.current_layout[self.selected_element]['show_key'] = self.show_key_var.get()
            self.update_card_preview()
    
    def update_image_size(self):
        if self.selected_element and "image" in self.selected_element.lower():
            try:
                width = int(self.width_entry.get())
                height = int(self.height_entry.get())
                self.current_layout[self.selected_element]['width'] = width
                self.current_layout[self.selected_element]['height'] = height
                self.update_card_preview()
            except ValueError:
                messagebox.showerror("Error", "Invalid width or height")
    
    def save_layout(self):
        if not self.current_card_data or not self.current_layout:
            messagebox.showerror("Error", "No layout to save!")
            return
            
        dialog = Toplevel(self.root)
        dialog.title("Save Layout")
        dialog.geometry("300x150")
        
        tk.Label(dialog, text="Layout Name:").pack(pady=5)
        name_entry = tk.Entry(dialog)
        name_entry.pack(pady=5)
        
        def do_save():
            name = name_entry.get().strip()
            if not name:
                messagebox.showerror("Error", "Please enter a name!")
                return
                
            layout_data = {
                'card_type': self.current_card_data.get('card_type', ''),
                'subclass': self.current_card_data.get('subclass', ''),
                'blueprint_subclass': self.current_card_data.get('blueprint_subclass', ''),
                'states': self.current_card_data.get('states', 1),
                'layout': self.current_layout
            }
            
            try:
                os.makedirs("layouts", exist_ok=True)
                with open(f"layouts/{name}.json", 'w') as f:
                    json.dump(layout_data, f, indent=4)
                messagebox.showinfo("Success", "Layout saved successfully!")
                dialog.destroy()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save layout: {str(e)}")
        
        tk.Button(dialog, text="Save", command=do_save).pack(pady=5)
    
    def save_card_image(self):
        if not self.current_card_data:
            messagebox.showerror("Error", "No card loaded!")
            return
            
        filename = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG files", "*.png"), ("All files", "*.*")],
            title="Save Card Image"
        )
        if not filename:
            return
            
        try:
            self.canvas.update()
            # Save only the card area, not the full workspace
            x = self.canvas.winfo_rootx() + self.card_x
            y = self.canvas.winfo_rooty() + self.card_y
            box = (x, y, x + self.card_width, y + self.card_height)
            img = ImageGrab.grab(bbox=box)
            img.save(filename, 'png')
            messagebox.showinfo("Success", "Card image saved successfully!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save image: {str(e)}")
    
    def run(self):
        os.makedirs("layouts", exist_ok=True)
        self.root.mainloop()

if __name__ == "__main__":
    app = CardTemplateMaker()
    app.run()

import tkinter as tk
from tkinter import font as tkfont
from tkinter import scrolledtext, simpledialog, messagebox
from manage_vector import VectorManager

class VectorQueryGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Redis Vector Storage & Search")
        self.root.geometry("980x800")

        # Define fonts using TkDefaultFont
        self.default_font = tkfont.nametofont("TkDefaultFont")
        self.default_bold = tkfont.Font(family=self.default_font.actual("family"), size=18, weight="bold")
        self.button_font = tkfont.Font(family=self.default_font.actual("family"), size=12)
        self.italic_font = tkfont.Font(family=self.default_font.actual("family"), size=12, slant="italic")
        self.fixed_font = tkfont.nametofont("TkFixedFont")
        self.fixed_font.configure(size=12)
        self.small_fixed = tkfont.nametofont("TkFixedFont")
        self.small_fixed.configure(size=11)
        self.label_bold = tkfont.Font(family=self.default_font.actual("family"), size=12, weight="bold")

        # Initialize vector manager
        try:
            self.manager = VectorManager()
            self.connection_status = "Connected"
        except Exception as e:
            self.connection_status = f"Error: {e}"
            self.manager = None

        # Create UI
        self.create_widgets()

    def center_window(self, dialog, width, height):
        """Center a child window relative to the main window"""
        self.root.update_idletasks()
        main_x = self.root.winfo_x()
        main_y = self.root.winfo_y()
        main_width = self.root.winfo_width()
        main_height = self.root.winfo_height()

        x = main_x + (main_width - width) // 2
        y = main_y + (main_height - height) // 2

        dialog.geometry(f"{width}x{height}+{x}+{y}")

    def create_widgets(self):
        """Create the GUI layout"""
        # Left frame - Menu
        left_frame = tk.Frame(self.root, width=320, bg="#f0f0f0")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, padx=5, pady=5)
        left_frame.pack_propagate(False)

        # Title
        title_label = tk.Label(left_frame, text="Product Operations",
                               font=self.default_bold, bg="#f0f0f0")
        title_label.pack(pady=15)

        # Menu buttons
        btn_style = {"font": self.button_font, "width": 20, "pady": 10, "bg": "#4a4a4a", "fg": "white"}

        tk.Button(left_frame, text="Load Sample Products",
                 command=self.load_samples, **btn_style).pack(pady=8)
        tk.Button(left_frame, text="List All Products",
                 command=self.list_products, **btn_style).pack(pady=8)
        tk.Button(left_frame, text="Store New Product",
                 command=self.store_new_vector, **btn_style).pack(pady=8)
        tk.Button(left_frame, text="Find Similar Products",
                 command=self.search_vectors, **btn_style).pack(pady=8)
        tk.Button(left_frame, text="Delete Product",
                 command=self.delete_vector, **btn_style).pack(pady=8)
        tk.Button(left_frame, text="Clear All Products",
                 command=self.clear_all_vectors, **btn_style).pack(pady=8)

        # Status label
        self.status_label = tk.Label(left_frame, text=f"Status: {self.connection_status}",
                                     font=self.default_font, bg="#f0f0f0", fg="green")
        self.status_label.pack(side=tk.BOTTOM, pady=20)

        # Exit button at bottom
        tk.Button(left_frame, text="Exit", command=self.exit_app,
                 **btn_style).pack(side=tk.BOTTOM, pady=8)

        # Right frame - Output
        right_frame = tk.Frame(self.root)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Output area label
        output_label = tk.Label(right_frame, text="Operation Results",
                               font=self.default_bold)
        output_label.pack(pady=5)

        # Scrolled text widget for output
        self.output_box = scrolledtext.ScrolledText(
            right_frame,
            wrap=tk.WORD,
            width=120,
            height=32,
            font=self.fixed_font,
            bg="#1e1e1e",
            fg="#d4d4d4"
        )
        self.output_box.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Initial message
        self.display_message("[+] Connected to Redis Vector Storage\n[i] Select an operation from the menu\n")

    def display_message(self, msg):
        """Add a message to the output box"""
        self.output_box.insert(tk.END, msg)
        self.output_box.see(tk.END)
        self.root.update()

    def clear_output(self):
        """Clear the output box"""
        self.output_box.delete(1.0, tk.END)

    def parse_embedding(self, embedding_str: str) -> list:
        """Parse embedding string in various formats: '0.1, 0.2, ...' or '[0.1, 0.2, ...]'"""
        # Remove brackets and extra whitespace
        embedding_str = embedding_str.strip().lstrip('[').rstrip(']').strip()
        # Split by comma and convert to float
        return [float(x.strip()) for x in embedding_str.split(",")]

    def load_samples(self):
        """Load sample vectors"""
        if not self.manager:
            messagebox.showerror("Error", "Not connected to Redis")
            return

        self.clear_output()
        self.display_message("[*] Loading sample vectors...\n")
        success, message = self.manager.load_sample_products()

        if success:
            self.display_message(f"[✓] {message}\n")
        else:
            self.display_message(f"[✗] {message}\n")

    def list_products(self):
        """List all products"""
        if not self.manager:
            messagebox.showerror("Error", "Not connected to Redis")
            return

        self.clear_output()
        self.display_message("[*] Retrieving product list...\n")
        success, result = self.manager.list_all_products()

        if success:
            self.display_message(f"[✓] Found {len(result)} products:\n\n")
            for key in result:
                self.display_message(f" • Key: {key}\n")
                # Retrieve product details including embedding
                prod_success, prod_data = self.manager.retrieve_product(key)
                if prod_success and isinstance(prod_data, dict):
                    name = prod_data.get("name", "N/A")
                    category = prod_data.get("category", "N/A")
                    self.display_message(f"      Name: {name}\n")
                    self.display_message(f"      Category: {category}\n")
                    # Format embedding for easy copy/paste
                    embedding_vector = prod_data.get("vector", [])
                    if embedding_vector:
                        formatted_vector = ", ".join([f"{v:.2f}" for v in embedding_vector])
                        self.display_message(f"      Embedding: [{formatted_vector}]\n")
                self.display_message("\n")
        else:
            self.display_message(f"[✗] {result}\n")

    def store_new_vector(self):
        """Store a new vector with dialog"""
        if not self.manager:
            messagebox.showerror("Error", "Not connected to Redis")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Store New Product")
        dialog.transient(self.root)
        self.center_window(dialog, 480, 390)

        # Product key input
        tk.Label(dialog, text="Product Key:", font=self.label_bold).pack(pady=0, anchor=tk.W, padx=15)
        key_entry = tk.Entry(dialog, width=50, font=self.fixed_font)
        key_entry.pack(pady=5, padx=15, anchor=tk.W)
        key_entry.insert(0, "product:<id>")

        # Embedding input
        tk.Label(dialog, text="Embedding (comma-separated):", font=self.label_bold).pack(pady=0, anchor=tk.W, padx=15)

        vector_text = tk.Text(dialog, width=50, height=2, font=self.fixed_font)
        vector_text.pack(pady=5, padx=15, anchor=tk.W)
        vector_text.insert(1.0, "0.1, 0.2, 0.15, 0.8,...")

        # Metadata section
        tk.Label(dialog, text="Metadata:", font=self.label_bold).pack(pady=0, anchor=tk.W, padx=15)
        metadata_text = tk.Text(dialog, width=50, height=3, font=self.fixed_font)
        metadata_text.pack(pady=5, padx=15, anchor=tk.W)
        metadata_text.insert(1.0, "product_id=<id>\nname=<Product Name>\ncategory=<Category>")

        def store():
            try:
                key = key_entry.get().strip()
                vector_str = vector_text.get(1.0, tk.END).strip()

                if not key or not vector_str:
                    messagebox.showwarning("Warning", "Key and vector cannot be empty")
                    return

                vector = self.parse_embedding(vector_str)

                # Parse metadata
                metadata = {}
                meta_lines = metadata_text.get(1.0, tk.END).strip().split("\n")
                for line in meta_lines:
                    if "=" in line:
                        k, v = line.split("=", 1)
                        metadata[k.strip()] = v.strip()

                success, message = self.manager.store_product(key, vector, metadata if metadata else None)

                self.clear_output()
                if success:
                    self.display_message(f"[✓] {message}\n")
                    if metadata:
                        self.display_message("Metadata:\n")
                        for k, v in metadata.items():
                            self.display_message(f"  {k}: {v}\n")
                else:
                    self.display_message(f"[✗] {message}\n")

                dialog.destroy()
            except ValueError as e:
                messagebox.showerror("Error", f"Invalid vector format: {e}")

        tk.Button(dialog, text="Store Product", command=store, bg="#4a4a4a", fg="white", font=self.button_font, width=20, height=1).pack(pady=10, padx=15, anchor=tk.W)

    def retrieve_vector(self):
        """Retrieve a vector by key"""
        if not self.manager:
            messagebox.showerror("Error", "Not connected to Redis")
            return
    def search_vectors(self):
        """Search for similar vectors"""
        if not self.manager:
            messagebox.showerror("Error", "Not connected to Redis")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Find Similar Products")
        dialog.transient(self.root)
        self.center_window(dialog, 585, 330)

        tk.Label(dialog, text="Query Embedding:", font=self.label_bold).pack(pady=0, anchor=tk.W, padx=15)

        vector_text = tk.Text(dialog, width=55, height=2, font=self.fixed_font)
        vector_text.pack(pady=5, padx=15, anchor=tk.W)
        vector_text.insert(1.0, "0.1, 0.2, 0.15, 0.8, 0.3, 0.6, 0.4,...")

        tk.Label(dialog, text="Number of results (1-10):", font=self.label_bold).pack(pady=0, anchor=tk.W, padx=15)

        count_entry = tk.Spinbox(dialog, from_=1, to=10, width=3, font=self.fixed_font)
        count_entry.delete(0, tk.END)
        count_entry.insert(0, 5)
        count_entry.pack(pady=5, padx=15, anchor=tk.W)

        def search():
            try:
                vector_str = vector_text.get(1.0, tk.END).strip()
                if not vector_str:
                    messagebox.showwarning("Warning", "Enter a query embedding")
                    return

                query_vector = self.parse_embedding(vector_str)
                top_k = int(count_entry.get())
                top_k = max(1, min(10, top_k))

                success, results = self.manager.search_similar_products(query_vector, top_k)

                self.clear_output()
                if success:
                    self.display_message(f"[✓] Found {len(results)} similar products\n\n")

                    for idx, result in enumerate(results, 1):
                        self.display_message(f"{idx}. {result['name']} ({result['key']})\n")
                        self.display_message(f"   Product ID: {result['product_id']}\n")
                        self.display_message(f"   Category: {result['category']}\n")
                        self.display_message(f"   Similarity Score: {result['similarity']:.4f}\n")
                        self.display_message("\n")
                else:
                    self.display_message(f"[✗] {results}\n")

                dialog.destroy()
            except ValueError as e:
                messagebox.showerror("Error", f"Invalid input: {e}")

        search_btn = tk.Button(dialog, text="Search", command=search, bg="#4a4a4a",
                 fg="white", font=self.button_font, width=20, height=1)
        search_btn.pack(pady=10, padx=15, anchor=tk.W)

    def delete_vector(self):
        """Delete a vector by key"""
        if not self.manager:
            messagebox.showerror("Error", "Not connected to Redis")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Delete Product")
        dialog.transient(self.root)
        self.center_window(dialog, 400, 150)

        tk.Label(dialog, text="Product Key:", font=self.label_bold).pack(pady=0, anchor=tk.W, padx=15)
        entry = tk.Entry(dialog, width=40, font=self.fixed_font)
        entry.pack(pady=5, padx=15, anchor=tk.W)
        entry.insert(0, "product:<id>")

        def delete():
            key = entry.get().strip()
            if not key:
                messagebox.showwarning("Warning", "Enter a product key")
                return

            success, message = self.manager.delete_product(key)

            self.clear_output()
            if success:
                self.display_message(f"[✓] {message}\n")
            else:
                self.display_message(f"[✗] {message}\n")

            dialog.destroy()

        delete_btn = tk.Button(dialog, text="Delete", command=delete, bg="#4a4a4a", fg="white", font=self.button_font, width=20, height=1)
        delete_btn.pack(pady=10, padx=15, anchor=tk.W)

    def clear_all_vectors(self):
        """Clear all vectors with confirmation"""
        if not self.manager:
            messagebox.showerror("Error", "Not connected to Redis")
            return

        success, message = self.manager.clear_all_products()

        self.clear_output()
        if success:
            self.display_message(f"[✓] {message}\n")
        else:
            self.display_message(f"[✗] {message}\n")

    def exit_app(self):
        """Exit the application"""
        self.root.destroy()

def run_gui():
    """Launch the GUI version"""
    root = tk.Tk()
    app = VectorQueryGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.exit_app)
    root.mainloop()

if __name__ == "__main__":
    run_gui()

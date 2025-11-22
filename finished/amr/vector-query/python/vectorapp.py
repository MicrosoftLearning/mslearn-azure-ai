import tkinter as tk
from tkinter import font as tkfont
from tkinter import scrolledtext, simpledialog, messagebox
from manage_vector import VectorManager

class VectorQueryGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Redis Vector Storage & Search")
        self.root.geometry("1000x700")
        
        # Define fonts using TkDefaultFont
        self.default_font = tkfont.nametofont("TkDefaultFont")
        self.default_bold = tkfont.Font(family=self.default_font.actual("family"), 
                                        size=14, weight="bold")
        self.button_font = tkfont.Font(family=self.default_font.actual("family"), 
                                       size=10)
        self.italic_font = tkfont.Font(family=self.default_font.actual("family"), 
                                       size=9, slant="italic")
        self.fixed_font = tkfont.nametofont("TkFixedFont")
        
        # Initialize vector manager
        try:
            self.manager = VectorManager()
            self.connection_status = "Connected"
        except Exception as e:
            self.connection_status = f"Error: {e}"
            self.manager = None
        
        # Create UI
        self.create_widgets()
    
    def create_widgets(self):
        """Create the GUI layout"""
        # Left frame - Menu
        left_frame = tk.Frame(self.root, width=280, bg="#f0f0f0")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, padx=5, pady=5)
        left_frame.pack_propagate(False)
        
        # Title
        title_label = tk.Label(left_frame, text="Vector Operations", 
                               font=self.default_bold, bg="#f0f0f0")
        title_label.pack(pady=15)
        
        # Menu buttons
        btn_style = {"font": self.button_font, "width": 30, "pady": 8, "bg": "#4a4a4a", "fg": "white"}
        
        tk.Button(left_frame, text="1. Load Sample Vectors", 
                 command=self.load_samples, **btn_style).pack(pady=5)
        tk.Button(left_frame, text="2. Store New Vector", 
                 command=self.store_new_vector, **btn_style).pack(pady=5)
        tk.Button(left_frame, text="3. Retrieve Vector", 
                 command=self.retrieve_vector, **btn_style).pack(pady=5)
        tk.Button(left_frame, text="4. Search Similar Vectors", 
                 command=self.search_vectors, **btn_style).pack(pady=5)
        tk.Button(left_frame, text="5. List All Vectors", 
                 command=self.list_vectors, **btn_style).pack(pady=5)
        tk.Button(left_frame, text="6. Delete Vector", 
                 command=self.delete_vector, **btn_style).pack(pady=5)
        tk.Button(left_frame, text="7. Clear All Vectors", 
                 command=self.clear_all_vectors, **btn_style).pack(pady=5)
        
        # Status label
        self.status_label = tk.Label(left_frame, text=f"Status: {self.connection_status}", 
                                     font=self.default_font, bg="#f0f0f0", fg="green")
        self.status_label.pack(pady=20)
        
        # Exit button at bottom
        tk.Button(left_frame, text="8. Exit", command=self.exit_app, 
                 **btn_style).pack(side=tk.BOTTOM, pady=10)
        
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
            width=70, 
            height=40,
            font=self.fixed_font,
            bg="#1e1e1e",
            fg="#d4d4d4"
        )
        self.output_box.pack(fill=tk.BOTH, expand=True)
        
        # Clear output button
        tk.Button(right_frame, text="Clear Output", 
                 command=self.clear_output, bg="#4a4a4a", fg="white").pack(pady=5)
        
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
    
    def load_samples(self):
        """Load sample vectors"""
        if not self.manager:
            messagebox.showerror("Error", "Not connected to Redis")
            return
        
        self.clear_output()
        self.display_message("[*] Loading sample vectors...\n")
        success, message = self.manager.load_sample_vectors()
        
        if success:
            self.display_message(f"[✓] {message}\n")
        else:
            self.display_message(f"[✗] {message}\n")
    
    def store_new_vector(self):
        """Store a new vector with dialog"""
        if not self.manager:
            messagebox.showerror("Error", "Not connected to Redis")
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Store New Vector")
        dialog.geometry("500x500")
        
        # Vector key input
        tk.Label(dialog, text="Vector Key:", font=self.default_font).pack(pady=5)
        key_entry = tk.Entry(dialog, width=40)
        key_entry.pack(pady=5)
        key_entry.insert(0, "vector:product_")
        
        # Vector input
        tk.Label(dialog, text="Vector (comma-separated):", font=self.default_font).pack(pady=5)
        tk.Label(dialog, text="Example: 0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8", 
                font=self.italic_font).pack()
        
        vector_text = tk.Text(dialog, width=40, height=6, font=self.fixed_font)
        vector_text.pack(pady=5)
        
        # Metadata section
        tk.Label(dialog, text="Metadata (key=value pairs, one per line):", font=self.default_font).pack(pady=5)
        metadata_text = tk.Text(dialog, width=40, height=6, font=self.fixed_font)
        metadata_text.pack(pady=5)
        metadata_text.insert(1.0, "name=Product Name\ncategory=Electronics")
        
        def store():
            try:
                key = key_entry.get().strip()
                vector_str = vector_text.get(1.0, tk.END).strip()
                
                if not key or not vector_str:
                    messagebox.showwarning("Warning", "Key and vector cannot be empty")
                    return
                
                vector = [float(x.strip()) for x in vector_str.split(",")]
                
                # Parse metadata
                metadata = {}
                meta_lines = metadata_text.get(1.0, tk.END).strip().split("\n")
                for line in meta_lines:
                    if "=" in line:
                        k, v = line.split("=", 1)
                        metadata[k.strip()] = v.strip()
                
                success, message = self.manager.store_vector(key, vector, metadata if metadata else None)
                
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
        
        tk.Button(dialog, text="Store Vector", command=store, bg="#4a4a4a", 
                 fg="white", font=self.button_font).pack(pady=10)
    
    def retrieve_vector(self):
        """Retrieve a vector by key"""
        if not self.manager:
            messagebox.showerror("Error", "Not connected to Redis")
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Retrieve Vector")
        dialog.geometry("400x200")
        
        tk.Label(dialog, text="Vector Key:", font=self.default_font).pack(pady=10)
        entry = tk.Entry(dialog, width=40)
        entry.pack(pady=5)
        
        def retrieve():
            key = entry.get().strip()
            if not key:
                messagebox.showwarning("Warning", "Enter a vector key")
                return
            
            success, result = self.manager.retrieve_vector(key)
            
            self.clear_output()
            if success:
                self.display_message(f"[✓] Retrieved vector: {key}\n\n")
                self.display_message(f"Dimensions: {len(result['vector'])}\n")
                self.display_message(f"Vector (first 5): {result['vector'][:5]}...\n")
                
                if result['metadata']:
                    self.display_message("\nMetadata:\n")
                    for k, v in result['metadata'].items():
                        self.display_message(f"  {k}: {v}\n")
            else:
                self.display_message(f"[✗] {result}\n")
            
            dialog.destroy()
        
        tk.Button(dialog, text="Retrieve", command=retrieve, bg="#4a4a4a", 
                 fg="white", font=self.button_font).pack(pady=10)
    
    def search_vectors(self):
        """Search for similar vectors"""
        if not self.manager:
            messagebox.showerror("Error", "Not connected to Redis")
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Search Similar Vectors")
        dialog.geometry("500x350")
        
        tk.Label(dialog, text="Query Vector (comma-separated):", font=self.default_font).pack(pady=5)
        tk.Label(dialog, text="Example: 0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8", 
                font=self.italic_font).pack()
        
        vector_text = tk.Text(dialog, width=40, height=6, font=self.fixed_font)
        vector_text.pack(pady=5)
        
        tk.Label(dialog, text="Number of results (1-10):", font=self.default_font).pack(pady=5)
        tk.Label(dialog, text="Default: 3", font=self.italic_font).pack()
        
        count_entry = tk.Entry(dialog, width=10)
        count_entry.pack(pady=5)
        count_entry.insert(0, "3")
        
        def search():
            try:
                vector_str = vector_text.get(1.0, tk.END).strip()
                if not vector_str:
                    messagebox.showwarning("Warning", "Enter a query vector")
                    return
                
                query_vector = [float(x.strip()) for x in vector_str.split(",")]
                top_k = int(count_entry.get().strip() or "3")
                top_k = max(1, min(10, top_k))
                
                success, results = self.manager.search_similar_vectors(query_vector, top_k)
                
                self.clear_output()
                if success:
                    self.display_message(f"[✓] Found {len(results)} similar vectors\n\n")
                    
                    for idx, result in enumerate(results, 1):
                        self.display_message(f"{idx}. Key: {result['key']}\n")
                        self.display_message(f"   Similarity: {result['similarity']:.4f}\n")
                        if result['metadata']:
                            self.display_message("   Metadata:\n")
                            for k, v in result['metadata'].items():
                                self.display_message(f"     {k}: {v}\n")
                        self.display_message("\n")
                else:
                    self.display_message(f"[✗] {results}\n")
                
                dialog.destroy()
            except ValueError as e:
                messagebox.showerror("Error", f"Invalid input: {e}")
        
        tk.Button(dialog, text="Search", command=search, bg="#4a4a4a", 
                 fg="white", font=self.button_font).pack(pady=10)
    
    def list_vectors(self):
        """List all vectors"""
        if not self.manager:
            messagebox.showerror("Error", "Not connected to Redis")
            return
        
        success, results = self.manager.list_all_vectors()
        
        self.clear_output()
        if success:
            self.display_message(f"[✓] Total vectors: {len(results)}\n\n")
            
            for vector_info in results:
                self.display_message(f"• {vector_info['key']}\n")
                self.display_message(f"  Dimensions: {vector_info['dimensions']}\n")
                if vector_info['metadata']:
                    self.display_message("  Metadata:\n")
                    for k, v in vector_info['metadata'].items():
                        self.display_message(f"    {k}: {v}\n")
                self.display_message("\n")
        else:
            self.display_message(f"[✗] {results}\n")
    
    def delete_vector(self):
        """Delete a vector by key"""
        if not self.manager:
            messagebox.showerror("Error", "Not connected to Redis")
            return
        
        dialog = tk.Toplevel(self.root)
        dialog.title("Delete Vector")
        dialog.geometry("400x200")
        
        tk.Label(dialog, text="Vector Key:", font=self.default_font).pack(pady=10)
        entry = tk.Entry(dialog, width=40)
        entry.pack(pady=5)
        
        def delete():
            key = entry.get().strip()
            if not key:
                messagebox.showwarning("Warning", "Enter a vector key")
                return
            
            if messagebox.askyesno("Confirm", f"Delete vector '{key}'?"):
                success, message = self.manager.delete_vector(key)
                
                self.clear_output()
                if success:
                    self.display_message(f"[✓] {message}\n")
                else:
                    self.display_message(f"[✗] {message}\n")
                
                dialog.destroy()
        
        tk.Button(dialog, text="Delete", command=delete, bg="#d32f2f", 
                 fg="white", font=self.button_font).pack(pady=10)
    
    def clear_all_vectors(self):
        """Clear all vectors with confirmation"""
        if not self.manager:
            messagebox.showerror("Error", "Not connected to Redis")
            return
        
        if messagebox.askyesno("Confirm", "Delete ALL vectors from Redis? This cannot be undone!"):
            success, message = self.manager.clear_all_vectors()
            
            self.clear_output()
            if success:
                self.display_message(f"[✓] {message}\n")
            else:
                self.display_message(f"[✗] {message}\n")
    
    def exit_app(self):
        """Exit the application"""
        if messagebox.askyesno("Exit", "Are you sure you want to exit?"):
            self.root.destroy()

def run_gui():
    """Launch the GUI version"""
    root = tk.Tk()
    app = VectorQueryGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.exit_app)
    root.mainloop()

if __name__ == "__main__":
    run_gui()

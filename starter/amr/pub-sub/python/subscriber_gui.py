import tkinter as tk
from tkinter import scrolledtext, simpledialog, messagebox
from subscriber import PubSubManager

class SubscriberGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Redis Pub/Sub - Message Subscriber")
        self.root.geometry("900x600")
        
        # Initialize pub/sub manager
        self.manager = PubSubManager()
        
        # Create UI
        self.create_widgets()
        
        # Start message polling
        self.poll_messages()
    
    def create_widgets(self):
        """Create the GUI layout"""
        # Left frame - Menu
        left_frame = tk.Frame(self.root, width=250, bg="#f0f0f0")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, padx=5, pady=5)
        left_frame.pack_propagate(False)
        
        # Title
        title_label = tk.Label(left_frame, text="Subscription Options", 
                               font=("Arial", 14, "bold"), bg="#f0f0f0")
        title_label.pack(pady=15)
        
        # Menu buttons
        btn_style = {"font": ("Arial", 10), "width": 25, "pady": 8, "bg": "#4a4a4a", "fg": "white"}
        
        tk.Button(left_frame, text="1. Subscribe to Channel", 
                 command=self.subscribe_channel, **btn_style).pack(pady=5)
        tk.Button(left_frame, text="2. Subscribe with Pattern", 
                 command=self.subscribe_pattern, **btn_style).pack(pady=5)
        tk.Button(left_frame, text="3. Unsubscribe from Channel", 
                 command=self.unsubscribe_channel, **btn_style).pack(pady=5)
        tk.Button(left_frame, text="4. Unsubscribe All", 
                 command=self.unsubscribe_all, **btn_style).pack(pady=5)
        tk.Button(left_frame, text="5. View Active Subscriptions", 
                 command=self.view_subs, **btn_style).pack(pady=5)
        
        # Status label
        self.status_label = tk.Label(left_frame, text="Listener: ACTIVE", 
                                     font=("Arial", 10), bg="#f0f0f0", fg="green")
        self.status_label.pack(pady=20)
        
        # Exit button at bottom
        tk.Button(left_frame, text="6. Exit", command=self.exit_app, 
                 **btn_style).pack(side=tk.BOTTOM, pady=10)
        
        # Right frame - Messages
        right_frame = tk.Frame(self.root)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Message area label
        msg_label = tk.Label(right_frame, text="Received Messages", 
                            font=("Arial", 14, "bold"))
        msg_label.pack(pady=5)
        
        # Scrolled text widget for messages
        self.message_box = scrolledtext.ScrolledText(
            right_frame, 
            wrap=tk.WORD, 
            width=60, 
            height=30,
            font=("Consolas", 9),
            bg="#1e1e1e",
            fg="#d4d4d4"
        )
        self.message_box.pack(fill=tk.BOTH, expand=True)
        
        # Clear messages button
        tk.Button(right_frame, text="Clear Messages", 
                 command=self.clear_messages, bg="#4a4a4a", fg="white").pack(pady=5)
        
        # Initial message
        self.display_message("[+] Connected to Redis\n[i] Use the menu to subscribe to channels\n")
    
    def display_message(self, msg):
        """Display message in the text box"""
        self.message_box.insert(tk.END, msg + "\n")
        self.message_box.see(tk.END)
    
    def poll_messages(self):
        """Poll for messages from the queue"""
        msg = self.manager.get_message(timeout=0.01)
        if msg:
            self.display_message(msg)
        
        self.root.after(100, self.poll_messages)
    
    def subscribe_channel(self):
        """Subscribe to a specific channel"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Subscribe to Channel")
        dialog.geometry("400x250")
        
        tk.Label(dialog, text="Available channels:", font=("Arial", 10, "bold")).pack(pady=10)
        channels_text = "  - orders:created\n  - orders:shipped\n  - inventory:alerts\n  - notifications"
        tk.Label(dialog, text=channels_text, justify=tk.LEFT).pack()
        
        tk.Label(dialog, text="Enter channel name:", font=("Arial", 10)).pack(pady=10)
        entry = tk.Entry(dialog, width=30)
        entry.pack()
        entry.focus()
        
        def do_subscribe():
            channel = entry.get().strip()
            if channel:
                result = self.manager.subscribe_to_channel(channel)
                self.display_message(result)
                dialog.destroy()
            else:
                messagebox.showwarning("Warning", "Channel name cannot be empty")
        
        tk.Button(dialog, text="Subscribe", command=do_subscribe).pack(pady=10)
        entry.bind('<Return>', lambda e: do_subscribe())
    
    def subscribe_pattern(self):
        """Subscribe using a pattern"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Subscribe with Pattern")
        dialog.geometry("400x250")
        
        tk.Label(dialog, text="Pattern examples:", font=("Arial", 10, "bold")).pack(pady=10)
        patterns_text = "  - orders:*       (matches orders:created, orders:shipped, etc.)\n  - inventory:*    (matches all inventory channels)\n  - *              (matches all channels)"
        tk.Label(dialog, text=patterns_text, justify=tk.LEFT).pack()
        
        tk.Label(dialog, text="Enter pattern:", font=("Arial", 10)).pack(pady=10)
        entry = tk.Entry(dialog, width=30)
        entry.pack()
        entry.focus()
        
        def do_subscribe():
            pattern = entry.get().strip()
            if pattern:
                result = self.manager.subscribe_to_pattern(pattern)
                self.display_message(result)
                dialog.destroy()
            else:
                messagebox.showwarning("Warning", "Pattern cannot be empty")
        
        tk.Button(dialog, text="Subscribe", command=do_subscribe).pack(pady=10)
        entry.bind('<Return>', lambda e: do_subscribe())
    
    def unsubscribe_channel(self):
        """Unsubscribe from a channel"""
        channel = simpledialog.askstring("Unsubscribe", "Enter channel name to unsubscribe:")
        if channel:
            result = self.manager.unsubscribe_from_channel(channel)
            self.display_message(result)
    
    def unsubscribe_all(self):
        """Unsubscribe from all channels and patterns"""
        result = self.manager.unsubscribe_all()
        self.display_message(result)
    
    def view_subs(self):
        """View active subscriptions"""
        subs = self.manager.get_subscriptions()
        
        msg = "\n=== Active Subscriptions ===\n"
        
        if subs['channels']:
            msg += "\nSubscribed channels:\n"
            for channel in subs['channels']:
                ch_name = channel.decode() if isinstance(channel, bytes) else channel
                msg += f"  - {ch_name}\n"
        else:
            msg += "\nNo channel subscriptions\n"
        
        if subs['patterns']:
            msg += "\nSubscribed patterns:\n"
            for pattern in subs['patterns']:
                pat_name = pattern.decode() if isinstance(pattern, bytes) else pattern
                msg += f"  - {pat_name}\n"
        else:
            msg += "\nNo pattern subscriptions\n"
        
        msg += f"\nListener status: {'Active' if subs['listening'] else 'Stopped'}\n"
        msg += "=" * 30 + "\n"
        
        self.display_message(msg)
    
    def clear_messages(self):
        """Clear the message display"""
        self.message_box.delete(1.0, tk.END)
    
    def exit_app(self):
        """Exit the application"""
        self.manager.close()
        self.root.destroy()

def run_gui():
    """Launch the GUI version of the subscriber"""
    root = tk.Tk()
    app = SubscriberGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.exit_app)
    root.mainloop()

if __name__ == "__main__":
    run_gui()

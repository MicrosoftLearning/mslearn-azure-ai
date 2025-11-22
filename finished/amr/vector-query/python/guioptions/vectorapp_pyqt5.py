import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
                             QFrame, QLabel, QPushButton, QTextEdit, QDialog, QLineEdit,
                             QMessageBox, QScrollArea, QSpinBox)
from PyQt5.QtGui import QFont, QColor, QTextCursor
from PyQt5.QtCore import Qt
from manage_vector import VectorManager

class VectorQueryGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Redis Vector Storage & Search")
        self.setGeometry(100, 100, 770, 800)
        
        # Initialize fonts
        self.default_font = QFont()
        self.default_font.setPointSize(11)
        
        self.default_bold = QFont()
        self.default_bold.setPointSize(14)
        self.default_bold.setBold(True)
        
        self.button_font = QFont()
        self.button_font.setPointSize(10)
        
        self.italic_font = QFont()
        self.italic_font.setPointSize(10)
        self.italic_font.setItalic(True)
        
        self.fixed_font = QFont("Monospace")
        self.fixed_font.setPointSize(10)
        
        # Initialize vector manager
        try:
            self.manager = VectorManager()
            self.connection_status = "Connected"
        except Exception as e:
            self.connection_status = f"Error: {e}"
            self.manager = None
        
        self.create_widgets()
    
    def create_widgets(self):
        """Create the GUI layout"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout()
        central_widget.setLayout(main_layout)
        
        # Left frame - Menu
        left_frame = QFrame()
        left_frame.setStyleSheet("background-color: #f0f0f0; border: 1px solid #ccc;")
        left_frame.setMaximumWidth(320)
        left_layout = QVBoxLayout()
        left_frame.setLayout(left_layout)
        
        # Title
        title_label = QLabel("Vector Operations")
        title_label.setFont(self.default_bold)
        title_label.setStyleSheet("color: black;")
        left_layout.addWidget(title_label)
        
        # Menu buttons
        buttons = [
            ("1. Load Sample Vectors", self.load_samples),
            ("2. Store New Vector", self.store_new_vector),
            ("3. Retrieve Vector", self.retrieve_vector),
            ("4. Search Similar Vectors", self.search_vectors),
            ("5. List All Vectors", self.list_vectors),
            ("6. Delete Vector", self.delete_vector),
            ("7. Clear All Vectors", self.clear_all_vectors),
        ]
        
        for text, callback in buttons:
            btn = QPushButton(text)
            btn.setFont(self.button_font)
            btn.setMinimumHeight(40)
            btn.setStyleSheet("background-color: #4a4a4a; color: white; border-radius: 4px;")
            btn.clicked.connect(callback)
            left_layout.addWidget(btn)
        
        # Status label
        self.status_label = QLabel(f"Status: {self.connection_status}")
        self.status_label.setFont(self.default_font)
        if self.connection_status == "Connected":
            self.status_label.setStyleSheet("color: green;")
        else:
            self.status_label.setStyleSheet("color: red;")
        left_layout.addSpacing(20)
        left_layout.addWidget(self.status_label)
        
        # Exit button at bottom
        exit_btn = QPushButton("8. Exit")
        exit_btn.setFont(self.button_font)
        exit_btn.setMinimumHeight(40)
        exit_btn.setStyleSheet("background-color: #4a4a4a; color: white; border-radius: 4px;")
        exit_btn.clicked.connect(self.exit_app)
        left_layout.addStretch()
        left_layout.addWidget(exit_btn)
        
        # Right frame - Output
        right_frame = QFrame()
        right_layout = QVBoxLayout()
        right_frame.setLayout(right_layout)
        
        # Output area label
        output_label = QLabel("Operation Results")
        output_label.setFont(self.default_bold)
        right_layout.addWidget(output_label)
        
        # Scrolled text widget for output
        self.output_box = QTextEdit()
        self.output_box.setReadOnly(False)
        self.output_box.setFont(self.fixed_font)
        self.output_box.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4; border: 1px solid #ccc;")
        right_layout.addWidget(self.output_box)
        
        # Clear output button
        clear_btn = QPushButton("Clear Output")
        clear_btn.setFont(self.button_font)
        clear_btn.setMinimumHeight(35)
        clear_btn.setStyleSheet("background-color: #4a4a4a; color: white; border-radius: 4px;")
        clear_btn.clicked.connect(self.clear_output)
        right_layout.addWidget(clear_btn)
        
        main_layout.addWidget(left_frame)
        main_layout.addWidget(right_frame)
        
        # Initial message
        self.display_message("[+] Connected to Redis Vector Storage\n[i] Select an operation from the menu\n")
    
    def display_message(self, msg):
        """Add a message to the output box"""
        self.output_box.insertPlainText(msg)
        self.output_box.moveCursor(QTextCursor.End)
    
    def clear_output(self):
        """Clear the output box"""
        self.output_box.clear()
    
    def load_samples(self):
        """Load sample vectors"""
        if not self.manager:
            QMessageBox.critical(self, "Error", "Not connected to Redis")
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
            QMessageBox.critical(self, "Error", "Not connected to Redis")
            return
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Store New Vector")
        dialog.setGeometry(200, 200, 600, 390)
        
        layout = QVBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(15, 15, 15, 15)
        
        # Vector key input
        key_label = QLabel("Vector Key:")
        key_label.setFont(QFont(self.default_font))
        key_label.font().setPointSize(self.default_font.pointSize() + 4)
        key_label.font().setBold(True)
        layout.addWidget(key_label)
        layout.addSpacing(3)
        key_entry = QLineEdit()
        key_entry.setText("vector:product_")
        key_entry.setFont(self.default_font)
        layout.addWidget(key_entry)
        layout.addSpacing(20)
        
        # Vector input
        vector_label = QLabel("Vector (comma-separated):")
        vector_label.setFont(QFont(self.default_font))
        vector_label.font().setPointSize(self.default_font.pointSize() + 4)
        vector_label.font().setBold(True)
        layout.addWidget(vector_label)
        layout.addSpacing(3)
        example_label = QLabel("Example: 0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8")
        example_label.setFont(self.italic_font)
        layout.addWidget(example_label)
        
        vector_text = QTextEdit()
        vector_text.setFont(self.fixed_font)
        vector_text.setMaximumHeight(50)
        layout.addWidget(vector_text)
        layout.addSpacing(20)
        
        # Metadata section
        metadata_label = QLabel("Metadata (key=value pairs, one per line):")
        metadata_label.setFont(QFont(self.default_font))
        metadata_label.font().setPointSize(self.default_font.pointSize() + 4)
        metadata_label.font().setBold(True)
        layout.addWidget(metadata_label)
        layout.addSpacing(3)
        metadata_text = QTextEdit()
        metadata_text.setFont(self.fixed_font)
        metadata_text.setText("product_id=001\nname=Product Name\ncategory=Electronics")
        metadata_text.setMaximumHeight(60)
        layout.addWidget(metadata_text)
        
        def store():
            try:
                key = key_entry.text().strip()
                vector_str = vector_text.toPlainText().strip()
                
                if not key or not vector_str:
                    QMessageBox.warning(self, "Warning", "Key and vector cannot be empty")
                    return
                
                vector = [float(x.strip()) for x in vector_str.split(",")]
                
                # Parse metadata
                metadata = {}
                meta_lines = metadata_text.toPlainText().strip().split("\n")
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
                
                dialog.close()
            except ValueError as e:
                QMessageBox.critical(self, "Error", f"Invalid vector format: {e}")
        
        layout.addSpacing(20)
        layout.addStretch()
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(5)
        store_btn = QPushButton("Store Vector")
        store_btn.setFont(self.button_font)
        store_btn.setMinimumHeight(35)
        store_btn.setStyleSheet("background-color: #4a4a4a; color: white; border-radius: 4px;")
        store_btn.clicked.connect(store)
        btn_layout.addWidget(store_btn)
        
        layout.addLayout(btn_layout)
        dialog.setLayout(layout)
        dialog.exec_()
    
    def retrieve_vector(self):
        """Retrieve a vector by key"""
        if not self.manager:
            QMessageBox.critical(self, "Error", "Not connected to Redis")
            return
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Retrieve Vector")
        dialog.setGeometry(200, 200, 400, 150)
        
        layout = QVBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(15, 15, 15, 15)
        
        key_label = QLabel("Vector Key:")
        key_label.setFont(QFont(self.default_font))
        key_label.font().setPointSize(self.default_font.pointSize() + 4)
        key_label.font().setBold(True)
        layout.addWidget(key_label)
        layout.addSpacing(3)
        entry = QLineEdit()
        entry.setFont(self.default_font)
        layout.addWidget(entry)
        
        def retrieve():
            key = entry.text().strip()
            if not key:
                QMessageBox.warning(self, "Warning", "Enter a vector key")
                return
            
            success, result = self.manager.retrieve_vector(key)
            
            self.clear_output()
            if success:
                self.display_message(f"[✓] Retrieved vector: {key}\n\n")
                self.display_message(f"Dimensions: {len(result['vector'])}\n")
                self.display_message(f"Vector: {result['vector']}\n")
                
                if result['metadata']:
                    self.display_message("\nMetadata:\n")
                    for k, v in result['metadata'].items():
                        self.display_message(f"  {k}: {v}\n")
            else:
                self.display_message(f"[✗] {result}\n")
            
            dialog.close()
        
        layout.addSpacing(20)
        layout.addStretch()
        retrieve_btn = QPushButton("Retrieve")
        retrieve_btn.setFont(self.button_font)
        retrieve_btn.setMinimumHeight(35)
        retrieve_btn.setStyleSheet("background-color: #4a4a4a; color: white; border-radius: 4px;")
        retrieve_btn.clicked.connect(retrieve)
        layout.addWidget(retrieve_btn)
        
        dialog.setLayout(layout)
        dialog.exec_()
    
    def search_vectors(self):
        """Search for similar vectors"""
        if not self.manager:
            QMessageBox.critical(self, "Error", "Not connected to Redis")
            return
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Search Similar Vectors")
        dialog.setGeometry(200, 200, 600, 330)
        
        layout = QVBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(15, 15, 15, 15)
        
        query_label = QLabel("Query Vector (comma-separated):")
        query_label.setFont(QFont(self.default_font))
        query_label.font().setPointSize(self.default_font.pointSize() + 4)
        query_label.font().setBold(True)
        layout.addWidget(query_label)
        layout.addSpacing(3)
        example_label = QLabel("Example: 0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8")
        example_label.setFont(self.italic_font)
        layout.addWidget(example_label)
        
        vector_text = QTextEdit()
        vector_text.setFont(self.fixed_font)
        vector_text.setMaximumHeight(50)
        layout.addWidget(vector_text)
        layout.addSpacing(20)
        
        count_label = QLabel("Number of results (1-10):")
        count_label.setFont(QFont(self.default_font))
        count_label.font().setPointSize(self.default_font.pointSize() + 4)
        count_label.font().setBold(True)
        layout.addWidget(count_label)
        layout.addSpacing(3)
        default_label = QLabel("Default: 3")
        default_label.setFont(self.italic_font)
        layout.addWidget(default_label)
        
        count_entry = QSpinBox()
        count_entry.setValue(3)
        count_entry.setMinimum(1)
        count_entry.setMaximum(10)
        count_entry.setFont(self.default_font)
        layout.addWidget(count_entry)
        
        def search():
            try:
                vector_str = vector_text.toPlainText().strip()
                if not vector_str:
                    QMessageBox.warning(self, "Warning", "Enter a query vector")
                    return
                
                query_vector = [float(x.strip()) for x in vector_str.split(",")]
                top_k = count_entry.value()
                
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
                
                dialog.close()
            except ValueError as e:
                QMessageBox.critical(self, "Error", f"Invalid input: {e}")
        
        layout.addSpacing(20)
        layout.addStretch()
        search_btn = QPushButton("Search")
        search_btn.setFont(self.button_font)
        search_btn.setMinimumHeight(35)
        search_btn.setStyleSheet("background-color: #4a4a4a; color: white; border-radius: 4px;")
        search_btn.clicked.connect(search)
        layout.addWidget(search_btn)
        
        dialog.setLayout(layout)
        dialog.exec_()
    
    def list_vectors(self):
        """List all vectors"""
        if not self.manager:
            QMessageBox.critical(self, "Error", "Not connected to Redis")
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
            QMessageBox.critical(self, "Error", "Not connected to Redis")
            return
        
        dialog = QDialog(self)
        dialog.setWindowTitle("Delete Vector")
        dialog.setGeometry(200, 200, 400, 150)
        
        layout = QVBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(15, 15, 15, 15)
        
        key_label = QLabel("Vector Key:")
        key_label.setFont(QFont(self.default_font))
        key_label.font().setPointSize(self.default_font.pointSize() + 4)
        key_label.font().setBold(True)
        layout.addWidget(key_label)
        layout.addSpacing(3)
        entry = QLineEdit()
        entry.setFont(self.default_font)
        layout.addWidget(entry)
        
        def delete():
            key = entry.text().strip()
            if not key:
                QMessageBox.warning(self, "Warning", "Enter a vector key")
                return
            
            if QMessageBox.question(self, "Confirm", f"Delete vector '{key}'?", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                success, message = self.manager.delete_vector(key)
                
                self.clear_output()
                if success:
                    self.display_message(f"[✓] {message}\n")
                else:
                    self.display_message(f"[✗] {message}\n")
                
                dialog.close()
        
        layout.addSpacing(20)
        layout.addStretch()
        delete_btn = QPushButton("Delete")
        delete_btn.setFont(self.button_font)
        delete_btn.setMinimumHeight(35)
        delete_btn.setStyleSheet("background-color: #d32f2f; color: white; border-radius: 4px;")
        delete_btn.clicked.connect(delete)
        layout.addWidget(delete_btn)
        
        dialog.setLayout(layout)
        dialog.exec_()
    
    def clear_all_vectors(self):
        """Clear all vectors with confirmation"""
        if not self.manager:
            QMessageBox.critical(self, "Error", "Not connected to Redis")
            return
        
        if QMessageBox.question(self, "Confirm", "Delete ALL vectors from Redis? This cannot be undone!", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            success, message = self.manager.clear_all_vectors()
            
            self.clear_output()
            if success:
                self.display_message(f"[✓] {message}\n")
            else:
                self.display_message(f"[✗] {message}\n")
    
    def exit_app(self):
        """Exit the application"""
        if QMessageBox.question(self, "Exit", "Are you sure you want to exit?", QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
            self.close()

def run_gui():
    """Launch the GUI version"""
    app = QApplication(sys.argv)
    window = VectorQueryGUI()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    run_gui()

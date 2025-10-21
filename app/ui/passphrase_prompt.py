from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QDialogButtonBox

def ask_passphrase(error: str | None = None) -> str | None:
    dlg = QDialog()
    dlg.setWindowTitle("Security Setup")
    layout = QVBoxLayout(dlg)
    if error:
        layout.addWidget(QLabel(f"<b>{error}</b>"))
    layout.addWidget(QLabel("Enter the setup passphrase provided to you:"))
    edit = QLineEdit()
    edit.setEchoMode(QLineEdit.Password)
    layout.addWidget(edit)
    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    layout.addWidget(buttons)
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    if dlg.exec():
        return edit.text().strip() or None
    return None

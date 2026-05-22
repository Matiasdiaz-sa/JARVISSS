try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    print("Success: QWebEngineView imported successfully.")
except Exception as e:
    import traceback
    print("Error importing QWebEngineView:")
    traceback.print_exc()

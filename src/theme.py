"""LX: three neutral roles, leaf-green accents and luminous gold interaction."""
STYLE = '''
QWidget { background:#ffffff; color:#202020; font:14px "Microsoft YaHei"; }
QWidget#sidebar { background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(134,184,61,24),stop:1 rgba(134,184,61,5)); border-right:1px solid rgba(119,119,119,45); }
QFrame#hero { background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(134,184,61,45),stop:1 rgba(134,184,61,10)); border:1px solid rgba(134,184,61,65); border-left:4px solid #86b83d; border-radius:16px; }
QFrame#card { background:#ffffff; border:1px solid rgba(119,119,119,55); border-radius:12px; }
QLabel { background:transparent; border:0; }
QLabel#title { font-size:29px; font-weight:700; }
QLabel#subtitle { color:#777777; }
QLabel#badge { color:#507522; font-size:12px; }
QPushButton { background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(134,184,61,23),stop:1 rgba(134,184,61,7)); border:1px solid rgba(134,184,61,95); border-radius:7px; padding:9px 14px; }
QPushButton:hover { background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(134,184,61,48),stop:1 rgba(134,184,61,14)); border-color:#e6dcc4; }
QPushButton:disabled { color:#777777; background:#ffffff; border-color:rgba(119,119,119,45); }
QPushButton#primary { background:#507522; color:#ffffff; border:0; font-weight:600; }
QPushButton#primary:hover { background:#86b83d; color:#202020; }
QPushButton#primary:disabled { background:rgba(119,119,119,16); color:#777777; }
QPushButton#nav { text-align:left; padding:14px; border:0; background:transparent; }
QPushButton#nav:checked { background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #86b83d,stop:1 #a0c85b); color:#202020; font-weight:600; }
QPushButton#danger { color:#202020; }
QLineEdit,QComboBox { padding:9px; border:1px solid rgba(119,119,119,65); border-radius:7px; background:#ffffff; }
QListWidget,QTreeWidget { background:#ffffff; border:1px solid rgba(119,119,119,45); border-radius:8px; outline:0; }
QListWidget::item,QTreeWidget::item { padding:12px; }
QListWidget::item:selected,QTreeWidget::item:selected { background:#86b83d; color:#202020; }
QHeaderView::section { background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 rgba(134,184,61,30),stop:1 rgba(134,184,61,8)); color:#202020; border:0; padding:10px; }
QScrollArea { border:0; }
QTextBrowser { background:#ffffff; border:1px solid rgba(119,119,119,45); border-radius:8px; padding:14px; selection-background-color:#86b83d; selection-color:#202020; }
QToolTip { background:#ffffff; color:#202020; border:1px solid #e6dcc4; padding:6px; }
QLineEdit:focus,QComboBox:focus { border:1px solid #86b83d; }
QPushButton#brandIcon { background:#ffffff; border:1px solid rgba(119,119,119,45); padding:0; }
QTabWidget::pane { border:1px solid rgba(119,119,119,45); border-radius:8px; }
QTabBar::tab { padding:12px 22px; background:transparent; color:#777777; }
QTabBar::tab:selected { color:#202020; background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(134,184,61,65),stop:1 rgba(134,184,61,18)); }
QProgressBar { max-height:6px; border:0; background:rgba(119,119,119,25); }
QProgressBar::chunk { background:#86b83d; }
QScrollBar:vertical { width:16px; background:rgba(134,184,61,16); margin:0; }
QScrollBar::handle:vertical { background:#86b83d; border-radius:7px; min-height:48px; margin:2px; }
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height:0; }
QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical { background:transparent; }
QScrollBar::handle:vertical:hover { background:#507522; }
'''

"""Copy into your own LX tool and redesign freely; no shelf internals imported."""
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTabWidget, QLineEdit, QTableWidget, QTableWidgetItem)
from .strings import TITLE


def create_panel(context, parent):
    return Panel(context, parent)


class Panel(QWidget):
    def __init__(self, context, parent):
        super().__init__(parent)
        self.context = context
        self.setObjectName('toolOwnedPanel')
        self.setStyleSheet('QWidget#toolOwnedPanel {background:#f5f8ff;} '
                          'QWidget#toolOwnedPanel QPushButton {background:#263d77;color:white;padding:12px;border-radius:8px;}')
        layout = QVBoxLayout(self)
        title = QLabel(TITLE);title.setStyleSheet('font-size:26px;font-weight:700;color:#263d77;')
        layout.addWidget(title)
        layout.addWidget(QLabel('布局、配色、输入、表格和页签全部来自工具包。'))
        tabs = QTabWidget();layout.addWidget(tabs,1)
        page = QWidget();body = QVBoxLayout(page);tabs.addTab(page,'交互演示')
        self.name = QLineEdit(context.load_settings().get('name','我的工作区'))
        body.addWidget(self.name)
        row=QHBoxLayout();body.addLayout(row)
        save=QPushButton('保存名称');save.clicked.connect(self.save);row.addWidget(save)
        add=QPushButton('增加一行');add.clicked.connect(self.add_row);row.addWidget(add)
        self.table=QTableWidget(0,2);self.table.setHorizontalHeaderLabels(['序号','工具自定义数据'])
        self.table.horizontalHeader().setStretchLastSection(True);body.addWidget(self.table,1)
        about=QLabel('这是工具自己的第二个页签，不是工具架的概览或版本管理。')
        tabs.addTab(about,'自定义页面')
        self.status=QLabel('准备就绪');layout.addWidget(self.status)
        self.timer=QTimer(self);self.timer.setInterval(1000)
        self.timer.timeout.connect(lambda: self.setProperty('alive',True));self.timer.start()

    def add_row(self):
        row=self.table.rowCount();self.table.insertRow(row)
        self.table.setItem(row,0,QTableWidgetItem(str(row+1)))
        self.table.setItem(row,1,QTableWidgetItem(self.name.text()))
        self.status.setText('已添加 '+str(row+1)+' 行')

    def save(self):
        self.context.save_settings({'name':self.name.text()})
        self.status.setText('名称已保存，重新打开仍会保留')

    def shutdown(self):
        self.timer.stop()

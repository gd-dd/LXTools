"""Subtle rotating gold edges; no flashing fill or input interception."""
from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QColor, QConicalGradient, QPainter, QPen
from PySide6.QtWidgets import QPushButton, QTabBar


def paint_gold(widget, rectangles, angle):
    painter = QPainter(widget)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(Qt.NoBrush)
    for rect in rectangles:
        rect = QRectF(rect).adjusted(2, 2, -2, -2)
        gradient = QConicalGradient(rect.center(), angle)
        # White light with a champagne tint and short pastel spectral glints.
        for position, color in [(0,'#f5edda'),(.16,'#fffdf5'),(.30,'#fff5df'),
                                (.36,'#ffe0eb'),(.39,'#e5dcff'),(.42,'#daf3ff'),
                                (.45,'#e2f8e7'),(.48,'#fffdf5'),(.64,'#fff5df'),
                                (.80,'#ffffff'),(.86,'#fff0df'),(1,'#f5edda')]:
            gradient.setColorAt(position,QColor(color))
        glow=QColor('#fff5df');glow.setAlpha(120)
        painter.setPen(QPen(glow,6));painter.drawRoundedRect(rect,6,6)
        contour=QColor('#c8bd9e');contour.setAlpha(100)
        painter.setPen(QPen(contour,3.8));painter.drawRoundedRect(rect,6,6)
        painter.setPen(QPen(QColor('#fffaf0'),2.8));painter.drawRoundedRect(rect,6,6)
        painter.setPen(QPen(gradient,2.0));painter.drawRoundedRect(rect,6,6)
    painter.end()


class GoldButton(QPushButton):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.angle=0.;self.hovered=False
        self.timer=QTimer(self);self.timer.setInterval(40);self.timer.timeout.connect(self.advance)
        self.toggled.connect(self.sync_animation)

    def sync_animation(self,*_):
        active=self.isVisible() and self.isEnabled() and (self.hovered or self.isChecked() or self.hasFocus())
        if active and not self.timer.isActive():self.timer.start()
        elif not active:self.timer.stop()
        self.update()

    def advance(self):
        self.angle=(self.angle+.9)%360;self.sync_animation()

    def enterEvent(self,event):
        super().enterEvent(event);self.hovered=True;self.sync_animation()

    def leaveEvent(self,event):
        super().leaveEvent(event);self.hovered=False;self.sync_animation()

    def showEvent(self,event):
        super().showEvent(event);self.sync_animation()

    def hideEvent(self,event):
        self.hovered=False;self.timer.stop();super().hideEvent(event)

    def focusInEvent(self,event):
        super().focusInEvent(event);self.sync_animation()

    def focusOutEvent(self,event):
        super().focusOutEvent(event);self.sync_animation()

    def paintEvent(self,event):
        super().paintEvent(event)
        if self.isEnabled() and (self.hovered or self.isChecked() or self.hasFocus()):
            paint_gold(self,[self.rect()],self.angle)


class GoldTabBar(QTabBar):
    def __init__(self,parent=None):
        super().__init__(parent);self.angle=0.;self.hovered=-1;self.setMouseTracking(True)
        self.timer=QTimer(self);self.timer.setInterval(40);self.timer.timeout.connect(self.advance)

    def advance(self):self.angle=(self.angle+.9)%360;self.update()

    def showEvent(self,event):super().showEvent(event);self.timer.start()

    def hideEvent(self,event):self.timer.stop();super().hideEvent(event)

    def mouseMoveEvent(self,event):
        self.hovered=self.tabAt(event.position().toPoint());self.update();super().mouseMoveEvent(event)

    def leaveEvent(self,event):self.hovered=-1;self.update();super().leaveEvent(event)

    def paintEvent(self,event):
        super().paintEvent(event)
        indices={self.currentIndex(),self.hovered}
        paint_gold(self,[self.tabRect(i) for i in indices if i>=0 and self.isTabEnabled(i)],self.angle)

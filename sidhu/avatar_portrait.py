"""Original animated Punjabi portrait for software and low power renderers.

The primary artwork is an original generated rendered portrait, animated by
this widget; original vector paths remain available if that asset is missing.
It contains no supplied celebrity likeness or licensed character. Neither
painted fallback is presented as the independently articulated 3D scene.
"""
import math
import time
from pathlib import Path
from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget


# SAPI's 22 mouth positions: aperture, width, roundness. Real speech callbacks
# select these shapes; no made-up phoneme timeline is inferred from plain text.
MOUTH_SHAPES = (
    (0.00,1.00,0.00),(0.60,1.04,0.10),(0.82,0.90,0.30),
    (0.62,0.78,0.60),(0.44,1.10,0.00),(0.52,1.10,0.00),
    (0.26,1.20,0.00),(0.34,0.70,0.85),(0.60,0.72,0.95),
    (0.60,1.02,0.20),(0.62,0.76,0.70),(0.66,1.10,0.10),
    (0.20,0.95,0.00),(0.23,1.04,0.00),(0.24,1.08,0.00),
    (0.22,0.94,0.10),(0.38,0.85,0.40),(0.36,0.95,0.10),
    (0.18,1.04,0.00),(0.27,1.00,0.00),(0.18,0.96,0.00),
    (0.00,0.90,0.00),
)


def _path(commands):
    path = QPainterPath()
    for kind, *points in commands:
        if kind == 'M': path.moveTo(*points)
        elif kind == 'L': path.lineTo(*points)
        elif kind == 'C': path.cubicTo(*points)
        elif kind == 'Q': path.quadTo(*points)
        elif kind == 'Z': path.closeSubpath()
    return path


def _gradient(x1, y1, x2, y2, *stops):
    gradient = QLinearGradient(x1, y1, x2, y2)
    for stop, color in stops:
        gradient.setColorAt(stop, QColor(color))
    return gradient


class TributePortrait(QWidget):
    """An original painter-rendered character, capped at 30 updates/second."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.activity = 'idle'
        self._phase = 0.0
        self._lightweight = False
        self._mouth = MOUTH_SHAPES[0]
        self._mouth_until = 0.0
        self._last_viseme = 0.0
        self._speech_serial = 0
        self._portrait = QImage(str(Path(__file__).parent / 'assets' / 'tribute-portrait.png'))
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(220, 300)
        self.timer = QTimer(self)
        self.timer.setInterval(34)
        self.timer.timeout.connect(self._tick)

    def set_performance(self, lightweight):
        self._lightweight = bool(lightweight)
        self.timer.setInterval(100 if lightweight else 34)
        self._update_timer()
        self.update()

    def _update_timer(self):
        if self.isVisible() and (not self._lightweight or self._mouth_until > time.monotonic()):
            self.timer.start()
        else:
            self.timer.stop()

    def _tick(self):
        if not self.isVisible():
            self.timer.stop()
            return
        if not self._lightweight:
            self._phase += self.timer.interval() / 1000
        if time.monotonic() > self._mouth_until:
            self._mouth = MOUTH_SHAPES[0]
            if self._lightweight:
                self.timer.stop()
        self.update()

    def viseme(self, viseme_id, duration_ms=100):
        if self.activity != 'speaking':
            return
        if isinstance(viseme_id, bool) or not isinstance(viseme_id, int) or not 0 <= viseme_id <= 21:
            return
        self._last_viseme = time.monotonic()
        self._mouth = MOUTH_SHAPES[viseme_id]
        self._mouth_until = self._last_viseme + max(20, min(1500, int(duration_ms))) / 1000
        self._speech_serial += 1
        self._update_timer()
        self.update()

    def word(self, location=0, length=0):
        if self.activity != 'speaking' or time.monotonic() - self._last_viseme <= 1.5:
            return
        self._speech_serial += 1
        self._mouth = (0.34 + (self._speech_serial % 3)*.10, 1.0, 0.1)
        self._mouth_until = time.monotonic() + .18
        self._update_timer()
        self.update()

    def showEvent(self, event):
        self._update_timer()
        super().showEvent(event)

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
        if not self._portrait.isNull():
            self._paint_rendered_portrait(p)
            p.end()
            return
        scale = min(self.width()/600, self.height()/760)
        p.translate((self.width()-600*scale)/2, self.height()-760*scale)
        p.scale(scale,scale)
        self._paint_character(p)
        p.end()

    @property
    def artwork_source(self):
        return 'original rendered portrait' if not self._portrait.isNull() else 'original vector portrait'

    def _paint_rendered_portrait(self, p):
        """Animate original rendered artwork; this remains explicitly 2D.

        Breathing and posture are restrained affine motion. Eyelids and SAPI
        mouth shapes are live painted overlays, not claims of a rigged image.
        The articulated GPU model is supplied independently in avatar.qml.
        """
        phase = 0 if self._lightweight else self._phase
        source_w,source_h = self._portrait.width(),self._portrait.height()
        # A slight bottom crop makes the face dominant while keeping the hand.
        scale = min(self.width()/source_w, self.height()*1.38/source_h)
        width,height = source_w*scale,source_h*scale
        left,top = (self.width()-width)/2,-self.height()*.035
        p.save()
        p.translate(left,top)
        p.scale(scale,scale)
        breathing = math.sin(phase*1.3)*2
        tilt = -.6 if self.activity=='listening' else .45 if self.activity in ('thinking','working','processing') else 0
        tilt += math.sin(phase*.5)*.18
        p.translate(source_w*.51,source_h*.7)
        p.rotate(tilt)
        p.translate(-source_w*.51,-source_h*.7+breathing)
        p.drawImage(QRectF(0,0,source_w,source_h),self._portrait)
        blink_age = phase%4.9
        closed = 0 if blink_age<4.67 else 1-max(.02,abs(blink_age-4.785)/.115)
        if closed>.025:
            for x,y,angle in ((.464,.251,-8),(.579,.241,-12)):
                p.save()
                p.translate(source_w*x,source_h*y)
                p.rotate(angle)
                eye_w,eye_h = source_w*.066,source_h*.010
                lid=QPainterPath()
                lid.moveTo(-eye_w/2,0)
                lid.quadTo(0,-eye_h*.6,eye_w/2,0)
                lid.quadTo(0,eye_h*.6,-eye_w/2,0)
                p.setClipPath(lid)
                color=self._portrait.pixelColor(int(source_w*x),int(source_h*y-eye_h*1.7))
                shading=QLinearGradient(0,-eye_h,0,eye_h)
                shading.setColorAt(0,color.lighter(104))
                shading.setColorAt(1,color.darker(115))
                p.setPen(Qt.NoPen)
                p.setBrush(shading)
                p.drawRect(QRectF(-eye_w/2,-eye_h,eye_w,eye_h*(1+closed)))
                p.setPen(QPen(QColor('#6a4436'),1.4))
                p.setBrush(Qt.NoBrush)
                line=QPainterPath()
                line.moveTo(-eye_w/2,0)
                line.quadTo(0,eye_h*.6*closed,eye_w/2,0)
                if closed>.7: p.drawPath(line)
                p.restore()
        if self.activity=='speaking' and time.monotonic()<=self._mouth_until:
            aperture,mouth_width,rounding=self._mouth
            if aperture>.01:
                p.save()
                p.translate(source_w*.535,source_h*.324)
                p.rotate(-7)
                w=source_w*.077*mouth_width
                h=source_h*(.001+aperture*.017)
                opening=QRectF(-w/2,-1,w,h)
                p.setPen(QPen(QColor('#6d382e'),1.4))
                inside=QLinearGradient(0,-1,0,h)
                inside.setColorAt(0,QColor('#1d1116'))
                inside.setColorAt(1,QColor('#542b30'))
                p.setBrush(inside)
                p.drawRoundedRect(opening,w*(.3+rounding*.15),h*.48)
                clip=QPainterPath()
                clip.addRoundedRect(opening,w*.35,h*.45)
                p.setClipPath(clip)
                p.setPen(Qt.NoPen)
                if aperture>.25:
                    p.setBrush(QColor('#c4b49d'))
                    p.drawRoundedRect(QRectF(-w/2+3,0,w-6,h*.22),3,3)
                    p.setBrush(QColor('#a35b61'))
                    p.drawEllipse(QRectF(-w*.3,h*.8,w*.6,h*.4))
                p.restore()
        p.restore()

    def _shape(self, p, commands, fill, stroke=None, width=1):
        p.setPen(Qt.NoPen if stroke is None else QPen(QColor(stroke),width))
        p.setBrush(fill if not isinstance(fill,str) else QColor(fill))
        p.drawPath(_path(commands))

    def _paint_character(self, p):
        phase = 0 if self._lightweight else self._phase
        glow = QRadialGradient(311,326,290)
        for at, color in ((0,QColor(0,130,250,34)),(.65,QColor(0,130,250,13)),(1,QColor(0,130,250,0))):
            glow.setColorAt(at,color)
        p.setPen(Qt.NoPen)
        p.setBrush(glow)
        p.drawEllipse(QRectF(20,30,580,620))
        self._shape(p,[('M',143,705),('L',150,360),('C',150,276,178,233,227,232),
            ('L',385,233),('C',443,240,461,288,462,358),('L',493,710),('Z',)],
            _gradient(150,250,440,710,(0,'#1c2735'),(.4,'#080f19'),(1,'#080b13')),'#35506a',2)
        self._shape(p,[('M',168,528),('L',174,351),('C',178,284,195,255,229,253),
            ('M',397,258),('C',428,276,441,306,440,374),('L',454,579)],Qt.NoBrush,'#102e48',4)
        p.save()
        p.translate(0,math.sin(phase*1.35)*1.9)
        self._jacket(p)
        self._neck(p)
        self._headphones(p)
        self._head(p,phase)
        self._hands(p,phase)
        p.restore()

    def _jacket(self,p):
        self._shape(p,[('M',257,347),('C',219,346,191,358,164,387),
            ('C',122,438,103,481,87,556),('C',76,614,78,694,93,760),
            ('L',524,760),('C',548,683,521,575,485,475),
            ('C',463,409,419,366,352,349),('Z',)],
            _gradient(128,385,472,694,(0,'#263549'),(.24,'#101a27'),(.54,'#070d15'),(.8,'#1a2534'),(1,'#0b111c')),'#2b3f55',2)
        self._shape(p,[('M',254,351),('C',221,340,184,361,162,391),
            ('C',174,402,194,412,223,412),('L',285,455),('L',301,403),('Z',)],
            _gradient(175,355,291,445,(0,'#344158'),(.44,'#121a28'),(1,'#050a12')),'#34435a',1.5)
        self._shape(p,[('M',347,347),('C',385,350,413,366,436,394),
            ('L',389,422),('L',330,456),('L',314,399),('Z',)],
            _gradient(340,345,417,424,(0,'#1d2c40'),(.6,'#101825'),(1,'#030910')),'#223a54',1.5)
        for commands in [
            [('M',169,421),('Q',142,463,130,507),('M',160,462),('Q',190,439,219,446)],
            [('M',444,440),('Q',464,458,475,505),('M',457,493),('Q',422,489,400,513)],
            [('M',245,555),('Q',217,613,211,681),('M',342,632),('Q',375,657,411,656)],
            [('M',119,672),('Q',153,681,181,671)],
        ]: self._shape(p,commands,Qt.NoBrush,'#2a3548',3)
        self._shape(p,[('M',300,425),('L',305,730)],Qt.NoBrush,'#707b87',3)
        self._shape(p,[('M',304,426),('L',309,730)],Qt.NoBrush,'#101521',2)
        for commands in [[('M',165,395),('Q',139,429,128,479)],
                         [('M',247,470),('L',230,595)],
                         [('M',385,472),('L',408,580)],
                         [('M',312,448),('L',316,634)]]:
            self._shape(p,commands,Qt.NoBrush,'#058abd',4)
            self._shape(p,commands,Qt.NoBrush,'#6bddff',1)
        p.save()
        p.translate(356,517)
        p.rotate(-5)
        p.setPen(QPen(QColor('#285479'),1))
        p.setBrush(QColor('#07111e'))
        p.drawRoundedRect(QRectF(0,0,107,47),5,5)
        p.setPen(QColor('#d8f6ff'))
        p.setFont(QFont('Segoe UI',17,QFont.Bold))
        p.drawText(QRectF(5,4,97,34),Qt.AlignCenter,'SIDHU AI')
        p.restore()

    def _neck(self,p):
        self._shape(p,[('M',271,304),('L',267,354),('Q',266,383,304,400),
            ('Q',343,394,355,360),('L',350,308),('Z',)],
            _gradient(273,321,350,383,(0,'#764a38'),(.45,'#c1885b'),(1,'#7c503b')))
        self._shape(p,[('M',267,355),('Q',296,379,349,355),('L',326,415),('L',294,426),('Z',)],'#0a0d14')

    def _headphones(self,p):
        self._shape(p,[('M',245,352),('C',230,392,259,423,297,426),
            ('C',345,434,381,410,376,363)],Qt.NoBrush,'#050a11',25)
        self._shape(p,[('M',245,352),('C',231,396,260,419,294,420),
            ('M',323,420),('Q',364,414,376,370)],Qt.NoBrush,'#36506a',3)
        for x,angle in ((248,-21),(369,20)):
            p.save()
            p.translate(x,382)
            p.rotate(angle)
            p.setPen(QPen(QColor('#31485f'),2))
            p.setBrush(_gradient(-25,-34,27,35,(0,'#253a51'),(.5,'#070d16'),(1,'#131d2c')))
            p.drawRoundedRect(QRectF(-25,-36,50,72),21,21)
            p.setPen(QPen(QColor('#0098e6'),3))
            p.setBrush(QColor('#07162b'))
            p.drawRoundedRect(QRectF(-17,-28,34,56),15,15)
            p.setPen(QPen(QColor('#81e8ff'),1.5))
            p.drawArc(QRectF(-13,-24,26,48),60*16,240*16)
            self._shape(p,[('M',-9,2),('L',-8,-6),('L',-2,-1),('L',0,-10),
                ('L',4,-1),('L',10,-7),('L',8,5),('L',-9,5)],Qt.NoBrush,'#52d9ff',1.8)
            p.restore()

    def _head(self,p,phase):
        p.save()
        listening = self.activity in ('listening','loading','recovering')
        thinking = self.activity in ('thinking','working','processing')
        speaking = self.activity == 'speaking'
        angle = -5.5 if listening else 3.5 if thinking else -2.3
        angle += math.sin(phase*(.9 if speaking else .48))*(1.6 if speaking else .8)
        p.translate(309,339)
        p.rotate(angle)
        p.translate(-309,-339)
        for x in (233,387):
            p.setPen(QPen(QColor('#5b3a32'),1))
            p.setBrush(_gradient(x-11,219,x+12,263,(0,'#e0a474'),(1,'#956044')))
            p.drawEllipse(QRectF(x-11,213,23,53))
            p.setPen(QPen(QColor('#a36c50'),3))
            p.drawArc(QRectF(x-6,222,12,31),-90*16,220*16)
        self._shape(p,[('M',241,171),('C',259,143,357,143,382,174),
            ('C',395,207,389,252,379,284),('C',367,318,344,339,311,343),
            ('C',278,340,252,316,244,284),('C',236,255,232,208,241,171),('Z',)],
            _gradient(236,215,390,272,(0,'#976144'),(.28,'#d79a6c'),(.6,'#e7ad7b'),(.83,'#ce8d62'),(1,'#a26748')),'#72503c',1)
        cheek = QRadialGradient(337,246,55)
        cheek.setColorAt(0,QColor(255,201,143,100))
        cheek.setColorAt(1,QColor(255,201,143,0))
        p.setPen(Qt.NoPen)
        p.setBrush(cheek)
        p.drawEllipse(QRectF(282,191,110,110))
        self._shape(p,[('M',240,236),('Q',250,245,256,265),
            ('Q',268,285,283,280),('Q',306,267,327,279),
            ('Q',348,287,363,269),('Q',377,249,386,236),
            ('C',388,279,376,317,349,335),('Q',315,363,278,338),
            ('C',249,319,239,285,240,236),('Z',)],
            _gradient(246,258,354,347,(0,'#241c1c'),(.5,'#211c1c'),(1,'#080e15')))
        for offset in range(6):
            self._shape(p,[('M',252+offset*4,293+offset*4),
                ('Q',277+offset*2,332+offset*2,310+offset*3,340-offset)],Qt.NoBrush,'#3c302b',.7)
        blink_age = phase%4.9
        eyes = 1.0 if blink_age<4.67 else max(.07,abs(blink_age-4.785)/.115)
        for index,(x,y) in enumerate(((271,220),(342,222))):
            p.save()
            p.translate(x,y)
            p.scale(1,eyes)
            self._shape(p,[('M',-17,0),('Q',-2,-10,16,-1),('Q',3,8,-17,0),('Z',)],'#ead8be','#6c4434',1)
            gaze=1.4*math.sin(phase*.33)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor('#62432b'))
            p.drawEllipse(QRectF(-5+gaze,-6,11,12))
            p.setBrush(QColor('#110f13'))
            p.drawEllipse(QRectF(-2+gaze,-5,6,10))
            p.setBrush(QColor('#fff2d9'))
            p.drawEllipse(QRectF(-1+gaze,-4,2.5,2.5))
            p.restore()
            self._shape(p,[('M',x-18,y-1),('Q',x,y-12*eyes,x+17,y)],Qt.NoBrush,'#392820',1.8)
            lift = -3.5 if thinking and index==1 else -1.5 if listening else 0
            self._shape(p,[('M',x-20,y-14+lift),('Q',x-3,y-28+lift,x+19,y-12+lift),
                ('Q',x+1,y-20+lift,x-18,y-10+lift),('Z',)],'#201b1a')
        self._shape(p,[('M',309,220),('Q',308,243,318,253),
            ('Q',326,264,312,268),('Q',300,270,294,261)],
            _gradient(293,239,322,264,(0,'#c58a5d'),(.55,'#efb783'),(1,'#9b6043')))
        self._shape(p,[('M',297,263),('Q',302,259,307,264),
            ('M',317,264),('Q',321,261,324,264)],Qt.NoBrush,'#8b513c',1.6)
        self._mouth_shape(p,speaking)
        self._shape(p,[('M',307,276),('C',290,268,280,268,268,280),
            ('Q',260,289,252,281),('Q',254,295,270,290),
            ('Q',291,281,306,285),('Q',326,281,343,290),
            ('Q',359,294,365,281),('Q',355,288,348,280),
            ('C',334,268,322,268,307,276),('Z',)],'#211c1b')
        self._turban(p)
        p.restore()

    def _mouth_shape(self,p,speaking):
        aperture,width,rounding = self._mouth if speaking and time.monotonic()<=self._mouth_until else MOUTH_SHAPES[0]
        w,h = 28*width,2.5+aperture*20
        p.setPen(QPen(QColor('#b77962'),2.3))
        p.setBrush(QColor('#24151a'))
        p.drawRoundedRect(QRectF(309-w/2,287,w,h),w*(.25+rounding*.2),h*.45)
        if aperture>.24:
            p.save()
            clip=QPainterPath()
            clip.addRoundedRect(QRectF(309-w/2,287,w,h),w*.35,h*.45)
            p.setClipPath(clip)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor('#dec7ac'))
            p.drawRoundedRect(QRectF(310-w/2,287,w-2,4.5),2,2)
            p.setBrush(QColor('#a25353'))
            p.drawEllipse(QRectF(301,287+h-5,17,8))
            p.restore()
        self._shape(p,[('M',294,312),('Q',309,317,325,311)],Qt.NoBrush,'#4b3431',1.4)

    def _turban(self,p):
        self._shape(p,[('M',221,212),('C',206,193,201,161,209,127),
            ('C',214,84,249,55,297,50),('C',342,42,388,58,406,92),
            ('C',428,129,410,181,389,210),('C',380,186,351,163,316,151),
            ('C',279,167,249,191,237,220),('Z',)],
            _gradient(219,80,382,191,(0,'#263447'),(.16,'#151f2e'),(.52,'#060c16'),(.8,'#111a29'),(1,'#1b2636')),'#344761',1.3)
        folds=[
            [('M',213,146),('C',232,103,283,79,365,64)],
            [('M',210,161),('C',243,109,302,86,388,79)],
            [('M',213,178),('C',249,127,315,94,399,99)],
            [('M',220,196),('C',251,148,318,111,407,119)],
            [('M',230,208),('C',251,170,302,139,359,116)],
            [('M',313,151),('C',345,130,365,112,381,86)],
            [('M',331,155),('C',365,131,390,122,404,124)],
            [('M',351,167),('C',369,147,388,139,406,140)],
            [('M',370,184),('Q',390,166,401,162)],
        ]
        for index,commands in enumerate(folds):
            self._shape(p,commands,Qt.NoBrush,'#030812',7 if index<5 else 5)
            self._shape(p,commands,Qt.NoBrush,'#304055' if index<3 else '#222e40',1.2)
        self._shape(p,[('M',211,148),('Q',208,98,249,73),('Q',278,51,319,51)],Qt.NoBrush,'#2a7db0',1.6)

    def _hands(self,p,phase):
        p.save()
        p.translate(158,560)
        p.rotate(-2+(math.sin(phase*1.8)*3.8 if self.activity=='speaking' else math.sin(phase*.6)*.9))
        p.translate(-158,-560)
        self._shape(p,[('M',119,568),('Q',136,535,163,517),('L',208,555),
            ('Q',192,601,166,617),('Q',137,603,119,568),('Z',)],
            _gradient(123,540,189,608,(0,'#354154'),(.4,'#111d2d'),(1,'#070e18')),'#38455b',1.5)
        self._shape(p,[('M',145,552),('Q',151,525,156,500),('L',143,466),
            ('C',137,449,143,435,152,443),('L',174,478),('L',172,419),
            ('C',171,402,184,399,188,415),('L',199,468),('L',205,402),
            ('C',207,386,220,390,221,405),('L',224,474),('L',239,423),
            ('C',243,409,256,415,252,431),('L',240,492),('L',258,466),
            ('C',269,451,279,460,270,474),('L',245,519),
            ('Q',226,546,208,566),('Q',179,582,145,552),('Z',)],
            _gradient(146,460,242,528,(0,'#b57c57'),(.35,'#edb58a'),(.65,'#d69a70'),(1,'#9d6248')),'#9a654e',1.3)
        for commands in [[('M',165,501),('Q',189,489,198,499)],
                         [('M',171,532),('Q',195,505,223,516)],
                         [('M',181,451),('L',193,480)],
                         [('M',215,443),('L',218,475)],
                         [('M',239,466),('L',232,490)]]:
            self._shape(p,commands,Qt.NoBrush,'#b37957',1.4)
        self._shape(p,[('M',140,553),('Q',171,579,203,572)],Qt.NoBrush,'#8c9eaf',8)
        self._shape(p,[('M',140,551),('Q',171,577,203,570)],Qt.NoBrush,'#d0d5d6',2)
        p.restore()
        self._shape(p,[('M',511,647),('Q',481,616,453,633),('L',386,676),
            ('Q',372,686,350,690),('Q',319,697,318,715),
            ('Q',340,726,370,713),('Q',387,712,415,702),
            ('L',484,682),('Q',508,675,511,647),('Z',)],
            _gradient(361,675,489,668,(0,'#b77751'),(.5,'#dfa578'),(1,'#bc8259')),'#9a674a',1.2)
        self._shape(p,[('M',334,709),('Q',347,697,369,695),
            ('M',347,716),('Q',358,704,379,702),('M',366,714),('Q',378,703,396,700)],Qt.NoBrush,'#9b6248',1)
        p.save()
        p.translate(447,663)
        p.rotate(-21)
        p.setPen(QPen(QColor('#263748'),2))
        p.setBrush(QColor('#111c2b'))
        p.drawRoundedRect(QRectF(-15,-30,30,60),5,5)
        p.setBrush(QColor('#080e17'))
        p.setPen(QPen(QColor('#527086'),2))
        p.drawRoundedRect(QRectF(-18,-19,36,38),10,10)
        p.setPen(QColor('#3ecbff'))
        p.setFont(QFont('Segoe UI',8))
        p.drawText(QRectF(-17,-15,34,30),Qt.AlignCenter,'AI')
        p.restore()
